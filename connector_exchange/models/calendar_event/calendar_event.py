# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models, fields, api
from odoo import tools
from odoo.addons.calendar.models.calendar import calendar_id2real_id
_logger = logging.getLogger(__name__)


class CalendarAttendee(models.Model):
    """
    Calendar Attendee Information
    """
    _inherit = 'calendar.attendee'

    @api.multi
    def _send_mail_to_attendees(
        self,
        email_from=tools.config.get('email_from', False),
        template_xmlid='calendar_template_meeting_invitation',
        force=False
    ):
        return False


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    exchange_bind_ids = fields.One2many(
        comodel_name='exchange.calendar.event',
        inverse_name='openerp_id',
        string="Exchange Bindings",
    )

    @api.multi
    def try_autobind(self, user, backend):
        """
            Try to find a binding with provided backend and user.
            If not found, create a new one.
        """
        real_calendars = (
            list(set([calendar_id2real_id(calendar_id=cal.id) for cal in self])
                 )
            )
        if self.env.context.get('job_uuid', False):
            return True
        else:
            for calendar in self.browse(real_calendars):
                bindings = calendar.exchange_bind_ids.filtered(
                    lambda a: a.backend_id == backend and a.user_id == user and
                    a['privacy'] != 'private')
                if not bindings:
                    self.env['exchange.calendar.event'].sudo().create(
                        {'backend_id': backend.id,
                         'user_id': user.id,
                         'openerp_id': calendar.id}
                    )
        return True

    @api.model
    def create(self, values):
        user = values.get('user_id')
        if not user:
            user = self.env.user.id
        no_mail = False
        if self.env['res.users'].browse(user).send_calendar_invitations:
            no_mail = True
        new_event = super(CalendarEvent, self.with_context(
            no_mail_to_attendees=no_mail)).create(values)
        if not self.env.context.get('job_uuid'):
            new_event.try_autobind(new_event.user_id,
                                   new_event.user_id.default_backend)
        return new_event

    @api.multi
    def write(self, values):
        """Overload write method to trigger connector events"""
        # FIXME: manage alteration of recurrent events
        for rec in self:
            user = values.get('user_id')
            if not user:
                user = rec.user_id.id
            no_mail = False
            if self.env['res.users'].browse(user).send_calendar_invitations:
                no_mail = True
            super(CalendarEvent, rec.sudo().with_context(
                no_mail_to_attendees=no_mail)).write(values)
            if isinstance(rec.id, basestring):
                if '-' in rec.id:
                    # we have a virtual recurrent event linked
                    # to a real on stored in database
                    if not values.get('active', True):
                        # an event has been deactivated
                        # 1. find real id behind the one we are on
                        real_id = calendar_id2real_id(calendar_id=rec.id)

                        # 2. create a delete event on the real id
                        # previously found
                        self.browse(real_id).with_context(
                            connector_no_export=True,
                            no_mail_to_attendees=no_mail).unlink()

            else:
                # we are dealing with a real event
                # (single or detached from a recurrency)
                if rec.recurrent_id:
                    # we have to update or delete an occurrence
                    # of the original event
                    pass
                else:
                    # single event
                    # nothing to do. Already managed by connector
                    pass
        return True

    @api.multi
    def already_exists(self, values):
        res = False
        for attendee in self.attendee_ids:
            if attendee.email == values.get('email'):
                res = attendee
                break
        return res

    @api.multi
    def create_attendees(self):

        current_user = self.env.user
        result = {}
        for meeting in self:
            already_meeting_partners = meeting.attendee_ids.mapped(
                'partner_id')
            meeting_attendees = self.env['calendar.attendee']
            meeting_partners = self.env['res.partner']
            for partner in meeting.partner_ids.filtered(
                    lambda partner: partner not in already_meeting_partners):
                values = {
                    'partner_id': partner.id,
                    'email': partner.email,
                    'event_id': meeting.id,
                }

                # current user don't have to accept his own meeting
                if partner == self.env.user.partner_id:
                    values['state'] = 'accepted'

                existing_att = meeting.already_exists(values)
                if existing_att:
                    existing_att.write(values)
                    attendee = existing_att
                else:
                    attendee = self.env['calendar.attendee'].create(values)

                meeting_attendees |= attendee
                meeting_partners |= partner

            if meeting_attendees:
                to_notify = meeting_attendees.filtered(
                    lambda a: a.email != current_user.email)
                to_notify._send_mail_to_attendees(
                    'calendar.calendar_template_meeting_invitation')

                meeting.write({'attendee_ids': [(4, meeting_attendee.id) for
                                                meeting_attendee in
                                                meeting_attendees]})
            if meeting_partners:
                meeting.message_subscribe(partner_ids=meeting_partners.ids)

            # We remove old attendees who are not in partner_ids now.
            all_partners = meeting.partner_ids
            all_partner_attendees = meeting.attendee_ids.mapped('partner_id')
            old_attendees = meeting.attendee_ids
            partners_to_remove = (
                all_partner_attendees + meeting_partners - all_partners)

            attendees_to_remove = self.env["calendar.attendee"]
            if partners_to_remove:
                attendees_to_remove = self.env["calendar.attendee"].search(
                    [('partner_id', 'in', partners_to_remove.ids),
                     ('event_id', '=', meeting.id)])
                attendees_to_remove.unlink()

            result[meeting.id] = {
                'new_attendees': meeting_attendees,
                'old_attendees': old_attendees,
                'removed_attendees': attendees_to_remove,
                'removed_partners': partners_to_remove
            }
        return result


class ExchangeCalendarEvent(models.Model):
    _name = 'exchange.calendar.event'
    _inherit = 'exchange.binding'
    _inherits = {'calendar.event': 'openerp_id'}
    _description = 'Exchange Calendar Event'

    openerp_id = fields.Many2one(comodel_name='calendar.event',
                                 string='Calendar Event',
                                 required=True,
                                 ondelete='cascade')
    created_at = fields.Datetime(string='Created At (on Exchange)',
                                 readonly=True)
    updated_at = fields.Datetime(string='Updated At (on Exchange)',
                                 readonly=True)
    calendar_folder = fields.Char(compute='_get_folder_calendar_id',
                                  readonly=True)

    @api.depends()
    def _get_folder_calendar_id(self):
        for binding in self:
            binding.calendar_folder = self.env.user.find_folder(
                binding.backend_id.id,
                create=False,
                folder_type='calendar',
                user=binding.user_id,
            ).folder_id

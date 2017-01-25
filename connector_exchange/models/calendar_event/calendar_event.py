# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models, fields, api, _
from odoo import tools
from odoo.addons.calendar.calendar import calendar_id2real_id
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
                    a['class'] != 'private')
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
        # session = ConnectorSession.from_env(self.env)
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
                        # delay_disable_all_bindings(session, self._name,
                        # real_id)

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

    @api.v7
    def already_exists(self, cr, uid, id, values, context=None):
        res = False
        for attendee in self.browse(cr, uid, id, context=context).attendee_ids:
            if attendee.email == values.get('email'):
                res = attendee.id
                break
        return res

    @api.v7
    def create_attendees(self, cr, uid, ids, context=None):
        # fully rewritten and old API ... FIXME
        if context is None:
            context = {}
        user_obj = self.pool['res.users']
        current_user = user_obj.browse(cr, uid, uid, context=context)
        res = {}
        attendee_obj = self.pool['calendar.attendee']
        for event in self.browse(cr, uid, ids, context):
            attendees = {}
            for att in event.attendee_ids:
                attendees[att.partner_id.id] = True
            new_attendees = []
            new_att_partner_ids = []
            for partner in event.partner_ids:
                if partner.id in attendees:
                    continue
                access_token = self.new_invitation_token(cr, uid, event,
                                                         partner.id)
                values = {
                    'partner_id': partner.id,
                    'event_id': event.id,
                    'access_token': access_token,
                    'email': partner.email,
                }

                if partner.id == current_user.partner_id.id:
                    values['state'] = 'accepted'

                existing_att = self.already_exists(cr, uid, event.id, values)
                if existing_att:
                    self.pool['calendar.attendee'].write(cr, uid,
                                                         [existing_att],
                                                         values,
                                                         context=context)
                    att_id = existing_att
                else:
                    att_id = self.pool['calendar.attendee'].create(
                        cr, uid,
                        values,
                        context=context)
                    new_attendees.append(att_id)
                    new_att_partner_ids.append(partner.id)

                if (not current_user.email or
                        current_user.email != partner.email):
                    mail_from = (
                        current_user.email or
                        tools.config.get('email_from', False)
                    )
                    if not context.get('no_email'):
                        if attendee_obj._send_mail_to_attendees(
                                cr, uid,
                                att_id,
                                email_from=mail_from,
                                context=context):
                            self.message_post(
                                cr, uid, event.id,
                                body=_("An invitation email has been sent to "
                                       "attendee %s") % (partner.name,),
                                subtype="calendar.subtype_invitation",
                                context=context)

            if new_attendees:
                self.write(
                    cr, uid, [event.id],
                    {'attendee_ids': [(4, att) for att in new_attendees]},
                    context=context)
            if new_att_partner_ids:
                self.message_subscribe(cr, uid, [event.id],
                                       new_att_partner_ids, context=context)

            # We remove old attendees who are not in partner_ids now.
            all_partner_ids = [part.id for part in event.partner_ids]
            all_part_attendee_ids = (
                [att.partner_id.id for att in event.attendee_ids]
            )
            all_attendee_ids = [att.id for att in event.attendee_ids]
            partner_ids_to_remove = map(
                lambda x: x,
                set(all_part_attendee_ids +
                    new_att_partner_ids) - set(all_partner_ids)
            )

            attendee_ids_to_remove = []

            if partner_ids_to_remove:
                attendee_ids_to_remove = attendee_obj.search(
                    cr, uid,
                    [('partner_id.id', 'in', partner_ids_to_remove),
                     ('event_id.id', '=', event.id)],
                    context=context
                )
                if attendee_ids_to_remove:
                    self.pool['calendar.attendee'].unlink(
                        cr, uid, attendee_ids_to_remove, context
                    )

            res[event.id] = {
                'new_attendee_ids': new_attendees,
                'old_attendee_ids': all_attendee_ids,
                'removed_attendee_ids': attendee_ids_to_remove
            }
        return res


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

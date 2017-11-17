# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import logging


import pytz
import datetime
from dateutil import parser
from ...backend import exchange_2010
from odoo import fields
from ...unit.importer import (ExchangeImporter,
                              RETRY_ON_ADVISORY_LOCK,
                              )


_logger = logging.getLogger(__name__)
try:
    from pyews.ews.data import (SensitivityType,
                                LegacyFreeBusyStatusType,
                                DayOfWeekIndexType,
                                ResponseTypeType,
                                )
except (ImportError, IOError) as err:
    _logger.debug(err)


EXCHANGE_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
EXCHANGE_REC_DATE_FORMAT = '%Y-%m-%d'

SIMPLE_VALUE_FIELDS = {'subject': 'name',
                       'location': 'location',
                       'body': 'description',
                       }

FREE_LIST = [LegacyFreeBusyStatusType.Free,
             LegacyFreeBusyStatusType.NoData,
             ]


def transform_to_odoo_date(exchange_date, user_tz, time=False, end=False):
    parsed = parser.parse(exchange_date)
    if not time:
        parsed_user_tz = parsed.astimezone(pytz.timezone(user_tz))
    else:
        parsed_user_tz = parsed.astimezone(pytz.UTC)

    if end:
        parsed_user_tz -= datetime.timedelta(minutes=1)
    naive_dt = parsed_user_tz.replace(tzinfo=None)
    if time:
        return fields.Datetime.to_string(naive_dt)
    else:
        return fields.Date.to_string(naive_dt)


@exchange_2010
class CalendarEventImporter(ExchangeImporter):
    _model_name = ['exchange.calendar.event']

    def fill_start_end(self, event_instance):
        vals = {}
        user_tz = self.openerp_user.tz
        if event_instance.is_all_day_event.value:
            # fill start_date and stop_date
            vals['allday'] = True
            vals['start'] = transform_to_odoo_date(
                event_instance.start.value, user_tz, time=False)
            vals['stop'] = transform_to_odoo_date(
                event_instance.end.value, user_tz, time=False, end=True)
        else:
            # fill start_datetime and stop_datetime
            vals['allday'] = False
            vals['start'] = transform_to_odoo_date(
                event_instance.start.value, user_tz, time=True)
            vals['stop'] = transform_to_odoo_date(
                event_instance.end.value, user_tz, time=True)
        return vals

    def fill_privacy(self, event_instance):
        vals = {}
        if event_instance.sensitivity.value == SensitivityType.Normal:
            vals['privacy'] = 'public'
        elif event_instance.sensitivity.value == SensitivityType.Confidential:
            vals['privacy'] = 'confidential'
        else:
            vals['privacy'] = 'private'

        return vals

    def fill_free_busy_status(self, event_instance):
        vals = {}

        if event_instance.legacy_free_busy_status.value in FREE_LIST:
            vals['show_as'] = 'free'
        else:
            vals['show_as'] = 'busy'

        return vals

    def fill_reminder(self, event_instance):
        vals = {}
        if event_instance.is_reminder_set.value:
            # fill reminder
            remind_time = event_instance.reminder_minutes_before_start.value
            alarms_obj = self.env['calendar.alarm']
            alarms = alarms_obj.search(
                [('duration_minutes', '=', remind_time)]
            )
            if alarms:
                # only take the first alarm found
                vals['alarm_ids'] = [alarms[0]]

        return vals

    def fill_attendees(self, event_instance):
        vals = {}
        vals['attendee_ids'] = []
        vals['partner_ids'] = []
        evt = self.env['exchange.calendar.event']
        contact = self.env['exchange.res.partner']

        STATES_MAPPING = {
            ResponseTypeType.Tentative: 'tentative',
            ResponseTypeType.Decline: 'declined',
            ResponseTypeType.Accept: 'accepted',
        }
        if self.exchange_events:
            evt = self.exchange_events[0]
        odoo_attendee_emails = evt.mapped('attendee_ids.email')
        for attendee in event_instance.required_attendees.entries:
            # attendee is a Attendee object from PyEWS
            exchange_email = attendee.mailbox.email_address.value
            if exchange_email in odoo_attendee_emails:
                if attendee.response_type.value in (ResponseTypeType.Tentative,
                                                    ResponseTypeType.Accept,
                                                    ResponseTypeType.Decline):
                    for attend in evt.attendee_ids:
                        if attend.email == exchange_email:
                            attend.state = (
                                STATES_MAPPING[attendee.response_type.value])
                        # auto accept event owner
                        if attend.partner_id == self.openerp_user.partner_id:
                            attend.state = 'accepted'
                continue
            else:
                # create attendee
                state = 'needsAction'
                if attendee.response_type.value in STATES_MAPPING:
                    state = STATES_MAPPING[attendee.response_type.value]
                att_dict = {'cn': attendee.mailbox.name.value,
                            'email': attendee.mailbox.email_address.value,
                            'state': state}
                vals['attendee_ids'].append((0, 0, att_dict))
            # try map attendee to a partner in odoo
            partner_added = False
            if attendee.mailbox.itemid.value is not None:
                # we have an itemid corresponding to a contact which should
                # have already been synchronized
                ext_id = attendee.mailbox.itemid.value
                contact = contact.search([('external_id', '=', ext_id)],
                                         order='create_date asc',
                                         limit=1)
                if contact and len(contact) == 1:
                    partner_added = True
                    vals['partner_ids'].append((4, contact.openerp_id.id))
            elif not partner_added:
                # search by name and email
                contact = contact.search(
                    [('name', '=', attendee.mailbox.name.value),
                     ('email', '=', attendee.mailbox.email_address.value),
                     ('is_company', '=', False)],
                    order='create_date asc',
                    limit=1
                )
                if contact:
                    partner_added = True
                    vals['partner_ids'].append((4, contact.openerp_id.id))
                else:
                    # create a contact with parent=Generic
                    new_partner = contact.create(
                        {'name': attendee.mailbox.name.value,
                         'email': attendee.mailbox.email_address.value,
                         'user_id': self.openerp_user.id,
                         'backend_id': self.backend_record.id,
                         'parent_id': self.env.ref(
                             'connector_exchange.res_partner_GENERIC').id,
                         }
                    )
                    vals['partner_ids'].append((4, new_partner.openerp_id.id))

        # add owner of the event as attendee
        added_partner_ids = [x[1] for x in vals['partner_ids']]
        if self.openerp_user.partner_id.id not in added_partner_ids:
            vals['partner_ids'].append((4, self.openerp_user.partner_id.id))
            vals['attendee_ids'].append(
                (0, 0,
                 {'cn': self.openerp_user.partner_id.name,
                  'email': self.openerp_user.partner_id.email,
                  'state': 'accepted'}
                 )
            )

        return vals

    def fill_recurrency(self, event_instance):
        """

        """
        vals = {}
        if event_instance.recurrence.get_children():
            user_tz = self.openerp_user.tz
            vals['recurrency'] = True
            # get recurrence end type
            rec_end_type = event_instance.recurrence._check_end_type()
            rec_end = getattr(event_instance.recurrence, rec_end_type)
            if rec_end.tag == 'NoEndRecurrence':
                # not implemented
                pass
            elif rec_end.tag == 'EndDateRecurrence':
                vals['end_type'] = 'end_date'
                vals['final_date'] = transform_to_odoo_date(
                    rec_end.end_date.value, user_tz, time=False)

            elif rec_end.tag == 'NumberedRecurrence':
                vals['end_type'] = 'count'
                vals['count'] = int(rec_end.nb_occurrences.value)

            # get recurrence type
            rec_rec_type = event_instance.recurrence._check_recurrence_type()
            rec_type = getattr(event_instance.recurrence, rec_rec_type)
            if rec_type.tag == 'DailyRecurrence':
                vals['rrule_type'] = 'daily'
                vals['interval'] = rec_type.interval.value

            elif rec_type.tag == 'WeeklyRecurrence':
                vals['rrule_type'] = 'weekly'
                vals['interval'] = rec_type.interval.value
                exchange_days = rec_type.days_of_week.value.split()
                odoo_days = [x[:2].lower() for x in exchange_days]
                for elem in odoo_days:
                    vals[elem] = True

            elif rec_type.tag == 'AbsoluteMonthlyRecurrence':
                vals['rrule_type'] = 'monthly'
                vals['interval'] = rec_type.interval.value
                vals['month_by'] = 'date'
                vals['day'] = rec_type.day_of_month.value

            elif rec_type.tag == 'RelativeMonthlyRecurrence':
                vals['rrule_type'] = 'monthly'
                vals['interval'] = rec_type.interval.value
                vals['month_by'] = 'day'
                vals['week_list'] = rec_type.days_of_week.value[:2].upper()
                exchange_index = {
                    DayOfWeekIndexType.First: '1',
                    DayOfWeekIndexType.Second: '2',
                    DayOfWeekIndexType.Third: '3',
                    DayOfWeekIndexType.Fourth: '4',
                    DayOfWeekIndexType.Last: '-1',
                }
                vals['byday'] = (
                    exchange_index[rec_type.day_of_week_index.value]
                )

            elif rec_type.tag == 'AbsoluteYearlyRecurrence':
                vals['rrule_type'] = 'yearly'
                vals['interval'] = rec_type.interval.value

            else:
                # not implemented
                pass

        return vals

    def map_exchange_instance(self, event_instance):
        vals = {}

        for ex_field, odoo_mapping in SIMPLE_VALUE_FIELDS.iteritems():
            if isinstance(odoo_mapping, basestring):
                vals[odoo_mapping] = getattr(event_instance, ex_field).value

        vals.update(self.fill_start_end(event_instance))
        vals.update(self.fill_privacy(event_instance))
        vals.update(self.fill_free_busy_status(event_instance))
        vals.update(self.fill_reminder(event_instance))
        vals.update(self.fill_attendees(event_instance))
        vals.update(self.fill_recurrency(event_instance))

        vals.update(change_key=event_instance.change_key.value,
                    external_id=event_instance.itemid.value)

        return vals

    def _map_data(self):
        """
            from exchange record, create an odoo dict than can be user
            both in write and create methods
        """
        event_id = self.external_id
        adapter = self.backend_adapter
        ews = adapter.ews

        # contact is an pyews.ews.contact.Contact instance
        event = ews.GetCalendarItems([event_id])[0]

        vals = self.map_exchange_instance(event)

        return vals

    def bind_attachments(self, binding, event_id):
        """
        A document attached to an Exchange event will be imported as this in
        the message_ids of the created/updated record

        For the moment, just add it as attachment of the record directly
        instead of in message_ids
        """
        adapter = self.backend_adapter
        ews = adapter.ews
        user = self.openerp_user
        att_obj = self.env['ir.attachment'].sudo(user.id)

        if isinstance(binding, int):
            binding = self.env['exchange.calendar.event'].browse(binding)

        search_args = [
            ('res_model', '=', 'calendar.event'),
            ('res_id', '=', binding.openerp_id.id),
            ('type', '=', 'binary'),
        ]
        odoo_attachments = att_obj.search(search_args)
        attach_by_name = {}
        for att in odoo_attachments:
            if att.name not in attach_by_name:
                attach_by_name[att.name] = att
            else:
                attach_by_name[att.name] |= att
        adapter.set_primary_smtp_address(user)

        new_read = ews.GetCalendarItems([event_id])[0]
        for attachment in new_read.attachments.entries:
            fname = attachment.name.value
            content = attachment.content.value

            odoo_att = attach_by_name.get(fname)
            # for att in odoo_att:
            #     if att.name == fname:
            #         odoo_att += att
            if odoo_att:
                # we already have this attachment
                # just check if it's the same content
                if content != odoo_att.datas:
                    odoo_att.write(
                        {
                            'datas': content,
                        }
                    )
            else:
                # create a new one for the binding
                # file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', fname)
                # att = att_obj.create(
                #     {
                #         'name': fname,
                #         'datas': content,
                #         'datas_fname': fname,
                #         'res_model': 'calendar.event',
                #         'res_id': binding.openerp_id.id,
                #         'type': 'binary'
                #     }
                # )
                binding.openerp_id.sudo(user.id).message_post(
                    attachments=[(fname, base64.b64decode(str(content)))])

        return True

    def _find_detached_or_detach_one(self, odoo_rec, occ_read):
        cal_env_obj = self.env['calendar.event']
        # In an accurrence, there is only 4 informations:
        #       - start
        #       - end
        #       - original_start
        #       - itemid
        #
        # We need to read the itemid to have a complete information
        # of this occurrence

        if odoo_rec.allday:
            occ_read_start = transform_to_odoo_date(
                occ_read.original_start.value,
                self.openerp_user.tz,
                time=False)
        else:
            occ_read_start = transform_to_odoo_date(
                occ_read.original_start.value,
                self.openerp_user.tz,
                time=True)
        # find odoo recurrent event based on master_id + original_start
        # detach event from recurrence in Odoo
        rec_events_ids = cal_env_obj.with_context(
            virtual_id=True).get_recurrent_ids([odoo_rec.id], [])
        # find the good event according to its ID
        start_date_id = (
            occ_read_start.replace(' ',
                                   '').replace('-',
                                               '').replace(':', '')
        )
        index, iid = None, None
        try:
            index = rec_events_ids.index(
                '%s-%s' % (odoo_rec.id, start_date_id)
            )
        except ValueError:
            all_recurring_ids = cal_env_obj.search(
                [('recurrent_id', '=', odoo_rec.id),
                 ('start', '=', occ_read_start)])

            iid = all_recurring_ids[0].id

        if index is not None:
            event_to_edit_id = rec_events_ids[index]
            if cal_env_obj.browse(event_to_edit_id).recurrency:
                detached_event_id = (
                    cal_env_obj.browse(
                        event_to_edit_id)._detach_one_event()
                )
                if isinstance(detached_event_id, (list, tuple)):
                    detached_event_id = detached_event_id[0]

                return detached_event_id
        else:
            return iid

    def _find_detached_or_detach_one_deleted(self, odoo_rec, delete_start):
        cal_env_obj = self.env['calendar.event']
        # In an accurrence, there is only 4 informations:
        #       - start
        #       - end
        #       - original_start
        #       - itemid
        #
        # We need to read the itemid to have a complete information
        # of this occurrence
        if odoo_rec.allday:
            occ_read_start = transform_to_odoo_date(
                delete_start,
                self.openerp_user.tz,
                time=False)
        else:
            occ_read_start = transform_to_odoo_date(
                delete_start,
                self.openerp_user.tz,
                time=True)

        # find odoo recurrent event based on master_id + original_start
        # detach event from recurrence in Odoo
        rec_events_ids = cal_env_obj.with_context(
            virtual_id=True).get_recurrent_ids([odoo_rec.id], [])
        # find the good event according to its ID
        start_date_id = (
            occ_read_start.replace(' ',
                                   '').replace('-',
                                               '').replace(':', '')
        )
        index, iid = None, None
        try:
            index = rec_events_ids.index(
                '%s-%s' % (odoo_rec.id, start_date_id)
            )
        except ValueError:
            all_recurring_ids = (
                cal_env_obj.with_context(active_test=False).search(
                    [('recurrent_id', '=', odoo_rec.id),
                     ('start', '=', occ_read_start)])
                )
            iid = all_recurring_ids[0].id

        if index is not None:
            event_to_edit_id = rec_events_ids[index]
            if cal_env_obj.browse(event_to_edit_id).recurrency:
                detached_event_id = (
                    cal_env_obj.browse(
                        event_to_edit_id)._detach_one_event()
                )
                if isinstance(detached_event_id, (list, tuple)):
                    detached_event_id = detached_event_id[0]

                return detached_event_id
        else:
            return iid

    def manage_modified_deleted_occurrences(self, binding, event_id):
        adapter = self.backend_adapter
        ews = adapter.ews
        cal_env_obj = self.env['calendar.event']
        if isinstance(binding, int):
            binding = self.env['exchange.calendar.event'].browse(binding)

        odoo_record = binding.openerp_id

        event_instance = ews.GetCalendarItems([event_id])[0]

        # manage modified_occurrences
        if event_instance.modified_occurrences.entries:
            for occ in event_instance.modified_occurrences.entries:
                # In an accurrence, there is only 4 informations:
                #       - start
                #       - end
                #       - original_start
                #       - itemid
                #
                # We need to read the itemid to have a complete information
                # of this occurrence
                occ_read = ews.GetCalendarItems([occ.itemid.value])[0]
                detached_event_id = self._find_detached_or_detach_one(
                    odoo_record, occ_read
                )

                # edit Odoo event
                vals = self.map_exchange_instance(occ_read)
                cal_env_obj.browse(detached_event_id).with_context(
                    connector_no_export=True).write(vals)

        # manage deleted_occurrences
        if event_instance.deleted_occurrences.entries:
            for occ in event_instance.deleted_occurrences.entries:
                # detach event from recurrence in Odoo
                delete_start = occ.start.value
                detached_event_id = self._find_detached_or_detach_one_deleted(
                    odoo_record, delete_start
                )

                # set active = False for the previously detached event
                cal_env_obj.browse(detached_event_id).with_context(
                    connector_no_export=True).write({'active': False})

        return True

    def _run(self, item_id, user_id):
        """ Beginning of the synchronization

        The first thing we do is to try to acquire an advisory lock
        on Postgresql. If it can't be acquired it means that another job
        does the same import at the same moment.
        The goal is to prevent 2 jobs to create the same binding because
        they each job is not aware of the other binding.
        It happens easily when 2 jobs import the same dependencies (such
        as partner categories for an import of partners).

        :param item_id: item_id
        """
        self.openerp_user = user_id
        self.external_id = item_id
        lock_name = 'import({}, {}, {}, {})'.format(
            self.backend_record._name,
            self.backend_record.id,
            self.model._name,
            self.external_id,
        )
        # Keep a lock on this import until the transaction is committed
        self.advisory_lock_or_retry(lock_name,
                                    retry_seconds=RETRY_ON_ADVISORY_LOCK)

        skip = self._must_skip()
        if skip:
            return skip

        self._before_import()

        # import the missing linked resources
        # self._import_dependencies()

        # try to find a exchange.calendar.event with the same
        # Id/user_id/backend_id
        # if found, update it
        # otherwise, create it
        event_id = self.external_id

        backend = self.backend_record

        args = [('backend_id', '=', backend.id),
                ('user_id', '=', self.openerp_user.id),
                ('external_id', '=', event_id)]
        exchange_events = self.env['exchange.calendar.event'].search(args)
        self.exchange_events = exchange_events
        data = self._map_data()
        data.update(user_id=self.openerp_user.id,
                    backend_id=self.backend_record.id)

        if not exchange_events:
            _logger.debug('does not exist --> CREATE')
            binding = self._create(data)
            binding.openerp_id.user_id = self.openerp_user.id
        else:
            _logger.debug('exists --> UPDATE')
            binding = exchange_events[0]
            self._update(binding, data)

        self.bind_attachments(binding, event_id)

        self.manage_modified_deleted_occurrences(binding, event_id)

    def _update(self, binding, data, context_keys=None):
        """ Update an Odoo record """
        context_keys = self._update_context_keys(keys=context_keys)
        context_keys.update(no_mail_to_attendees=True)
        return super(CalendarEventImporter, self)._update(
            binding, data, context_keys=context_keys
        )

    def _create(self, data, context_keys=None):
        context_keys = self._create_context_keys(keys=context_keys)
        context_keys.update(no_mail_to_attendees=True)
        return super(CalendarEventImporter, self)._create(
            data, context_keys=context_keys
        )

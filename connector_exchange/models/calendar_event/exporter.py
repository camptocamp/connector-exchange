# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import datetime
from odoo import _, fields
from odoo.tools import (DEFAULT_SERVER_DATE_FORMAT,
                        DEFAULT_SERVER_DATETIME_FORMAT)
from ...unit.exporter import (ExchangeExporter,
                              ExchangeDisabler)
from ...backend import exchange_2010


_logger = logging.getLogger(__name__)
_logger = logging.getLogger(__name__)

from exchangelib import EWSDate, EWSDateTime, EWSTimeZone, Mailbox, Attendee, \
    CalendarItem, fields
from exchangelib.items import SEND_ONLY_TO_ALL, SEND_ONLY_TO_CHANGED
import pytz

EXCHANGE_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'
EXCHANGE_REC_DATE_FORMAT = '%Y-%m-%d'

# UTILITY FUNTIONS


def get_exchange_month_from_date(month):
    maps = {
        1: fields.January,
        2: fields.February,
        3: fields.March,
        4: fields.April,
        5: fields.May,
        6: fields.June,
        7: fields.July,
        8: fields.August,
        9: fields.September,
        10: fields.October,
        11: fields.November,
        12: fields.December,
    }
    return maps[month]


def convert_to_exchange(date, time=False, rec=False, add_day=False):

    fmt = DEFAULT_SERVER_DATE_FORMAT
    if time:
        fmt = DEFAULT_SERVER_DATETIME_FORMAT
    odoo_dt = datetime.datetime.strptime(date, fmt)
    if rec:
        return odoo_dt.strftime(EXCHANGE_REC_DATE_FORMAT)
    if add_day:
        odoo_dt = odoo_dt + datetime.timedelta(days=1)
    return odoo_dt.strftime(EXCHANGE_DATETIME_FORMAT)


# MAPPINGS DECLARATION
SIMPLE_VALUE_FIELDS = {'name': 'subject',
                       'location': 'location',
                       'description': 'body',
                       }


@exchange_2010
class CalendarEventExporter(ExchangeExporter):
    _model_name = ['exchange.calendar.event']

    def fill_privacy(self, event):
        """
        Here is the mapping between Odoo and Exchange:
        | Odoo         | Exchange     |
        | public       | Normal       |
        | private      | Personal     |
        | private      | Private      |
        | confidential | Confidential |
        """
        if self.binding['privacy'] == 'public':
            event.sensitivity = 'Normal'
        elif self.binding['privacy'] == 'confidential':
            event.sensitivity = 'Confidential'
        else:
            event.sensitivity = 'Private'

    def fill_free_busy_status(self, event):
        """
        Here is the mapping between Odoo and Exchange:
        | Odoo | Exchange     |
        | free | Free         |
        | free | NoData       |
        | busy | Busy         |
        | busy | OOF          |
        | busy | Tentative    |
        """
        if self.binding.show_as == 'free':
            event.legacy_free_busy_status = 'Free'
        else:
            event.legacy_free_busy_status = 'Busy'

    def fill_reminder(self, event):
        """
        In Exchange, only one reminder can be set.
        So Odoo side, only the first reminder will be exported to Exchange.
        """
        alarms = self.binding.alarm_ids
        if alarms:
            alarm = alarms[0]
            event.is_reminder_set = True
            event.reminder_due_by = convert_to_exchange(
                self.parse_date(self.binding.start), time=True)
            event.reminder_minutes_before_start = alarm.duration_minutes
        else:
            event.is_reminder_set = False

    def parse_date(self, dt, all_day=False, end=False):
        tz = EWSTimeZone.timezone('UTC')
        if all_day:
            dt = datetime.datetime.strptime(
                dt, DEFAULT_SERVER_DATE_FORMAT)
        else:
            dt = datetime.datetime.strptime(
                dt, DEFAULT_SERVER_DATETIME_FORMAT)
        if all_day and end:
            odt = tz.localize(EWSDateTime(dt.year, dt.month, dt.day, 23,
                          59))
        else:
            odt = tz.localize(EWSDateTime(dt.year, dt.month, dt.day, dt.hour,
                              dt.minute))
        return odt

    def fill_start_end(self, event):
        event.is_all_day = self.binding.allday
        if self.binding.allday:
            start = self.parse_date(self.binding.start_date,
                                    all_day=self.binding.allday)
            stop = self.parse_date(self.binding.stop_date,
                                   all_day=self.binding.allday, end=True)
        else:
            start = self.parse_date(self.binding.start,
                                    all_day=self.binding.allday)
            stop = self.parse_date(self.binding.stop,
                                   all_day=self.binding.allday)
        event.start = start
        event.end = stop

    def _attendee_already_exists(self, attendee_email, event):
        """
        try to find an attendee in the calendar with same email address
        """
        result = False
        if event.required_attendees:
            att = event.required_attendees
            att_mail = att.mailbox.email_address
            if (att_mail == attendee_email or
                    att_mail == self.openerp_user.email):
                return True

        return result

    def fill_attendees(self, event):
        """
        For each attendee in Odoo:
            if there is not already an attendee with the same email address:
                - create an Exchange attendee
                - add it in required_attendees of the meeting.
        """
        STATES_MAPPING = {
            'tentative': 'Tentative',
            'declined': 'Decline',
            'accepted': 'Accept',
        }
        for attendee in self.binding.attendee_ids:
            if attendee.email == self.openerp_user.email:
                continue
            # cn, email
            if event.required_attendees:
                att = event.required_attendees
                if att.mailbox.email_address == attendee.email:
                    att.response_type = \
                        STATES_MAPPING.get(attendee.state, 'Unknown')
            if (not self._attendee_already_exists(
                    attendee.email, event)):
                att = Attendee(
                    mailbox=Mailbox(email_address=attendee.email,
                                    name=attendee.common_name,
                                    ),
                    response_type='Accept',
                )

                event.required_attendees = att

    def fill_recurrency(self, event):
        """
        If Odoo event is recurrent, fill recurrency options
        in `event` Exchange object.

        Odoo only supports numbered_recurrence and end_date recurrence.
        """
        evt = self.binding
        if evt.recurrency:

            if evt.end_type == "count":
                event.recurrence.numbered_rec.nb_occurrences.set(evt.count)
                if self.binding.allday:
                    event.recurrence.numbered_rec.start_date.set(
                        convert_to_exchange(self.binding.start_date,
                                            time=False, rec=True)
                    )
                else:
                    event.recurrence.numbered_rec.start_date.set(
                        convert_to_exchange(self.binding.start_datetime,
                                            time=True, rec=True)
                    )
            else:
                # end_date recurrency
                event.recurrence.end_date_rec.start_date(
                    convert_to_exchange(self.binding.start_date,
                                        time=False, rec=True))
                event.recurrence.end_date_rec.end_date(
                    convert_to_exchange(self.binding.final_date,
                                        time=False, rec=True))

            ExchangeDays = {
                'mo': fields.Monday,
                'tu': fields.Tuesday,
                'we': fields.Wednesday,
                'th': fields.Thursday,
                'fr': fields.Friday,
                'sa': fields.Saturday,
                'su': fields.Sunday,
            }

            interval_rec = evt.interval
            if evt.rrule_type == 'daily':
                event.recurrence.day_rec.interval.set(interval_rec)

            elif evt.rrule_type == 'weekly':
                weekly = event.recurrence.week_rec
                days = []
                for day in ExchangeDays:
                    if getattr(evt, day):
                        days.append(day)
                days = days.map(lambda x: ExchangeDays['x'])
                days = ' '.join(days)
                weekly.days_of_week.set(days)
                weekly.interval.set(interval_rec)
                weekly.first_day_of_week.set(fields.Monday)

            elif evt.rrule_type == 'monthly':
                if evt.month_by == 'date':
                    # AbsoluteMonthlyRecurrence
                    event.abs_month_rec.interval.set(interval_rec)
                    event.abs_month_rec.day_of_month.set(evt.day)

                else:
                    # evt.month_by = 'day'
                    # RelativeMonthlyRecurrence
                    event.rel_month_rec.interval.set(interval_rec)
                    event.rel_month_rec.days_of_week.set(
                        ExchangeDays[evt.week_list.lower()]
                    )

                    ExchangeIndex = {
                        '1': fields.First,
                        '2': fields.Second,
                        '3': fields.Third,
                        '4': fields.Fourth,
                        '5': fields.Last,
                        '-1': fields.Last,
                    }

                    event.rel_month_rec.day_of_week_index.set(
                        ExchangeIndex[evt.byday]
                    )

            else:
                # yearly
                # AbsoluteYearlyRecurrence
                date = (evt.allday and
                        fields.Date.from_string(evt.start_date) or
                        fields.Datetime.from_string(evt.start_datetime)
                        )

                event.abs_year_rec.day_of_month.set(date.day)
                event.abs_year_rec.month.set(
                    get_exchange_month_from_date(date.month)
                )

    def fill_calendar_event(self, event, fields=None):
        """

        """
        if fields is None:
            fields = SIMPLE_VALUE_FIELDS.keys()

        for f, v in SIMPLE_VALUE_FIELDS.iteritems():
            if fields is not None and f not in fields:
                continue
            odoo_value = getattr(self.binding, f)
            if not odoo_value:
                continue
            event.__setattr__(v, odoo_value)

        self.fill_start_end(event)
        self.fill_privacy(event)
        self.fill_free_busy_status(event)
        self.fill_reminder(event)
        self.fill_attendees(event)
        self.fill_recurrency(event)
        __import__('pdb').set_trace()
        return event

    def _update_data(self, event=None, fields=None, **kwargs):
        record = self.fill_calendar_event(event, fields)
        event.categories = ['Odoo']
        if self.binding.send_calendar_invitations:
            record.is_draft = True
        return record

    def _create_data(self, fields=None):
        adapter = self.backend_adapter
        account = adapter.get_account(self.openerp_user)
        event = CalendarItem()
        event = self.fill_calendar_event(event, fields)
        event.categories = ['Odoo']
        record = account.bulk_create(folder=account.calendar, items=[event])
        # add Odoo category on create calendar on exchange todo
        return record[0]

    def _update(self, record):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_update_data(record)
        return self.backend_adapter.write(
            self.binding.external_id,
            record,
            self.binding.send_calendar_invitations)

    def _create(self, folder, record):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_create_data(record)
        return self.backend_adapter.create(
            folder, record,
            self.binding.send_calendar_invitations)

    def get_exchange_record(self, account, external_id):
        return account.calendar.get(id=external_id)

    def run_delayed_import_of_exchange_calendar_event(self, user_id,
                                                      calendar_event_instance):
        """
            run a delayed job for the exchange record
        """
        user = self.env['res.users'].browse(user_id)
        return self.env['exchange.calendar.event'].with_delay().import_record(
            self.backend_record,
            user,
            calendar_event_instance.item_id,
            priority=30)

    def run_delayed_delete_of_exchange_calendar_event(self, user_id,
                                                      calendar_event_instance):
        return self.backend_record.with_delay().export_delete_record(
            calendar_event_instance.item_id,
            self.openerp_user,
            priority=30)

    def create_exchange_calendar_event(self, fields):
        record = self._create_data(fields=fields)
        return record

    def update_existing(self, event, fields):
        record = self._update_data(event=event, fields=fields)
        if not record:
            return _('Nothing to export.')
        response = self._update(record)
        self.binding.with_context(
            connector_no_export=True).write(
            {'external_id': response.item_id,  # in case of convertId
             'change_key': response.changekey})

    def change_key_equals(self, exchange_record):
        return (
            exchange_record.changekey == self.binding.change_key)

    def _run(self, fields=None):
        assert self.binding
        user = self.binding.user_id
        self.openerp_user = user
        adapter = self.backend_adapter
        account = adapter.get_account(self.openerp_user)
        external_id = self.binding.external_id
        if not external_id:
            fields = None

        if not external_id:
            exchange_record = self.create_exchange_calendar_event(fields)
            self.binding.external_id = exchange_record.id
            self.binding.change_key = exchange_record.changekey
        else:
            # we have a binding
            # try to find an exchange event with tord(account)
            exchange_record = account.calendar.get(id=external_id)
            if exchange_record:
                # Compare change_keys of odoo binding and
                # Exchange record found
                if self.change_key_equals(exchange_record):
                    # update contact
                    self.update_existing(exchange_record, fields)
                else:
                    # run a delayed import of this Exchange contact
                    self.run_delayed_import_of_exchange_calendar_event(
                        user.id,
                        exchange_record)

            else:
                # binding defined in Odoo but does not exist anymore
                # in Exchange --> delete it from Odoo
                self.binding.openerp_id.with_context(
                    connector_no_export=True).unlink()
                return

        return _("Record exported with ID %s on Exchange") % \
            self.binding.external_id

    def delete_calendar_event(self, external_id, account):
        """
        delete calendar item from exchange
        """
        event = account.calendar.get(id=external_id)
        if event.send_calendar_invitations:
            invit = "SendToAllAndSaveCopy"
            CalendarItem.DeleteItem(
                [external_id],
                send_meeting_cancellations=invit)
        event.delete()
        return _("Record with ID %s deleted on Exchange") % external_id


@exchange_2010
class CalendarEventDisabler(ExchangeDisabler):
    _model_name = ['exchange.calendar.event']

    def delete_calendar_event(self, external_id, account):
        """
        delete calendar item from exchange
        """
        if not external_id:
            return _("Record does not exists in exchange")
        if self.env.context.get('connector_no_export'):
            return
        event = account.calendar.get(id=external_id)
        try:
            event.delete(send_meeting_cancellations=SEND_ONLY_TO_ALL)
        except AttributeError as exp:
            return _(
                "Seems event with ID %s has already been deleted in Exchange"
            ) % external_id
        return _("Record with ID %s deleted on Exchange") % external_id

    def _run(self, external_id, user_id):
        """ Implementation of the deletion """
        # search for correct user
        adapter = self.backend_adapter
        account = adapter.get_account(user_id)
        self.delete_calendar_event(external_id, account)

# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import logging
import datetime
from pyews.ews.calendar import CalendarItem, Attendee
from pyews.ews.data import (SensitivityType,
                            LegacyFreeBusyStatusType,
                            DaysOfWeekBaseType,
                            DayOfWeekIndexType,
                            MonthRecurrenceType,
                            ResponseTypeType,
                            )

from openerp import _, fields
from openerp.tools import (DEFAULT_SERVER_DATE_FORMAT,
                           DEFAULT_SERVER_DATETIME_FORMAT)
from ...unit.exporter import (ExchangeExporter,
                              ExchangeDisabler)
from ...backend import exchange_2010
from ...unit.importer import import_record
from ...unit.exporter import export_delete_record

_logger = logging.getLogger(__name__)

EXCHANGE_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'
EXCHANGE_REC_DATE_FORMAT = '%Y-%m-%d'

# UTILITY FUNTIONS


def get_exchange_month_from_date(month):
    maps = {
        1: MonthRecurrenceType.January,
        2: MonthRecurrenceType.February,
        3: MonthRecurrenceType.March,
        4: MonthRecurrenceType.April,
        5: MonthRecurrenceType.May,
        6: MonthRecurrenceType.June,
        7: MonthRecurrenceType.July,
        8: MonthRecurrenceType.August,
        9: MonthRecurrenceType.September,
        10: MonthRecurrenceType.October,
        11: MonthRecurrenceType.November,
        12: MonthRecurrenceType.December,
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

    def fill_privacy(self, calendar):
        """
        Here is the mapping between Odoo and Exchange:
        | Odoo         | Exchange     |
        | public       | Normal       |
        | private      | Personal     |
        | private      | Private      |
        | confidential | Confidential |
        """
        if self.binding_record['class'] == 'public':
            calendar.sensitivity.set(SensitivityType.Normal)
        elif self.binding_record['class'] == 'confidential':
            calendar.sensitivity.set(SensitivityType.Confidential)
        else:
            calendar.sensitivity.set(SensitivityType.Private)

    def fill_free_busy_status(self, calendar):
        """
        Here is the mapping between Odoo and Exchange:
        | Odoo | Exchange     |
        | free | Free         |
        | free | NoData       |
        | busy | Busy         |
        | busy | OOF          |
        | busy | Tentative    |
        """
        if self.binding_record.show_as == 'free':
            calendar.legacy_free_busy_status.set(LegacyFreeBusyStatusType.Free)
        else:
            calendar.legacy_free_busy_status.set(LegacyFreeBusyStatusType.Busy)

    def fill_reminder(self, calendar):
        """
        In Exchange, only one reminder can be set.
        So Odoo side, only the first reminder will be exported to Exchange.
        """
        alarms = self.binding_record.alarm_ids
        if alarms:
            alarm = alarms[0]
            calendar.is_reminder_set.set(True)
            calendar.reminder_due_by.set(convert_to_exchange(
                self.binding_record.start, time=True)
            )
            calendar.reminder_minutes_before_start.set(alarm.duration_minutes)
        else:
            calendar.is_reminder_set.set(False)

    def fill_start_end(self, calendar):
        if self.binding_record.allday:
            calendar.is_all_day_event.set(True)
            calendar.start.set(convert_to_exchange(
                self.binding_record.start_date, time=False)
            )
            calendar.end.set(convert_to_exchange(
                self.binding_record.stop_date, time=False, add_day=True)
            )
        else:
            calendar.is_all_day_event.set(False)
            calendar.start.set(convert_to_exchange(
                self.binding_record.start_datetime, time=True)
            )
            calendar.end.set(convert_to_exchange(
                self.binding_record.stop_datetime, time=True)
            )

    def _attendee_already_exists(self, attendee_email, calendar):
        """
        try to find an attendee in the calendar with same email address
        """
        result = False

        for att in calendar.required_attendees.entries:
            if att.mailbox.email_address.value == attendee_email:
                return True

        return result

    def fill_attendees(self, calendar):
        """
        For each attendee in Odoo:
            if there is not already an attendee with the same email address:
                - create an Exchange attendee
                - add it in required_attendees of the meeting.
        """
        STATES_MAPPING = {
            'tentative': ResponseTypeType.Tentative,
            'declined': ResponseTypeType.Decline,
            'accepted': ResponseTypeType.Accept,
        }
        for attendee in self.binding_record.attendee_ids:
            # cn, email
            for att in calendar.required_attendees.entries:
                if att.mailbox.email_address.value == attendee.email:
                    att.response_type.value = (
                        STATES_MAPPING.get(attendee.state,
                                           ResponseTypeType.Unknown)
                    )
            if (not self._attendee_already_exists(
                    attendee.email, calendar)):
                att = Attendee()
                att.mailbox.name.set(attendee.cn)
                att.mailbox.email_address.set(attendee.email)
                att.response_type.set(
                    STATES_MAPPING.get(attendee.state,
                                       ResponseTypeType.Unknown)
                )
                calendar.required_attendees.add(att)

    def fill_recurrency(self, calendar):
        """
        If Odoo event is recurrent, fill recurrency options
        in `calendar` Exchange object.

        Odoo only supports numbered_recurrence and end_date recurrence.
        """
        evt = self.binding_record
        if evt.recurrency:

            if evt.end_type == "count":
                calendar.recurrence.numbered_rec.nb_occurrences.set(evt.count)
                if self.binding_record.allday:
                    calendar.recurrence.numbered_rec.start_date.set(
                        convert_to_exchange(self.binding_record.start_date,
                                            time=False, rec=True)
                    )
                else:
                    calendar.recurrence.numbered_rec.start_date.set(
                        convert_to_exchange(self.binding_record.start_datetime,
                                            time=True, rec=True)
                    )
            else:
                # end_date recurrency
                calendar.recurrence.end_date_rec.start_date(
                    convert_to_exchange(self.binding_record.start_date,
                                        time=False, rec=True))
                calendar.recurrence.end_date_rec.end_date(
                    convert_to_exchange(self.binding_record.final_date,
                                        time=False, rec=True))

            ExchangeDays = {
                'mo': DaysOfWeekBaseType.Monday,
                'tu': DaysOfWeekBaseType.Tuesday,
                'we': DaysOfWeekBaseType.Wednesday,
                'th': DaysOfWeekBaseType.Thursday,
                'fr': DaysOfWeekBaseType.Friday,
                'sa': DaysOfWeekBaseType.Saturday,
                'su': DaysOfWeekBaseType.Sunday,
            }

            interval_rec = evt.interval
            if evt.rrule_type == 'daily':
                calendar.recurrence.day_rec.interval.set(interval_rec)

            elif evt.rrule_type == 'weekly':
                weekly = calendar.recurrence.week_rec
                days = []
                for day in ('mo', 'tu', 'we', 'th', 'fr', 'sa', 'su'):
                    if getattr(evt, day):
                        days.append(day)
                days = days.map(lambda x: ExchangeDays['x'])
                days = ' '.join(days)
                weekly.days_of_week.set(days)
                weekly.interval.set(interval_rec)
                weekly.first_day_of_week.set(DaysOfWeekBaseType.Monday)

            elif evt.rrule_type == 'monthly':
                if evt.month_by == 'date':
                    # AbsoluteMonthlyRecurrence
                    calendar.abs_month_rec.interval.set(interval_rec)
                    calendar.abs_month_rec.day_of_month.set(evt.day)

                else:
                    # evt.month_by = 'day'
                    # RelativeMonthlyRecurrence
                    calendar.rel_month_rec.interval.set(interval_rec)
                    calendar.rel_month_rec.days_of_week.set(
                        ExchangeDays[evt.week_list.lower()]
                    )

                    ExchangeIndex = {
                        '1': DayOfWeekIndexType.First,
                        '2': DayOfWeekIndexType.Second,
                        '3': DayOfWeekIndexType.Third,
                        '4': DayOfWeekIndexType.Fourth,
                        '5': DayOfWeekIndexType.Last,
                        '-1': DayOfWeekIndexType.Last,
                    }

                    calendar.rel_month_rec.day_of_week_index.set(
                        ExchangeIndex[evt.byday]
                    )

            else:
                # yearly
                # AbsoluteYearlyRecurrence
                date = (evt.allday and
                        fields.Date.from_string(evt.start_date) or
                        fields.Datetime.from_string(evt.start_datetime)
                        )

                calendar.abs_year_rec.day_of_month.set(date.day)
                calendar.abs_year_rec.month.set(
                    get_exchange_month_from_date(date.month)
                )

    def fill_calendar_event(self, calendar, fields):
        """

        """
        if fields is None:
            fields = SIMPLE_VALUE_FIELDS.keys()

        for f, v in SIMPLE_VALUE_FIELDS.iteritems():
            if fields is not None and f not in fields:
                continue
            odoo_value = getattr(self.binding_record, f)
            if not odoo_value:
                odoo_value = None

            if isinstance(v, list):
                ff = getattr(calendar, v[0])
                for elem in v[1:]:
                    ff = getattr(ff, elem)
                ff.value = odoo_value
            else:
                getattr(calendar, v).value = odoo_value

        self.fill_start_end(calendar)
        self.fill_privacy(calendar)
        self.fill_free_busy_status(calendar)
        self.fill_reminder(calendar)
        self.fill_attendees(calendar)
        self.fill_recurrency(calendar)

    def check_folder_still_exists(self, folder_id):
        """
            Check if provided 'folder_id' still exists in Exchange.
            If provided 'folder_id' is 'False', create a new one in Exchange
            and fill information on 'res.users.backend.folder' object (if no
            existing one in Exchange 'Calendar' folder, create).
        """
        br = self.binding_record
        odoo_folder = br.user_id.find_folder(br.backend_id.id, create=True,
                                             default_name='Odoo',
                                             folder_type='calendar')
        adapter = self.backend_adapter
        folder = None
        if folder_id:
            folder = adapter.find_folder(odoo_folder)
        if not folder:
            folder = adapter.create_folder(odoo_folder)
            odoo_folder.folder_id = folder.Id
        return folder

    def _update_data(self, fields=None, **kwargs):
        exchange_service = self.backend_adapter.ews
        calendar = exchange_service.GetCalendarItems(
            [self.binding_record.external_id])[0]
        self.fill_calendar_event(calendar, fields)

        return calendar

    def _create_data(self, fields=None):
        exchange_service = self.backend_adapter.ews
        parent_folder_id = self.check_folder_still_exists(
            self.binding_record.calendar_folder
            ).Id
        calendar = CalendarItem(exchange_service, parent_folder_id)
        self.fill_calendar_event(calendar, fields)
        # add Odoo category on create calendar on exchange
        calendar.categories.add('Odoo')

        return calendar, parent_folder_id

    def _update(self, record):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_update_data(record)
        return self.backend_adapter.write(self.external_id,
                                          record,
                                          self.openerp_user)

    def _create(self, folder, record):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_create_data(record)
        return self.backend_adapter.create(folder, record, self.openerp_user)

    def get_exchange_record(self):
        return self.backend_adapter.ews.GetCalendarItems(
            [self.binding_record.external_id])

    def run_delayed_import_of_exchange_calendar_event(self, user_id,
                                                      calendar_event_instance):
        """
            run a delayed job for the exchange record
        """
        return import_record.delay(self.session,
                                   'exchange.calendar.event',
                                   self.backend_record.id,
                                   user_id,
                                   calendar_event_instance.itemid,
                                   priority=30)

    def run_delayed_delete_of_exchange_calendar_event(self, user_id,
                                                      calendar_event_instance):
        return export_delete_record.delay(self.session,
                                          'exchange.calendar.event',
                                          self.backend_record.id,
                                          calendar_event_instance.itemid.value,
                                          priority=30)

    def create_exchange_calendar_event(self, fields):
        record, folder = self._create_data(fields=fields)
        if not record:
            return _('Nothing to export.')
        Id, CK = self._create(folder, record)
        self.binding_record.with_context(connector_no_export=True).write(
            {'change_key': CK, 'external_id': Id})

    def update_existing(self, fields):
        record = self._update_data(fields=fields)
        if not record:
            return _('Nothing to export.')
        response = self._update(record)
        self.binding_record.with_context(
            connector_no_export=True).write(
            {'change_key': response[0].change_key.value})

    def change_key_equals(self, exchange_record):
        return (
            exchange_record.change_key.value == self.binding_record.change_key)

    def _run(self, fields=None):
        assert self.binding_id
        user = self.binding_record.user_id
        self.openerp_user = user
        self.backend_adapter.set_primary_smtp_address(user)

        if not self.binding_record.external_id:
            fields = None

        if not self.binding_record.external_id:
            self.create_exchange_calendar_event(fields)
        else:
            # we have a binding
            # try to find an exchange event with this binding ID
            exchange_record = self.get_exchange_record()
            if exchange_record:
                exchange_record = exchange_record[0]
                # Compare change_keys of odoo binding and
                # Exchange record found
                if self.change_key_equals(exchange_record):
                    # update contact
                    self.update_existing(fields)
                else:
                    # run a delayed import of this Exchange contact
                    self.run_delayed_import_of_exchange_calendar_event(
                        user.id,
                        exchange_record)
            else:
                # create contact in exchange and update its `external_id`
                self.create_exchange_calendar_event(fields)

        return _("Record exported with ID %s on Exchange") % (
            self.binding_record.external_id)


@exchange_2010
class CalendarEventDisabler(ExchangeDisabler):
    _model_name = ['exchange.calendar.event']

    def get_exchange_record(self, external_id):
        return self.backend_adapter.ews.GetCalendarItems([external_id])

    def delete_calendar_event(self, external_id, user):
        """
        delete calendar item from exchange
        """
        self.backend_adapter.ews.DeleteCalendarItems([external_id])
        return _("Record with ID %s deleted on Exchange") % external_id

    def _run(self, external_id):
        """ Implementation of the deletion """
        user_id = self.session.uid
        user = self.env['res.users'].browse(user_id)
        self.backend_adapter.set_primary_smtp_address(user)
        self.delete_calendar_event(external_id, user)

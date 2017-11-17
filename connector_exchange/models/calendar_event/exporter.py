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

try:
    from pyews.ews.calendar import CalendarItem, Attendee
    from pyews.ews.data import (SensitivityType,
                                LegacyFreeBusyStatusType,
                                DaysOfWeekBaseType,
                                DayOfWeekIndexType,
                                MonthRecurrenceType,
                                ResponseTypeType,
                                )
except (ImportError, IOError) as err:
    _logger.debug(err)


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
        if self.binding['privacy'] == 'public':
            calendar.sensitivity.set(SensitivityType.Normal)
        elif self.binding['privacy'] == 'confidential':
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
        if self.binding.show_as == 'free':
            calendar.legacy_free_busy_status.set(LegacyFreeBusyStatusType.Free)
        else:
            calendar.legacy_free_busy_status.set(LegacyFreeBusyStatusType.Busy)

    def fill_reminder(self, calendar):
        """
        In Exchange, only one reminder can be set.
        So Odoo side, only the first reminder will be exported to Exchange.
        """
        alarms = self.binding.alarm_ids
        if alarms:
            alarm = alarms[0]
            calendar.is_reminder_set.set(True)
            calendar.reminder_due_by.set(convert_to_exchange(
                self.binding.start, time=True)
            )
            calendar.reminder_minutes_before_start.set(alarm.duration_minutes)
        else:
            calendar.is_reminder_set.set(False)

    def fill_start_end(self, calendar):
        if self.binding.allday:
            calendar.is_all_day_event.set(True)
            calendar.start.set(convert_to_exchange(
                self.binding.start_date)
            )
            calendar.end.set(convert_to_exchange(
                self.binding.stop_date)
            )
        else:
            calendar.is_all_day_event.set(False)
            calendar.start.set(convert_to_exchange(
                self.binding.start, time=True)
            )
            calendar.end.set(convert_to_exchange(
                self.binding.stop, time=True)
            )

    def _attendee_already_exists(self, attendee_email, calendar):
        """
        try to find an attendee in the calendar with same email address
        """
        result = False

        for att in calendar.required_attendees.entries:
            att_mail = att.mailbox.email_address.value
            if (att_mail == attendee_email or
                    att_mail == self.openerp_user.email):
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
        for attendee in self.binding.attendee_ids:
            if attendee.email == self.openerp_user.email:
                continue
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
                att.mailbox.name.set(attendee.common_name)
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
        evt = self.binding
        if evt.recurrency:

            if evt.end_type == "count":
                calendar.recurrence.numbered_rec.nb_occurrences.set(evt.count)
                if self.binding.allday:
                    calendar.recurrence.numbered_rec.start_date.set(
                        convert_to_exchange(self.binding.start_date,
                                            time=False, rec=True)
                    )
                else:
                    calendar.recurrence.numbered_rec.start_date.set(
                        convert_to_exchange(self.binding.start_datetime,
                                            time=True, rec=True)
                    )
            else:
                # end_date recurrency
                calendar.recurrence.end_date_rec.start_date(
                    convert_to_exchange(self.binding.start_date,
                                        time=False, rec=True))
                calendar.recurrence.end_date_rec.end_date(
                    convert_to_exchange(self.binding.final_date,
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
                for day in ExchangeDays:
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
            odoo_value = getattr(self.binding, f)
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
        br = self.binding
        odoo_folder = br.user_id.find_folder(br.backend_id.id, create=True,
                                             folder_type='calendar')
        adapter = self.backend_adapter
        folder = None
        if folder_id:
            folder = adapter.find_folder(odoo_folder)
        if not folder:
            folder = adapter.find_folder(odoo_folder)
            odoo_folder.folder_id = folder.Id
        return folder

    def _update_data(self, fields=None, **kwargs):
        exchange_service = self.backend_adapter.ews
        calendar = exchange_service.GetCalendarItems(
            [self.binding.external_id])[0]
        self.fill_calendar_event(calendar, fields)
        calendar.categories.add('Odoo')

        if self.binding_record.send_calendar_invitations:
            calendar.is_draft = True
        return calendar

    def _create_data(self, fields=None):
        exchange_service = self.backend_adapter.ews
        parent_folder_id = self.check_folder_still_exists(
            self.binding.calendar_folder
        ).Id
        calendar = CalendarItem(exchange_service, parent_folder_id)
        self.fill_calendar_event(calendar, fields)
        # add Odoo category on create calendar on exchange
        calendar.categories.add('Odoo')

        if self.binding_record.send_calendar_invitations:
            calendar.is_draft = True

        return calendar, parent_folder_id

    def _update(self, record):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_update_data(record)
        return self.backend_adapter.write(
            self.external_id,
            record,
            self.binding_record.send_calendar_invitations)

    def _create(self, folder, record):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_create_data(record)
        return self.backend_adapter.create(
            folder, record,
            self.binding_record.send_calendar_invitations)

    def get_exchange_record(self):
        return self.backend_adapter.ews.GetCalendarItems(
            [self.binding.external_id])

    def run_delayed_import_of_exchange_calendar_event(self, user_id,
                                                      calendar_event_instance):
        """
            run a delayed job for the exchange record
        """
        user = self.env['res.users'].browse(user_id)
        return self.env['exchange.calendar.event'].with_delay().import_record(
            self.backend_record,
            user,
            calendar_event_instance.itemid,
            priority=30)

    def run_delayed_delete_of_exchange_calendar_event(self, user_id,
                                                      calendar_event_instance):
        user = self.env['res.users'].browse(user_id)
        return self.backend_record.with_delay().export_delete_record(
            calendar_event_instance.itemid.value,
            user,
            priority=30)

    def create_exchange_calendar_event(self, fields):
        record, folder = self._create_data(fields=fields)
        if not record:
            return _('Nothing to export.')
        Id, CK = self._create(folder, record)
        self.binding.with_context(connector_no_export=True).write(
            {'change_key': CK, 'external_id': Id})

    def update_existing(self, fields):
        record = self._update_data(fields=fields)
        if not record:
            return _('Nothing to export.')
        response = self._update(record)
        self.binding.with_context(
            connector_no_export=True).write(
            {'external_id': response[0].itemid.value,  # in case of convertId
             'change_key': response[0].change_key.value})

    def change_key_equals(self, exchange_record):
        return (
            exchange_record.change_key.value == self.binding.change_key)

    def _run(self, fields=None):
        assert self.binding
        user = self.binding.user_id
        self.openerp_user = user
        self.backend_adapter.set_primary_smtp_address(user)
        external_id = self.binding.external_id
        if not external_id:
            fields = None

        if not external_id:
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
                # binding defined in Odoo but does not exist anymore
                # in Exchange --> delete it from Odoo
                self.binding.openerp_id.with_context(
                    connector_no_export=True).unlink()
                return

        return _("Record exported with ID %s on Exchange") % external_id


@exchange_2010
class CalendarEventDisabler(ExchangeDisabler):
    _model_name = ['exchange.calendar.event']

    def get_exchange_record(self, external_id):
        return self.backend_adapter.ews.GetCalendarItems([external_id])

    def delete_calendar_event(self, external_id, user):
        """
        delete calendar item from exchange
        """
        invit = "SendToNone"
        event = self.env['exchange.calendar.event'].search(
            [('external_id', '=', external_id)], limit=1
        )
        if event.send_calendar_invitations:

            invit = "SendToAllAndSaveCopy"
        self.backend_adapter.ews.DeleteCalendarItems(
            [external_id],
            send_meeting_cancellations=invit)
        return _("Record with ID %s deleted on Exchange") % external_id

    def _run(self, external_id, user_id):
        """ Implementation of the deletion """
        # search for correct user
        user = self.env['res.users'].browse(user_id)
        self.backend_adapter.set_primary_smtp_address(user)
        self.delete_calendar_event(external_id, user)

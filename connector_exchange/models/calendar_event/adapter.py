# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from ...unit.backend_adapter import ExchangeAdapter
from ...backend import exchange_2010


_logger = logging.getLogger(__name__)

try:
    from exchangelib import FolderCollection
except (ImportError, IOError) as err:
    _logger.debug(err)


@exchange_2010
class EventBackendAdapter(ExchangeAdapter):
    _model_name = ['exchange.calendar.event']

    def create(self, folder, exchange_obj, send_calendar_invitations):
        invit = "SendToNone"
        if send_calendar_invitations:
            invit = "SendToAllAndSaveCopy"
        exchange_obj.send_meeting_invitations = invit
        return self.account.bulk_create(
            folder=self.account.calendar,
            items=exchange_obj)

    def write(self, external_id, exchange_obj, send_calendar_invitations):
        exchange_obj.send_meeting_invitations = send_calendar_invitations
        return exchange_obj.save()

    def find_folder(self, account, odoo_folder):
        f = account.Contacts.glob(odoo_folder.name)
        return f

    def create_folder(self, account, odoo_folder):
        f = FolderCollection(parent=account.Calendar, name=odoo_folder.name)
        return f

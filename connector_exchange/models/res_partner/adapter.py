# -*- coding: utf-8 -*-
# © 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pyews.ews.data import FolderClass
from openerp import _
from openerp.addons.connector.exception import FailedJobError
from ...unit.backend_adapter import ExchangeAdapter
from ...backend import exchange_2010


@exchange_2010
class PartnerBackendAdapter(ExchangeAdapter):
    _model_name = ['exchange.res.partner']

    def create(self, folder, exchange_contact_obj):
        return self.ews.CreateItem(folder, exchange_contact_obj)

    def write(self, external_id, exchange_contact_obj):
        return self.ews.UpdateItems([exchange_contact_obj])

    def find_folder(self, odoo_folder):
        self.ews.get_root_folder()

        exchange_folder = self.ews.root_folder.FindFolderByDisplayName(
            str(odoo_folder.name),
            types=[FolderClass.Contacts],
            recursive=True)
        return exchange_folder[0]

    def create_folder(self, odoo_folder):
        self.ews.get_root_folder()

        contact_folder = self.ews.root_folder.FindFolderByDisplayName(
            "Contacts",
            types=[FolderClass.Contacts])
        if not contact_folder:
            raise FailedJobError(
                _('Unable to find folder "Contacts" in Exchange')
                )
        contact_folder = contact_folder[0]
        if (odoo_folder.folder_type == 'create' and
                odoo_folder.name == 'Contacts'):
            return contact_folder

        self.ews.CreateFolder(
            contact_folder.Id,
            [(str(odoo_folder.name), FolderClass.Contacts)]
            )

        # The folder returned by ews.CreateFolder contains only an Id.
        # Read the rest of the data
        exchange_folder = self.ews.root_folder.FindFolderByDisplayName(
            str(odoo_folder.name),
            types=[FolderClass.Contacts],
            recursive=True)

        return exchange_folder[0]

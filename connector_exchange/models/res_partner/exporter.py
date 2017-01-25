# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging
from pyews.ews.contact import Contact, PostalAddress
from pyews.ews.data import (EmailKey,
                            PhoneKey,
                            PhysicalAddressType,
                            )
from odoo import _
from odoo.addons.connector.exception import FailedJobError
from ...unit.exporter import (ExchangeExporter,
                              ExchangeDisabler)
from ...backend import exchange_2010
from ...unit.importer import import_record


_logger = logging.getLogger(__name__)
EXCHANGE_STREET_SEPARATOR = ' // '


def _compute_subst(binding_record):
    return {
        'street_computed': _construct_street(binding_record,
                                             sep=EXCHANGE_STREET_SEPARATOR),
        'city': binding_record.city,
        'zipcode': binding_record.zip,
        'state': binding_record.state_id.name,
        'country': binding_record.country_id.name,
    }


def _construct_street(rec, sep=' '):
        streets = [rec.street, rec.street2, rec.street3]
        return sep.join(part for part in streets if part)


SIMPLE_VALUE_FIELDS = {'firstname': ['complete_name', 'given_name'],
                       'lastname': ['complete_name', 'surname'],
                       'website': 'business_home_page',
                       'function': 'job_title'
                       }

RELATIONAL_VALUE_FIELDS = {'title': ['complete_name', 'title'],
                           'parent_id': 'company_name',
                           # 'position_id': 'profession',
                           }

MULTIPLE_VALUE_FIELDS = {'email': {'exchange': 'emails',
                                   'type': EmailKey.Email1},
                         'phone': {'exchange': 'phones',
                                   'type': PhoneKey.PrimaryPhone},
                         'fax': {'exchange': 'phones',
                                 'type': PhoneKey.BusinessFax},
                         'mobile': {'exchange': 'phones',
                                    'type': PhoneKey.MobilePhone},
                         }

ADDRESS_FIELDS = ['street', 'street2', 'street3', 'zip', 'city', 'state_id',
                  'country_id']

ADDRESS_DICT = {'physical_addresses': {
    'street': "%(street_computed)s",
    'city': "%(city)s",
    'postal_code': "%(zipcode)s",
    'state': "%(state)s",
    'country_region': "%(country)s"}
    }


@exchange_2010
class PartnerExporter(ExchangeExporter):
    _model_name = ['exchange.res.partner']

    def fill_contact(self, contact, fields):
        if fields is None:
            fields = (
                SIMPLE_VALUE_FIELDS.keys() + RELATIONAL_VALUE_FIELDS.keys() +
                MULTIPLE_VALUE_FIELDS.keys() + ADDRESS_FIELDS
                )

        if 'lastname' in fields or 'firstname' in fields:
            fields.append('name')

        for f, v in SIMPLE_VALUE_FIELDS.iteritems():
            if fields is not None and f not in fields:
                continue
            odoo_value = getattr(self.binding_record, f)
            if not odoo_value:
                odoo_value = None

            if isinstance(v, list):
                ff = getattr(contact, v[0])
                for elem in v[1:]:
                    ff = getattr(ff, elem)
                ff.value = odoo_value
            else:
                getattr(contact, v).value = odoo_value

        for f, v in RELATIONAL_VALUE_FIELDS.iteritems():
            if fields is not None and f not in fields:
                continue
            odoo_value = getattr(self.binding_record, f)
            if odoo_value:
                odoo_value = odoo_value.name
            else:
                odoo_value = None

            if isinstance(v, list):
                ff = getattr(contact, v[0])
                for elem in v[1:]:
                    ff = getattr(ff, elem)
                ff.value = odoo_value
            else:
                getattr(contact, v).value = odoo_value

        for f, v in MULTIPLE_VALUE_FIELDS.iteritems():
            if fields is not None and f not in fields:
                continue
            odoo_value = getattr(self.binding_record, f)
            if not odoo_value:
                odoo_value = None

            exchange_field = getattr(contact, v['exchange'])
            not_found = True
            for entry in exchange_field.entries:
                if entry.attrib['Key'] == v['type']:
                    not_found = False
                    entry.value = odoo_value

            if not_found:
                exchange_field.add(v['type'], odoo_value)

        if set(ADDRESS_FIELDS) & set(fields):
            # import pdb; pdb.set_trace()
            not_found = True
            if contact.physical_addresses:
                for atype in contact.physical_addresses.entries:
                    if atype.attrib['Key'] == PhysicalAddressType.Business:
                        not_found = False
                        subst = _compute_subst(self.binding_record)

                        for key, valu in ADDRESS_DICT[
                                "physical_addresses"].iteritems():
                            valu = valu % subst
                            if valu == 'False':
                                valu = None
                            getattr(atype, key).value = valu

            if not_found:
                addr = PostalAddress()
                addr.add_attrib('Key', PhysicalAddressType.Business)

                subst = _compute_subst(self.binding_record)
                for key, valu in ADDRESS_DICT[
                        "physical_addresses"].iteritems():
                    valu = valu % subst
                    if valu == 'False':
                        valu = None
                    getattr(addr, key).value = valu

                contact.physical_addresses.add(addr)

    def check_folder_still_exists(self, folder_id):
        """
            Check if provided 'folder_id' still exists in Exchange.
            If provided 'folder_id' is 'False', create a new one in Exchange
            and fill information on 'res.users.backend.folder' object (if no
            existing one in Exchange 'Contacts' folder, create).
        """
        br = self.binding_record
        odoo_folder = br.user_id.find_folder(br.backend_id.id)
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
        contact = exchange_service.GetContacts(
            [self.binding_record.external_id])[0]
        self.fill_contact(contact, fields)
        # add Odoo category on create contact on exchange
        contact.categories.add('Odoo')

        return contact

    def _create_data(self, fields=None):
        exchange_service = self.backend_adapter.ews
        parent_folder_id = self.check_folder_still_exists(
            self.binding_record.current_folder
            ).Id
        contact = Contact(exchange_service, parent_folder_id)
        self.fill_contact(contact, fields)
        # add Odoo category on create contact on exchange
        contact.categories.add('Odoo')
        contact.file_as_mapping.value = 'FirstSpaceLast'

        return contact, parent_folder_id

    def _update(self, record):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_update_data(record)
        return self.backend_adapter.write(self.external_id, record)

    def _create(self, folder, record):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_create_data(record)
        return self.backend_adapter.create(folder, record)

    def get_exchange_record(self):
        return self.backend_adapter.ews.GetContacts(
            [self.binding_record.external_id])

    def find_by_email(self):
        """
            search for an exchange record with same email as
            the partner we try to export
        """
        parent_folder_id = self.check_folder_still_exists(
            self.binding_record.current_folder
        ).Id
        response = self.backend_adapter.ews.SearchContactByEmail(
            parent_folder_id,
            self.binding_record.email)

        return response

    def run_delayed_import_of_exchange_contact(self, user_id,
                                               contact_instance):
        """
            run a delayed job for the exchange record
        """
        return import_record.delay(self.session,
                                   'exchange.res.partner',
                                   self.backend_record.id,
                                   user_id,
                                   contact_instance.itemid,
                                   priority=30)

    def create_exchange_contact(self, fields):
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
        self.backend_adapter.set_primary_smtp_address(user)

        if not self.binding_record.external_id:
            fields = None

        if not self.binding_record.external_id:
            # create contact in exchange
            self.create_exchange_contact(fields)
        else:
            # we have a binding
            # try to find an exchange contact with this binding ID
            exchange_record = self.get_exchange_record()
            if exchange_record:
                exchange_record = exchange_record[0]
                # Compare change_keys of odoo binding and Exchange record found
                if self.change_key_equals(exchange_record):
                    # update contact
                    self.update_existing(fields)
                else:
                    # run a delayed import of this Exchange contact
                    self.run_delayed_import_of_exchange_contact(
                        user.id,
                        exchange_record)
            else:
                # create contact in exchange and update its `external_id`
                self.create_exchange_contact(fields)

        return _("Record exported with ID %s on Exchange") % (
            self.binding_record.external_id)


@exchange_2010
class PartnerDisabler(ExchangeDisabler):
    _model_name = ['exchange.res.partner']

    def get_exchange_record(self, external_id):
        return self.backend_adapter.ews.GetContacts([external_id])

    def check_folder_still_exists(self, folder_id, user):
        """
            Check if provided 'folder_id' still exists in Exchange.
            If provided 'folder_id' is 'False', create a new one in Exchange
            and fill information on 'res.users.backend.folder' object (if no
            existing one in Exchange 'Contacts' folder, create).
        """
        odoo_folder = user.find_folder(self.backend_record.id,
                                       create=True,
                                       default_name='Odoo Deleted',
                                       folder_type='delete')
        adapter = self.backend_adapter
        folder = None
        if folder_id:
            folder = adapter.find_folder(odoo_folder)
        if not folder:
            folder = adapter.create_folder(odoo_folder)
            odoo_folder.folder_id = folder.Id
        return folder

    def move_contact(self, contact_id, user_rec):
        """
            move contact to "Odoo Deleted" Folder.
        """
        ews_service = self.backend_adapter.ews
        ews_service.get_root_folder()

        deleted_folder = user_rec.find_folder(
            self.backend_record.id,
            create=True,
            default_name='Odoo Deleted',
            folder_type='delete')

        folder = self.check_folder_still_exists(deleted_folder.folder_id,
                                                user_rec).Id

        if folder:
            ews_service.MoveItems(folder, [contact_id])
        else:
            raise FailedJobError(
                _('Unable to find folder %s in Exchange' % deleted_folder.name)
                )

    def _run(self, external_id, user_id):
        """ Implementation of the deletion """
        user = self.env['res.users'].browse(user_id)
        self.backend_adapter.set_primary_smtp_address(user)
        self.move_contact(external_id, user)

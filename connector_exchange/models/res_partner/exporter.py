# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging
from odoo import _
from ...unit.exporter import (ExchangeExporter,
                              ExchangeDisabler)
from ...backend import exchange_2010

from exchangelib import Contact
from exchangelib.indexed_properties import (PhysicalAddress,
                                            EmailAddress,
                                            PhoneNumber)

_logger = logging.getLogger(__name__)

EXCHANGE_STREET_SEPARATOR = ' // '
EXCHANGE_NOT_FOUND = 'The specified object was not found in the store.'
EXCHANGE_ERROR = 'Id is malformed.'


def _compute_subst(binding):
    return {
        'street_computed': _construct_street(binding,
                                             sep=EXCHANGE_STREET_SEPARATOR),
        'city': binding.city,
        'zipcode': binding.zip,
        'state': binding.state_id.name or "/",
        'country': binding.country_id.name,
    }


def _construct_street(rec, sep=' '):
        streets = [rec.street, rec.street2, rec.street3]
        return sep.join(part for part in streets if part)


SIMPLE_VALUE_FIELDS = {'firstname': 'given_name',
                       'name': 'display_name',
                       'lastname': 'nickname',
                       'website': 'business_homepage',
                       'function': 'job_title',
                       # 'email': ['email_addresses'],
                       # 'phone': ['phone_numbers'],
                       # 'fax': ['phone_numbers'],
                       # 'mobile': ['phone_numbers']
                       }

RELATIONAL_VALUE_FIELDS = {'title': ['complete_name', 'title'],
                           'parent_id': 'company_name',
                           # 'position_id': 'profession',
                           }

PHONE_VALUE_FIELDS = {'phone': 'BusinessPhone',
                      'fax': 'BusinessFax',
                      'mobile': 'MobilePhone'}

ADDRESS_FIELDS = ['street', 'street2', 'street3', 'zip', 'city', 'state_id',
                  'country_id']

ADDRESS_DICT = {'physical_addresses': {
    'street': "%(street_computed)s",
    'city': "%(city)s",
    'zipcode': "%(zipcode)s",
    'state': "%(state)s",
    'country': "%(country)s"}
    }


@exchange_2010
class PartnerExporter(ExchangeExporter):
    _model_name = ['exchange.res.partner']

    def fill_contact(self, contact, fields):
        contact.file_as_mapping = 'FirstSpaceLast'
        if fields is None or fields == []:
            fields = (
                SIMPLE_VALUE_FIELDS.keys() + RELATIONAL_VALUE_FIELDS.keys() +
                ADDRESS_FIELDS + PHONE_VALUE_FIELDS.keys() + ['email']
                )

        if 'lastname' in fields or 'firstname' in fields:
            fields.append('name')
        for f, v in SIMPLE_VALUE_FIELDS.iteritems():
            if fields is not None and f not in fields:
                continue
            odoo_value = getattr(self.binding, f)
            if not odoo_value:
                continue

            if isinstance(v, list):
                if hasattr(contact, v[0]):
                    for elem in v[1:]:
                        contact.__setattr__(elem, odoo_value)
            else:
                contact.__setattr__(v, odoo_value)

        for f, v in RELATIONAL_VALUE_FIELDS.iteritems():
            if fields is not None and f not in fields:
                continue
            odoo_value = getattr(self.binding, f)
            if not odoo_value:
                continue

            if isinstance(v, list):
                if hasattr(contact, v[0]):
                    ff = contact.__getattribute__(v[0])
                    for elem in v[1:]:
                        if hasattr(contact, elem):
                            ff = contact.__getattribute__(elem)
                        ff.__setattr__(elem, odoo_value.name)
            else:
                contact.__setattr__(v, odoo_value.name)

        if set(ADDRESS_FIELDS) & set(fields):
            # sync only Business address
            not_found = True
            if contact.physical_addresses:
                for atype in contact.physical_addresses:
                    if atype.label == 'Business':
                        not_found = False
                        subst = _compute_subst(self.binding)

                        for key, valu in ADDRESS_DICT[
                                "physical_addresses"].iteritems():
                            valu = valu % subst
                            if valu == 'False':
                                valu = None
                            atype.__setattr__(key, valu)

            if not_found:
                subst = _compute_subst(self.binding)
                addrs = []
                addr = PhysicalAddress(street=subst['street_computed'],
                                       city=subst['city'],
                                       country=subst['country'],
                                       state='',
                                       zipcode=subst['zipcode']
                                       )
                addr.label = "Business"
                addrs.append(addr)
                contact.physical_addresses = addrs
        else:
            if contact.physical_addresses:
                for addr in contact.physical_addresses:
                    for fi in addr.__slots__:
                        if getattr(addr, fi) is None:
                            setattr(addr, fi, ' ')

        if 'email' in fields:
            contact.email_addresses = [EmailAddress(label='EmailAddress1',
                                                    email=self.binding.email)]
        phones_to_update = set(PHONE_VALUE_FIELDS.keys()) & set(fields)
        if phones_to_update:
            not_found = True
            for f in list(phones_to_update):
                if contact.phone_numbers:
                    for mails_inst in contact.phone_numbers:
                        if mails_inst.label == PHONE_VALUE_FIELDS[f]:
                            not_found = False
                            mails_inst.phone_number = getattr(self.binding, f)
                if not_found:
                    value = PhoneNumber(label=PHONE_VALUE_FIELDS[f],
                                        phone_number=getattr(self.binding, f))
                    if isinstance(contact.phone_numbers, list):
                        contact.phone_numbers.append(value)
                    else:
                        contact.phone_numbers = [value]
        return contact

    def _update_data(self, fields=None, **kwargs):
        adapter = self.backend_adapter
        account = adapter.get_account(self.openerp_user)
        contact = account.contacts.get(id=self.binding.external_id)
        self.fill_contact(contact, fields)
        contact.categories = ['Odoo']
        return contact

    def _create_data(self, fields=None):
        adapter = self.backend_adapter
        account = adapter.get_account(self.openerp_user)
        contact = Contact(account=account)
        contact = self.fill_contact(contact, fields)
        contact.categories = ['Odoo']
        contact = account.bulk_create(folder=account.contacts, items=[contact])
        return contact[0]

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
        adapter = self.backend_adapter
        account = adapter.get_account(self.openerp_user)
        return account.contacts.get(id=self.binding.external_id)

    def run_delayed_import_of_exchange_contact(self, user_id,
                                               contact_instance):
        """
            run a delayed job for the exchange record
        """
        user = self.env['res.users'].browse(user_id)
        return self.env['exchange.res.partner'].with_delay(
            priority=30).import_record(
                self.backend_record,
                user,
                contact_instance.itemid)

    def create_exchange_contact(self, fields):
        record = self._create_data(fields=fields)
        return record

    def update_existing(self, fields):
        record = self._update_data(fields=fields)
        if not record:
            return _('Nothing to export.')
        response = self._update(record)
        self.binding.with_context(
            connector_no_export=True).write(
            {'change_key': response.changekey})

    def change_key_equals(self, exchange_record):
        return (
            exchange_record.changekey == self.binding.change_key)

    def _run(self, fields=None):
        assert self.binding
        user = self.binding.user_id
        self.openerp_user = user
        if not self.binding.external_id:
            fields = None

        if not self.binding.external_id:
            # create contact in exchange
            exchange_record = self.create_exchange_contact(fields)
            self.binding.external_id = exchange_record.id
            self.binding.change_key = exchange_record.changekey
        else:
            # we have a binding
            # try to find an exchange contact with this binding ID
            exchange_record = self.get_exchange_record()
            # if record not found, create it.
            if isinstance(exchange_record, Contact):
                exchange_record = exchange_record
                # Compare change_keys of odoo binding and Exchange record found
                if self.change_key_equals(exchange_record):
                    # update contact
                    self.update_existing(fields)
                else:
                    # run a delayed import of this Exchange contact
                    # self.run_delayed_import_of_exchange_contact(
                    #     user.id,
                    #     exchange_record)
                    #  todo uncomment delay part
                    self.env['exchange.res.partner'].import_record(
                        self.backend_record,
                        user,
                        exchange_record.item_id)
            else:
                # if not self.external_id:
                #     _logger.debug('deleted --> UNLINK')
                #     rid = self.binding.openerp_id
                #     self.binding.openerp_id.with_context(
                #         connector_no_export=True).unlink()
                #     return _("Record deleted with ID %s on Exchange") % (rid)
                # else:
                # create contact in exchange and update its `external_id`
                exchange_record = self.create_exchange_contact(fields)
                self.binding.external_id = exchange_record.id
                self.binding.change_key = exchange_record.changekey
        return _("Record exported with ID %s on Exchange") % (
            self.binding.external_id)


@exchange_2010
class PartnerDisabler(ExchangeDisabler):
    _model_name = ['exchange.res.partner']

    def get_exchange_record(self, external_id):
        return self.backend_adapter.ews.GetContacts([external_id])

    def move_contact(self, contact_id, account):
        """
            move contact to "Odoo Deleted" Folder.
        """
        contact = account.calendar.get(id=contact_id)
        contact.delete()

    def _run(self, external_id, user_id):
        """ Implementation of the deletion """
        # search for correct user
        adapter = self.backend_adapter
        account = adapter.get_account(user_id)
        self.move_contact(external_id, account)

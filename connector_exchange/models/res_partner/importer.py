# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging
from odoo.addons.queue_job.exception import FailedJobError
from odoo import _
from ...backend import exchange_2010
from ...unit.importer import ExchangeImporter
from .exporter import EXCHANGE_STREET_SEPARATOR

_logger = logging.getLogger(__name__)


SIMPLE_VALUE_FIELDS = {'given_name': 'firstname',
                       'display_name': 'name',
                       'complete_name': 'lastname',
                       'surname': 'lastname',
                       'business_homepage': 'website',
                       'company_name': 'company_name',
                       'job_title': 'function',
                       }

RELATIONAL_VALUE_FIELDS = {
    'display_name': {'title': {'partner_field': 'title',
                               'relation': 'res.partner.title',
                               'search_operator': '=',
                               'relation_field': 'name'}},
    }

PARTNER_DEFAULT_VALUES = {
    'customer': True
}


@exchange_2010
class PartnerExchangeImporter(ExchangeImporter):
    _model_name = ['exchange.res.partner']

    def map_business_address(self, contact_instance):
        addr = {}
        # 1. retrieve Business address
        exchange_address = None
        if hasattr(contact_instance, 'physical_addresses'):
            if contact_instance.physical_addresses:
                for address in contact_instance.physical_addresses:
                    exchange_address = address
                    break

        if exchange_address is None:
            # no business address defined on the exchange record
            _logger.debug('No Business address found in exchange contact')
            return {}

        # 2. split address according to separator
        if exchange_address.street:
            address_parts = exchange_address.street.split(
                EXCHANGE_STREET_SEPARATOR)
            if address_parts:
                addr['street'] = address_parts.pop(0)
                for i, elem in enumerate(address_parts):
                    addr['street'+str(i+2)] = elem

        # 3. try to find an Odoo ID for 'state' and 'country_region' fields
        if exchange_address.state:
            state = self.env['res.country.state'].search(
                [('name', 'ilike', exchange_address.state)], limit=1)
            if state:
                addr['state_id'] = state.id
            else:
                _logger.debug('No "state" found in exchange contact')

        if exchange_address.country:
            country = self.env['res.country'].search(
                [('name', 'ilike', exchange_address.country)], limit=1)
            if country:
                addr['country_id'] = country.id
            else:
                _logger.debug('No "country" found in exchange contact')

        # 4. return built address dict
        addr['city'] = exchange_address.city or False
        addr['zip'] = exchange_address.zipcode or False

        return addr

    def map_exchange_instance(self, contact_instance):
        vals = {}

        for ex_field, odoo_mapping in SIMPLE_VALUE_FIELDS.iteritems():
            if isinstance(odoo_mapping, basestring):
                if hasattr(contact_instance, ex_field):
                    vals[odoo_mapping] = getattr(contact_instance, ex_field)

            elif isinstance(odoo_mapping, dict):
                exchange_obj = getattr(contact_instance, ex_field)
                for k, v in odoo_mapping.iteritems():
                    vals[v] = getattr(exchange_obj, k)
            else:
                # not supported
                raise FailedJobError(
                    _('odoo_mapping must be string or dict type')
                    )

        for ex_field, map_dict in RELATIONAL_VALUE_FIELDS.iteritems():
            # try search relation object with name = contact.ex_field.value
            # if found: fill partner's field with id found
            # else: leave this field empty and log something
            keys = map_dict.keys()
            if keys and isinstance(map_dict[keys[0]], dict):
                for k, v in map_dict.iteritems():
                    obj = self.env[map_dict[k]['relation']]
                    obj_search = obj.search(
                        [(map_dict[k]['relation_field'],
                          map_dict[k]['search_operator'], ex_field)])
                    if obj_search:
                        vals[map_dict[k]['partner_field']] = obj_search.id
            elif keys and isinstance(map_dict[keys[0]], basestring):
                obj = self.env[map_dict['relation']]
                obj_search = obj.search(
                    [(map_dict['relation_field'],
                      map_dict['search_operator'],
                      ex_field)])
                if obj_search:
                    vals[map_dict['partner_field']] = obj_search.id
                # else:
                #     if ex_field == 'company_name':
                #         vals[map_dict['partner_field']] = (
                #             self.env.ref(
                #                 'connector_exchange.res_partner_GENERIC').id)

        vals.update(self.map_email(contact_instance))
        vals.update(self.map_phones(contact_instance))
        vals.update(self.map_business_address(contact_instance))

        vals.update(change_key=contact_instance.changekey,
                    external_id=contact_instance.item_id)
        return vals

    def map_email(self, contact_instance):
        """
        Take the first email address found in the contact instance and
        fill the 'email' odoo field with the value found
        """
        email = None
        for mail_addr in contact_instance.email_addresses:
            if mail_addr.email:
                email = mail_addr.email
                break

        return {'email': email}

    def map_phones(self, contact_instance):
        """
        Mapping is done as follow:
            - phone: BusinessPhone
            - fax: BusinessFax
            - mobile: MobilePhone
        """
        vals = {'phone': None, 'mobile': None, 'fax': None}
        for phone_inst in contact_instance.phone_numbers:
            if phone_inst.label == 'BusinessPhone':
                vals['phone'] = phone_inst.phone_number
            if phone_inst.label == 'BusinessFax':
                vals['fax'] = phone_inst.phone_number
            if phone_inst.label == 'MobilePhone':
                vals['mobile'] = phone_inst.phone_number
        return vals

    def _map_data(self):
        """
            from exchange record, create an odoo dict than can be user
            both in write and create methods
        """
        contact_id = self.external_id
        adapter = self.backend_adapter
        account = adapter.get_account(self.openerp_user)
        # contact is an exchangelib.Contact instance
        contact = account.contacts.get(id=contact_id)

        # contact is an exchangelib.Contact instance
        vals = self.map_exchange_instance(contact)
        vals['external_record'] = self.external_record
        return vals

    def _update(self, binding, data, context_keys=None):
        """ Update an Odoo record """
        user = self.openerp_user
        folder = user.find_folder(self.backend_record.id,
                                  create=False,
                                  folder_type='create')
        context_keys = {
            '__changeset_rules_source_model': 'res.users.backend.folder',
            '__changeset_rules_source_id': folder.id,
        }
        return super(PartnerExchangeImporter, self)._update(
            binding, data, context_keys=context_keys
        )

    def _create(self, data, context_keys=None):
        user = self.openerp_user
        folder = user.find_folder(self.backend_record.id,
                                  create=False,
                                  folder_type='create')
        context_keys = {
            '__changeset_rules_source_model': 'res.users.backend.folder',
            '__changeset_rules_source_id': folder.id,
        }
        return super(PartnerExchangeImporter, self)._create(
            data, context_keys=context_keys
        )

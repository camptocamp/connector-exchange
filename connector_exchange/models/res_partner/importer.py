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

try:
    from pyews.ews.data import (EmailKey,
                                PhoneKey,
                                PhysicalAddressType
                                )
except (ImportError, IOError) as err:
    _logger.debug(err)


SIMPLE_VALUE_FIELDS = {'complete_name': {'given_name': 'firstname',
                                         'surname': 'lastname'},
                       'business_home_page': 'website',
                       'company_name': 'company_name',
                       'job_title': 'function',
                       }

RELATIONAL_VALUE_FIELDS = {
    'complete_name': {'title': {'partner_field': 'title',
                                'relation': 'res.partner.title',
                                'search_operator': '=',
                                'relation_field': 'name'}},
    }

MULTIPLE_VALUE_FIELDS = {
    'emails': {EmailKey.Email1: 'email'},
    'phones': {PhoneKey.PrimaryPhone: 'phone',
               PhoneKey.BusinessFax: 'fax',
               PhoneKey.MobilePhone: 'mobile',
               },
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
        for address in contact_instance.physical_addresses.entries:
            if address.attrib['Key'] == PhysicalAddressType.Business:
                exchange_address = address
                break

        if exchange_address is None:
            # no business address defined on the exchange record
            _logger.debug('No Business address found in exchange contact')
            return {}

        # 2. split address according to separator
        if exchange_address.street.value:
            address_parts = exchange_address.street.value.split(
                EXCHANGE_STREET_SEPARATOR)
            if address_parts:
                addr['street'] = address_parts.pop(0)
                for i, elem in enumerate(address_parts):
                    addr['street'+str(i+1)] = elem

        # 3. try to find an Odoo ID for 'state' and 'country_region' fields
        if exchange_address.state.value:
            state = self.env['res.country.state'].search(
                [('name', '=', exchange_address.state.value)])
            if state:
                addr['state_id'] = state.id
            else:
                _logger.debug('No "state" found in exchange contact')

        if exchange_address.country_region.value:
            country = self.env['res.country'].search(
                [('name', '=', exchange_address.country_region.value)])
            if country:
                addr['country'] = country.id
            else:
                _logger.debug('No "country" found in exchange contact')

        # 4. return built address dict
        addr['city'] = exchange_address.city.value or False
        addr['zip'] = exchange_address.postal_code.value or False

        return addr

    def map_exchange_instance(self, contact_instance):
        vals = {}

        for ex_field, odoo_mapping in SIMPLE_VALUE_FIELDS.iteritems():
            if isinstance(odoo_mapping, basestring):
                vals[odoo_mapping] = getattr(contact_instance, ex_field).value
            elif isinstance(odoo_mapping, dict):
                exchange_obj = getattr(contact_instance, ex_field)
                for k, v in odoo_mapping.iteritems():
                    vals[v] = getattr(exchange_obj, k).value
            else:
                # not supported
                raise FailedJobError(
                    _('odoo_mapping must be string or dict type')
                    )

        for ex_field, map_dict in RELATIONAL_VALUE_FIELDS.iteritems():
            # try search relation object with name = contact.ex_field.value
            # if found: fill partner's field with id found
            # else: leave this field empty and log something
            exchange_field = getattr(contact_instance, ex_field)
            keys = map_dict.keys()
            if keys and isinstance(map_dict[keys[0]], dict):
                for k, v in map_dict.iteritems():
                    obj = self.env[map_dict[k]['relation']]
                    obj_search = obj.search(
                        [(map_dict[k]['relation_field'],
                          map_dict[k]['search_operator'],
                          getattr(exchange_field, k).value)])
                    if obj_search:
                        vals[map_dict[k]['partner_field']] = obj_search.id
            elif keys and isinstance(map_dict[keys[0]], basestring):
                obj = self.env[map_dict['relation']]
                obj_search = obj.search(
                    [(map_dict['relation_field'],
                      map_dict['search_operator'],
                      exchange_field.value)])
                if obj_search:
                    vals[map_dict['partner_field']] = obj_search.id
                # else:
                #     if ex_field == 'company_name':
                #         vals[map_dict['partner_field']] = (
                #             self.env.ref(
                #                 'connector_exchange.res_partner_GENERIC').id)

        for ex_field, map_dict in MULTIPLE_VALUE_FIELDS.iteritems():
            exchange_field = getattr(contact_instance, ex_field)
            for entry in exchange_field.entries:
                for k, v in map_dict.iteritems():
                    if entry.attrib['Key'] == k:
                        vals[v] = entry.value

        vals.update(self.map_business_address(contact_instance))

        vals.update(change_key=contact_instance.change_key.value,
                    external_id=contact_instance.itemid.value)
        return vals

    def _map_data(self):
        """
            from exchange record, create an odoo dict than can be user
            both in write and create methods
        """
        contact_id = self.external_id
        adapter = self.backend_adapter
        ews = adapter.ews
        user = self.openerp_user

        adapter.set_primary_smtp_address(user)

        # contact is an pyews.ews.contact.Contact instance
        contact = ews.GetContacts([contact_id])[0]

        vals = self.map_exchange_instance(contact)

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

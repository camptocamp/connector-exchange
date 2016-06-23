# -*- coding: utf-8 -*-
#
#
#    Authors: Guewen Baconnier, Damien Crier
#    Copyright 2015-2016 Camptocamp SA
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
import mock

from openerp.addons.connector_exchange.unit.importer import (
    import_record,
)
from openerp.addons.connector_exchange.unit.exporter import (
    export_record,
    export_delete_record,
)

from .common import (
    my_vcr,
    ExchangeBackendTransactionCase,
)


class TestExchangeBackendSyncExport(ExchangeBackendTransactionCase):

    def test_batch_export_partner_contact(self):
        import_job_path = ('openerp.addons.connector_exchange.consumer.'
                           'export_record')
        cassette_name = 'test_batch_export_partner_batch'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path):

            self.exchange_backend.export_contact_partners(self.sync_session)

            # import record jobs were properly delayed
            self.assertFalse(len(cassette.requests))


class TestExchangeBackendSyncImport(ExchangeBackendTransactionCase):

    def setUp(self):
        super(TestExchangeBackendSyncImport, self).setUp()
        import_job_path = ('openerp.addons.connector_exchange.consumer.'
                           'export_record')
        cassette_name = 'test_export_contact'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path):
            self.create_exchange_binding()
            export_record(self.connector_session,
                          'exchange.res.partner',
                          self.binding.id)
            self.assertTrue(self.binding.external_id)
            self.assertTrue(self.binding.change_key)
            self.assertTrue(len(cassette.requests))

    def create_exchange_binding(self):
        self.binding = self.created_user.exchange_bind_ids.create(
            {'backend_id': self.exchange_backend.id,
             'user_id': self.created_user.user_id.id,
             'openerp_id': self.created_user.id
             }
        )

    def test_batch_import_partner_batch(self):
        import_job_path = ('openerp.addons.connector_exchange.models.'
                           'exchange_backend.common.import_record')
        cassette_name = 'test_batch_import_partner_batch'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path):

            self.exchange_backend.import_contact_partners(self.sync_session)

            # import record jobs were properly delayed
            self.assertTrue(len(cassette.requests))


class TestExchangeBackendSyncContactRecord(ExchangeBackendTransactionCase):

    def setUp(self):
        super(TestExchangeBackendSyncContactRecord, self).setUp()

    def create_exchange_binding(self):
        self.binding = self.created_user.exchange_bind_ids.create(
            {'backend_id': self.exchange_backend.id,
             'user_id': self.created_user.user_id.id,
             'openerp_id': self.created_user.id}
            )

    def test_export_contact(self):
        import_job_path = ('openerp.addons.connector_exchange.consumer.'
                           'export_record')
        cassette_name = 'test_export_contact'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path):
            self.create_exchange_binding()
            export_record(self.connector_session,
                          'exchange.res.partner',
                          self.binding.id)
            self.assertTrue(self.binding.external_id)
            self.assertTrue(self.binding.change_key)

            # self.binding.zip = False
            # export_record(self.connector_session,
            #               'exchange.res.partner',
            #               self.binding.id,
            #               fields=['zip'])

            # self.binding.phone = False
            # export_record(self.connector_session,
            #               'exchange.res.partner',
            #               self.binding.id,
            #               fields=['phone'])

            # self.binding.email = "aaa@bbb.ccc"
            # # self.binding.email = False
            # export_record(self.connector_session,
            #               'exchange.res.partner',
            #               self.binding.id,
            #               fields=['email'])

            # self.binding.zip = '1337'
            # export_record(self.connector_session,
            #               'exchange.res.partner',
            #               self.binding.id,
            #               fields=['zip'])

            self.binding.write(
                {"zip": '8888', 'city': 'City',
                 'email': 'exchange@exchange.com',
                 'phone': '88586586', 'lastname': 'TITI'})

            # apply all 'applicable' changeset rules
            # (see demo file  'in partner_changeset' module)
            self.binding.changeset_ids.mapped('change_ids').apply()
            export_record(self.connector_session,
                          'exchange.res.partner',
                          self.binding.id,
                          fields=['zip', 'city', 'email', 'phone', 'lastname'])

            # email won't be changed because of partner changeset rules ...
            self.assertTrue(self.binding.change_key)
            self.assertTrue(len(cassette.requests))


class TestExchangeBackendSyncContactRecordImport(
        ExchangeBackendTransactionCase):

    def setUp(self):
        super(TestExchangeBackendSyncContactRecordImport, self).setUp()

    def create_exchange_binding(self):
        self.binding = self.created_user.exchange_bind_ids.create(
            {'backend_id': self.exchange_backend.id,
             'user_id': self.created_user.user_id.id,
             'openerp_id': self.created_user.id}
            )

    def test_import_contact(self):
        export_job_path = ('openerp.addons.connector_exchange.consumer.'
                           'export_record')
        import_job_path = ('openerp.addons.connector_exchange.models.'
                           'res_partner.exporter.import_record')
        cassette_name = 'test_import_contact'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path), \
                mock.patch(export_job_path):
            self.create_exchange_binding()
            export_record(self.connector_session,
                          'exchange.res.partner',
                          self.binding.id)
            self.assertTrue(self.binding.external_id)
            self.assertTrue(self.binding.change_key)

            import_record(self.connector_session,
                          'exchange.res.partner',
                          self.exchange_backend.id,
                          self.created_user.user_id.id,
                          self.binding.external_id
                          )
            self.assertTrue(len(cassette.requests))


class TestExchangeBackendSyncContactRecordDelete(
        ExchangeBackendTransactionCase):

    def setUp(self):
        super(TestExchangeBackendSyncContactRecordDelete, self).setUp()

    def create_exchange_binding(self):
        self.binding = self.created_user.exchange_bind_ids.create(
            {'backend_id': self.exchange_backend.id,
             'user_id': self.created_user.user_id.id,
             'openerp_id': self.created_user.id}
            )

    def test_delete_contact(self):
        import_job_path = ('openerp.addons.connector_exchange.consumer.'
                           'export_record')
        export_job_path = ('openerp.addons.connector_exchange.consumer.'
                           'export_delete_record')
        cassette_name = 'test_delete_contact'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path), \
                mock.patch(export_job_path):
            self.create_exchange_binding()
            export_record(self.connector_session,
                          'exchange.res.partner',
                          self.binding.id)
            self.assertTrue(self.binding.external_id)
            self.assertTrue(self.binding.change_key)

            export_delete_record(self.connector_session,
                                 'exchange.res.partner',
                                 self.exchange_backend.id,
                                 self.binding.external_id
                                 )
            self.assertTrue(len(cassette.requests))

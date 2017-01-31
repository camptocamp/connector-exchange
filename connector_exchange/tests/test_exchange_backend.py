# -*- coding: utf-8 -*-
# Authors: Guewen Baconnier, Damien Crier
# Copyright 2015-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import mock

from .common import (
    my_vcr,
    ExchangeBackendTransactionCase,
)


class TestExchangeBackendSyncExport(ExchangeBackendTransactionCase):

    def test_batch_export_partner_contact(self):
        import_job_path = ('odoo.addons.connector_exchange.connector.'
                           'ExchangeBinding.export_record')
        cassette_name = 'test_batch_export_partner_batch'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path):

            self.exchange_backend.export_contact_partners()

            # import record jobs were properly delayed
            self.assertFalse(len(cassette.requests))


class TestExchangeBackendSyncImport(ExchangeBackendTransactionCase):

    def setUp(self):
        super(TestExchangeBackendSyncImport, self).setUp()
        import_job_path = ('odoo.addons.connector_exchange.connector.'
                           'ExchangeBinding.export_record')
        cassette_name = 'test_export_contact'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path):
            self.create_exchange_binding()
            self.binding.export_record()
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
        import_job_path = ('odoo.addons.connector_exchange.connector.'
                           'ExchangeBinding.import_record')
        cassette_name = 'test_batch_import_partner_batch'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path):

            self.exchange_backend.import_contact_partners()

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
        import_job_path = ('odoo.addons.connector_exchange.connector.'
                           'ExchangeBinding.export_record')
        cassette_name = 'test_export_contact'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path):
            self.create_exchange_binding()
            self.binding.export_record()
            self.assertTrue(self.binding.external_id)
            self.assertTrue(self.binding.change_key)

            # self.binding.zip = False
            # export_record(self.env,
            #               'exchange.res.partner',
            #               self.binding.id,
            #               fields=['zip'])

            # self.binding.phone = False
            # export_record(self.env,
            #               'exchange.res.partner',
            #               self.binding.id,
            #               fields=['phone'])

            # self.binding.email = "aaa@bbb.ccc"
            # # self.binding.email = False
            # export_record(self.env,
            #               'exchange.res.partner',
            #               self.binding.id,
            #               fields=['email'])

            # self.binding.zip = '1337'
            # export_record(self.env,
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
            self.binding.export_record(
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
        export_job_path = ('odoo.addons.connector_exchange.connector.'
                           'ExchangeBinding.export_record')
        import_job_path = ('odoo.addons.connector_exchange.connector.'
                           'ExchangeBinding.import_record')
        cassette_name = 'test_import_contact'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path), \
                mock.patch(export_job_path):
            self.create_exchange_binding()
            self.binding.export_record()
            self.assertTrue(self.binding.external_id)
            self.assertTrue(self.binding.change_key)

            self.env['exchange.res.partner'].import_record(
                self.exchange_backend,
                self.created_user.user_id,
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
        import_job_path = ('odoo.addons.connector_exchange.connector.'
                           'ExchangeBinding.export_record')
        export_job_path = ('odoo.addons.connector_exchange.connector.'
                           'ExchangeBinding.export_delete_record')
        cassette_name = 'test_delete_contact'

        with my_vcr.use_cassette(cassette_name,
                                 match_on=['method', 'query']) as cassette, \
                mock.patch(import_job_path), \
                mock.patch(export_job_path):
            self.create_exchange_binding()
            self.binding.export_record()
            self.assertTrue(self.binding.external_id)
            self.assertTrue(self.binding.change_key)

            self.binding.export_delete_record(
                self.binding.external_id,
                self.env.user
            )
            self.assertTrue(len(cassette.requests))

# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from datetime import datetime
from odoo import models, fields, api


class ConnectorSyncSession(models.Model):
    _inherit = 'connector.sync.session'

    sync_exchange_import = fields.Boolean(string='Sync Exchange Import',
                                          default=True)
    sync_exchange_export = fields.Boolean(string='Sync Exchange Export',
                                          default=True)
    sync_calendar_exchange_import = fields.Boolean(
        string='Sync Calendar Exchange Import',
        default=True)
    sync_calendar_exchange_export = fields.Boolean(
        string='Sync Calendar Exchange Export',
        default=True)
    exchange_backend_ids = fields.Many2many(
        comodel_name='exchange.backend',
        string='Backends',
        default=lambda self: self._default_exchange_backend_ids(),
    )

    @api.model
    @api.returns('exchange.backend')
    def _default_exchange_backend_ids(self):
        return self.env['exchange.backend'].search([])

    @api.multi
    def exchange_export(self):
        """ Export from Odoo to Exchange
        Called only when 'sync_exchange_export' is True.
        """
        self.ensure_one()
        for exchange_backend in self.exchange_backend_ids:
            import_start_time = datetime.now()
            exchange_backend.export_contact_partners(self)
            next_time = fields.Datetime.to_string(import_start_time)
            exchange_backend.write({'last_export_date': next_time})
        return True

    @api.multi
    def exchange_import(self):
        """ Import from Exchange
        Called only when 'sync_exchange_import' is True.
        """
        self.ensure_one()
        for exchange_backend in self.exchange_backend_ids:
            import_start_time = datetime.now()
            exchange_backend.import_contact_partners(self)
            next_time = fields.Datetime.to_string(import_start_time)
            exchange_backend.write({'last_import_date': next_time})
        return True

    @api.multi
    def exchange_calendar_import(self):
        """

        """
        self.ensure_one()
        for exchange_backend in self.exchange_backend_ids:
            # import_start_time = datetime.now()
            exchange_backend.import_user_calendar(self)
            # next_time = fields.Datetime.to_string(import_start_time)
            # exchange_backend.write({'last_import_date': next_time})
        return True

    @api.multi
    def exchange_calendar_export(self):
        """

        """
        self.ensure_one()
        for exchange_backend in self.exchange_backend_ids:
            # import_start_time = datetime.now()
            exchange_backend.export_user_calendar(self)
            # next_time = fields.Datetime.to_string(import_start_time)
            # exchange_backend.write({'last_import_date': next_time})
        return True

    @api.multi
    def _synchronize(self):
        """ Logic for one synchronization session.  """
        super(ConnectorSyncSession, self)._synchronize()
        if self.sync_exchange_import:
            self.exchange_import()

        if self.sync_exchange_export:
            self.exchange_export()

        if self.sync_calendar_exchange_import:
            self.exchange_calendar_import()

        if self.sync_calendar_exchange_export:
            self.exchange_calendar_export()

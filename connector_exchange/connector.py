# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api
from odoo.addons.queue_job.job import job

from .unit.exporter import ExchangeExporter, ExchangeDisabler
from .unit.importer import ExchangeImporter


class ExchangeBinding(models.AbstractModel):
    _name = 'exchange.binding'
    _inherit = 'external.binding'
    _description = 'Exchange Binding (abstract)'

    backend_id = fields.Many2one(
        comodel_name='exchange.backend',
        string='Exchange Backend',
        required=True,
        ondelete='restrict'
    )
    external_id = fields.Char(string='ID in Exchange',
                              index=True)
    user_id = fields.Many2one(comodel_name='res.users',
                              string='User',
                              required=True,
                              ondelete='cascade')
    change_key = fields.Char("Change Key")
    current_folder = fields.Char(compute='_get_folder_create_id',
                                 readonly=True)
    delete_folder = fields.Char(compute='_get_folder_delete_id',
                                readonly=True)
    contact_folder = fields.Char(compute='_get_folder_contact_id',
                                 readonly=True)
    calendar_folder = fields.Char(compute='_get_folder_calendar_id',
                                  readonly=True)

    _sql_constraints = [('exchange_uniq',
                         'unique(backend_id, external_id, user_id)',
                         'A binding already exists with the same '
                         'Exchange ID for the same record.')]

    @api.depends()
    def _get_folder_create_id(self):
        for binding in self:
            binding.current_folder = self.env.user.find_folder(
                binding.backend_id.id,
                create=False,
                folder_type='create',
            )

    @api.depends()
    def _get_folder_delete_id(self):
        for binding in self:
            binding.delete_folder = self.env.user.find_folder(
                binding.backend_id.id,
                create=False,
                folder_type='delete',
            )

    @api.depends()
    def _get_folder_contact_id(self):
        for binding in self:
            binding.contact_folder = self.env.user.find_folder(
                binding.backend_id.id,
                create=False,
                folder_type='contact',
            )

    @api.depends()
    def _get_folder_calendar_id(self):
        for binding in self:
            binding.calendar_folder = self.env.user.find_folder(
                binding.backend_id.id,
                create=False,
                folder_type='calendar',
            ).folder_id

    @api.multi
    def get_backend(self):
        self.ensure_one()
        return self.backend_id

    @job
    def import_record(self, backend, user, item_id):
        """ Import a record from Exchange """
        with backend.get_environment(self._name) as connector_env:
            importer = connector_env.get_connector_unit(ExchangeImporter)
            importer.run(item_id, user)

    @job
    def export_record(self, fields=None):
        """ Export a record from Exchange """
        self.ensure_one()
        with self.backend_id.get_environment(self._name) as connector_env:
            exporter = connector_env.get_connector_unit(ExchangeExporter)
            return exporter.run(self, fields=fields)

    @job
    def export_delete_record(self, external_id, user):
        """ Delete a record on Exchange """
        self.ensure_one()
        with user.default_backend.get_environment(self._name) as connector_env:
            deleter = connector_env.get_connector_unit(ExchangeDisabler)
            return deleter.run(external_id, user)

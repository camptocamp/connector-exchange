# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api


def add_checkpoint(env, model_name, record_id,
                   backend_model_name, backend_id):
    checkpoint_model = env['connector.checkpoint']
    return checkpoint_model.create_from_name(model_name, record_id,
                                             backend_model_name, backend_id)


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
                              select=True)
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

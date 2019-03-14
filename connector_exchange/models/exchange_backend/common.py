# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import pytz
import logging
from odoo import models, fields, api

from odoo.addons.connector.connector import ConnectorEnvironment

from ..res_partner.adapter import PartnerBackendAdapter
from ..calendar_event.adapter import EventBackendAdapter

from exchangelib import EWSDateTime, EWSTimeZone
_logger = logging.getLogger(__name__)

from contextlib import contextmanager


class ExchangeBackend(models.Model):
    _name = 'exchange.backend'
    _description = 'Exchange Backend'
    _inherit = 'connector.backend'

    _backend_type = 'exchange'

    @api.model
    def select_versions(self):
        """ Available versions

        Can be inherited to add custom versions.
        """
        return [('exchange_2010', 'Exchange 2010')]

    # todo remove version, no needed in exchangelib
    version = fields.Selection(selection='select_versions', required=True)
    username = fields.Char(
        string='Username',
        required=True,
        help="Webservice user",
    )
    password = fields.Char(
        string='Password',
        required=True,
        help="Webservice password",
    )
    disable_autodiscover = fields.Boolean(default=False)
    location = fields.Char(
        required=True,
        help="Address of Exchange WSDL",
    )
    last_import_date = fields.Datetime(string='Last Import Date')
    last_export_date = fields.Datetime(string='Last Export Date')
    backend_folder_ids = fields.One2many('res.users.backend.folder',
                                         'backend_id',
                                         string="Folders")
    contact_bind_ids = fields.One2many('exchange.res.partner', 'backend_id',
                                       string="Contact bindings")

    @api.model
    def cron_export_contact_partner(self):
        for backend in self.search([]):
            backend.export_contact_partners()

    @api.model
    def cron_import_contact_partner(self):
        for backend in self.search([]):
            backend.import_contact_partners()

    @api.multi
    def export_contact_partners(self):
        """ Export partners to exchange backend """
        self.ensure_one()
        _logger.debug('export contact partners')
        users = self.env['res.users'].search([('exchange_synch', '=', True)])
        for backend in self:
            for user in users:
                # this will trigger an export for these contacts
                user.exchange_contact_ids.try_autobind(user, backend)
        return True

    @api.multi
    def import_contact_partners(self):
        """ Import partners from exchange backend """
        _logger.debug('import contact partners')
        users = self.env['res.users'].search([('exchange_synch', '=', True)])
        for backend in self:
            for user in users:
                # find folder for this user. If not exists do not try to import
                folder = user.find_folder(backend.id, create=True,
                                          default_name="Contacts",
                                          folder_type='contact')
                if not folder:
                    continue

                # get all contacts for this user
                model_name = 'exchange.res.partner'
                with backend.get_environment(model_name) as connector_env:
                    adapter = connector_env.get_connector_unit(
                        PartnerBackendAdapter)
                account = adapter.get_account(user)
                contact_folder = account.contacts
                # for each contact found, run import_record
                for exchange_contact in contact_folder.all():
                    odoo_categ = False
                    if not exchange_contact.categories:
                        continue
                    for categ in exchange_contact.categories:
                        if categ == 'Odoo':
                            odoo_categ = True
                            break
                    if odoo_categ:
                        self.env['exchange.res.partner'].with_delay(
                            priority=30).import_record(
                                backend,
                                user,
                                exchange_contact.item_id)
        return True

    @api.model
    def cron_export_calendar(self):
        for backend in self.search([]):
            backend.export_user_calendar()

    @api.model
    def cron_import_calendar(self):
        for backend in self.search([]):
            backend.import_user_calendar()

    @api.multi
    def import_user_calendar(self):
        """ Import events from exchange backend """
        _logger.debug('import events')
        users = self.env['res.users'].search(
            [('exchange_calendar_sync', '=', True)])

        for backend in self:
            for user in users:
                start_date = user.last_calendar_sync_date
                exchange_start_date = '%sT00:00:00Z' % start_date

                imported_events = []
                existing_events = user.exchange_calendar_ids.mapped(
                    'exchange_bind_ids')
                existing_events = existing_events.filtered(
                    (lambda u: lambda a: a.user_id == u)(user)
                )
                existing_events = existing_events.mapped('external_id')

                # find folder for this user. If not exists, create one
                folder = user.find_folder(backend.id, create=True,
                                          default_name="Calendar",
                                          folder_type='calendar')
                if not folder:
                    continue
                tz = EWSTimeZone.localzone()
                # get all contacts for this user
                model_name = 'exchange.calendar.event'
                with backend.get_environment(model_name) as connector_env:
                    adapter = connector_env.get_connector_unit(
                        EventBackendAdapter)
                account = adapter.get_account(user)
                calendar_folder = account.calendar
                exchange_events = calendar_folder.filter(start__gt=(
                    tz.localize(EWSDateTime(2017, 1, 1))
                ))  # Filter by a date range
                # for each event found, run import_record if sensitivity
                # is not "Private" or "Personnal"
                # and if categories contains Odoo
                for exchange_event in exchange_events:
                    sensitivity = exchange_event.sensitivity
                    odoo_categ = False
                    if not exchange_event.categories:
                        continue
                    for categ in exchange_event.categories:
                        if categ == 'Odoo':
                            odoo_categ = True
                            break
                    if odoo_categ and sensitivity not in \
                            ['Private', 'Personal']:
                        self.env['exchange.calendar.event'].with_delay(
                            ).import_record(
                                backend,
                                user,
                                exchange_event.item_id)
                        imported_events.append(exchange_event.item_id)

                to_delete = list(set(existing_events) - set(imported_events))
                cal_ex_obj = self.env['exchange.calendar.event']
                to_delete_ids = cal_ex_obj.search(
                    [('external_id', 'in', to_delete),
                     ('user_id', '=', user.id)]
                )
                calendar_event_ids = to_delete_ids.mapped('openerp_id')
                calendar_event_ids.with_context(
                    connector_no_export=True).unlink()
                user.last_calendar_sync_date = fields.Date.today()
        return True

    @api.multi
    def export_user_calendar(self):
        self.ensure_one()
        _logger.debug('export calendar events')
        users = self.env['res.users'].search(
            [('exchange_calendar_sync', '=', True)])
        for backend in self:
            for user in users:
                # this will trigger an export for these contacts
                user.exchange_calendar_ids.try_autobind(user, backend)
        return True

    @contextmanager
    @api.multi
    def get_environment(self, model_name):
        """ Create an environment to work with.  """
        self.ensure_one()
        yield ConnectorEnvironment(self, model_name)

# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import logging

from pyews.ews.data import FolderClass, SensitivityType

from openerp import models, fields, api
from openerp.addons.connector.session import ConnectorSession

from ...unit.importer import import_record
from ...unit.environment import get_environment
from ..res_partner.adapter import PartnerBackendAdapter
from ..calendar_event.adapter import EventBackendAdapter

_logger = logging.getLogger(__name__)


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

    version = fields.Selection(selection='select_versions', required=True)
    certificate_location = fields.Char(
        required=True,
        default="/opt/exchange_ws/certificates/")
    location = fields.Char(
        string='Location',
        required=True,
        help="Address of Exchange WSDL",
    )
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
        session = ConnectorSession.from_env(self.env)
        users = self.env['res.users'].search([('exchange_synch', '=', True)])
        for backend in self:
            for user in users:
                # find folder for this user. If not exists do not try to import
                folder = user.find_folder(backend.id, create=False)
                if not folder:
                    continue

                # get all contacts for this user
                env = get_environment(session,
                                      'exchange.res.partner',
                                      backend.id)
                adapter = env.get_connector_unit(PartnerBackendAdapter)
                subst = {
                    'u_login': user.login,
                    'exchange_suffix': user.company_id.exchange_suffix or '',
                    }

                adapter.ews.primary_smtp_address = (
                    str("%(u_login)s%(exchange_suffix)s" % subst)
                    )
                adapter.ews.get_root_folder()
                exchange_folder = (
                    adapter.ews.root_folder.FindFolderByDisplayName(
                        str(folder.name),
                        types=[FolderClass.Contacts],
                        recursive=True))
                if exchange_folder:
                    exchange_folder = exchange_folder[0]
                else:
                    continue

                exchange_contacts = adapter.ews.FindItems(exchange_folder,
                                                          ids_only=True)
                # for each contact found, run import_record
                for exchange_contact in exchange_contacts:
                    import_record.delay(session,
                                        'exchange.res.partner',
                                        backend.id,
                                        user.id,
                                        exchange_contact.itemid.value,
                                        priority=30)
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
        session = ConnectorSession.from_env(self.env)
        users = self.env['res.users'].search(
            [('exchange_calendar_sync', '=', True)])
        for backend in self:
            for user in users:
                imported_events = []
                existing_events = user.exchange_calendar_ids.mapped(
                    'exchange_bind_ids')
                existing_events = existing_events.filtered(
                    (lambda u: lambda a: a.user_id == u)(user)
                )
                existing_events = existing_events.mapped('external_id')

                # find folder for this user. If not exists, create one
                folder = user.find_folder(backend.id, create=True,
                                          default_name='Odoo',
                                          folder_type='calendar')
                if not folder:
                    continue

                # get all contacts for this user
                env = get_environment(session,
                                      'exchange.calendar.event',
                                      backend.id)
                adapter = env.get_connector_unit(EventBackendAdapter)
                subst = {
                    'u_login': user.login,
                    'exchange_suffix': user.company_id.exchange_suffix or '',
                    }

                adapter.ews.primary_smtp_address = (
                    str("%(u_login)s%(exchange_suffix)s" % subst)
                    )
                adapter.ews.get_root_folder()
                exchange_folder = (
                    adapter.ews.root_folder.FindFolderByDisplayName(
                        str(folder.name),
                        types=[FolderClass.Calendars],
                        recursive=True))
                if exchange_folder:
                    exchange_folder = exchange_folder[0]
                else:
                    continue

                exchange_events = adapter.ews.FindCalendarItems(
                    exchange_folder,
                    ids_only=True)
                # for each event found, run import_record if sensitivity
                # is not "Private"
                for exchange_event in exchange_events:
                    sensitivity = exchange_event.sensitivity
                    if (sensitivity.value != SensitivityType.Private and
                            sensitivity.value != SensitivityType.Personal):
                        import_record.delay(session,
                                            'exchange.calendar.event',
                                            backend.id,
                                            user.id,
                                            exchange_event.itemid.value,
                                            priority=30)
                        imported_events.append(exchange_event.itemid.value)

                to_delete = list(set(existing_events) - set(imported_events))
                cal_ex_obj = self.env['exchange.calendar.event']
                to_delete_ids = cal_ex_obj.search(
                    [('external_id', 'in', to_delete),
                     ('user_id', '=', user.id)]
                )
                calendar_event_ids = to_delete_ids.mapped('openerp_id')
                calendar_event_ids.unlink()
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

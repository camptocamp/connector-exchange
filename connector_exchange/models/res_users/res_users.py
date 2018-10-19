# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from odoo import models, fields, api, _


_logger = logging.getLogger(__name__)
try:
    from pyews.pyews import ExchangeService
    from pyews.soap import SoapClient
    from pyews.ews.data import WellKnownFolderName
except (ImportError, IOError) as err:
    _logger.debug(err)


class ResCompany(models.Model):
    _inherit = 'res.company'

    exchange_suffix = fields.Char(
        help="Will be appended to login to generate "
             "PrincipalName for Exchange Impersonation",
        default='@company.com'
        )


class ResUserBackendFolder(models.Model):
    _name = 'res.users.backend.folder'

    name = fields.Char(required=True)
    user_id = fields.Many2one(comodel_name='res.users',
                              string='User',
                              required=True)
    backend_id = fields.Many2one(comodel_name='exchange.backend',
                                 string='Backend',
                                 required=True)
    folder_id = fields.Char('Folder Exchange Id')
    folder_type = fields.Selection([('create', 'Create'),
                                    ('delete', 'Delete'),
                                    ('contact', 'Contact'),
                                    ('calendar', 'Calendar')],
                                   default='create')

    _sql_constraints = [
        ('unique_folder', "unique(backend_id, user_id, folder_type)",
         _('Only one folder by user, by backend and by folder type')),
    ]


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    @api.returns('exchange.backend')
    def _get_default_backend(self):
        return self.env['exchange.backend'].search([], limit=1)

    exchange_synch = fields.Boolean('Synch Contacts with Exchange',
                                    default=False)
    exchange_calendar_sync = fields.Boolean('Synch Calendars with Exchange',
                                            default=False)
    exchange_contact_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Exchange partners',
        groups='connector.group_connector_manager',
        compute='_get_exchange_contacts'
        )
    exchange_calendar_ids = fields.Many2many(
        comodel_name='calendar.event',
        string='Exchange Events',
        groups='connector.group_connector_manager',
        compute='_get_exchange_calendar_events'
        )
    backend_folder_ids = fields.One2many('res.users.backend.folder', 'user_id',
                                         string="Folders")
    default_backend = fields.Many2one(comodel_name='exchange.backend',
                                      default=_get_default_backend)

    @api.onchange('exchange_synch', 'exchange_calendar_sync')
    def create_odoo_category(self):
        """
        Try to create odoo category on Exchange.
        If it already exists, do nothing
        """
        # find exchange backend
        ex_backends = self.default_backend
        if ex_backends:
            back = ex_backends
            ews = ExchangeService()
            ews.soap = SoapClient(back.location,
                                  back.username,
                                  back.password,
                                  back.certificate_location)
            subst = {
                'u_login': self.login,
                'exchange_suffix': self.company_id.exchange_suffix or '',
            }
            ews.primary_smtp_address = (
                str("%(u_login)s%(exchange_suffix)s" % subst)
            )
            # envoyer requete
            ews.UpdateCategoryList('Odoo', 23, WellKnownFolderName.Calendar)

    @api.multi
    def find_folder(self, backend_id, create=True,
                    default_name='Contacts',
                    folder_type='create',
                    user=None):
        self.ensure_one()
        if user is None:
            user = self
        folders = user.backend_folder_ids.filtered(
            lambda a: a.backend_id.id == backend_id and
            a.folder_type == folder_type and
            a.user_id == user
            )

        if not folders and create:
            return self.backend_folder_ids.create({'user_id': self.id,
                                                   'backend_id': backend_id,
                                                   'name': default_name,
                                                   'folder_type': folder_type})
        elif not folders and not create:
            return self.env['res.users.backend.folder']
        else:
            return folders[0]

    @api.depends()
    def _get_exchange_contacts(self):
        for user in self:
            user.exchange_contact_ids = user.find_exchange_contacts()

    @api.depends()
    def _get_exchange_calendar_events(self):
        for user in self:
            user.exchange_calendar_ids = user.find_exchange_calendar_events()

    @api.multi
    @api.returns('res.partner')
    def _get_contacts(self):
        partners = self.env['res.partner']
        res = partners.search([('user_id', '=', self.id),
                               ('is_company', '=', False)])

        leads_partners = self.env['crm.lead'].search(
            [('user_id', '=', self.id)]
            ).mapped('partner_id')
        res |= leads_partners

        # Following
        # ---------
        mail_follow_obj = self.env['mail.followers']
        mail_followers = mail_follow_obj.search(
            [('res_model', '=', 'res.partner'),
             ('partner_id', '=', self.partner_id.id)]
            )
        mail_followers_res_ids = mail_followers.mapped('res_id')
        followed_partners = partners.browse(mail_followers_res_ids).exists()
        res |= followed_partners

        return res

    @api.multi
    @api.returns('res.partner')
    def find_exchange_contacts(self):
        """ Retrieve all contacts linked to the user.
        Retrieve 3 categories of contacts :
            - Direct:
                salesperson,
                contacts from sale.order (by installing
                    'connector_exchange_sale' module)
                contacts from purchase.order (by installing
                    'connector_exchange_purchase' module)
                crm.lead
            - Following:
                contacts the user follows
            - Related
                contacts who the user had interacted with in the past
        Returns a set of res.partners
        """

        contacts = self._get_contacts()

        # Related
        # -------
        # @TODO : search for partners invovlved in convesations in mail_thread
        #         refer to def message_post() for  fields to search
        return contacts.filtered(lambda r: not r.is_company)

    @api.multi
    @api.returns('calendar.event')
    def find_exchange_calendar_events(self):
        return self.env['calendar.event'].search(
            [('user_id', '=', self.id)])

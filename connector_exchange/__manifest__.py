# -*- coding: utf-8 -*-
# Author: Guewen Baconnier, Damien Crier
# Copyright 2015-2017 Camptocamp SA
# Author: Nicolas Clavier
# Copyright 2014 HighCo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{'name': 'Connector Exchange',
 'version': '10.0.1.0.0',
 'author': "Camptocamp, Nicolas Clavier, Odoo Community Association (OCA)",
 'website': "http://www.camptocamp.com",
 'summary': "Microsoft Exchange Connector",
 'images': [],
 'license': 'AGPL-3',
 'category': 'Connector',
 'depends': ['base',
             'calendar',
             'connector',
             'partner_changeset',
             'partner_firstname',
             'partner_address_street3',
             ],
 'external_dependencies': {'python': ['pyews']},
 'data': ['security/ir.model.access.csv',
          'views/connector_exchange_menu.xml',
          'views/exchange_backend_views.xml',
          'views/calendar_event_view.xml',
          'views/partner_views.xml',
          'views/users_views.xml',
          'views/res_company_view.xml',
          'views/userbackendfolder_views.xml',
          'data/cron.xml',
          'data/company_data.xml',
          'data/generic_partner.xml',
          'data/changeset_field_rule.xml',
          ],
 'installable': False,
 'auto_install': False,
 }

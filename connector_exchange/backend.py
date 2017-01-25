# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import odoo.addons.connector.backend as backend


exchange = backend.Backend('exchange')
exchange_2010 = backend.Backend(parent=exchange, version='exchange_2010')

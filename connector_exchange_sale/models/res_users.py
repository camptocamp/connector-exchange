# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openerp import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _get_contacts(self):
        res = super(ResUsers, self)._get_contacts()

        sale_partner_fields = ['partner_id',
                               'partner_invoice_id',
                               'partner_shipping_id'
                               ]
        sales = self.env['sale.order'].search(
            [('user_id', '=', self.id)]
            )
        sales_partners = self.env['res.partner']
        for f in sale_partner_fields:
            sales_partners |= sales.mapped(f)

        res |= sales_partners

        return res

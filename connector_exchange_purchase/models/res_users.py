# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openerp import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _get_contacts(self):
        res = super(ResUsers, self)._get_contacts()

        # how to search in purchases ? create_uid ? validator ?
        purchases_partners = self.env['purchase.order'].search(
            ['|',
             ('create_uid', '=', self.id),
             ('validator', '=', self.id)]
            ).mapped('partner_id')

        res |= purchases_partners

        return res

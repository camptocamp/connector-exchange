# -*- coding: utf-8 -*-
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)


from odoo import models, api


class ChangesetFieldRule(models.Model):
    _inherit = 'changeset.field.rule'

    @api.model
    def _domain_source_models(self):
        models = super(ChangesetFieldRule, self)._domain_source_models()
        xmlid = 'connector_exchange.model_res_users_backend_folder'
        model = self.env.ref(xmlid)
        return models | model

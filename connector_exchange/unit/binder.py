# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# Author: Nicolas Clavier
# Copyright 2014 HighCo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.connector.connector import Binder
from ..backend import exchange_2010


@exchange_2010
class ExchangeModelBinder(Binder):
    """
    Bindings are done directly on the binding model.

    Binding models are models called ``exchange.{normal_model}``,
    like ``exchange.partner.company`` or ``exchange.product.product``.
    They are ``_inherits`` of the normal models and contains
    the Exchange ID, the ID of the Exchange Backend and the additional
    fields belonging to the Exchange instance.
    """
    _model_name = [
        'exchange.res.partner',
        'exchange.calendar.event'
    ]

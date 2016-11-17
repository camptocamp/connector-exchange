# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openerp.addons.connector.event import (on_record_write,
                                            on_record_create,
                                            on_record_unlink
                                            )
from openerp.addons.connector.connector import Binder
from ... import consumer
from ...unit.environment import get_environment
from ...unit.exporter import export_delete_record


@on_record_create(model_names=[
    'exchange.res.partner',
    'exchange.calendar.event',
    ])
@on_record_write(model_names=[
    'exchange.res.partner',
    'exchange.calendar.event',
    ])
def delay_export(session, model_name, record_id, vals):
    consumer.delay_export(session, model_name, record_id, vals)


@on_record_write(model_names=[
    'res.partner',
    'calendar.event',
    ])
def delay_export_all_bindings(session, model_name, record_id, vals):
    if vals.keys() == ['exchange_bind_ids']:
        # a user just added a binding on an existing partner, we don't need to
        # create an export job because it will be created by the creation
        # of the binding
        return
    consumer.delay_export_all_bindings(session, model_name, record_id, vals)


@on_record_unlink(model_names=[
    'exchange.res.partner',
    'exchange.calendar.event',
    ])
def delay_disable(session, model_name, binding_record_id):
    record = session.env[model_name].browse(binding_record_id)
    env = get_environment(session, model_name, record.backend_id.id)
    binder = env.get_connector_unit(Binder)
    magento_id = binder.to_backend(binding_record_id)
    if magento_id:
        export_delete_record.delay(session, model_name,
                                   record.backend_id.id, magento_id,
                                   record.user_id.id)


@on_record_unlink(model_names=[
    'res.partner',
    'calendar.event',
    ])
def delay_disable_all_bindings(session, model_name, record_id):
    consumer.delay_disable_all_bindings(session, model_name,
                                        record_id)

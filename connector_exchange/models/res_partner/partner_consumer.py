# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.addons.connector.event import (on_record_write,
                                            on_record_create,
                                            on_record_unlink
                                            )
from odoo.addons.connector.connector import Binder
from ... import consumer


@on_record_create(model_names=[
    'exchange.res.partner',
    'exchange.calendar.event',
    ])
@on_record_write(model_names=[
    'exchange.res.partner',
    'exchange.calendar.event',
    ])
def delay_export(env, model_name, record_id, vals):
    record = env[model_name].browse(record_id)
    consumer.delay_export(record, vals)


@on_record_write(model_names=[
    'res.partner',
    'calendar.event',
    ])
def delay_export_all_bindings(env, model_name, record_id, vals):
    if vals.keys() == ['exchange_bind_ids']:
        # a user just added a binding on an existing partner, we don't need to
        # create an export job because it will be created by the creation
        # of the binding
        return
    record = env[model_name].browse(record_id)
    consumer.delay_export_all_bindings(record, vals)


@on_record_unlink(model_names=[
    'exchange.res.partner',
    'exchange.calendar.event',
    ])
def delay_disable(env, model_name, binding_record_id):
    record = env[model_name].browse(binding_record_id)
    with record.backend_id.get_environment(model_name) as connector_env:
        binder = connector_env.get_connector_unit(Binder)
    external_id = binder.to_backend(binding_record_id)
    if external_id:
        record.export_delete_record.delay(external_id, record.user_id)


@on_record_unlink(model_names=[
    'res.partner',
    'calendar.event',
    ])
def delay_disable_all_bindings(env, model_name, record_id):
    record = env[model_name].browse(record_id)
    consumer.delay_disable_all_bindings(record)

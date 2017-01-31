# -*- coding: utf-8 -*-
# Author: Guewen Baconnier
# Copyright 2013-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


def delay_export(env, model_name, record_id, vals):
    if env.context.get('connector_no_export'):
        return
    fields = vals.keys()
    record = env[model_name].browse(record_id)
    record.export_record.delay(fields=fields)


def delay_export_all_bindings(env, model_name, record_id, vals):
    """ Delay a job which export all the bindings of a record.
    In this case, it is called on records of normal models and will delay
    the export for all the bindings.
    """
    if env.context.get('connector_no_export'):
        return
    record = env[model_name].browse(record_id)
    fields = vals.keys()
    for binding in record.exchange_bind_ids:
        binding.export_record.delay(fields=fields)


def delay_disable_all_bindings(env, model_name, record_id):
    record = env[model_name].browse(record_id)
    for binding in record.exchange_bind_ids:
        binding.export_delete_record.delay(
            binding.external_id,
            binding.user_id)

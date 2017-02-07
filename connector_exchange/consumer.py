# -*- coding: utf-8 -*-
# Author: Guewen Baconnier
# Copyright 2013-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


def delay_export(record, vals):
    if record.env.context.get('connector_no_export'):
        return
    fields = vals.keys()
    record.with_delay().export_record(fields=fields)


def delay_export_all_bindings(record, vals):
    """ Delay a job which export all the bindings of a record.
    In this case, it is called on records of normal models and will delay
    the export for all the bindings.
    """
    if record.env.context.get('connector_no_export'):
        return
    fields = vals.keys()
    for binding in record.exchange_bind_ids:
        binding.with_delay().export_record(fields=fields)


def delay_disable_all_bindings(record):
    for binding in record.exchange_bind_ids:
        binding.with_delay().export_delete_record(
            binding.external_id,
            binding.user_id)

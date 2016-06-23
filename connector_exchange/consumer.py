# -*- coding: utf-8 -*-
# Author: Guewen Baconnier
# Copyright 2013 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# -*- coding: utf-8 -*-
##############################################################################

from .unit.exporter import export_record, export_delete_record


def delay_export(session, model_name, record_id, vals):
    if session.context.get('connector_no_export'):
        return
    fields = vals.keys()
    export_record.delay(session, model_name, record_id, fields=fields)


def delay_export_all_bindings(session, model_name, record_id, vals):
    """ Delay a job which export all the bindings of a record.
    In this case, it is called on records of normal models and will delay
    the export for all the bindings.
    """
    if session.context.get('connector_no_export'):
        return
    record = session.env[model_name].browse(record_id)
    fields = vals.keys()
    for binding in record.exchange_bind_ids:
        export_record.delay(session, binding._model._name, binding.id,
                            fields=fields)


def delay_disable_all_bindings(session, model_name, record_id):
    record = session.env[model_name].browse(record_id)
    for binding in record.exchange_bind_ids:
        export_delete_record.delay(session, binding._name,
                                   binding.backend_id.id,
                                   binding.external_id)

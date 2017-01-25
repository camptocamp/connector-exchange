# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# Author: Nicolas Clavier
# Copyright 2014 HighCo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

"""

Exporters for Exchange.

They should call the ``bind`` method if the binder even if the records
are already bound, to update the last sync date.

"""

import logging

import psycopg2

from odoo import _
from odoo.addons.connector.exception import RetryableJobError
from odoo.addons.connector.unit.synchronizer import Deleter
from odoo.addons.connector.unit.synchronizer import Exporter
from odoo.addons.connector.queue.job import job
from . import environment

_logger = logging.getLogger(__name__)


class ExchangeExporter(Exporter):
    # Name of the field which contains the ID
    _id_field = None

    def __init__(self, environment):
        """
        :param environment: current environment (backend, session, ...)
        :type environment: :py:class:`connector.connector.Environment`
        """
        super(ExchangeExporter, self).__init__(environment)
        self.external_id = None
        self.binding_id = None
        self.binding_record = None

    def get_openerp_data(self, binding_id):
        """

        """
        return self.model.browse(self.binding_id)

    def run(self, binding_id, *args, **kwargs):
        """ The connectors have to implement the _run method """
        self.binding_id = binding_id
        self.binding_record = self.get_openerp_data(binding_id)

        # prevent other jobs to export the same record
        # will be released on commit (or rollback)
        self._lock()

        result = self._run(*args, **kwargs)

        # Commit so we keep the external ID when there are several
        # exports (due to dependencies) and one of them fails.
        # The commit will also release the lock acquired on the binding
        # record
        self.session.commit()

        self._after_export()
        return result

    def _lock(self):
        """ Lock the binding record.

        Lock the binding record so we are sure that only one export
        job is running for this record if concurrent jobs have to export the
        same record.

        When concurrent jobs try to export the same record, the first one
        will lock and proceed, the others will fail to lock and will be
        retried later.

        This behavior works also when the export becomes multilevel
        with :meth:`_export_dependencies`. Each level will set its own lock
        on the binding record it has to export.

        """
        sql = ("SELECT id FROM %s WHERE ID = %%s FOR UPDATE NOWAIT" %
               self.model._table)
        try:
            self.session.cr.execute(sql, (self.binding_id, ),
                                    log_exceptions=False)
        except psycopg2.OperationalError:
            raise RetryableJobError(
                'A concurrent job is already exporting the same record '
                '(%s with id %s). The job will be retried later.' %
                (self.model._name, self.binding_id))

    def _after_export(self):
        """ Can do several actions after exporting a record """
        pass

    def _export_record(self, record, action, **kwargs):
        super(ExchangeExporter, self)._export_record(
            record,
            action,
            priority=30,
            description='Export record of one record from Exchange',
        )

    def _map_data(self):
        """ Returns an instance of
        :py:class:`~odoo.addons.connector.unit.mapper.MapRecord`
        """
        return self.mapper.map_record(self.binding_record)

    def _validate_create_data(self, data):
        """ Check if the values to import are correct
        Pro-actively check before the ``Model.create`` if some fields
        are missing or invalid
        Raise `InvalidDataError`
        """
        return

    def _validate_update_data(self, data):
        """ Check if the values to import are correct
        Pro-actively check before the ``Model.update`` if some fields
        are missing or invalid
        Raise `InvalidDataError`
        """
        return

    def _create_data(self, map_record, fields=None, **kwargs):
        """ Get the data to pass to :py:meth:`_create` """
        return map_record.values(for_create=True, fields=fields, **kwargs)

    def _create(self, data):
        """ Create the Exchange record """
        # special check on data before export
        self._validate_create_data(data)
        return self.backend_adapter.create(data)

    def _update_data(self, map_record, fields=None, **kwargs):
        """ Get the data to pass to :py:meth:`_update` """
        return map_record.values(fields=fields, **kwargs)

    def _update(self, data):
        """ Update an Exchange record """
        assert self.external_id
        # special check on data before export
        self._validate_update_data(data)
        self.backend_adapter.write(self.external_id, data)

    def _run(self, fields=None):
        assert self.binding_id
        map_record = self._map_data()

        if not self.external_id:
            fields = None

        if self.external_id:
            # update
            record = self._update_data(map_record, fields=fields)
            if not record:
                return _('Nothing to export.')
            self._update(record)
        else:
            # create
            record = self._create_data(map_record, fields=fields)
            if not record:
                return _('Nothing to export.')
            self.external_id = self._create(record)

        return _("Record exported with ID %s on Exchange") % self.external_id


class ExchangeDisabler(Deleter):
    """ Base record disabler for Exchange """

    def run(self, external_id, user_id):
        """ Run the synchronization, delete the record on Exchange
        :param external_id: identifier of the record to delete
        """

        return self._run(external_id, user_id)


@job
def export_record(session, model_name, binding_id, fields=None):
    """ Export a record from Exchange """
    record = session.env[model_name].browse(binding_id)
    env = environment.get_environment(session, model_name,
                                      record.backend_id.id)
    exporter = env.get_connector_unit(ExchangeExporter)
    return exporter.run(binding_id, fields=fields)


@job
def export_delete_record(session, model_name, backend_id, external_id, user_id
                         ):
    """ Delete a record on Exchange """
    env = environment.get_environment(session, model_name, backend_id)
    deleter = env.get_connector_unit(ExchangeDisabler)
    return deleter.run(external_id, user_id)

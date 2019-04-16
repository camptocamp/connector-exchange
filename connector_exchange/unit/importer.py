# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

"""

Importers for Exchange.

An import can be skipped if the last sync date is more recent than
the last update in Exchange.

They should call the ``bind`` method if the binder even if the records
are already bound, to update the last sync date.

"""

import logging
import odoo
from odoo import SUPERUSER_ID
from odoo.addons.connector.connector import ConnectorUnit
# from odoo.addons.queue_job.exception import FailedJobError
from odoo.addons.connector.unit.synchronizer import Importer

from ..backend import exchange_2010

from contextlib import closing, contextmanager

_logger = logging.getLogger(__name__)

RETRY_ON_ADVISORY_LOCK = 1  # seconds
RETRY_WHEN_CONCURRENT_DETECTED = 1  # seconds


RETRY_ON_ADVISORY_LOCK = 1  # seconds
RETRY_WHEN_CONCURRENT_DETECTED = 1  # seconds


class ExchangeImporter(Importer):
    """ Exchange Importer """

    # Name of the field which contains the ID
    _id_field = None  # set in sub-classes

    def run(self, *args, **kwargs):
        """ The connectors have to implement the _run method """
        return self._run(*args, **kwargs)

    def __init__(self, environment):
        """
        :param environment: current environment (backend, session, ...)
        :type environment: :py:class:`connector.connector.Environment`
        """
        super(ExchangeImporter, self).__init__(environment)
        self.external_id = None
        self.external_record = None

    def external_id_from_record(self, record):
        assert self._id_field, "_id_field must be defined"
        return record[self._id_field]

    def _before_import(self):
        """ Hook called before the import, when we have the external
        data"""

    def _import_dependency(self, subrecord, binding_model,
                           importer_class=None, always=False,
                           **kwargs):
        """ Import a dependency.

        The importer class is a class or subclass of
        :class:`ExchangeImporter`. A specific class can be defined.

        :param subrecord: subrecord to import
        :param binding_model: name of the binding model for the relation
        :type binding_model: str | unicode
        :param importer_cls: :class:`odoo.addons.connector.\
                                     connector.ConnectorUnit`
                             class or parent class to use for the export.
                             By default: ExchangeImporter
        :type importer_cls: :class:`odoo.addons.connector.\
                                    connector.MetaConnectorUnit`
        :param always: if True, the record is updated even if it already
                       exists, note that it is still skipped if it has
                       not been modified on the backend since the last
                       update. When False, it will import it only when
                       it does not yet exist.
        :type always: boolean
        :param **kwargs: additional args are propagated to the importer
        """
        if importer_class is None:
            importer_class = ExchangeImporter
        importer = self.unit_for(importer_class, model=binding_model)
        external_id = importer.external_id_from_record(subrecord)
        binder = self.binder_for(binding_model)
        if always or not binder.to_openerp(external_id):
            importer.run(subrecord, **kwargs)

    def _import_dependencies(self):
        """ Import the dependencies for the record

        Import of dependencies can be done manually or by calling
        :meth:`_import_dependency` for each dependency.
        """
        return

    def _validate_data(self, data):
        """ Check if the values to import are correct

        Pro-actively check before the ``_create`` or
        ``_update`` if some fields are missing or invalid.

        Raise `InvalidDataError`
        """
        return

    def _must_skip(self):
        """ Hook called right after we read the data from the backend.

        If the method returns a message giving a reason for the
        skipping, the import will be interrupted and the message
        recorded in the job (if the import is called directly by the
        job, not by dependencies).

        If it returns None, the import will continue normally.

        :returns: None | str | unicode
        """
        return

    def _get_binding(self):
        """Return the binding id from the external id"""
        return self.binder.to_openerp(self.external_id)

    def _skip_create(self, map_record, values):
        """ Defines if a create import should be skipped

        A reason can be returned in string
        """
        return

    def _create_data(self, map_record, **kwargs):
        return map_record.values(for_create=True, **kwargs)

    def _create_context_keys(self, keys=None):
        if keys and 'connector_no_export' in keys:
            context_keys = dict(**keys or {})
        else:
            context_keys = dict(
                connector_no_export=True,
                **keys or {}
            )
        if self.env.user.id == SUPERUSER_ID:
            context_keys['mail_create_nosubscribe'] = True

        return context_keys

    def _create(self, data, context_keys=None):
        """ Create the Odoo record """
        # special check on data before import
        self._validate_data(data)
        context_keys = self._create_context_keys(keys=context_keys)
        binding = self.model.with_context(**context_keys).create(data)

        _logger.debug('%s %d created from %s %s',
                      self.model._name, binding.id,
                      self.backend_record._name, self.external_id)
        return binding

    def _skip_update(self, map_record, values):
        """ Defines if an update import should be skipped

        A reason can be returned in string
        """
        return

    def _update_data(self, map_record, **kwargs):
        return map_record.values(**kwargs)

    def _update_context_keys(self, keys=None):
        context_keys = dict(
            connector_no_export=True,
            __deduplicate_no_name_search=True,
            __changeset_rules_source_model=self.backend_record._name,
            __changeset_rules_source_id=self.backend_record.id)

        if keys:
            context_keys.update(keys)

        if self.env.user.id == SUPERUSER_ID:
            context_keys['tracking_disable'] = True

        return context_keys

    def _update(self, binding, data, context_keys=None):
        """ Update an Odoo record """
        # special check on data before import
        self._validate_data(data)

        context_keys = self._update_context_keys(keys=context_keys)
        binding.with_context(**context_keys).write(data)
        _logger.debug('%s %d updated from %s %s',
                      self.model._name, binding.id,
                      self.backend_record._name, self.external_id)
        return

    def _after_import(self, binding):
        """ Hook called at the end of the import """
        return

    @contextmanager
    def do_in_new_connector_env(self, model_name=None):
        """ Context manager that yields a new connector environment

        Using a new Odoo Environment thus a new PG transaction.

        This can be used to make a preemptive check in a new transaction,
        for instance to see if another transaction already made the work.
        """
        with odoo.api.Environment.manage():
            registry = odoo.modules.registry.RegistryManager.get(
                self.env.cr.dbname
            )
            with closing(registry.cursor()) as cr:
                try:
                    new_env = odoo.api.Environment(cr, self.env.uid,
                                                   self.env.context)
                    connector_env = self.connector_env.create_environment(
                        self.backend_record.with_env(new_env),
                        self.env,
                        model_name or self.model._name,
                        connector_env=self.connector_env
                    )
                    yield connector_env
                except Exception as exp:
                    cr.rollback()
                    raise exp
                else:
                    cr.commit()

    def _run(self, item_id, user):
        """ Beginning of the synchronization

        The first thing we do is to try to acquire an advisory lock
        on Postgresql. If it can't be acquired it means that another job
        does the same import at the same moment.
        The goal is to prevent 2 jobs to create the same binding because
        they each job is not aware of the other binding.
        It happens easily when 2 jobs import the same dependencies (such
        as partner categories for an import of partners).

        :param item_id: item_id
        """
        self.openerp_user = user
        self.external_id = item_id
        # lock_name = 'import({}, {}, {}, {})'.format(
        #     self.backend_record._name,
        #     self.backend_record.id,
        #     self.model._name,
        #     self.external_id,
        # )
        # Keep a lock on this import until the transaction is committed
        # self.advisory_lock_or_retry(lock_name,
        #                             retry_seconds=RETRY_ON_ADVISORY_LOCK)

        skip = self._must_skip()
        if skip:
            return skip

        self._before_import()

        # import the missing linked resources
        # self._import_dependencies()

        contact_id = self.external_id

        data = self._map_data()
        data.update(user_id=self.openerp_user.id,
                    backend_id=self.backend_record.id)

        # try to find a exchange.res.partner with the same
        # Id/user_id/backend_id
        # if found, update it
        # otherwise, create it
        backend = self.backend_record
        args = [('backend_id', '=', backend.id),
                ('user_id', '=', self.openerp_user.id),
                ('external_id', '=', contact_id)]
        exchange_partners = self.env['exchange.res.partner'].search(args)

        partners = self.env['res.partner']
        if data.get('company_name'):
            partners = self.env['res.partner'].search(
                [('name', '=', data['company_name'])])
            del data['company_name']

        if not exchange_partners:
            GENERIC = self.env.ref('connector_exchange.res_partner_GENERIC').id
            _logger.debug('does not exist --> CREATE')
            data['active'] = False
            binding = exchange_partners._create(data)
            write_dict = {
                'active': True,
                'parent_id': partners and partners[0].id or GENERIC
            }
            binding_rs = exchange_partners.browse(binding)
            self._update(binding_rs, write_dict)
            # self.move_contact(contact_id)
        else:
            # if not self.external_record:
            #     _logger.debug('deleted in Exchange')
            #     # self.binding.openerp_id.with_context(
            #     #     connector_no_export=True).unlink()
            # else:
            _logger.debug('exists --> UPDATE')
            binding = exchange_partners[0]
            self._update(binding, data)

    def _map_data(self):
        raise NotImplementedError('Must be implemented in subclasses')

    # def move_contact(self, contact_id):
    #     ews_service = self.backend_adapter.ews
    #     ews_service.get_root_folder()
    #     contact_folder = ews_service.root_folder.FindFolderByDisplayName(
    #         "Contacts",
    #         types=[FolderClass.Contacts])
    #     if contact_folder:
    #         contact_folder = contact_folder[0]
    #         ews_service.MoveItems(contact_folder.Id, [contact_id])
    #     else:
    #         raise FailedJobError(
    #             _('Unable to find folder "Contacts" in Exchange')
    #         )


def add_checkpoint(env, model_name, record_id,
                   backend_model_name, backend_id):
    checkpoint_model = env['connector.checkpoint']
    return checkpoint_model.create_from_name(model_name, record_id,
                                             backend_model_name, backend_id)


@exchange_2010
class AddCheckpoint(ConnectorUnit):
    """ Add a connector.checkpoint on the underlying model
    (not the exchange.* but the _inherits'ed model) """

    _model_name = ['exchange.res.partner']

    def run(self, openerp_binding_id):
        binding = self.model.browse(openerp_binding_id)
        record = binding.openerp_id
        add_checkpoint(self.env,
                       record._model._name,
                       record.id,
                       self.backend_record.id)

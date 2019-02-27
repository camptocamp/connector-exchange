# -*- coding: utf-8 -*-
# Author: Damien Crier
# Copyright 2016-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from odoo.addons.connector.unit.backend_adapter import BackendAdapter
from exchangelib import IMPERSONATION, Account, Credentials, ServiceAccount, Configuration, NTLM
from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter


BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter

_logger = logging.getLogger(__name__)


class ExchangeLocation(Credentials):

    def __init__(self, user, pwd):
        self.user = user
        self.pwd = pwd


class ExchangeAdapter(BackendAdapter):
    def __init__(self, connector_env):
        """
        :param connector_env: current environment (backend, session, ...)
        :type connector_env: :class:`connector.connector.ConnectorEnvironment`
        """
        super(BackendAdapter, self).__init__(connector_env)
        backend = self.backend_record
        # Embed a ExchangeService instance in the backend adapter
        self.credentials = ServiceAccount(username=backend.username,
                                          password=backend.password)

    def get_account(self, user):
        if self.backend_record.disable_autodiscover:
            config = Configuration(server=self.backend_record.location,
                                   auth_type=NTLM,
                                   credentials=self.credentials)

            return Account(primary_smtp_address=user.email,
                           config=config,
                           autodiscover=False,
                           access_type=IMPERSONATION)

        return Account(primary_smtp_address=user.email,
                       credentials=self.credentials,
                       autodiscover=True, access_type=IMPERSONATION)

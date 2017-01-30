# -*- coding: utf-8 -*-
# Authors: Guewen Baconnier, Damien Crier
# Copyright 2015-2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from os.path import dirname, join, exists

from lxml import etree
from vcr import VCR

from odoo import SUPERUSER_ID
from odoo.tests.common import TransactionCase
from odoo.addons.connector.session import ConnectorSession
from odoo.addons.connector_exchange.connector import get_environment


# This is the true URL. Please be sure to record the calls made to it
# with vcr so that the tests don't hit the service.
exchange_wsdl = ''
exchange_user = ''
exchange_password = ''

# secret.txt is a file which can be placed by the developer in the
# 'tests' directory. It contains the username in the first line at the
# password in the second. The secret.txt file must not be committed.
# The API username and password will be used to record the requests
# with vcr, but will not be stored in the fixtures files (cleaned by
# before_record_callback())
filename = join(dirname(__file__), 'secret.txt')
if exists(filename):
    with open(filename, 'r') as fp:
        exchange_user = next(fp).strip()
        exchange_password = next(fp).strip()
        exchange_wsdl = next(fp).strip()
else:
    exchange_wsdl = 'https://exchange'
    exchange_user = 'exchange'
    exchange_password = 'exchange'


def before_record_callback(request):
    """ Replace the login and the password before vcr stores the request

    Prevent to leak login and password in the fixtures.
    """
    if not request.method == 'POST':
        return request
    body = request.body
    root = etree.fromstring(body)
    body_el = root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
    method_el = body_el.getchildren()[0]
    login_el = method_el.find('login')
    login_el.text = 'XXX'
    password_el = method_el.find('password')
    password_el.text = 'XXX'
    request.body = etree.tostring(root)
    return request


my_vcr = VCR(
    record_mode='once',
    cassette_library_dir=join(dirname(__file__), 'fixtures/cassettes'),
    path_transformer=VCR.ensure_suffix('.yaml')
    # before_record=before_record_callback,
)


class ExchangeBackendTransactionCase(TransactionCase):

    def setUp(self):
        super(ExchangeBackendTransactionCase, self).setUp()
        self.ExchangeBackend = self.env['exchange.backend']
        self.exchange_backend = self.ExchangeBackend.create({
            'location': exchange_wsdl,
            'username': exchange_user,
            'password': exchange_password,
            'name': 'TEST',
            'version': 'exchange_2010'
        })
        self.connector_session = ConnectorSession.from_env(self.env)

        self.user = self.env['res.users'].browse(SUPERUSER_ID)
        self.user.exchange_synch = True
        self.user.login = 'c1odoo'

        # create a contact with user_id = SUPERUSER_ID to be able to sync it
        self.created_user = self.env['res.partner'].create(
            {'firstname': 'John',
             'lastname': 'Lennon',
             'street': 'Abbey Road',
             'street2': 'Beatles',
             'zip': '1969',
             'country_id': self.env.ref('base.uk').id,
             'user_id': SUPERUSER_ID,
             'phone': '0123456789',
             'email': 'toot@tooto.com'
             }
            )

    def _get_environment(self, model_name):
        return get_environment(self.connector_session, model_name,
                               self.lefac_backend.id)

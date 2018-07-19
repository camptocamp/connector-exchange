# Connector Exchange

![Logo](./images/OdooXchange.png) 

## Principles

Odoo Exchange Connector is a bi-directional connector, 100% compatible with Odoo 10.0 (Community and Enterprise edition) and Exchange 2010 SP2 version.

Using this connector, you will be able to synchronize your contacts and your calendar events.

Unlike other connectors existing to sync Odoo and Exchange, this connector makes a server to server connection. Nothing to setup in Outlook or other tools. Once configured, it works seemlessly to either import contact/calendar events created in Exchange or export contacts/calendar events created in Odoo.

Moreover, this connector does not use paid third-party library to connect and interact with Microsoft Exchange.

This connector is based on the [OpenERP Connector framework](https://github.com/OCA/connector) and the [PyEWS library](https://github.com/camptocamp/PyEWS).

Here is a quick video to show you the features provided by this connector:

[![Odoo Exchange Connector presentation video](https://img.youtube.com/vi/jEhFTtzG1MU/0.jpg)](https://www.youtube.com/watch?v=jEhFTtzG1MU)


## Configuration

### [In Exchange](./config/exchange_configuration.md)

### [In Odoo](./config/odoo_configuration.md)


## How it works?

* [Activate connector by user](./how_to/activate.md)
* [Importing contacts](./how_to/import_contacts.md)
* [Importing calendar events](./how_to/import_calendar_events.md)
* [Exporting contacts](./how_to/export_contacts.md)
* [Exporting calendar events](./how_to/export_calendar_events.md)
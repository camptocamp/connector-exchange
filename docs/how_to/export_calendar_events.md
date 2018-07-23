# Exporting calendar events

## Pre-requisites

You must have activated the calendar sync on user form view to be able to export calendar events.

## How it works

### TL;DR

Export of a calendar event is done automatically by Odoo. No scheduled task, nothing to do except a correct configuration of the user.

### More explainations

Logged as a user for whom calendar event sync is enabled, simply go on the calendar app and create an event.

The created event will try to autobind itself to an exchange backend. This backend is the one configured as *default backend* on the user form view.

![Direct calendar export](./images/exchange_export_calendar_event.gif) 
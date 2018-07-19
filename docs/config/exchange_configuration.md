# Exchange Configuration 

>**Disclaimer:** This configuration has been tested with an Microsoft Exchange 2010 SP2. This connector can require some modification to work with other versions of Microsoft Exchange.

## Security concerns

### Impersonation mechanism

The connector uses the [impersonation mechanism](https://docs.microsoft.com/fr-fr/exchange/client-developer/exchange-web-services/impersonation-and-ews-in-exchange) to perform operations.

This means you have to configure an *impersonation* account and allow this one to act for some exchange accounts.

### HttpBasicAuth

The *impersonation* account is used by Odoo to connect Exchange server. The credentials are stored in Odoo and the authentication is made using HttpBasicAuth.

There's currently no plans to add other authentication types but AuthNTLM has been tested manually on a separate script and seems to work properly.

## Configuration

A good start is reading this [reference article](https://msdn.microsoft.com/en-us/library/office/bb204095(v=exchg.140).

Here are the steps to create a impersonation account (PowerShell commands):

1) Create a role to assign it to a user

	New-ManagementRoleAssignment –Name:impersonationAssignmentName –Role:ApplicationImpersonation –User:serviceAccount
 
2) Create the action scope

	New-ManagementScope –Name:scopeName –RecipientRestrictionFilter:recipientFilter
 
You can read this [article](https://technet.microsoft.com/en-us/library/aa995993(v=exchg.141).aspx) to know how [RecipientFiltrer](https://technet.microsoft.com/en-us/library/aa995993(v=exchg.141).aspx) works.
 
3) Check the configuration done is correct:

	python
		def blabla
		GET- ManagementRoleAssignment | format-list
		GET –ManagementScope | format-list
		

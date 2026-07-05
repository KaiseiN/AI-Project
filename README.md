# PIM Activation Azure Function

Python Azure Functions backend API for activating a Microsoft Entra PIM role after deterministic backend validation.

## Endpoint

```http
POST /api/pim/activate
Authorization: Bearer <access-token-for-this-api>
Content-Type: application/json
```

```json
{
  "roleName": "User Administrator",
  "durationHours": 2,
  "ticketNumber": "INC12345",
  "justification": "INC12345"
}
```

The Function derives the user from the caller token, maps the role name to an allowlisted Microsoft Graph role definition ID, validates the ticket placeholder, and calls Microsoft Graph:

```http
POST https://graph.microsoft.com/v1.0/roleManagement/directory/roleAssignmentScheduleRequests
```

## Local Setup

Install Azure Functions Core Tools, then create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
func start
```

Update `local.settings.json` with your tenant ID, backend API app registration client ID, and local development client secret.

## Azure Configuration

Create or use an app registration for the Function API:

- Expose an API scope such as `api://<client-id>/pim.activate`.
- Add delegated Microsoft Graph permission `RoleAssignmentSchedule.ReadWrite.Directory`.
- Grant admin consent.
- Configure a client secret or certificate for local/OBO token exchange.
- Enable Authentication on the Function App with Microsoft Entra.
- Require authenticated requests.
- Store secrets in Function App settings or Key Vault references.

The HTTP trigger uses `AuthLevel.ANONYMOUS` because Microsoft Entra authentication should be enforced by App Service Authentication before requests reach the Function code.

## Security Notes

The AI agent should only send role name, duration, ticket number, and justification. Do not let the agent supply `principalId`, `roleDefinitionId`, or raw Microsoft Graph payloads.

Before production use, replace `shared/tickets.py` with a real ITSM lookup and expand the allowlisted roles in `shared/config.py`.

# PIM Activation Orchestrator

Browser-based orchestrator for the permanent architecture:

```text
User signs in with Entra ID
  -> App gets a user access token for the Function API
  -> App extracts role/duration/ticket intent
  -> App calls the deployed Azure Function with the user token
  -> Function performs OBO and activates PIM
```

This app uses the browser authorization code flow with PKCE directly. It has no external JavaScript dependency.

## Setup

Copy the example config:

```powershell
Copy-Item .\orchestrator\config.example.js .\orchestrator\config.js
```

Edit `orchestrator/config.js` if needed.

The default values are already set for this project:

```javascript
tenantId: "a373f986-e6fe-48b3-8acd-d9cc4dbdb2e6"
clientId: "2d927dbc-e54f-4e43-a1d9-ab9988006dc6"
apiScope: "api://2450d4e7-7781-4a1f-885b-710a17d3d31b/pim.activate"
functionUrl: "https://knakano-ai-project-app-h9cxeyfufqdhahcx.eastus2-01.azurewebsites.net/api/pim/activate"
```

## Entra Redirect URI

Add this redirect URI to the local client app registration as a **Single-page application (SPA)** redirect URI:

```text
http://localhost:8000/orchestrator/
```

If you use another port, add that exact URL instead.

## Run Locally

From the project root:

```powershell
.\.venv\Scripts\python.exe -m http.server 8000
```

Open:

```text
http://localhost:8000/orchestrator/
```

## Test Prompt

```text
Activate my AI Reader role for 2 hours for Ticket12345.
```

Expected payload:

```json
{
  "roleName": "AI Reader",
  "durationHours": 2,
  "ticketNumber": "Ticket12345",
  "justification": "Ticket12345"
}
```

## Foundry Integration Point

For production, replace `extractIntentLocally` in `app.js` with a call to your Foundry agent/orchestrator endpoint. Keep the final Function call in this app or a trusted backend so it uses the current signed-in user's token.

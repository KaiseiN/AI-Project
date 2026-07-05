import logging

import azure.functions as func
import msal

from shared.config import settings


def get_bearer_token(req: func.HttpRequest) -> str | None:
    auth_header = req.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None

    return auth_header.split(" ", 1)[1]


def acquire_graph_token_on_behalf_of(user_token: str) -> str:
    confidential_client = msal.ConfidentialClientApplication(
        settings.azure_client_id,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
        client_credential=settings.azure_client_secret,
    )

    result = confidential_client.acquire_token_on_behalf_of(
        user_assertion=user_token,
        scopes=["https://graph.microsoft.com/.default"],
    )

    if "access_token" not in result:
        logging.warning("OBO token acquisition failed: %s", result)
        error = result.get("error_description") or result.get("error") or "Unknown auth error"
        raise RuntimeError(error)

    return result["access_token"]

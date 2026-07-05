import json
import os
import sys
from pathlib import Path

import msal

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / ".local" / "user_access_token.txt"


def load_local_settings() -> None:
    settings_path = ROOT / "local.settings.json"
    with settings_path.open("r", encoding="utf-8") as settings_file:
        settings = json.load(settings_file)

    for key, value in settings.get("Values", {}).items():
        os.environ.setdefault(key, value)


def main() -> None:
    load_local_settings()

    tenant_id = os.environ["AZURE_TENANT_ID"]
    backend_client_id = os.environ["AZURE_CLIENT_ID"]
    token_client_id = os.getenv("TOKEN_CLIENT_ID", backend_client_id)
    api_scope = os.getenv("PIM_API_SCOPE", f"api://{backend_client_id}/pim.activate")

    app = msal.PublicClientApplication(
        client_id=token_client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )

    flow = app.initiate_device_flow(scopes=[api_scope])
    if "user_code" not in flow:
        raise RuntimeError(f"Could not create device flow: {flow}")

    print(flow["message"], file=sys.stderr)
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        print(json.dumps(result, indent=2), file=sys.stderr)
        if result.get("error") == "invalid_client" and 7000218 in result.get("error_codes", []):
            print(
                "\nThis client app is configured as confidential. Create a separate public "
                "client app registration for local device-code sign-in, then set "
                "TOKEN_CLIENT_ID to that app's Application (client) ID.",
                file=sys.stderr,
            )
        raise RuntimeError("Could not acquire access token.")

    TOKEN_PATH.parent.mkdir(exist_ok=True)
    TOKEN_PATH.write_text(result["access_token"], encoding="utf-8")

    print(result["access_token"])
    print(f"\nSaved token to: {TOKEN_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()

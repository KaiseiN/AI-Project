import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_local_settings() -> dict:
    settings_path = ROOT / "local.settings.json"
    with settings_path.open("r", encoding="utf-8") as settings_file:
        settings = json.load(settings_file)

    return settings.get("Values", {})


def mask(value: str | None) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 8:
        return "<set>"
    return f"{value[:4]}...{value[-4:]}"


def main() -> None:
    values = load_local_settings()
    tenant_id = values.get("AZURE_TENANT_ID")
    backend_client_id = values.get("AZURE_CLIENT_ID")
    token_client_id = os.getenv("TOKEN_CLIENT_ID") or values.get("TOKEN_CLIENT_ID") or backend_client_id
    api_scope = (
        os.getenv("PIM_API_SCOPE")
        or values.get("PIM_API_SCOPE")
        or f"api://{backend_client_id}/pim.activate"
    )

    print(f"AZURE_TENANT_ID: {tenant_id or '<missing>'}")
    print(f"AZURE_CLIENT_ID: {backend_client_id or '<missing>'}")
    print(f"AZURE_CLIENT_SECRET: {mask(values.get('AZURE_CLIENT_SECRET'))}")
    print(f"TOKEN_CLIENT_ID: {token_client_id or '<missing>'}")
    print(f"PIM_API_SCOPE: {api_scope}")


if __name__ == "__main__":
    main()

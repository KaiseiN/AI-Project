import os


class Settings:
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    ticket_system_name: str
    max_pim_duration_hours: int
    foundry_intent_mode: str
    foundry_project_endpoint: str | None
    foundry_agent_name: str
    foundry_agent_version: str | None
    foundry_agent_isolation_key: str
    foundry_responses_endpoint: str | None
    foundry_managed_identity_client_id: str | None
    foundry_token_scope: str
    foundry_api_version: str

    def __init__(self) -> None:
        self.azure_tenant_id = self._required("AZURE_TENANT_ID")
        self.azure_client_id = self._required("AZURE_CLIENT_ID")
        self.azure_client_secret = self._required("AZURE_CLIENT_SECRET")
        self.ticket_system_name = os.getenv("TICKET_SYSTEM_NAME", "ServiceNow")
        self.max_pim_duration_hours = int(os.getenv("MAX_PIM_DURATION_HOURS", "4"))
        self.foundry_intent_mode = os.getenv("FOUNDRY_INTENT_MODE", "local").lower()
        self.foundry_project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
        self.foundry_agent_name = os.getenv("FOUNDRY_AGENT_NAME", "PIM-Activation")
        self.foundry_agent_version = os.getenv("FOUNDRY_AGENT_VERSION")
        self.foundry_agent_isolation_key = os.getenv(
            "FOUNDRY_AGENT_ISOLATION_KEY", "pim-intent-extraction"
        )
        self.foundry_responses_endpoint = os.getenv("FOUNDRY_RESPONSES_ENDPOINT")
        self.foundry_managed_identity_client_id = os.getenv("FOUNDRY_MANAGED_IDENTITY_CLIENT_ID")
        self.foundry_token_scope = os.getenv("FOUNDRY_TOKEN_SCOPE", "https://ai.azure.com/.default")
        self.foundry_api_version = os.getenv("FOUNDRY_API_VERSION", "2025-05-01-preview")

        self._role_map = {
            "AI Reader": "1fe13547-53f6-408d-ac04-7f8eed167b38",
            "Security Reader": "5d6b6bb7-de71-4623-b4af-96380a352509",
            "User Administrator": "fe930be7-5e62-47db-91af-98c3a49a38b1",
        }

    def role_definition_id(self, role_name: str) -> str | None:
        return self._role_map.get(role_name)

    def allowed_role_names(self) -> list[str]:
        return list(self._role_map.keys())

    @staticmethod
    def _required(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"Missing required setting: {name}")
        return value


settings = Settings()

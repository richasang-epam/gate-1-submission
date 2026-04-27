from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str = "sk-ant-placeholder"
    CRM_BASE_URL: str = "https://crm.example.com/api/v1"
    CRM_CLIENT_ID: str = "mock-client-id"
    CRM_CLIENT_SECRET: str = "mock-client-secret"
    DMS_BASE_URL: str = "https://dms.example.com/api/v1"
    DMS_API_KEY: str = "mock-api-key"
    SOAP_WSDL_URL: str = "https://policy-admin.example.com/ws?wsdl"
    REDIS_URL: Optional[str] = None
    MOCK_MODE: bool = True
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


config = Settings()

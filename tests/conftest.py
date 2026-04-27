"""Shared fixtures for all test modules."""
import pytest
from fnol_agent.integrations.mock_clients import MockCRMClient, MockPolicyClient, MockDMSClient
import fnol_agent.tools as tools


@pytest.fixture(autouse=True)
def mock_clients():
    """Inject mock clients before every test; reset after."""
    tools.configure_clients(
        crm=MockCRMClient(),
        policy=MockPolicyClient(),
        dms=MockDMSClient(),
    )
    yield
    tools.configure_clients(crm=None, policy=None, dms=None)
    tools._clients["crm"] = None
    tools._clients["policy"] = None
    tools._clients["dms"] = None

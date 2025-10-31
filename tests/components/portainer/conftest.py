"""Common fixtures for the portainer tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

from pyportainer.models.docker import DockerContainer
from pyportainer.models.docker_inspect import DockerInfo, DockerVersion
from pyportainer.models.portainer import Endpoint
import pytest

from homeassistant.components.portainer.const import DOMAIN
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL

from tests.common import (
    MockConfigEntry,
    load_json_array_fixture,
    load_json_value_fixture,
)

MOCK_TEST_CONFIG = {
    CONF_URL: "https://127.0.0.1:9000/",
    CONF_API_TOKEN: "test_api_token",
    CONF_VERIFY_SSL: True,
}


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.portainer.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_portainer_client() -> Generator[AsyncMock]:
    """Mock Portainer client with dynamic exception injection support."""
    with (
        patch(
            "homeassistant.components.portainer.Portainer", autospec=True
        ) as mock_client,
        patch(
            "homeassistant.components.portainer.config_flow.Portainer", new=mock_client
        ),
    ):
        client = mock_client.return_value

        client.get_endpoints.return_value = [
            Endpoint.from_dict(endpoint)
            for endpoint in load_json_array_fixture("endpoints.json", DOMAIN)
        ]
        client.get_containers.return_value = [
            DockerContainer.from_dict(container)
            for container in load_json_array_fixture("containers.json", DOMAIN)
        ]
        client.docker_info.return_value = DockerInfo.from_dict(
            load_json_value_fixture("docker_info.json", DOMAIN)
        )
        client.docker_version.return_value = DockerVersion.from_dict(
            load_json_value_fixture("docker_version.json", DOMAIN)
        )

        client.restart_container = AsyncMock(return_value=None)

        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Mock a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Portainer test",
        data=MOCK_TEST_CONFIG,
        unique_id=MOCK_TEST_CONFIG[CONF_API_TOKEN],
        entry_id="portainer_test_entry_123",
        version=2,
    )

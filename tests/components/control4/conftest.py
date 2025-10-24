"""Common fixtures for the Control4 tests."""

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.control4.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform

from tests.common import MockConfigEntry, load_fixture

MOCK_HOST = "192.168.1.100"
MOCK_USERNAME = "test-username"
MOCK_PASSWORD = "test-password"
MOCK_CONTROLLER_UNIQUE_ID = "control4_test_123"


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Controller",
        data={
            CONF_HOST: MOCK_HOST,
            CONF_USERNAME: MOCK_USERNAME,
            CONF_PASSWORD: MOCK_PASSWORD,
            "controller_unique_id": MOCK_CONTROLLER_UNIQUE_ID,
        },
        unique_id="00:aa:00:aa:00:aa",
    )


@pytest.fixture
def mock_c4_account() -> Generator[MagicMock]:
    """Mock a Control4 Account client."""
    with patch(
        "homeassistant.components.control4.C4Account", autospec=True
    ) as mock_account_class:
        mock_account = mock_account_class.return_value
        mock_account.getAccountBearerToken = AsyncMock()
        mock_account.getAccountControllers = AsyncMock(
            return_value={"href": "https://example.com"}
        )
        mock_account.getDirectorBearerToken = AsyncMock(return_value={"token": "test"})
        mock_account.getControllerOSVersion = AsyncMock(return_value="3.2.0")
        yield mock_account


@pytest.fixture
def mock_c4_director() -> Generator[MagicMock]:
    """Mock a Control4 Director client."""
    with patch(
        "homeassistant.components.control4.C4Director", autospec=True
    ) as mock_director_class:
        mock_director = mock_director_class.return_value
        # Multi-platform setup: media room, climate room, shared devices
        # Note: The API returns JSON strings, so we load fixtures as strings
        mock_director.getAllItemInfo = AsyncMock(
            return_value=load_fixture("director_all_items.json", DOMAIN)
        )
        mock_director.getUiConfiguration = AsyncMock(
            return_value=load_fixture("ui_configuration.json", DOMAIN)
        )
        yield mock_director


@pytest.fixture
def mock_update_variables() -> Generator[AsyncMock]:
    """Mock the update_variables_for_config_entry function."""

    async def _mock_update_variables(*args, **kwargs):
        return {
            1: {
                "POWER_STATE": True,
                "CURRENT_VOLUME": 50,
                "IS_MUTED": False,
                "CURRENT_VIDEO_DEVICE": 100,
                "CURRENT MEDIA INFO": {},
                "PLAYING": False,
                "PAUSED": False,
                "STOPPED": False,
            }
        }

    with patch(
        "homeassistant.components.control4.media_player.update_variables_for_config_entry",
        new=_mock_update_variables,
    ) as mock_update:
        yield mock_update


@pytest.fixture
def mock_climate_variables() -> dict:
    """Mock climate variable data for default thermostat state."""
    return {
        123: {
            "HVAC_STATE": "idle",
            "HVAC_MODE": "Heat",
            "TEMPERATURE_F": 72.5,
            "HUMIDITY": 45,
            "COOL_SETPOINT_F": 75.0,
            "HEAT_SETPOINT_F": 68.0,
        }
    }


@pytest.fixture
def mock_climate_update_variables(
    mock_climate_variables: dict,
) -> Generator[AsyncMock]:
    """Mock update_variables for climate platform."""

    async def _mock_update_variables(*args, **kwargs):
        return mock_climate_variables

    with patch(
        "homeassistant.components.control4.climate.update_variables_for_config_entry",
        new=_mock_update_variables,
    ) as mock_update:
        yield mock_update


@pytest.fixture
def mock_c4_climate() -> Generator[MagicMock]:
    """Mock C4Climate class."""
    with patch(
        "homeassistant.components.control4.climate.C4Climate", autospec=True
    ) as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.setHvacMode = AsyncMock()
        mock_instance.setHeatSetpointF = AsyncMock()
        mock_instance.setCoolSetpointF = AsyncMock()
        yield mock_instance


@pytest.fixture
def platforms() -> list[Platform]:
    """Platforms which should be loaded during the test."""
    return [Platform.MEDIA_PLAYER]


@pytest.fixture(autouse=True)
async def mock_patch_platforms(platforms: list[Platform]) -> AsyncGenerator[None]:
    """Fixture to set up platforms for tests."""
    with patch("homeassistant.components.control4.PLATFORMS", platforms):
        yield

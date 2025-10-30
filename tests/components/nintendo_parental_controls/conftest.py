"""Common fixtures for the Nintendo Switch parental controls tests."""

from collections.abc import Generator
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

from pynintendoparental import NintendoParental
from pynintendoparental.device import Device
from pynintendoparental.exceptions import InvalidOAuthConfigurationException
import pytest

from homeassistant.components.nintendo_parental_controls.const import DOMAIN

from .const import ACCOUNT_ID, API_TOKEN, LOGIN_URL

from tests.common import MockConfigEntry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={"session_token": API_TOKEN},
        unique_id=ACCOUNT_ID,
    )


@pytest.fixture
def mock_nintendo_device() -> Device:
    """Return a mocked device."""
    mock = AsyncMock(spec=Device)
    mock.device_id = "testdevid"
    mock.name = "Home Assistant Test"
    mock.extra = {
        "firmwareVersion": {"displayedVersion": "99.99.99"},
        "serialNumber": "SN12345678",
    }
    mock.limit_time = 120
    mock.today_playing_time = 110
    mock.today_time_remaining = 10
    mock.bedtime_alarm = time(hour=19)
    mock.add_extra_time.return_value = None
    mock.set_bedtime_alarm.return_value = None
    mock.update_max_daily_playtime.return_value = None
    mock.forced_termination_mode = True
    mock.model = "Test Model"
    mock.generation = "P00"
    return mock


@pytest.fixture
def mock_nintendo_authenticator() -> Generator[MagicMock]:
    """Mock Nintendo Authenticator."""
    with (
        patch(
            "homeassistant.components.nintendo_parental_controls.Authenticator",
            autospec=True,
        ) as mock_auth_class,
        patch(
            "homeassistant.components.nintendo_parental_controls.config_flow.Authenticator",
            new=mock_auth_class,
        ),
        patch(
            "homeassistant.components.nintendo_parental_controls.coordinator.NintendoParental.update",
            return_value=None,
        ),
    ):
        mock_auth = MagicMock()
        mock_auth._id_token = API_TOKEN
        mock_auth._at_expiry = datetime(2099, 12, 31, 23, 59, 59)
        mock_auth.account_id = ACCOUNT_ID
        mock_auth.login_url = LOGIN_URL
        mock_auth.get_session_token = API_TOKEN
        # Patch complete_login as an AsyncMock on both instance and class as this is a class method
        mock_auth.complete_login = AsyncMock()
        type(mock_auth).complete_login = mock_auth.complete_login
        mock_auth_class.generate_login.return_value = mock_auth
        yield mock_auth


@pytest.fixture
def mock_nintendo_api() -> Generator[AsyncMock]:
    """Mock Nintendo API."""
    with patch(
        "homeassistant.components.nintendo_parental_controls.config_flow.Api",
        autospec=True,
    ) as mock_api_class:
        mock_api_instance = MagicMock()
        # patch async_get_account_devices as an AsyncMock
        mock_api_instance.async_get_account_devices = AsyncMock()
        mock_api_class.return_value = mock_api_instance
        yield mock_api_instance


@pytest.fixture
def mock_failed_nintendo_authenticator() -> Generator[MagicMock]:
    """Mock a failed Nintendo Authenticator."""
    with (
        patch(
            "homeassistant.components.nintendo_parental_controls.Authenticator",
            autospec=True,
        ) as mock_auth_class,
        patch(
            "homeassistant.components.nintendo_parental_controls.config_flow.Authenticator",
            new=mock_auth_class,
        ),
        patch(
            "homeassistant.components.nintendo_parental_controls.coordinator.NintendoParental.update",
            return_value=None,
        ),
    ):
        mock_auth = MagicMock()
        mock_auth.complete_login = AsyncMock(
            side_effect=InvalidOAuthConfigurationException(
                status_code=401,
                message="Authentication failed",
            )
        )
        mock_auth_class.complete_login = mock_auth.complete_login
        yield mock_auth


@pytest.fixture
def mock_nintendo_client(
    mock_nintendo_device: Device, mock_nintendo_authenticator: MagicMock
) -> Generator[AsyncMock]:
    """Mock a Nintendo client."""
    # Create a mock instance with our device(s) first
    mock_client_instance = AsyncMock(spec=NintendoParental)
    mock_client_instance.devices = {"testdevid": mock_nintendo_device}
    # Now patch the NintendoParental class in the coordinator with our mock instance
    with patch(
        "homeassistant.components.nintendo_parental_controls.coordinator.NintendoParental",
        autospec=True,
    ) as mock_client_class:
        mock_client_class.return_value = mock_client_instance
        mock_client_instance.update.return_value = None

        yield mock_client_instance


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.nintendo_parental_controls.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry

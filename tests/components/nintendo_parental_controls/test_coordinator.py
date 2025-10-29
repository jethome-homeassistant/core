"""Test coordinator error handling."""

from unittest.mock import AsyncMock

from pynintendoparental.exceptions import (
    InvalidOAuthConfigurationException,
    NoDevicesFoundException,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration

from tests.common import MockConfigEntry


async def test_invalid_authentication(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test handling of invalid authentication."""
    mock_nintendo_client.update.side_effect = InvalidOAuthConfigurationException(
        status_code=401, message="Authentication failed"
    )

    await setup_integration(hass, mock_config_entry)

    # Ensure no entities are created
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert len(entries) == 0
    # Ensure the config entry is marked as error
    assert mock_config_entry.state == ConfigEntryState.SETUP_ERROR


async def test_no_devices(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test handling of invalid authentication."""
    mock_nintendo_client.update.side_effect = NoDevicesFoundException()

    await setup_integration(hass, mock_config_entry)

    # Ensure no entities are created
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert len(entries) == 0
    # Ensure the config entry is marked as error
    assert mock_config_entry.state == ConfigEntryState.SETUP_ERROR

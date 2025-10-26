"""Test the Xbox sensor platform."""

from collections.abc import Generator
from unittest.mock import patch

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.xbox.const import DOMAIN
from homeassistant.components.xbox.sensor import XboxSensor
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture(autouse=True)
def sensor_only() -> Generator[None]:
    """Enable only the sensor platform."""
    with patch(
        "homeassistant.components.xbox.PLATFORMS",
        [Platform.SENSOR],
    ):
        yield


@pytest.mark.usefixtures("xbox_live_client", "entity_registry_enabled_by_default")
async def test_sensors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setup of the Xbox sensor platform."""

    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED

    await snapshot_platform(hass, entity_registry, snapshot, config_entry.entry_id)


@pytest.mark.parametrize(
    ("entity_id", "key"),
    [
        ("gsr_ae_account_tier", XboxSensor.ACCOUNT_TIER),
        ("gsr_ae_gold_tenure", XboxSensor.GOLD_TENURE),
    ],
)
@pytest.mark.usefixtures("xbox_live_client", "entity_registry_enabled_by_default")
async def test_sensor_deprecation_remove_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    entity_id: str,
    key: XboxSensor,
) -> None:
    """Test we remove a deprecated sensor."""

    entity_registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        f"271958441785640_{key}",
        suggested_object_id=entity_id,
    )

    assert entity_registry is not None

    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED

    assert entity_registry.async_get(f"sensor.{entity_id}") is None

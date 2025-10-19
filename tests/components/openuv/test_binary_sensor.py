"""Test OpenUV binary sensors."""

from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry, async_fire_time_changed, snapshot_platform


async def test_binary_sensors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_pyopenuv: None,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test all binary sensors created by the integration."""
    with patch("homeassistant.components.openuv.PLATFORMS", [Platform.BINARY_SENSOR]):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    await snapshot_platform(hass, entity_registry, snapshot, config_entry.entry_id)


async def test_protection_window_update(
    hass: HomeAssistant,
    set_time_zone,
    config,
    client,
    config_entry,
    setup_config_entry,
    snapshot: SnapshotAssertion,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that updating the protection window makes an extra API call."""

    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})

    assert client.uv_protection_window.call_count == 1

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: "binary_sensor.openuv_protection_window"},
        blocking=True,
    )

    assert client.uv_protection_window.call_count == 2


@pytest.mark.parametrize(
    "data_protection_window",
    [{"result": {"from_time": None, "from_uv": 0, "to_time": None, "to_uv": 0}}],
)
async def test_protection_window_null_value_response(
    hass: HomeAssistant,
    set_time_zone,
    config,
    client,
    config_entry,
    setup_config_entry,
) -> None:
    """Test that null values in the protection window clears the state."""

    entity_id = "binary_sensor.openuv_protection_window"
    hass.states.async_set(entity_id, "on", {})

    assert await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})

    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    state = hass.states.get(entity_id)
    assert state.state == "unknown"


@pytest.mark.parametrize(
    "data_protection_window",
    [{"result": {"error": "missing expected keys"}}],
)
async def test_protection_window_invalid_response(
    hass: HomeAssistant,
    set_time_zone,
    config,
    client,
    config_entry,
    mock_pyopenuv,
) -> None:
    """Test that missing values in the protection window generate an error."""

    assert await hass.config_entries.async_setup(config_entry.entry_id) is False
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_protection_window_recalculation(
    hass: HomeAssistant,
    config,
    config_entry,
    snapshot: SnapshotAssertion,
    set_time_zone,
    mock_pyopenuv,
    client,
    freezer: FrozenDateTimeFactory,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that protection window updates automatically without extra API calls."""

    freezer.move_to("2018-07-30T06:17:59-06:00")

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "binary_sensor.openuv_protection_window"
    state = hass.states.get(entity_id)
    assert state.state == "off"
    assert state == snapshot(name="before-protection-state")

    # move to when the protection window starts
    freezer.move_to("2018-07-30T09:17:59-06:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    entity_id = "binary_sensor.openuv_protection_window"
    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state == snapshot(name="during-protection-state")

    # move to when the protection window ends
    freezer.move_to("2018-07-30T16:47:59-06:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    entity_id = "binary_sensor.openuv_protection_window"
    state = hass.states.get(entity_id)
    assert state.state == "off"
    assert state == snapshot(name="after-protection-state")

    assert client.uv_protection_window.call_count == 1

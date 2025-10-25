"""The DALI Center integration."""

from __future__ import annotations

import logging

from PySrDaliGateway import DaliGateway
from PySrDaliGateway.exceptions import DaliGatewayError

from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_SERIAL_NUMBER, DOMAIN, MANUFACTURER
from .types import DaliCenterConfigEntry, DaliCenterData

_PLATFORMS: list[Platform] = [Platform.LIGHT]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: DaliCenterConfigEntry) -> bool:
    """Set up DALI Center from a config entry."""

    gateway = DaliGateway(
        entry.data[CONF_SERIAL_NUMBER],
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        name=entry.data[CONF_NAME],
    )
    gw_sn = gateway.gw_sn

    try:
        await gateway.connect()
    except DaliGatewayError as exc:
        raise ConfigEntryNotReady(
            "You can try to delete the gateway and add it again"
        ) from exc

    def on_online_status(dev_id: str, available: bool) -> None:
        signal = f"{DOMAIN}_update_available_{dev_id}"
        hass.add_job(async_dispatcher_send, hass, signal, available)

    gateway.on_online_status = on_online_status

    try:
        devices = await gateway.discover_devices()
    except DaliGatewayError as exc:
        raise ConfigEntryNotReady(
            "Unable to discover devices from the gateway"
        ) from exc

    _LOGGER.debug("Discovered %d devices on gateway %s", len(devices), gw_sn)

    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, gw_sn)},
        manufacturer=MANUFACTURER,
        name=gateway.name,
        model="SR-GW-EDA",
        serial_number=gw_sn,
    )

    entry.runtime_data = DaliCenterData(
        gateway=gateway,
        devices=devices,
    )
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DaliCenterConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, _PLATFORMS):
        await entry.runtime_data.gateway.disconnect()
    return unload_ok

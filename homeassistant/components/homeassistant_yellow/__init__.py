"""The Home Assistant Yellow integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.hassio import get_os_info
from homeassistant.components.homeassistant_hardware.coordinator import (
    FirmwareUpdateCoordinator,
)
from homeassistant.components.homeassistant_hardware.silabs_multiprotocol_addon import (
    check_multi_pan_addon,
)
from homeassistant.components.homeassistant_hardware.util import (
    ApplicationType,
    guess_firmware_info,
)
from homeassistant.config_entries import SOURCE_HARDWARE, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.hassio import is_hassio

from .const import (
    FIRMWARE,
    FIRMWARE_VERSION,
    NABU_CASA_FIRMWARE_RELEASES_URL,
    RADIO_DEVICE,
    ZHA_HW_DISCOVERY_DATA,
)

_LOGGER = logging.getLogger(__name__)

type HomeAssistantYellowConfigEntry = ConfigEntry[HomeAssistantYellowData]


@dataclass
class HomeAssistantYellowData:
    """Runtime data definition."""

    coordinator: (
        FirmwareUpdateCoordinator  # Type from homeassistant_hardware.coordinator
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: HomeAssistantYellowConfigEntry
) -> bool:
    """Set up a Home Assistant Yellow config entry."""
    if not is_hassio(hass):
        # Not running under supervisor, Home Assistant may have been migrated
        hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))
        return False

    if (os_info := get_os_info(hass)) is None:
        # The hassio integration has not yet fetched data from the supervisor
        raise ConfigEntryNotReady

    if os_info.get("board") != "yellow":
        # Not running on a Home Assistant Yellow, Home Assistant may have been migrated
        hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))
        return False

    firmware = ApplicationType(entry.data[FIRMWARE])

    # Auto start the multiprotocol addon if it is in use
    if firmware is ApplicationType.CPC:
        try:
            await check_multi_pan_addon(hass)
        except HomeAssistantError as err:
            raise ConfigEntryNotReady from err

    if firmware is ApplicationType.EZSP:
        discovery_flow.async_create_flow(
            hass,
            "zha",
            context={"source": SOURCE_HARDWARE},
            data=ZHA_HW_DISCOVERY_DATA,
        )

    # Create and store the firmware update coordinator in runtime_data
    session = async_get_clientsession(hass)
    coordinator = FirmwareUpdateCoordinator(
        hass,
        entry,
        session,
        NABU_CASA_FIRMWARE_RELEASES_URL,
    )
    entry.runtime_data = HomeAssistantYellowData(coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, ["switch", "update"])

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HomeAssistantYellowConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["switch", "update"])


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: HomeAssistantYellowConfigEntry
) -> bool:
    """Migrate old entry."""

    _LOGGER.debug(
        "Migrating from version %s.%s", config_entry.version, config_entry.minor_version
    )

    if config_entry.version == 1:
        if config_entry.minor_version == 1:
            # Add-on startup with type service get started before Core, always (e.g. the
            # Multi-Protocol add-on). Probing the firmware would interfere with the add-on,
            # so we can't safely probe here. Instead, we must make an educated guess!
            firmware_guess = await guess_firmware_info(hass, RADIO_DEVICE)

            new_data = {**config_entry.data}
            new_data[FIRMWARE] = firmware_guess.firmware_type.value

            hass.config_entries.async_update_entry(
                config_entry,
                data=new_data,
                version=1,
                minor_version=2,
            )

        if config_entry.minor_version <= 3:
            # Add a `firmware_version` key if it doesn't exist to handle entries created
            # with minor version 1.3 where the firmware version was not set.
            hass.config_entries.async_update_entry(
                config_entry,
                data={
                    **config_entry.data,
                    FIRMWARE_VERSION: config_entry.data.get(FIRMWARE_VERSION),
                },
                version=1,
                minor_version=4,
            )

        _LOGGER.debug(
            "Migration to version %s.%s successful",
            config_entry.version,
            config_entry.minor_version,
        )

        return True

    # This means the user has downgraded from a future version
    return False

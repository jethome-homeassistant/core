"""VOIP contact storage."""

from dataclasses import dataclass
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_VER

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceContact:
    """Device contact data."""

    contact: str


class DeviceContacts(dict[str, DeviceContact]):
    """Map of device contact data."""


class VoipStore(Store):
    """Store for VOIP device contact information."""

    def __init__(self, hass: HomeAssistant, storage_key: str) -> None:
        """Initialize the VOIP Storage."""
        super().__init__(hass, STORAGE_VER, f"voip-{storage_key}")

    async def async_load_devices(self) -> DeviceContacts:
        """Load data from store as DeviceContacts."""
        raw_data: dict[str, dict[str, str]] = await self.async_load() or {}
        return self._dict_to_devices(raw_data)

    async def async_update_device(self, voip_id: str, contact_header: str) -> None:
        """Update the device store with the contact information."""
        _LOGGER.debug("Saving new VOIP device %s contact %s", voip_id, contact_header)
        devices_data: DeviceContacts = await self.async_load_devices()
        _LOGGER.debug("devices_data: %s", devices_data)
        device_data: DeviceContact | None = devices_data.get(voip_id)
        if device_data is not None:
            device_data.contact = contact_header
        else:
            devices_data[voip_id] = DeviceContact(contact_header)
        await self.async_save(devices_data)
        _LOGGER.debug("Saved new VOIP device contact")

    def _dict_to_devices(self, raw_data: dict[str, dict[str, str]]) -> DeviceContacts:
        contacts = DeviceContacts()
        for k, v in (raw_data or {}).items():
            contacts[k] = DeviceContact(**v)
        return contacts

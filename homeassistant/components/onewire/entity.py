"""Support for 1-Wire entities."""

from __future__ import annotations

import logging
from typing import Any

from aio_ownet.exceptions import OWServerError
from aio_ownet.proxy import OWServerStatelessProxy

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

_LOGGER = logging.getLogger(__name__)


class OneWireEntity(Entity):
    """Implementation of a 1-Wire entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        description: EntityDescription,
        device_id: str,
        device_info: DeviceInfo,
        device_file: str,
        owproxy: OWServerStatelessProxy,
    ) -> None:
        """Initialize the entity."""
        self.entity_description = description
        self._last_update_success = True
        self._attr_unique_id = f"/{device_id}/{description.key}"
        self._attr_device_info = device_info
        self._device_file = device_file
        self._state: str | None = None
        self._owproxy = owproxy

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes of the entity."""
        return {
            "device_file": self._device_file,
        }

    async def _write_value(self, value: bytes) -> None:
        """Write a value to the server."""
        await self._owproxy.write(self._device_file, value)

    async def async_update(self) -> None:
        """Get the latest data from the device."""
        try:
            state = await self._owproxy.read(self._device_file)
        except OWServerError as exc:
            if self._last_update_success:
                _LOGGER.error("Error fetching %s data: %s", self.name, exc)
                self._last_update_success = False
            self._state = None
        else:
            if not self._last_update_success:
                self._last_update_success = True
                _LOGGER.debug("Fetching %s data recovered", self.name)
            self._state = state.decode("ascii").strip()

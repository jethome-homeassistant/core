"""OpenRGB light platform."""

from __future__ import annotations

import asyncio
from typing import Any

from openrgb.orgb import Device
from openrgb.utils import ModeColors, ModeData, RGBColor

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    EFFECT_OFF,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from homeassistant.util.color import color_hs_to_RGB, color_RGB_to_hsv

from .const import (
    CONNECTION_ERRORS,
    DEFAULT_BRIGHTNESS,
    DEFAULT_COLOR,
    DEVICE_TYPE_ICONS,
    DOMAIN,
    EFFECT_OFF_OPENRGB_MODES,
    OFF_COLOR,
    OpenRGBMode,
)
from .coordinator import OpenRGBConfigEntry, OpenRGBCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OpenRGBConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the OpenRGB light platform."""
    coordinator = config_entry.runtime_data
    known_device_keys: set[str] = set()

    def _check_device() -> None:
        """Add entities for newly discovered OpenRGB devices."""
        nonlocal known_device_keys
        current_keys = set(coordinator.data.keys())
        new_keys = current_keys - known_device_keys
        if new_keys:
            known_device_keys.update(new_keys)
            async_add_entities(
                [OpenRGBLight(coordinator, device_key) for device_key in new_keys]
            )

    _check_device()
    config_entry.async_on_unload(coordinator.async_add_listener(_check_device))


class OpenRGBLight(CoordinatorEntity[OpenRGBCoordinator], LightEntity):
    """Representation of an OpenRGB light."""

    _attr_has_entity_name = True
    _attr_name = None  # Use the device name
    _attr_translation_key = "openrgb_light"

    _mode: str | None = None

    _supports_color_modes: list[str]
    _preferred_no_effect_mode: str
    _supports_off_mode: bool
    _supports_effects: bool

    _previous_brightness: int | None = None
    _previous_rgb_color: tuple[int, int, int] | None = None
    _previous_mode: str | None = None

    _update_events: list[asyncio.Event] = []

    _effect_to_mode: dict[str, str]

    def __init__(self, coordinator: OpenRGBCoordinator, device_key: str) -> None:
        """Initialize the OpenRGB light."""
        super().__init__(coordinator)
        self.device_key = device_key
        self._attr_unique_id = device_key

        device_name = coordinator.get_device_name(device_key)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=device_name,
            manufacturer=self.device.metadata.vendor,
            model=f"{self.device.metadata.description} ({self.device.type.name})",
            sw_version=self.device.metadata.version,
            serial_number=self.device.metadata.serial,
            via_device=(DOMAIN, coordinator.entry_id),
        )

        modes = [mode.name for mode in self.device.modes]

        if self.device.metadata.description == "ASRock Polychrome USB Device":
            # https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/5145
            self._preferred_no_effect_mode = OpenRGBMode.STATIC
        else:
            # https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c71cc4f18a54f83d388165ef2ab4c4ad3e980b89/RGBController/RGBController.cpp#L2075-2081
            self._preferred_no_effect_mode = (
                OpenRGBMode.DIRECT
                if OpenRGBMode.DIRECT in modes
                else OpenRGBMode.CUSTOM
                if OpenRGBMode.CUSTOM in modes
                else OpenRGBMode.STATIC
            )
        # Determine if the device supports being turned off through modes
        self._supports_off_mode = OpenRGBMode.OFF in modes
        # Determine which modes supports color
        self._supports_color_modes = [
            mode.name
            for mode in self.device.modes
            if check_if_mode_supports_color(mode)
        ]

        # Initialize effects from modes
        self._effect_to_mode = {}
        effects = []
        for mode in modes:
            if mode != OpenRGBMode.OFF and mode not in EFFECT_OFF_OPENRGB_MODES:
                effect_name = slugify(mode)
                effects.append(effect_name)
                self._effect_to_mode[effect_name] = mode

        if len(effects) > 0:
            self._supports_effects = True
            self._attr_supported_features = LightEntityFeature.EFFECT
            self._attr_effect_list = [EFFECT_OFF, *effects]
        else:
            self._supports_effects = False

        self._attr_icon = DEVICE_TYPE_ICONS.get(self.device.type)

        self._update_attrs()

    @callback
    def _update_attrs(self) -> None:
        """Update the attributes based on the current device state."""
        mode_data = self.device.modes[self.device.active_mode]
        mode = mode_data.name
        if mode == OpenRGBMode.OFF:
            mode = None
            mode_supports_colors = False
        else:
            mode_supports_colors = check_if_mode_supports_color(mode_data)

        color_mode = None
        rgb_color = None
        brightness = None
        on_by_color = True
        if mode_supports_colors:
            # Consider the first non-black LED color as the device color
            openrgb_off_color = RGBColor(*OFF_COLOR)
            openrgb_color = next(
                (color for color in self.device.colors if color != openrgb_off_color),
                openrgb_off_color,
            )

            if openrgb_color == openrgb_off_color:
                on_by_color = False
            else:
                rgb_color = (
                    openrgb_color.red,
                    openrgb_color.green,
                    openrgb_color.blue,
                )
                # Derive color and brightness from the scaled color
                hsv_color = color_RGB_to_hsv(*rgb_color)
                rgb_color = color_hs_to_RGB(hsv_color[0], hsv_color[1])
                brightness = round(255.0 * (hsv_color[2] / 100.0))

        elif mode is None:
            # If mode is Off, retain previous color mode to avoid changing the UI
            color_mode = self._attr_color_mode
        else:
            # If the current mode is not Off and does not support color, change to ON/OFF mode
            color_mode = ColorMode.ONOFF

        if not on_by_color:
            # If Off by color, retain previous color mode to avoid changing the UI
            color_mode = self._attr_color_mode

        if color_mode is None:
            # If color mode is still None, default to RGB
            color_mode = ColorMode.RGB

        if self._attr_brightness is not None and self._attr_brightness != brightness:
            self._previous_brightness = self._attr_brightness
        if self._attr_rgb_color is not None and self._attr_rgb_color != rgb_color:
            self._previous_rgb_color = self._attr_rgb_color
        if self._mode is not None and self._mode != mode:
            self._previous_mode = self._mode

        self._attr_color_mode = color_mode
        self._attr_supported_color_modes = {color_mode}
        self._attr_rgb_color = rgb_color
        self._attr_brightness = brightness
        if not self._supports_effects or mode is None:
            self._attr_effect = None
        elif mode in EFFECT_OFF_OPENRGB_MODES:
            self._attr_effect = EFFECT_OFF
        else:
            self._attr_effect = slugify(mode)
        self._mode = mode

        if mode is None:
            # If the mode is Off, the light is off
            self._attr_is_on = False
        else:
            self._attr_is_on = on_by_color

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.available:
            self._update_attrs()
        super()._handle_coordinator_update()

        # Signal that the update has completed for all waiting events
        for event in self._update_events:
            event.set()
        self._update_events.clear()

    @property
    def available(self) -> bool:
        """Return if the light is available."""
        return super().available and self.device_key in self.coordinator.data

    @property
    def device(self) -> Device:
        """Return the OpenRGB device."""
        return self.coordinator.data[self.device_key]

    async def _async_refresh_data(self) -> None:
        """Request a data refresh from the coordinator and wait for it to complete."""
        update_event = asyncio.Event()
        self._update_events.append(update_event)
        await self.coordinator.async_request_refresh()
        await update_event.wait()

    async def _async_apply_color(
        self, rgb_color: tuple[int, int, int], brightness: int
    ) -> None:
        """Apply the RGB color and brightness to the device."""
        brightness_factor = brightness / 255.0
        scaled_color = RGBColor(
            int(rgb_color[0] * brightness_factor),
            int(rgb_color[1] * brightness_factor),
            int(rgb_color[2] * brightness_factor),
        )

        async with self.coordinator.client_lock:
            try:
                await self.hass.async_add_executor_job(
                    self.device.set_color, scaled_color, True
                )
            except CONNECTION_ERRORS as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="communication_error",
                    translation_placeholders={
                        "server_address": self.coordinator.server_address,
                        "error": str(err),
                    },
                ) from err
            except ValueError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="openrgb_error",
                    translation_placeholders={
                        "error": str(err),
                    },
                ) from err

    async def _async_apply_mode(self, mode: str) -> None:
        """Apply the given mode to the device."""
        async with self.coordinator.client_lock:
            try:
                await self.hass.async_add_executor_job(self.device.set_mode, mode)
            except CONNECTION_ERRORS as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="communication_error",
                    translation_placeholders={
                        "server_address": self.coordinator.server_address,
                        "error": str(err),
                    },
                ) from err
            except ValueError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="openrgb_error",
                    translation_placeholders={
                        "error": str(err),
                    },
                ) from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        mode = None
        if ATTR_EFFECT in kwargs:
            effect = kwargs[ATTR_EFFECT]
            if self._attr_effect_list is None or effect not in self._attr_effect_list:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="unsupported_effect",
                    translation_placeholders={
                        "effect": effect,
                        "device_name": self.device.name,
                    },
                )
            if effect == EFFECT_OFF:
                mode = self._preferred_no_effect_mode
            else:
                mode = self._effect_to_mode[effect]
        elif self._mode is None or (
            self._attr_rgb_color is None and self._attr_brightness is None
        ):
            # Restore previous mode when turning on from Off mode or black color
            mode = self._previous_mode or self._preferred_no_effect_mode

        # Check if current or new mode supports colors
        if mode is None:
            # When not applying a new mode, check if the current mode supports color
            mode_supports_color = self._mode in self._supports_color_modes
        else:
            mode_supports_color = mode in self._supports_color_modes

        color_or_brightness_requested = (
            ATTR_RGB_COLOR in kwargs or ATTR_BRIGHTNESS in kwargs
        )
        if color_or_brightness_requested and not mode_supports_color:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="effect_no_color_support",
                translation_placeholders={
                    "effect": slugify(mode or self._mode or ""),
                    "device_name": self.device.name,
                },
            )

        # Apply color even if switching from Off mode to a color-capable mode
        # because there is no guarantee that the device won't go back to black
        need_to_apply_color = color_or_brightness_requested or (
            mode_supports_color
            and (self._attr_brightness is None or self._attr_rgb_color is None)
        )

        # If color/brightness restoration require color support but mode doesn't support it,
        # switch to a color-capable mode
        if need_to_apply_color and not mode_supports_color:
            mode = self._preferred_no_effect_mode

        if mode is not None:
            await self._async_apply_mode(mode)

        if need_to_apply_color:
            brightness = None
            if ATTR_BRIGHTNESS in kwargs:
                brightness = kwargs[ATTR_BRIGHTNESS]
            elif self._attr_brightness is None:
                # Restore previous brightness when turning on
                brightness = self._previous_brightness
            if brightness is None:
                # Retain current brightness or use default if still None
                brightness = self._attr_brightness or DEFAULT_BRIGHTNESS

            color = None
            if ATTR_RGB_COLOR in kwargs:
                color = kwargs[ATTR_RGB_COLOR]
            elif self._attr_rgb_color is None:
                # Restore previous color when turning on
                color = self._previous_rgb_color
            if color is None:
                # Retain current color or use default if still None
                color = self._attr_rgb_color or DEFAULT_COLOR

            await self._async_apply_color(color, brightness)

        await self._async_refresh_data()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        if self._supports_off_mode:
            await self._async_apply_mode(OpenRGBMode.OFF)
        else:
            # If the device does not support Off mode, set color to black
            await self._async_apply_color(OFF_COLOR, 0)

        await self._async_refresh_data()


def check_if_mode_supports_color(mode: ModeData) -> bool:
    """Return True if the mode supports colors."""
    return mode.color_mode == ModeColors.PER_LED

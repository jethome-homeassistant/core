"""Sensor platform for the Xbox integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial

from xbox.webapi.api.provider.people.models import Person

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import XboxConfigEntry, XboxUpdateCoordinator
from .entity import XboxBaseEntity, check_deprecated_entity


class XboxSensor(StrEnum):
    """Xbox sensor."""

    STATUS = "status"
    GAMER_SCORE = "gamer_score"
    ACCOUNT_TIER = "account_tier"
    GOLD_TENURE = "gold_tenure"
    LAST_ONLINE = "last_online"
    FOLLOWING = "following"
    FOLLOWER = "follower"


@dataclass(kw_only=True, frozen=True)
class XboxSensorEntityDescription(SensorEntityDescription):
    """Xbox sensor description."""

    value_fn: Callable[[Person], StateType | datetime]
    deprecated: bool | None = None


SENSOR_DESCRIPTIONS: tuple[XboxSensorEntityDescription, ...] = (
    XboxSensorEntityDescription(
        key=XboxSensor.STATUS,
        translation_key=XboxSensor.STATUS,
        value_fn=lambda x: x.presence_text,
    ),
    XboxSensorEntityDescription(
        key=XboxSensor.GAMER_SCORE,
        translation_key=XboxSensor.GAMER_SCORE,
        value_fn=lambda x: x.gamer_score,
    ),
    XboxSensorEntityDescription(
        key=XboxSensor.ACCOUNT_TIER,
        value_fn=lambda _: None,
        deprecated=True,
    ),
    XboxSensorEntityDescription(
        key=XboxSensor.GOLD_TENURE,
        value_fn=lambda _: None,
        deprecated=True,
    ),
    XboxSensorEntityDescription(
        key=XboxSensor.LAST_ONLINE,
        translation_key=XboxSensor.LAST_ONLINE,
        value_fn=(
            lambda x: x.last_seen_date_time_utc.replace(tzinfo=UTC)
            if x.last_seen_date_time_utc
            else None
        ),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    XboxSensorEntityDescription(
        key=XboxSensor.FOLLOWING,
        translation_key=XboxSensor.FOLLOWING,
        value_fn=lambda x: x.detail.following_count if x.detail else None,
    ),
    XboxSensorEntityDescription(
        key=XboxSensor.FOLLOWER,
        translation_key=XboxSensor.FOLLOWER,
        value_fn=lambda x: x.detail.follower_count if x.detail else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: XboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Xbox Live friends."""
    coordinator = config_entry.runtime_data

    update_friends = partial(
        async_update_friends, hass, coordinator, {}, async_add_entities
    )

    config_entry.async_on_unload(coordinator.async_add_listener(update_friends))
    update_friends()


class XboxSensorEntity(XboxBaseEntity, SensorEntity):
    """Representation of a Xbox presence state."""

    entity_description: XboxSensorEntityDescription

    @property
    def native_value(self) -> StateType | datetime:
        """Return the state of the requested attribute."""
        return self.entity_description.value_fn(self.data)


@callback
def async_update_friends(
    hass: HomeAssistant,
    coordinator: XboxUpdateCoordinator,
    current: dict[str, list[XboxSensorEntity]],
    async_add_entities,
) -> None:
    """Update friends."""
    new_ids = set(coordinator.data.presence)
    current_ids = set(current)

    # Process new favorites, add them to Home Assistant
    new_entities: list[XboxSensorEntity] = []
    for xuid in new_ids - current_ids:
        current[xuid] = []
        for description in SENSOR_DESCRIPTIONS:
            entity = XboxSensorEntity(coordinator, xuid, description)
            if check_deprecated_entity(hass, entity, SENSOR_DOMAIN):
                current[xuid].append(entity)
        new_entities = new_entities + current[xuid]
    if new_entities:
        async_add_entities(new_entities)

    # Process deleted favorites, remove them from Home Assistant
    for xuid in current_ids - new_ids:
        del current[xuid]

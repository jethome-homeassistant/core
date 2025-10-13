"""Test KNX sensor."""

from freezegun.api import FrozenDateTimeFactory

from homeassistant.components.knx.const import CONF_STATE_ADDRESS, CONF_SYNC_STATE
from homeassistant.components.knx.schema import SensorSchema
from homeassistant.const import CONF_NAME, CONF_TYPE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import KNXTestKit

from tests.common import async_capture_events, async_fire_time_changed


async def test_sensor(hass: HomeAssistant, knx: KNXTestKit) -> None:
    """Test simple KNX sensor."""

    await knx.setup_integration(
        {
            SensorSchema.PLATFORM: {
                CONF_NAME: "test",
                CONF_STATE_ADDRESS: "1/1/1",
                CONF_TYPE: "current",  # 2 byte unsigned int
            }
        }
    )
    state = hass.states.get("sensor.test")
    assert state.state is STATE_UNKNOWN

    # StateUpdater initialize state
    await knx.assert_read("1/1/1")
    await knx.receive_response("1/1/1", (0, 40))
    state = hass.states.get("sensor.test")
    assert state.state == "40"

    # update from KNX
    await knx.receive_write("1/1/1", (0x03, 0xE8))
    state = hass.states.get("sensor.test")
    assert state.state == "1000"

    # don't answer to GroupValueRead requests
    await knx.receive_read("1/1/1")
    await knx.assert_no_telegram()


async def test_last_reported(
    hass: HomeAssistant,
    knx: KNXTestKit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test KNX sensor properly sets last_reported."""

    await knx.setup_integration(
        {
            SensorSchema.PLATFORM: [
                {
                    CONF_NAME: "test",
                    CONF_STATE_ADDRESS: "1/1/1",
                    CONF_SYNC_STATE: False,
                    CONF_TYPE: "percentU8",
                },
            ]
        }
    )
    events = async_capture_events(hass, "state_changed")

    # receive initial telegram
    await knx.receive_write("1/1/1", (0x42,))
    first_reported = hass.states.get("sensor.test").last_reported
    assert len(events) == 1

    # receive second telegram with identical payload
    freezer.tick(1)
    async_fire_time_changed(hass)
    await knx.receive_write("1/1/1", (0x42,))

    assert first_reported != hass.states.get("sensor.test").last_reported
    assert len(events) == 1, events  # last_reported shall not fire state_changed


async def test_always_callback(hass: HomeAssistant, knx: KNXTestKit) -> None:
    """Test KNX sensor with always_callback."""

    await knx.setup_integration(
        {
            SensorSchema.PLATFORM: [
                {
                    CONF_NAME: "test_normal",
                    CONF_STATE_ADDRESS: "1/1/1",
                    CONF_SYNC_STATE: False,
                    CONF_TYPE: "percentU8",
                },
                {
                    CONF_NAME: "test_always",
                    CONF_STATE_ADDRESS: "2/2/2",
                    SensorSchema.CONF_ALWAYS_CALLBACK: True,
                    CONF_SYNC_STATE: False,
                    CONF_TYPE: "percentU8",
                },
            ]
        }
    )
    events = async_capture_events(hass, "state_changed")

    # receive initial telegram
    await knx.receive_write("1/1/1", (0x42,))
    await knx.receive_write("2/2/2", (0x42,))
    assert len(events) == 2

    # receive second telegram with identical payload
    # always_callback shall force state_changed event
    await knx.receive_write("1/1/1", (0x42,))
    await knx.receive_write("2/2/2", (0x42,))
    assert len(events) == 3

    # receive telegram with different payload
    await knx.receive_write("1/1/1", (0xFA,))
    await knx.receive_write("2/2/2", (0xFA,))
    assert len(events) == 5

    # receive telegram with second payload again
    # always_callback shall force state_changed event
    await knx.receive_write("1/1/1", (0xFA,))
    await knx.receive_write("2/2/2", (0xFA,))
    assert len(events) == 6

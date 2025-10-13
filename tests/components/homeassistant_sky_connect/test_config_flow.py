"""Test the Home Assistant SkyConnect config flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from homeassistant.components.hassio import AddonInfo, AddonState
from homeassistant.components.homeassistant_hardware.firmware_config_flow import (
    STEP_PICK_FIRMWARE_THREAD,
    STEP_PICK_FIRMWARE_ZIGBEE,
)
from homeassistant.components.homeassistant_hardware.helpers import (
    async_notify_firmware_info,
)
from homeassistant.components.homeassistant_hardware.silabs_multiprotocol_addon import (
    CONF_DISABLE_MULTI_PAN,
    get_flasher_addon_manager,
    get_multiprotocol_addon_manager,
)
from homeassistant.components.homeassistant_hardware.util import (
    ApplicationType,
    FirmwareInfo,
)
from homeassistant.components.homeassistant_sky_connect.const import DOMAIN
from homeassistant.components.usb import USBDevice
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.usb import UsbServiceInfo
from homeassistant.setup import async_setup_component

from .common import USB_DATA_SKY, USB_DATA_ZBT1

from tests.common import MockConfigEntry


@pytest.fixture(name="supervisor")
def mock_supervisor_fixture() -> Generator[None]:
    """Mock Supervisor."""
    with patch(
        "homeassistant.components.homeassistant_hardware.firmware_config_flow.is_hassio",
        return_value=True,
    ):
        yield


@pytest.fixture(name="setup_entry", autouse=True)
def setup_entry_fixture() -> Generator[AsyncMock]:
    """Mock entry setup."""
    with patch(
        "homeassistant.components.homeassistant_sky_connect.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.mark.parametrize(
    ("usb_data", "model"),
    [
        (
            USB_DATA_SKY,
            "Home Assistant SkyConnect",
        ),
        (
            USB_DATA_ZBT1,
            "Home Assistant Connect ZBT-1",
        ),
    ],
)
async def test_config_flow_zigbee(
    usb_data: UsbServiceInfo,
    model: str,
    hass: HomeAssistant,
) -> None:
    """Test the config flow for SkyConnect with Zigbee."""
    fw_type = ApplicationType.EZSP
    fw_version = "7.4.4.0 build 0"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "usb"}, data=usb_data
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "pick_firmware"
    description_placeholders = result["description_placeholders"]
    assert description_placeholders is not None
    assert description_placeholders["model"] == model

    async def mock_install_firmware_step(
        self,
        fw_update_url: str,
        fw_type: str,
        firmware_name: str,
        expected_installed_firmware_type: ApplicationType,
        step_id: str,
        next_step_id: str,
    ) -> ConfigFlowResult:
        self._probed_firmware_info = FirmwareInfo(
            device=usb_data.device,
            firmware_type=expected_installed_firmware_type,
            firmware_version=fw_version,
            owners=[],
            source="probe",
        )
        return await getattr(self, f"async_step_{next_step_id}")()

    with (
        patch(
            "homeassistant.components.homeassistant_hardware.firmware_config_flow.BaseFirmwareConfigFlow._install_firmware_step",
            autospec=True,
            side_effect=mock_install_firmware_step,
        ),
    ):
        pick_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"next_step_id": STEP_PICK_FIRMWARE_ZIGBEE},
        )

        assert pick_result["type"] is FlowResultType.MENU
        assert pick_result["step_id"] == "zigbee_installation_type"

        create_result = await hass.config_entries.flow.async_configure(
            pick_result["flow_id"],
            user_input={"next_step_id": "zigbee_intent_recommended"},
        )

    assert create_result["type"] is FlowResultType.CREATE_ENTRY
    config_entry = create_result["result"]
    assert config_entry.data == {
        "firmware": fw_type.value,
        "firmware_version": fw_version,
        "device": usb_data.device,
        "manufacturer": usb_data.manufacturer,
        "pid": usb_data.pid,
        "description": usb_data.description,
        "product": usb_data.description,
        "serial_number": usb_data.serial_number,
        "vid": usb_data.vid,
    }

    flows = hass.config_entries.flow.async_progress()

    # Ensure a ZHA discovery flow has been created
    assert len(flows) == 1
    zha_flow = flows[0]
    assert zha_flow["handler"] == "zha"
    assert zha_flow["context"]["source"] == "hardware"
    assert zha_flow["step_id"] == "confirm"


@pytest.mark.usefixtures("addon_installed", "supervisor")
@pytest.mark.parametrize(
    ("usb_data", "model"),
    [
        (
            USB_DATA_SKY,
            "Home Assistant SkyConnect",
        ),
        (
            USB_DATA_ZBT1,
            "Home Assistant Connect ZBT-1",
        ),
    ],
)
async def test_config_flow_thread(
    usb_data: UsbServiceInfo,
    model: str,
    hass: HomeAssistant,
    start_addon: AsyncMock,
) -> None:
    """Test the config flow for SkyConnect with Thread."""
    fw_type = ApplicationType.SPINEL
    fw_version = "2.4.4.0"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "usb"}, data=usb_data
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "pick_firmware"
    description_placeholders = result["description_placeholders"]
    assert description_placeholders is not None
    assert description_placeholders["model"] == model

    async def mock_install_firmware_step(
        self,
        fw_update_url: str,
        fw_type: str,
        firmware_name: str,
        expected_installed_firmware_type: ApplicationType,
        step_id: str,
        next_step_id: str,
    ) -> ConfigFlowResult:
        self._probed_firmware_info = FirmwareInfo(
            device=usb_data.device,
            firmware_type=expected_installed_firmware_type,
            firmware_version=fw_version,
            owners=[],
            source="probe",
        )
        return await getattr(self, f"async_step_{next_step_id}")()

    with (
        patch(
            "homeassistant.components.homeassistant_hardware.firmware_config_flow.BaseFirmwareConfigFlow._install_firmware_step",
            autospec=True,
            side_effect=mock_install_firmware_step,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"next_step_id": STEP_PICK_FIRMWARE_THREAD},
        )

        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "start_otbr_addon"

        # Make sure the flow continues when the progress task is done.
        await hass.async_block_till_done()

        create_result = await hass.config_entries.flow.async_configure(
            result["flow_id"]
        )

    assert start_addon.call_count == 1
    assert start_addon.call_args == call("core_openthread_border_router")
    assert create_result["type"] is FlowResultType.CREATE_ENTRY
    config_entry = create_result["result"]
    assert config_entry.data == {
        "firmware": fw_type.value,
        "firmware_version": fw_version,
        "device": usb_data.device,
        "manufacturer": usb_data.manufacturer,
        "pid": usb_data.pid,
        "description": usb_data.description,
        "product": usb_data.description,
        "serial_number": usb_data.serial_number,
        "vid": usb_data.vid,
    }

    flows = hass.config_entries.flow.async_progress()

    assert len(flows) == 0


@pytest.mark.parametrize(
    ("usb_data", "model"),
    [
        (USB_DATA_SKY, "Home Assistant SkyConnect"),
        (USB_DATA_ZBT1, "Home Assistant Connect ZBT-1"),
    ],
)
async def test_options_flow(
    usb_data: UsbServiceInfo, model: str, hass: HomeAssistant
) -> None:
    """Test the options flow for SkyConnect."""
    config_entry = MockConfigEntry(
        domain="homeassistant_sky_connect",
        data={
            "firmware": "spinel",
            "device": usb_data.device,
            "manufacturer": usb_data.manufacturer,
            "pid": usb_data.pid,
            "description": usb_data.description,
            "product": usb_data.description,
            "serial_number": usb_data.serial_number,
            "vid": usb_data.vid,
        },
        version=1,
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)

    # First step is confirmation
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "pick_firmware"
    description_placeholders = result["description_placeholders"]
    assert description_placeholders is not None
    assert description_placeholders["firmware_type"] == "spinel"
    assert description_placeholders["model"] == model

    async def mock_install_firmware_step(
        self,
        fw_update_url: str,
        fw_type: str,
        firmware_name: str,
        expected_installed_firmware_type: ApplicationType,
        step_id: str,
        next_step_id: str,
    ) -> ConfigFlowResult:
        self._probed_firmware_info = FirmwareInfo(
            device=usb_data.device,
            firmware_type=expected_installed_firmware_type,
            firmware_version="7.4.4.0 build 0",
            owners=[],
            source="probe",
        )
        return await getattr(self, f"async_step_{next_step_id}")()

    with (
        patch(
            "homeassistant.components.homeassistant_hardware.firmware_config_flow.guess_hardware_owners",
            return_value=[],
        ),
        patch(
            "homeassistant.components.homeassistant_hardware.firmware_config_flow.BaseFirmwareOptionsFlow._install_firmware_step",
            autospec=True,
            side_effect=mock_install_firmware_step,
        ),
    ):
        pick_result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"next_step_id": STEP_PICK_FIRMWARE_ZIGBEE},
        )

        assert pick_result["type"] is FlowResultType.MENU
        assert pick_result["step_id"] == "zigbee_installation_type"

        create_result = await hass.config_entries.options.async_configure(
            pick_result["flow_id"],
            user_input={"next_step_id": "zigbee_intent_recommended"},
        )

    assert create_result["type"] is FlowResultType.CREATE_ENTRY

    assert config_entry.data == {
        "firmware": "ezsp",
        "firmware_version": "7.4.4.0 build 0",
        "device": usb_data.device,
        "manufacturer": usb_data.manufacturer,
        "pid": usb_data.pid,
        "description": usb_data.description,
        "product": usb_data.description,
        "serial_number": usb_data.serial_number,
        "vid": usb_data.vid,
    }


@pytest.mark.usefixtures("supervisor_client")
@pytest.mark.parametrize(
    ("usb_data", "model"),
    [
        (USB_DATA_SKY, "Home Assistant SkyConnect"),
        (USB_DATA_ZBT1, "Home Assistant Connect ZBT-1"),
    ],
)
async def test_options_flow_multipan_uninstall(
    usb_data: UsbServiceInfo, model: str, hass: HomeAssistant
) -> None:
    """Test options flow for when multi-PAN firmware is installed."""
    config_entry = MockConfigEntry(
        domain="homeassistant_sky_connect",
        data={
            "firmware": "cpc",
            "device": usb_data.device,
            "manufacturer": usb_data.manufacturer,
            "pid": usb_data.pid,
            "product": usb_data.description,
            "serial_number": usb_data.serial_number,
            "vid": usb_data.vid,
        },
        version=1,
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)

    # Multi-PAN addon is running
    mock_multipan_manager = Mock(spec_set=await get_multiprotocol_addon_manager(hass))
    mock_multipan_manager.async_get_addon_info.return_value = AddonInfo(
        available=True,
        hostname=None,
        options={"device": usb_data.device},
        state=AddonState.RUNNING,
        update_available=False,
        version="1.0.0",
    )

    mock_flasher_manager = Mock(spec_set=get_flasher_addon_manager(hass))
    mock_flasher_manager.async_get_addon_info.return_value = AddonInfo(
        available=True,
        hostname=None,
        options={},
        state=AddonState.NOT_RUNNING,
        update_available=False,
        version="1.0.0",
    )

    with (
        patch(
            "homeassistant.components.homeassistant_hardware.silabs_multiprotocol_addon.get_multiprotocol_addon_manager",
            return_value=mock_multipan_manager,
        ),
        patch(
            "homeassistant.components.homeassistant_hardware.silabs_multiprotocol_addon.get_flasher_addon_manager",
            return_value=mock_flasher_manager,
        ),
        patch(
            "homeassistant.components.homeassistant_hardware.silabs_multiprotocol_addon.is_hassio",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        assert result["type"] is FlowResultType.MENU
        assert result["step_id"] == "addon_menu"
        assert "uninstall_addon" in result["menu_options"]

        # Pick the uninstall option
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"next_step_id": "uninstall_addon"},
        )

        # Check the box
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_DISABLE_MULTI_PAN: True}
        )

        # Finish the flow
        result = await hass.config_entries.options.async_configure(result["flow_id"])
        await hass.async_block_till_done(wait_background_tasks=True)
        result = await hass.config_entries.options.async_configure(result["flow_id"])
        await hass.async_block_till_done(wait_background_tasks=True)
        result = await hass.config_entries.options.async_configure(result["flow_id"])
        assert result["type"] is FlowResultType.CREATE_ENTRY

    # We've reverted the firmware back to Zigbee
    assert config_entry.data["firmware"] == "ezsp"


@pytest.mark.parametrize(
    ("usb_data", "model"),
    [
        (USB_DATA_SKY, "Home Assistant SkyConnect"),
        (USB_DATA_ZBT1, "Home Assistant Connect ZBT-1"),
    ],
)
async def test_firmware_callback_auto_creates_entry(
    usb_data: UsbServiceInfo,
    model: str,
    hass: HomeAssistant,
) -> None:
    """Test that firmware notification triggers import flow that auto-creates config entry."""
    await async_setup_component(hass, "homeassistant_hardware", {})
    await async_setup_component(hass, "usb", {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "usb"}, data=usb_data
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "pick_firmware"

    usb_device = USBDevice(
        device=usb_data.device,
        vid=usb_data.vid,
        pid=usb_data.pid,
        serial_number=usb_data.serial_number,
        manufacturer=usb_data.manufacturer,
        description=usb_data.description,
    )

    with patch(
        "homeassistant.components.homeassistant_hardware.helpers.usb_device_from_path",
        return_value=usb_device,
    ):
        await async_notify_firmware_info(
            hass,
            "zha",
            FirmwareInfo(
                device=usb_data.device,
                firmware_type=ApplicationType.EZSP,
                firmware_version="7.4.4.0",
                owners=[],
                source="zha",
            ),
        )

        await hass.async_block_till_done()

    # The config entry was auto-created
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].data == {
        "device": usb_data.device,
        "firmware": ApplicationType.EZSP.value,
        "firmware_version": "7.4.4.0",
        "vid": usb_data.vid,
        "pid": usb_data.pid,
        "serial_number": usb_data.serial_number,
        "manufacturer": usb_data.manufacturer,
        "description": usb_data.description,
        "product": usb_data.description,
    }

    # The discovery flow is gone
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


@pytest.mark.parametrize(
    ("usb_data", "model"),
    [
        (USB_DATA_SKY, "Home Assistant SkyConnect"),
        (USB_DATA_ZBT1, "Home Assistant Connect ZBT-1"),
    ],
)
async def test_duplicate_usb_discovery_aborts_early(
    usb_data: UsbServiceInfo, model: str, hass: HomeAssistant
) -> None:
    """Test USB discovery aborts early when unique_id exists before serial path resolution."""
    # Create existing config entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "firmware": "ezsp",
            "device": "/dev/oldpath",
            "manufacturer": usb_data.manufacturer,
            "pid": usb_data.pid,
            "description": usb_data.description,
            "product": usb_data.description,
            "serial_number": usb_data.serial_number,
            "vid": usb_data.vid,
        },
        unique_id=(
            f"{usb_data.vid}:{usb_data.pid}_"
            f"{usb_data.serial_number}_"
            f"{usb_data.manufacturer}_"
            f"{usb_data.description}"
        ),
    )
    config_entry.add_to_hass(hass)

    # Try to discover the same device with a different path
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "usb"}, data=usb_data
    )

    # Should abort before get_serial_by_id is called
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("usb_data", "model"),
    [
        (USB_DATA_SKY, "Home Assistant SkyConnect"),
        (USB_DATA_ZBT1, "Home Assistant Connect ZBT-1"),
    ],
)
async def test_firmware_callback_updates_existing_entry(
    usb_data: UsbServiceInfo, model: str, hass: HomeAssistant
) -> None:
    """Test that firmware notification updates existing config entry device path."""
    await async_setup_component(hass, "homeassistant_hardware", {})
    await async_setup_component(hass, "usb", {})

    # Create existing config entry with old device path
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "firmware": ApplicationType.EZSP.value,
            "firmware_version": "7.4.4.0",
            "device": "/dev/oldpath",
            "vid": usb_data.vid,
            "pid": usb_data.pid,
            "serial_number": usb_data.serial_number,
            "manufacturer": usb_data.manufacturer,
            "description": usb_data.description,
            "product": usb_data.description,
        },
        unique_id=(
            f"{usb_data.vid}:{usb_data.pid}_"
            f"{usb_data.serial_number}_"
            f"{usb_data.manufacturer}_"
            f"{usb_data.description}"
        ),
    )
    config_entry.add_to_hass(hass)

    usb_device = USBDevice(
        device=usb_data.device,
        vid=usb_data.vid,
        pid=usb_data.pid,
        serial_number=usb_data.serial_number,
        manufacturer=usb_data.manufacturer,
        description=usb_data.description,
    )

    with patch(
        "homeassistant.components.homeassistant_hardware.helpers.usb_device_from_path",
        return_value=usb_device,
    ):
        await async_notify_firmware_info(
            hass,
            "zha",
            FirmwareInfo(
                device=usb_data.device,
                firmware_type=ApplicationType.EZSP,
                firmware_version="7.4.4.0",
                owners=[],
                source="zha",
            ),
        )

        await hass.async_block_till_done()

    # The config entry device path should be updated
    assert config_entry.data["device"] == usb_data.device

    # No new config entry was created
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1

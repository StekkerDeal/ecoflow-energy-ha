"""Write-path tests for the STREAM AC 5000 (ES22) controls.

Every control here builds a `cmd_func=254 / cmd_id=38` config write and hands
it to the coordinator's proto SET sender. The frames themselves are checked
against the app's own bytes in `tests/test_stream_ac5000_commands.py`; these
tests cover what the entity does with them, which is where the device-specific
awkwardness lives: the SoC limits share one field, and a power setpoint is
really a rewrite of a scheduled task.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ecoflow_energy.const import (
    STREAMAC5000_NUMBERS,
    STREAMAC5000_SELECTS,
)
from custom_components.ecoflow_energy.coordinator import EcoFlowDeviceCoordinator
from custom_components.ecoflow_energy.ecoflow.proto.decoder import (
    decode_header_message,
)
from custom_components.ecoflow_energy.ecoflow.proto_encoding import (
    encode_field_bytes,
    encode_field_varint,
    encode_varint,
)
from custom_components.ecoflow_energy.number import EcoFlowNumber
from custom_components.ecoflow_energy.select import EcoFlowSelect

from .test_stream_ac5000_entities import ES22_DEVICE

# A task the device already reports: discharge, 00:00-23:00, 600 W.
REPORTED: dict[str, Any] = {
    "max_charge_soc_pct": 90,
    "min_discharge_soc_pct": 15,
    "work_mode": "custom",
    "scheduled_discharge_power_w": 600,
    "scheduled_discharge_start_min": 0,
    "scheduled_discharge_end_min": 1380,
    "scheduled_discharge_enabled": True,
}


def _coordinator(
    hass: HomeAssistant, entry: MockConfigEntry, data: dict[str, Any] | None = None
) -> EcoFlowDeviceCoordinator:
    entry.add_to_hass(hass)
    coordinator = EcoFlowDeviceCoordinator(hass, entry, ES22_DEVICE)
    coordinator._device_data = dict(REPORTED if data is None else data)
    coordinator.async_set_updated_data(dict(coordinator._device_data))
    coordinator.async_send_proto_set_command = AsyncMock(return_value=True)
    return coordinator


def _number(coordinator: EcoFlowDeviceCoordinator, key: str) -> EcoFlowNumber:
    defn = next(d for d in STREAMAC5000_NUMBERS if d.key == key)
    entity = EcoFlowNumber(coordinator, defn)
    entity.async_write_ha_state = MagicMock()
    return entity


def _select(coordinator: EcoFlowDeviceCoordinator, key: str) -> EcoFlowSelect:
    defn = next(d for d in STREAMAC5000_SELECTS if d.key == key)
    entity = EcoFlowSelect(coordinator, defn)
    entity.async_write_ha_state = MagicMock()
    return entity


def _sent(coordinator: EcoFlowDeviceCoordinator) -> tuple[dict, bytes]:
    """Return the header and pdata of the single frame that was sent."""
    coordinator.async_send_proto_set_command.assert_called_once()
    payload = coordinator.async_send_proto_set_command.call_args[0][0]
    assert isinstance(payload, bytes)
    headers, _ = decode_header_message(payload)
    assert headers
    return headers[0], bytes.fromhex(headers[0]["pdata"])


def _config_field(pdata: bytes) -> int:
    """pdata always opens with field 1 naming the config field being written."""
    assert pdata[0] == 0x08
    return pdata[1]


class TestWorkModeSelect:
    async def test_writes_a_config_field_25_frame(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, enhanced_config_entry)
        entity = _select(coordinator, "work_mode")

        await entity.async_select_option("self_powered")

        header, pdata = _sent(coordinator)
        assert int(header["cmd_func"]) == 254
        assert int(header["cmd_id"]) == 38
        assert _config_field(pdata) == 25
        assert pdata[-1] == 0  # self_powered
        assert coordinator.data["work_mode"] == "self_powered"

    async def test_failed_write_raises_and_keeps_the_device_value(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, enhanced_config_entry)
        coordinator.async_send_proto_set_command = AsyncMock(return_value=False)
        entity = _select(coordinator, "work_mode")

        with pytest.raises(HomeAssistantError):
            await entity.async_select_option("self_powered")

        assert coordinator.data["work_mode"] == "custom"


class TestSocLimitNumbers:
    async def test_charge_limit_carries_the_current_discharge_limit(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        """Config field 29 holds both, so the untouched one travels along."""
        coordinator = _coordinator(hass, enhanced_config_entry)
        entity = _number(coordinator, "max_charge_soc_pct")

        await entity.async_set_native_value(85)

        header, pdata = _sent(coordinator)
        assert int(header["cmd_id"]) == 38
        assert _config_field(pdata) == 29
        # field 29 = {1: charge, 2: discharge}
        assert pdata.endswith(bytes([0x08, 85, 0x10, 15]))

    async def test_discharge_limit_carries_the_current_charge_limit(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, enhanced_config_entry)
        entity = _number(coordinator, "min_discharge_soc_pct")

        await entity.async_set_native_value(20)

        _header, pdata = _sent(coordinator)
        assert pdata.endswith(bytes([0x08, 90, 0x10, 20]))

    async def test_refuses_when_the_counterpart_is_unknown(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        """Guessing it would change a limit the user never touched."""
        coordinator = _coordinator(hass, enhanced_config_entry, data={})
        entity = _number(coordinator, "max_charge_soc_pct")

        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(85)

        coordinator.async_send_proto_set_command.assert_not_called()

    async def test_a_limit_the_device_would_reject_is_not_sent(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        """The builder refuses discharge >= charge, so nothing leaves."""
        coordinator = _coordinator(hass, enhanced_config_entry)
        entity = _number(coordinator, "max_charge_soc_pct")

        with pytest.raises(ValueError):
            await entity.async_set_native_value(10)

        coordinator.async_send_proto_set_command.assert_not_called()


class TestPowerSetpoints:
    async def test_discharge_power_rewrites_the_reported_task(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, enhanced_config_entry)
        entity = _number(coordinator, "max_discharging_power")

        await entity.async_set_native_value(300)

        header, pdata = _sent(coordinator)
        assert int(header["cmd_id"]) == 38
        assert _config_field(pdata) == 39
        # operation 2 (update), type 2 (discharge)
        assert bytes([0x08, 2, 0x10, 2]) in pdata
        # the reported window survives
        assert encode_field_bytes(7, encode_varint((1380 << 16) | 0)) in pdata
        # field 9 = {1: 300}
        assert encode_field_bytes(9, encode_field_varint(1, 300)) in pdata

    async def test_a_device_without_a_task_gets_one_for_the_whole_day(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        """A setpoint means nothing without a task, so one is added."""
        coordinator = _coordinator(
            hass, enhanced_config_entry, data={"work_mode": "custom"}
        )
        entity = _number(coordinator, "max_discharging_power")

        await entity.async_set_native_value(500)

        _header, pdata = _sent(coordinator)
        # operation 1 (add), not 2 (update)
        assert bytes([0x08, 1, 0x10, 2]) in pdata
        # 00:00 to 23:59
        assert encode_field_bytes(7, encode_varint((1439 << 16) | 0)) in pdata

    async def test_charge_power_is_per_device(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        """A charge task names the device it applies to, a discharge one does not."""
        coordinator = _coordinator(hass, enhanced_config_entry)
        entity = _number(coordinator, "max_grid_charging_power")

        await entity.async_set_native_value(600)

        _header, pdata = _sent(coordinator)
        assert bytes([0x08, 1, 0x10, 1]) in pdata  # add, charge
        assert ES22_DEVICE["sn"].encode() in pdata

    async def test_a_disabled_task_stays_disabled(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        """Changing the power must not silently re-enable a task."""
        data = dict(REPORTED, scheduled_discharge_enabled=False)
        coordinator = _coordinator(hass, enhanced_config_entry, data=data)
        entity = _number(coordinator, "max_discharging_power")

        await entity.async_set_native_value(300)

        _header, pdata = _sent(coordinator)
        assert bytes.fromhex("18002001") in pdata

    async def test_zero_is_writable(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        """Zero means idle on this device rather than "no setting"."""
        coordinator = _coordinator(hass, enhanced_config_entry)
        entity = _number(coordinator, "max_discharging_power")

        await entity.async_set_native_value(0)

        _header, pdata = _sent(coordinator)
        assert bytes.fromhex("4a020800") in pdata

    async def test_warns_when_the_mode_cannot_act_on_it(
        self,
        hass: HomeAssistant,
        enhanced_config_entry: MockConfigEntry,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The write succeeds and the device ignores it, which is worth saying."""
        data = dict(REPORTED, work_mode="self_powered")
        coordinator = _coordinator(hass, enhanced_config_entry, data=data)
        entity = _number(coordinator, "max_discharging_power")

        await entity.async_set_native_value(300)

        coordinator.async_send_proto_set_command.assert_called_once()
        assert "custom mode" in caplog.text

    async def test_no_warning_in_custom_mode(
        self,
        hass: HomeAssistant,
        enhanced_config_entry: MockConfigEntry,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        coordinator = _coordinator(hass, enhanced_config_entry)
        entity = _number(coordinator, "max_discharging_power")

        await entity.async_set_native_value(300)

        assert "custom mode" not in caplog.text

    async def test_failed_write_raises_and_keeps_the_device_value(
        self, hass: HomeAssistant, enhanced_config_entry: MockConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, enhanced_config_entry)
        coordinator.async_send_proto_set_command = AsyncMock(return_value=False)
        entity = _number(coordinator, "max_discharging_power")

        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(300)

        assert coordinator.data["scheduled_discharge_power_w"] == 600

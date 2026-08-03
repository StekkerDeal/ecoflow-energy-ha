"""Tests for the STREAM AC 5000 (ES22) protobuf telemetry parser."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from ecoflow_energy.ecoflow.parsers.stream_ac5000_proto import (
    parse_stream_ac5000_message,
)
from ecoflow_energy.ecoflow.proto_encoding import (
    encode_field_bytes,
    encode_field_varint,
    encode_varint,
)

FIXTURES = Path(__file__).parent / "fixtures" / "stream_ac5000"
GET_REPLY = FIXTURES / "es22_get_reply_masked.json"
PUSHES = FIXTURES / "es22_push_capture_masked.json"


def _encode_fixed32_field(field_number: int, value: float) -> bytes:
    """Encode one protobuf fixed32 field."""
    tag = (field_number << 3) | 5
    return encode_varint(tag) + struct.pack("<f", value)


def _sub(field_number: int, inner: bytes) -> bytes:
    """Wrap ``inner`` as a length-delimited submessage."""
    return encode_field_bytes(field_number, inner)


def _build_frame(cmd_func: int, cmd_id: int, inner: bytes) -> bytes:
    """Build a minimal EcoFlow header frame for tests."""
    header = bytearray()
    header.extend(encode_field_bytes(1, inner))
    header.extend(encode_field_varint(8, cmd_func))
    header.extend(encode_field_varint(9, cmd_id))
    return encode_field_bytes(1, bytes(header))


def _build_masked_frame(cmd_func: int, cmd_id: int, inner: bytes, seq: int) -> bytes:
    """Build a frame whose payload is XOR-masked with its own sequence byte."""
    masked = bytes(value ^ (seq & 0xFF) for value in inner)
    header = bytearray()
    header.extend(encode_field_bytes(1, masked))
    header.extend(encode_field_varint(6, 1))  # enc_type
    header.extend(encode_field_varint(8, cmd_func))
    header.extend(encode_field_varint(9, cmd_id))
    header.extend(encode_field_varint(14, seq))
    return encode_field_bytes(1, bytes(header))


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["frames"]


class TestNestedWalker:
    """The map addresses nested paths, which the Stream walker cannot do."""

    def test_reads_a_value_two_levels_down(self) -> None:
        inner = _sub(50, _sub(1, _encode_fixed32_field(4, -593.0)))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["batt_w"] == pytest.approx(-593.0, rel=1e-5)

    def test_half_watt_node_totals_are_halved(self) -> None:
        inner = _sub(11, encode_field_varint(1, 4042))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["home_w"] == pytest.approx(2021.0, rel=1e-6)

    def test_solar_node_total_is_already_watts(self) -> None:
        """f11.9 is the one field in this block that is not half-watts."""
        inner = _sub(11, encode_field_varint(9, 1556))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["solar_w"] == pytest.approx(1556.0, rel=1e-6)

    def test_undeclared_string_field_is_not_entered(self) -> None:
        """A length-delimited field the map does not declare is skipped.

        `f23.3` holds a timezone name. Walking into it as if it were a
        submessage is how a parser invents fields that do not exist.
        """
        timezone_block = _sub(23, _sub(3, b"Europe/Amsterdam"))
        battery = _sub(50, _sub(1, _encode_fixed32_field(4, 100.0)))
        frame = _build_frame(254, 39, bytes(timezone_block + battery))
        result = parse_stream_ac5000_message(frame)
        assert result is not None
        assert result["batt_w"] == pytest.approx(100.0, rel=1e-5)
        assert not any(key.startswith("23") for key in result)

    def test_group_arriving_as_a_scalar_is_ignored(self) -> None:
        """A declared group sent as a varint is a layout difference."""
        inner = encode_field_varint(11, 5) + _sub(
            50, _sub(1, _encode_fixed32_field(4, 42.0))
        )
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert "home_w" not in result
        assert result["batt_w"] == pytest.approx(42.0, rel=1e-5)

    def test_masked_payload_is_unmasked(self) -> None:
        """No ES22 frame has set enc_type, so this path is synthetic only."""
        inner = _sub(11, encode_field_varint(5, 18))
        frame = _build_masked_frame(254, 39, bytes(inner), seq=77)
        result = parse_stream_ac5000_message(frame)
        assert result is not None
        assert result["soc_pct"] == 18


class TestFlowEdges:
    def test_present_edge_group_zero_fills_its_missing_edges(self) -> None:
        """proto3 omits a zero, so an absent edge in a present group is 0.

        Without this an idle battery would keep reporting the last power it
        delivered, forever.
        """
        inner = _sub(12, encode_field_varint(6, 800))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["home_from_grid_w"] == 800
        assert result["home_from_batt_w"] == 0.0
        assert result["grid_export_power_w"] == 0.0
        assert result["grid_import_power_w"] == 800.0

    def test_absent_edge_group_reports_nothing(self) -> None:
        """An `f11`-only push means unchanged, not zero.

        116 of 355 observed pushes have this shape. Zero-filling them would
        blank an edge that is still delivering power.
        """
        inner = _sub(11, encode_field_varint(1, 2000))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["home_w"] == pytest.approx(1000.0)
        assert "home_from_batt_w" not in result
        assert "home_from_grid_w" not in result
        assert "grid_import_power_w" not in result
        assert "grid_export_power_w" not in result

    def test_solar_edges_are_not_zero_filled(self) -> None:
        """Reporting them on every frame would defeat the accessory gating."""
        inner = _sub(12, encode_field_varint(4, 500))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert "home_from_solar_w" not in result

    def test_export_sums_the_two_outbound_edges(self) -> None:
        inner = _sub(
            12,
            encode_field_varint(5, 356) + encode_field_varint(10, 62),
        )
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["grid_export_power_w"] == pytest.approx(418.0)
        assert result["grid_import_power_w"] == pytest.approx(0.0)


class TestDerivedValues:
    @pytest.mark.parametrize(
        ("batt_w", "charge", "discharge"),
        [(599.6, 599.6, 0.0), (-593.0, 0.0, 593.0), (0.0, 0.0, 0.0)],
    )
    def test_signed_battery_power_splits_one_way_only(
        self, batt_w: float, charge: float, discharge: float
    ) -> None:
        inner = _sub(50, _sub(1, _encode_fixed32_field(4, batt_w)))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["batt_charge_power_w"] == pytest.approx(charge, rel=1e-5)
        assert result["batt_discharge_power_w"] == pytest.approx(discharge, rel=1e-5)

    def test_charge_discharge_state_is_left_to_the_coordinator(self) -> None:
        """The coordinator derives it with hysteresis over a rolling window."""
        inner = _sub(50, _sub(1, _encode_fixed32_field(4, -593.0)))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert "batt_charge_discharge_state" not in result

    def test_meter_block_carries_the_grid_sign(self) -> None:
        """A Tibber Pulse reports one signed total; negative is export."""
        inner = _sub(15, _encode_fixed32_field(3, -419.0))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["grid_w"] == pytest.approx(-419.0, rel=1e-5)

    def test_p1_meter_net_feeds_the_same_key(self) -> None:
        """An EcoFlow P1 reports per-phase values and its net in f16.16."""
        inner = _sub(
            16,
            _encode_fixed32_field(4, 1111.0)
            + _encode_fixed32_field(5, -506.0)
            + _encode_fixed32_field(6, -607.0)
            + _encode_fixed32_field(7, 231.4)
            + _encode_fixed32_field(15, 50.02)
            + _encode_fixed32_field(16, -2.0),
        )
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["grid_phase_a_active_power_w"] == pytest.approx(1111.0, rel=1e-5)
        assert result["grid_phase_b_active_power_w"] == pytest.approx(-506.0, rel=1e-5)
        assert result["grid_phase_c_active_power_w"] == pytest.approx(-607.0, rel=1e-5)
        assert result["grid_phase_a_voltage_v"] == pytest.approx(231.4, rel=1e-5)
        assert result["ac_frequency_hz"] == pytest.approx(50.02, rel=1e-5)
        assert result["grid_w"] == pytest.approx(-2.0, rel=1e-5)

    def test_account_power_limits(self) -> None:
        """f10.1 and f10.6 are the limits the app calls max grid-tied output
        and max grid input. Identified by watching them follow the app: both
        read 600 under a 600 W account limit, both became 2500 when it was
        raised, and .1 alone became 2400 when the output limit was set there."""
        inner = _sub(10, encode_field_varint(1, 2400) + encode_field_varint(6, 2500))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["max_grid_output_power_w"] == 2400
        assert result["max_grid_input_power_w"] == 2500

    def test_the_milliwatt_pair_is_not_mapped(self) -> None:
        """254/40 f22 reads 600000/1200000 and stayed there while the account
        limit went to 2500 W, the output limit to 2400 W and the discharge task
        to 1400 W. It is neither, so it is left alone."""
        inner = _sub(22, encode_field_varint(1, 600000) + encode_field_varint(3, 1200000))
        assert parse_stream_ac5000_message(_build_frame(254, 40, bytes(inner))) is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(0, "self_powered"), (1, "intelligent_plus"), (2, "custom"), (9, None)],
    )
    def test_work_mode_enum(self, raw: int, expected: str | None) -> None:
        inner = encode_field_varint(25, raw)
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["work_mode"] == expected

    def test_bms_current_and_voltage_convert_from_milli_units(self) -> None:
        inner = encode_field_varint(7, 16063) + encode_field_varint(
            8, (1 << 64) - 40735
        )
        result = parse_stream_ac5000_message(_build_frame(32, 50, bytes(inner)))
        assert result is not None
        assert result["batt_voltage_v"] == pytest.approx(16.063)
        assert result["bms_current_a"] == pytest.approx(-40.735)

    def test_bms_soc_does_not_overwrite_the_system_soc(self) -> None:
        """The pack reads about two points above what the app shows."""
        system = _sub(33, _encode_fixed32_field(6, 18.63))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(system)))
        assert result is not None
        assert result["soc_precise_pct"] == pytest.approx(18.63, rel=1e-4)

        bms = parse_stream_ac5000_message(
            _build_frame(32, 50, bytes(_encode_fixed32_field(25, 20.93)))
        )
        assert bms is not None
        assert bms["bms_precise_soc"] == pytest.approx(20.93, rel=1e-4)
        assert "soc_precise_pct" not in bms


class TestSocLimits:
    def test_limits_from_the_config_block(self) -> None:
        inner = _sub(29, encode_field_varint(1, 90) + encode_field_varint(2, 15))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["max_charge_soc_pct"] == 90
        assert result["min_discharge_soc_pct"] == 15

    def test_same_limits_from_the_battery_heartbeat(self) -> None:
        inner = _sub(1, encode_field_varint(7, 90) + encode_field_varint(21, 15))
        result = parse_stream_ac5000_message(_build_frame(32, 2, bytes(inner)))
        assert result is not None
        assert result["max_charge_soc_pct"] == 90
        assert result["min_discharge_soc_pct"] == 15

    def test_scheduled_discharge_setpoint_is_read_back(self) -> None:
        """f40.1.9.1 followed every setpoint written during a control test."""
        task = (
            encode_field_varint(2, 2)  # discharge
            + encode_field_varint(3, 1)  # enabled
            + _sub(7, encode_varint((1380 << 16) | 0))
            + _sub(9, encode_field_varint(1, 500))
        )
        inner = _sub(40, _sub(1, task))
        result = parse_stream_ac5000_message(_build_frame(254, 39, bytes(inner)))
        assert result is not None
        assert result["scheduled_discharge_power_w"] == 500
        assert result["scheduled_discharge_enabled"] is True
        assert result["scheduled_discharge_start_min"] == 0
        assert result["scheduled_discharge_end_min"] == 1380
        # The charge task is a separate frame, so nothing about it is implied.
        assert "scheduled_charge_power_w" not in result


class TestScheduledTasks:
    def test_charge_task_keys_are_separate_from_discharge(self) -> None:
        per_device = (
            encode_field_bytes(1, b"ES22TEST00000001")
            + encode_field_varint(2, 100)
            + encode_field_varint(3, 600)
        )
        task = (
            encode_field_varint(2, 1)  # charge
            + encode_field_varint(3, 1)
            + _sub(7, encode_varint((960 << 16) | 780))
            + _sub(8, encode_field_varint(1, 1) + _sub(3, per_device))
        )
        result = parse_stream_ac5000_message(
            _build_frame(254, 39, bytes(_sub(40, _sub(1, task))))
        )
        assert result is not None
        assert result["scheduled_charge_power_w"] == 600
        assert result["scheduled_charge_start_min"] == 780
        assert result["scheduled_charge_end_min"] == 960
        assert "scheduled_discharge_power_w" not in result

    def test_disabled_task_reports_disabled(self) -> None:
        """Disabling a task in the app dropped f40.1.3 rather than sending 0."""
        task = encode_field_varint(2, 2) + _sub(9, encode_field_varint(1, 600))
        result = parse_stream_ac5000_message(
            _build_frame(254, 39, bytes(_sub(40, _sub(1, task))))
        )
        assert result is not None
        assert result["scheduled_discharge_enabled"] is False

    def test_task_without_a_kind_is_dropped(self) -> None:
        """Which task a power belongs to cannot be guessed."""
        task = _sub(9, encode_field_varint(1, 500))
        result = parse_stream_ac5000_message(
            _build_frame(254, 39, bytes(_sub(40, _sub(1, task))))
        )
        assert result is None


class TestRejectsGarbage:
    def test_empty_payload(self) -> None:
        assert parse_stream_ac5000_message(b"") is None

    def test_random_bytes(self) -> None:
        assert parse_stream_ac5000_message(b"\xff\xfe\xfd\xfc") is None

    def test_unmapped_command_yields_nothing(self) -> None:
        frame = _build_frame(53, 77, bytes.fromhex("08021003"))
        assert parse_stream_ac5000_message(frame) is None


class TestCaptureReplay:
    """Replay of the real masked captures through the production entry point."""

    def test_get_reply_bundle_decodes_every_command(self) -> None:
        frame = _load(GET_REPLY)[0]
        result = parse_stream_ac5000_message(bytes.fromhex(frame["hex"]))
        assert result is not None
        # One bundle carries the whole picture: battery, flow, meter, limits.
        for key in (
            "soc_pct",
            "batt_w",
            "home_w",
            "grid_w",
            "max_charge_soc_pct",
            "min_discharge_soc_pct",
            "bms_soh_pct",
            "batt_voltage_v",
            "work_mode",
        ):
            assert key in result, key

    def test_push_frames_parse_or_carry_nothing_we_map(self) -> None:
        """A 254/40-only push yields nothing, since none of its fields are
        mapped. Every other shape has to produce data."""
        frames = _load(PUSHES)
        assert len(frames) >= 20
        empty_cmds = []
        for frame in frames:
            if parse_stream_ac5000_message(bytes.fromhex(frame["hex"])):
                continue
            empty_cmds.append(
                tuple(sorted((c["cmd_func"], c["cmd_id"]) for c in frame["cmds"]))
            )
        assert len(empty_cmds) < len(frames) / 2
        for cmds in empty_cmds:
            assert cmds == ((254, 40),), cmds

    def test_no_solar_entity_data_on_a_unit_without_pv(self) -> None:
        """Most frames must not carry solar, or the gating never holds off."""
        parsed = [
            parse_stream_ac5000_message(bytes.fromhex(f["hex"])) or {}
            for f in _load(PUSHES)
        ]
        with_solar = [p for p in parsed if "solar_w" in p]
        assert len(with_solar) < len(parsed) / 2

    def test_home_equals_the_edges_into_home(self) -> None:
        """The identity the flow matrix has to preserve, on real frames."""
        checked = 0
        for frame in _load(PUSHES):
            parsed = parse_stream_ac5000_message(bytes.fromhex(frame["hex"])) or {}
            home = parsed.get("home_w")
            from_batt = parsed.get("home_from_batt_w")
            from_grid = parsed.get("home_from_grid_w")
            if not all(isinstance(v, (int, float)) for v in (home, from_batt, from_grid)):
                continue
            total = from_batt + from_grid + (parsed.get("home_from_solar_w") or 0.0)
            assert abs(home - total) <= 2, frame["ts_iso"]
            checked += 1
        assert checked >= 5

    def test_import_and_export_are_never_negative(self) -> None:
        for frame in _load(PUSHES) + _load(GET_REPLY):
            parsed = parse_stream_ac5000_message(bytes.fromhex(frame["hex"])) or {}
            for key in ("grid_import_power_w", "grid_export_power_w"):
                value = parsed.get(key)
                if isinstance(value, (int, float)):
                    assert value >= 0, f"{key} = {value}"

    def test_fixtures_carry_no_identifier(self) -> None:
        """Guards the fixtures themselves, not the parser."""
        import re

        for path in (GET_REPLY, PUSHES):
            for frame in _load(path):
                raw = bytes.fromhex(frame["hex"])
                runs = [m for m in re.findall(rb"[A-Z0-9]{15,}", raw) if set(m) != {ord("X")}]
                assert not runs, f"{path.name}: {runs}"
                assert "{sn}" in frame["topic"]

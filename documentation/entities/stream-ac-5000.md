# STREAM AC 5000 - Entity Reference

Full list of all entities created for the STREAM AC 5000.

**Models:** STREAM AC 5000 (`ES22`).

**This is not the Stream entity set.** Despite the shared product name, an `ES22` speaks a different protocol from the BK-series Stream devices: it sends none of their telemetry messages and describes power as a flow matrix rather than as individual readings. It therefore has its own device type, parser and entity list. See [Stream](stream.md) for the BK series.

**Totals:** 52 sensors, 2 binary sensors, 2 switches, 5 numbers, 1 select

> Entities marked with *disabled* are available but hidden by default. Enable them in **Settings > Devices > EcoFlow STREAM AC 5000 > Entities** (click the filter icon and show disabled entities).

> **Enhanced Mode only.** This device is not reachable through the IoT Developer API, so Standard Mode reports error 1006 and no entities fill. Set the integration up with an EcoFlow account e-mail and password.

> **Entities marked *accessory* are created only once the device actually reports the reading**, and they appear on their own the moment it does, without a restart. Whether a unit has solar wired to the EcoFlow itself, and which smart meter is linked in the app, are installation choices rather than model differences, so listing them for everyone would leave most owners with entities that can never fill.

---

## Sensors - Battery

| Entity | Unit | Category | Default | Description |
|:---|:---:|:---:|:---:|:---|
| Battery SOC | % | - | enabled | State of charge, as shown in the app |
| Battery SOC (Precise) | % | diagnostic | disabled | High-resolution system SoC |
| Precise SoC | % | diagnostic | disabled | Pack-level SoC, straight from the BMS. Runs about two points above Battery SOC (Precise) directly above it, which is the system figure and the one the app shows. The two names are easy to confuse; prefer the system one unless you specifically want the pack reading |
| Battery SoH | % | - | enabled | State of health |
| Battery Power | W | - | enabled | Signed battery power (positive = charging, negative = discharging) |
| Battery Charge Power | W | - | enabled | Charging power (always >= 0) |
| Battery Discharge Power | W | - | enabled | Discharging power (always >= 0) |
| Battery Charge/Discharge State | - | diagnostic | disabled | `standby`, `charging` or `discharging` |

## Sensors - Power Flow

| Entity | Unit | Category | Default | Description |
|:---|:---:|:---:|:---:|:---|
| Home Power | W | - | enabled | Total house consumption |
| Grid Power | W | - | enabled | Signed grid power from the linked smart meter (positive = drawing, negative = feeding in). Absent while no meter is linked in the EcoFlow app |
| Grid Import Power | W | - | enabled | Power drawn from the grid, derived from the flow matrix |
| Grid Export Power | W | - | enabled | Power fed into the grid, derived from the flow matrix |
| Home From Battery | W | diagnostic | disabled | House load covered by the battery |
| Home From Grid | W | diagnostic | disabled | House load covered by the grid |
| Solar Power | W | - | *accessory* | Solar production, only on a unit with PV wired to the EcoFlow |
| Home From Solar | W | diagnostic | *accessory*, disabled | House load covered by solar |

## Sensors - Smart Meter

Only an EcoFlow P1 meter reports per-phase values. A meter that reports a single total, such as a Tibber Pulse, feeds Grid Power above and creates none of these.

| Entity | Unit | Category | Default | Description |
|:---|:---:|:---:|:---:|:---|
| Grid Phase A/B/C Power | W | diagnostic | *accessory*, disabled | Active power per phase |
| Grid Phase A/B/C Voltage | V | diagnostic | *accessory*, disabled | Voltage per phase |
| Grid Phase A/B/C Current | A | diagnostic | *accessory*, disabled | Current per phase |
| AC Frequency | Hz | diagnostic | *accessory*, disabled | Grid frequency |

## Sensors - Configuration

The settings that also have a control read back here, so an automation can see what the device reports rather than what was last requested.

| Entity | Unit | Category | Default | Description |
|:---|:---:|:---:|:---:|:---|
| Work Mode | - | diagnostic | enabled | `self_powered`, `intelligent_plus` or `custom` |
| Max Charge SoC | % | diagnostic | enabled | Upper SoC limit set in the app |
| Min Discharge SoC | % | diagnostic | enabled | Lower SoC limit set in the app |
| Backup Reserve | % | diagnostic | enabled | Reserve level held for a power cut |
| Max Grid-tied Output Power | W | diagnostic | enabled | Account-level output limit. Raised by asking EcoFlow. A task power above it is clamped, not refused |
| Max Grid Input Power | W | diagnostic | enabled | Account-level input limit, settable in the app |
| Scheduled Discharge Power | W | diagnostic | enabled | Power setpoint of the discharge task, mirrors the Max Discharging Power number |
| Scheduled Charge Power | W | diagnostic | enabled | Power setpoint of the charge task, mirrors the Max Grid Charging Power number |
| Scheduled Charge Target SoC | % | diagnostic | enabled | The charge task's own SoC target, shown in the app as "Charge limit". Preserved on every power write |

## Sensors - Battery Diagnostics

| Entity | Unit | Category | Default | Description |
|:---|:---:|:---:|:---:|:---|
| Battery Voltage | V | - | enabled | Pack voltage |
| Battery Current | A | diagnostic | disabled | Pack current (positive = charging) |
| Battery Temp | C | - | enabled | Pack temperature |
| Max Cell Temp | C | diagnostic | disabled | Highest cell temperature |
| Min Cell Temp | C | diagnostic | disabled | Lowest cell temperature |
| Max MOSFET Temp | C | diagnostic | disabled | Highest MOSFET temperature |
| Max Cell Voltage | mV | diagnostic | disabled | Highest cell voltage |
| Min Cell Voltage | mV | diagnostic | disabled | Lowest cell voltage |
| Design Capacity | mAh | diagnostic | disabled | Nameplate capacity |
| Full Capacity | mAh | diagnostic | disabled | Present full-charge capacity |
| Remaining Capacity | mAh | diagnostic | disabled | Charge left in the pack |

## Sensors - Energy Dashboard

All six are integrated from the matching power reading, so they only ever count up.

| Entity | Unit | Category | Default | Description |
|:---|:---:|:---:|:---:|:---|
| Battery Charge Energy | kWh | - | enabled | Lifetime energy into the battery |
| Battery Discharge Energy | kWh | - | enabled | Lifetime energy out of the battery |
| Grid Import Energy | kWh | - | enabled | Lifetime energy drawn from the grid |
| Grid Export Energy | kWh | - | enabled | Lifetime energy fed into the grid |
| Home Energy | kWh | diagnostic | disabled | Lifetime house consumption |
| Solar Energy | kWh | diagnostic | *accessory*, disabled | Lifetime solar production |

## Binary Sensors

| Entity | Category | Default | Description |
|:---|:---:|:---:|:---|
| Backup Reserve | diagnostic | enabled | Whether a reserve is held for a power cut |
| Backup Socket | diagnostic | enabled | Whether the backup socket is switched on |

## Numbers

| Entity | Unit | Range | Description |
|:---|:---:|:---:|:---|
| Max Discharging Power | W | 0-2500 | Discharge power setpoint. This is the entity an external optimiser writes |
| Max Grid Charging Power | W | 0-2500 | Charge power setpoint. Grid charging, so it is how a cheap-tariff charge is driven |
| Max Charge SoC | % | 50-100 | Upper SoC limit. Both limits are one setting on the wire, so changing either sends both |
| Min Discharge SoC | % | 0-50 | Lower SoC limit |
| Backup Reserve | % | 0-100 | Level held back for a power cut. Field 30 holds this and the on/off flag together, so changing either sends both |

## Selects

| Entity | Options | Description |
|:---|:---|:---|
| Work Mode | Self-powered, Intelligent Mode+, Custom | The device's operating mode |

## Switches

| Entity | Description |
|:---|:---|
| Backup Reserve | Whether a reserve is held back for a power cut. Writes the on/off flag together with the level, since the device holds both in one field |
| Backup Socket | The app's backup socket control |

## Driving this battery from an optimiser

### Whether a smart meter is linked changes what the controls mean

This is the single most important thing about this device, and it is not obvious.

**With a smart meter linked in the EcoFlow app**, the device runs closed loop against that meter. It will not discharge into an export, so the power setpoint acts only as a ceiling on covering house load. Request 1400 W into a house that needs 200 W and you get 200 W. This was measured, including with feed-in explicitly enabled, which does not change it.

**With no meter linked**, the device runs open loop. The app's own help text says it plainly: *"When no meter is linked, power from the system's grid-tied ports goes to the home, and any unused power will flow to the grid."* The setpoint then becomes an absolute power command. Confirmed on hardware: unlinking a Tibber Pulse turned a 1400 W request that had been delivering nothing extra into a measured 1400 W discharge.

So for an optimiser that wants to command power rather than cap it, **unlink the meter from the EcoFlow app** and let the optimiser do the metering. The cost is the Grid Power sensor, which comes from the meter block and disappears with it, and the device no longer self-consuming on its own.

### The rest

- **The setpoint is a scheduled task**, because that is the only power control this device has. Everything else about the task is read back and written unchanged, so changing a power cannot alter a window, an enabled flag or a charge target set in the app. On a device with no task at all, one covering the whole day is created, since a setpoint with no task would do nothing.
- **Zero means idle**, not "no setting". Writing 0 stops the battery entirely rather than falling back to self-consumption. That is the way to park it.
- **A setpoint is only acted on in Custom mode.** In self-powered or Intelligent Mode+ the device follows its own logic. The write is still accepted, so nothing reports an error; a warning goes to the log instead.
- **A setpoint above an account limit is clamped, not refused.** Max Grid-tied Output Power and Max Grid Input Power report those limits. The output limit is raised by asking EcoFlow, the input limit is set in the app.

Response is quick: a change settles in 10 to 20 seconds in either direction.

## Both limits travel together

Charge Limit and Discharge Limit are one setting on the wire, so changing either sends both. The one you did not touch goes out at the value the device last reported. If that value has not arrived yet the write is refused rather than guessed at, and the device itself rejects a discharge limit at or above the charge limit.

## Notes

- **Grid import and export come from the flow matrix, not from the meter.** The device reports the grid split as separate paths, so both counters are non-negative by construction, which is what the Energy Dashboard needs. Grid Power carries the signed meter reading alongside them.
- **Solar can appear on a unit with no PV wired to the EcoFlow.** The device derives a solar figure of its own from the house flows, and the app shows it too, as "Solar generation" on the home screen. It is reported here as the device reports it. On an installation whose PV is a separate system this figure is the EcoFlow's inference, not a measurement of that system.
- **Cycle count is not reported.** One field looks like one but was observed at 497, 499 and 1311 within minutes, so it is left out rather than exposed as a counter that would read as a meter reset.
- **A task deleted in the app leaves its last values behind.** The device reports one task per message and simply stops mentioning a task that no longer exists, which is indistinguishable from not having mentioned it yet. The Scheduled Charge and Scheduled Discharge Power sensors therefore keep their last reading until a task of that kind is reported again. Writing a power setpoint recreates the task, so the value becomes true again at that point.

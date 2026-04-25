"""Register definitions for the Local Felicity Modbus RTU bridge."""

from __future__ import annotations

STATUS_BLOCK_START = 0x1101
STATUS_BLOCK_END = 0x112A
STATUS_BLOCK_COUNT = STATUS_BLOCK_END - STATUS_BLOCK_START + 1

STATUS_REGISTERS: dict[int, tuple[str, float | int, str, str]] = {
    0x1101: ("working_mode", 1, "", "0=POWER 1=STANDBY 2=BYPASS 3=BATTERY 4=FAULT 5=LINE 6=CHARGING"),
    0x1102: ("charge_mode", 1, "", "0=NONE 1=BULK 2=ABSORB 3=FLOAT"),
    0x1108: ("battery_voltage", 0.01, "V", "raw / 100"),
    0x1109: ("battery_current", 1, "A", "signed int16; negative = discharging"),
    0x110A: ("battery_power", 1, "W", "signed int16; negative = discharging"),
    0x1111: ("output_voltage", 0.1, "V", "raw / 10"),
    0x1117: ("grid_voltage", 0.1, "V", "raw / 10"),
    0x111E: ("load_watts", 1, "W", "AC output active power"),
    0x1120: ("load_percentage", 1, "%", "load as % of inverter capacity"),
    0x1126: ("pv_voltage", 0.1, "V", "PV input voltage; raw / 10"),
    0x112A: ("pv_power", 1, "W", "PV input active power; signed int16"),
}

SETTINGS_BLOCK_START = 0x211F
SETTINGS_BLOCK_END = 0x2159
SETTINGS_BLOCK_COUNT = SETTINGS_BLOCK_END - SETTINGS_BLOCK_START + 1

SETTINGS_REGISTERS: dict[int, tuple[str, float | int, str, str]] = {
    0x211F: ("discharge_cutoff_voltage", 0.1, "V", "Battery cut-off voltage; raw = value * 10"),
    0x2122: ("bulk_charge_voltage", 0.1, "V", "Battery C.V (bulk) charging voltage; raw = value * 10"),
    0x2123: ("float_charge_voltage", 0.1, "V", "Battery floating charging voltage; raw = value * 10"),
    0x212A: ("output_source_priority", 1, "", "0=Utility first 1=Solar first 2=SBU"),
    0x212C: ("charge_source_priority", 1, "", "0=Utility first 1=Solar first 2=Solar+Utility 3=Only solar"),
    0x212E: ("max_charge_current", 1, "A", "Max combined charging current"),
    0x2130: ("max_ac_charge_current", 1, "A", "Max AC (utility) charging current"),
    0x2156: ("back_to_grid_voltage", 0.1, "V", "Battery voltage at which inverter switches back to grid; raw = value * 10"),
    0x2159: ("back_to_battery_voltage", 0.1, "V", "Battery voltage at which inverter switches back to battery; raw = value * 10"),
}

SIGNED_REGISTERS = {
    0x1109,
    0x110A,
    0x112A,
}

WORKING_MODE = {
    0: "POWER",
    1: "STANDBY",
    2: "BYPASS",
    3: "BATTERY",
    4: "FAULT",
    5: "LINE",
    6: "CHARGING",
}

CHARGE_MODE = {
    0: "NONE",
    1: "BULK",
    2: "ABSORB",
    3: "FLOAT",
}

OUTPUT_PRIORITY = {
    0: "Utility first",
    1: "Solar first",
    2: "SBU (Solar -> Battery -> Utility)",
}

CHARGE_PRIORITY = {
    0: "Utility first",
    1: "Solar first",
    2: "Solar + Utility",
    3: "Only solar",
}

FIELD_ENUMS = {
    "working_mode": WORKING_MODE,
    "charge_mode": CHARGE_MODE,
    "output_source_priority": OUTPUT_PRIORITY,
    "charge_source_priority": CHARGE_PRIORITY,
}

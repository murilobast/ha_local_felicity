# Felicity IVEM5048 — Modbus RTU Register Map
# Sources:
#   - dj-nitehawk/Felicity-Inverter-Monitor (FelicityInverter.cs, InverterSetting.cs)
#   - Akkudoktor forum thread by andreasm (RS232 @ 2400 8N1)
#   - Felicity protocol doc: 高频逆变器对外通信协议20210608B.pdf

# Protocol:
#   Interface : RS232 on the RJ45 port of the inverter (NOT RS485)
#   Baud rate : 2400 bps, 8N1
#   Protocol  : Modbus RTU, Slave ID = 0x01
#   Read fn   : 0x03 (Read Holding Registers)
#   Write fn  : 0x06 (Write Single Register)
#   CAUTION   : Pin 3 of the included RJ45-to-DB9 cable carries 12V (Ring Indicator).
#               CUT the green/white wire before connecting a USB-RS232 adapter or it
#               will overheat and be destroyed. Only TX / RX / GND are needed.

# ── STATUS REGISTERS (read-only, fn 0x03) ─────────────────────────────────────
# Block: 0x1101 – 0x112A  (42 registers, read in one shot)

STATUS_BLOCK_START = 0x1101
STATUS_BLOCK_END = 0x112A
STATUS_BLOCK_COUNT = STATUS_BLOCK_END - STATUS_BLOCK_START + 1

STATUS_REGISTERS = {
    # addr   name                      scale    unit    notes
    0x1101: ("working_mode",           1,       "",     "0=POWER 1=STANDBY 2=BYPASS 3=BATTERY 4=FAULT 5=LINE 6=CHARGING"),
    0x1102: ("charge_mode",            1,       "",     "0=NONE 1=BULK 2=ABSORB 3=FLOAT"),
    # 0x1103–0x1107: reserved / not mapped
    0x1108: ("battery_voltage",        0.01,    "V",    "raw / 100"),
    0x1109: ("battery_current",        1,       "A",    "signed int16; negative = discharging"),
    0x110A: ("battery_power",          1,       "W",    "signed int16; negative = discharging"),
    # 0x110B–0x1110: reserved / not mapped
    0x1111: ("output_voltage",         0.1,     "V",    "raw / 10"),
    # 0x1112–0x1116: reserved / not mapped
    0x1117: ("grid_voltage",           0.1,     "V",    "raw / 10"),
    # 0x1118–0x111D: reserved / not mapped
    0x111E: ("load_watts",             1,       "W",    "AC output active power"),
    # 0x111F: reserved
    0x1120: ("load_percentage",        1,       "%",    "load as % of inverter capacity"),
    # 0x1121–0x1125: reserved / not mapped
    0x1126: ("pv_voltage",             0.1,     "V",    "PV input voltage; raw / 10"),
    # 0x1127–0x1129: reserved / not mapped
    0x112A: ("pv_power",               1,       "W",    "PV input active power; signed int16"),
}

# Offset table for the single-block read (start = 0x1101):
# offset = address - 0x1101
STATUS_OFFSETS = {
    0:  ("working_mode",     1,    "",   "0=POWER 1=STANDBY 2=BYPASS 3=BATTERY 4=FAULT 5=LINE 6=CHARGING"),
    1:  ("charge_mode",      1,    "",   "0=NONE 1=BULK 2=ABSORB 3=FLOAT"),
    7:  ("battery_voltage",  0.01, "V",  "raw / 100"),
    8:  ("battery_current",  1,    "A",  "signed; negative = discharging"),
    9:  ("battery_power",    1,    "W",  "signed; negative = discharging"),
    16: ("output_voltage",   0.1,  "V",  "raw / 10"),
    22: ("grid_voltage",     0.1,  "V",  "raw / 10"),
    29: ("load_watts",       1,    "W",  ""),
    31: ("load_percentage",  1,    "%",  ""),
    37: ("pv_voltage",       0.1,  "V",  "raw / 10"),
    41: ("pv_power",         1,    "W",  "signed"),
}

# ── SETTINGS REGISTERS (read/write, fn 0x03 to read / 0x06 to write) ──────────
# Block: 0x211F – 0x2159  (59 registers)
# Offsets below are relative to 0x211F.

SETTINGS_BLOCK_START = 0x211F
SETTINGS_BLOCK_END = 0x2159
SETTINGS_BLOCK_COUNT = SETTINGS_BLOCK_END - SETTINGS_BLOCK_START + 1

SETTINGS_REGISTERS = {
    # addr    name                           scale   unit    range / notes
    0x211F: ("discharge_cutoff_voltage",     0.1,    "V",    "Battery cut-off voltage; raw = value * 10"),
    0x2122: ("bulk_charge_voltage",          0.1,    "V",    "Battery C.V (bulk) charging voltage; raw = value * 10"),
    0x2123: ("float_charge_voltage",         0.1,    "V",    "Battery floating charging voltage; raw = value * 10"),
    0x212A: ("output_source_priority",       1,      "",     "0=Utility first 1=Solar first 2=SBU"),
    0x212C: ("charge_source_priority",       1,      "",     "0=Utility first 1=Solar first 2=Solar+Utility 3=Only solar"),
    0x212E: ("max_charge_current",           1,      "A",    "Max combined charging current"),
    0x2130: ("max_ac_charge_current",        1,      "A",    "Max AC (utility) charging current"),
    0x2156: ("back_to_grid_voltage",         0.1,    "V",    "Battery voltage at which inverter switches back to grid; raw = value * 10"),
    0x2159: ("back_to_battery_voltage",      0.1,    "V",    "Battery voltage at which inverter switches back to battery; raw = value * 10"),
}

# Settings offsets relative to 0x211F (for single-block read):
SETTINGS_OFFSETS = {
    0:  ("discharge_cutoff_voltage",  0.1, "V",  "raw / 10"),
    3:  ("bulk_charge_voltage",       0.1, "V",  "raw / 10"),
    4:  ("float_charge_voltage",      0.1, "V",  "raw / 10"),
    11: ("output_source_priority",    1,   "",   "0=Utility 1=Solar 2=SBU"),
    13: ("charge_source_priority",    1,   "",   "0=Utility 1=Solar 2=Solar+Utility 3=OnlySolar"),
    15: ("max_charge_current",        1,   "A",  ""),
    17: ("max_ac_charge_current",     1,   "A",  ""),
    55: ("back_to_grid_voltage",      0.1, "V",  "raw / 10"),
    58: ("back_to_battery_voltage",   0.1, "V",  "raw / 10"),
}

# ── WRITE ENCODING ─────────────────────────────────────────────────────────────
# To write a setting, use Modbus fn 0x06 (Write Single Register):
#   Frame: [0x01][0x06][addr_hi][addr_lo][value_hi][value_lo][crc_lo][crc_hi]
#
# Value encoding per register:
#   Voltages (discharge_cutoff, bulk, float, back_to_grid, back_to_battery):
#       register_value = int(desired_voltage_V * 10)
#       e.g. 44.0 V -> 440
#
#   Currents (max_charge_current, max_ac_charge_current):
#       register_value = int(desired_amps)
#
#   Priorities (output_source_priority, charge_source_priority):
#       register_value = integer enum value (see notes above)

# ── WORKING MODE ENUM ──────────────────────────────────────────────────────────
WORKING_MODE = {
    0: "POWER",
    1: "STANDBY",
    2: "BYPASS",
    3: "BATTERY",
    4: "FAULT",
    5: "LINE",
    6: "CHARGING",
}

# ── CHARGE MODE ENUM ───────────────────────────────────────────────────────────
CHARGE_MODE = {
    0: "NONE",
    1: "BULK",
    2: "ABSORB",
    3: "FLOAT",
}

# ── OUTPUT SOURCE PRIORITY ─────────────────────────────────────────────────────
OUTPUT_PRIORITY = {
    0: "Utility first",
    1: "Solar first",
    2: "SBU (Solar → Battery → Utility)",
}

# ── CHARGE SOURCE PRIORITY ─────────────────────────────────────────────────────
CHARGE_PRIORITY = {
    0: "Utility first",
    1: "Solar first",
    2: "Solar + Utility",
    3: "Only solar",
}

# Registers that should be interpreted as signed int16 values.
SIGNED_REGISTERS = {
    0x1109,  # battery_current
    0x110A,  # battery_power
    0x112A,  # pv_power
}

# Field-level enum mapping used by the reader.
FIELD_ENUMS = {
    "working_mode": WORKING_MODE,
    "charge_mode": CHARGE_MODE,
    "output_source_priority": OUTPUT_PRIORITY,
    "charge_source_priority": CHARGE_PRIORITY,
}

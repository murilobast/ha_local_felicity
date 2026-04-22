"""
Felicity Solar Inverter - Modbus RTU reader
Python port of FelicityInverter.cs from dj-nitehawk/Felicity-Inverter-Monitor
Communicates via raw TCP to bridge.py running on the server.
"""

import socket
import struct

# ── Connection ────────────────────────────────────────────────────────────────
SERVER_HOST = "10.0.0.10"
SERVER_PORT = 54321
TIMEOUT     = 2.0

# ── Modbus constants (from FelicityInverter.cs) ───────────────────────────────
SLAVE_ADDRESS = 0x01

STATUS_START   = 0x1101
STATUS_COUNT   = 0x112A - 0x1101 + 1   # 42 registers

# ── CRC-16 (Modbus) ───────────────────────────────────────────────────────────
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


# ── Frame builders ───────────────────────────────────────────────────────────
def build_read_request(start_address: int, count: int) -> bytes:
    frame = bytes([
        SLAVE_ADDRESS,
        0x03,                        # Function: Read Holding Registers
        (start_address >> 8) & 0xFF,
        start_address & 0xFF,
        (count >> 8) & 0xFF,
        count & 0xFF,
    ])
    crc = crc16(frame)
    return frame + bytes([crc & 0xFF, crc >> 8])  # CRC lo, CRC hi


def build_write_request(address: int, value: int) -> bytes:
    """Modbus fn 0x06 — Write Single Register."""
    frame = bytes([
        SLAVE_ADDRESS,
        0x06,
        (address >> 8) & 0xFF,
        address & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ])
    crc = crc16(frame)
    return frame + bytes([crc & 0xFF, crc >> 8])


# ── Low-level read ────────────────────────────────────────────────────────────
def recv_exactly(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed by bridge")
        buf += chunk
    return buf


def send_request(sock: socket.socket, frame: bytes) -> bytes:
    sock.sendall(frame)

    # Read fixed header: [slave][function][byte_count_or_addr_hi]
    header = recv_exactly(sock, 3)
    slave, fn, third = header

    if fn & 0x80:
        # Modbus exception — read remaining 2 bytes (error code + CRC lo)
        rest = recv_exactly(sock, 2)
        raise RuntimeError(f"Modbus exception: fn=0x{fn:02X} code=0x{rest[0]:02X}")

    if fn == 0x06:
        # Write single register echo: [slave][0x06][addr_hi][addr_lo][val_hi][val_lo][crc_lo][crc_hi]
        # We already read 3 bytes; read remaining 5
        rest = recv_exactly(sock, 5)
        return header + rest

    # fn 0x03: third byte is byte_count; read data + CRC
    rest = recv_exactly(sock, third + 2)
    return header + rest


# ── Register parser ───────────────────────────────────────────────────────────
def parse_registers(data: bytes, count: int) -> list[int]:
    # data[0]=slave, data[1]=fn, data[2]=byte_count, data[3:3+byte_count]=values
    regs = []
    for i in range(count):
        hi = data[3 + i * 2]
        lo = data[3 + i * 2 + 1]
        raw = (hi << 8) | lo
        # interpret as signed 16-bit (same as C# short)
        regs.append(raw if raw < 32768 else raw - 65536)
    return regs


def charge_status(value: int):
    is_discharge = value < 0
    positive = -value if is_discharge else value
    return is_discharge, positive


# ── Main ──────────────────────────────────────────────────────────────────────
def read_status(sock: socket.socket) -> dict:
    frame    = build_read_request(STATUS_START, STATUS_COUNT)
    response = send_request(sock, frame)
    regs     = parse_registers(response, STATUS_COUNT)

    is_dis_cur, bat_cur   = charge_status(regs[8])
    is_dis_pow, bat_pow   = charge_status(regs[9])

    return {
        "working_mode":             regs[0],
        "charge_mode":              regs[1],
        "battery_voltage_v":        round(regs[7] / 100.0, 1),
        "battery_charge_a":         0 if is_dis_cur else bat_cur,
        "battery_discharge_a":      bat_cur if is_dis_cur else 0,
        "battery_charge_w":         0 if is_dis_pow else bat_pow,
        "battery_discharge_w":      bat_pow if is_dis_pow else 0,
        "output_voltage_v":         round(regs[16] / 10.0, 0),
        "grid_voltage_v":           round(regs[22] / 10.0, 0),
        "load_w":                   regs[29],
        "load_pct":                 regs[31],
        "pv_voltage_v":             round(regs[37] / 10.0, 0),
        "pv_power_w":               regs[41],
    }


def read_single(sock: socket.socket, address: int) -> int:
    frame    = build_read_request(address, 1)
    response = send_request(sock, frame)
    regs     = parse_registers(response, 1)
    return regs[0]


def write_register(sock: socket.socket, address: int, value: int) -> None:
    frame = build_write_request(address, value)
    send_request(sock, frame)


OUTPUT_PRIORITY_REG = 0x212A
CHARGE_PRIORITY_REG = 0x212C

# SAFE modes only.
# charge_priority=3 (Solar only) with no solar LOCKS UP the inverter — do not use.
# output_priority=2 appears to be BYPASS on this model (not SBU).
# Use 'probe' in the menu to find the correct output_priority value for battery mode.
MODES = {
    "grid_charge": (0, 2),   # Utility output + Solar+Utility charging  (safe default)
    "grid_only":   (0, 0),   # Utility output + Utility-first charging   (less charging)
    "battery":  (2, 3),  # use probe mode first to find the right output_priority value
}

WORKING_MODE = {0: "POWER", 1: "STANDBY", 2: "BYPASS", 3: "BATTERY", 4: "FAULT", 5: "LINE", 6: "CHARGING"}
CHARGE_MODE  = {0: "NONE",  1: "BULK",    2: "ABSORB", 3: "FLOAT"}


BACK_TO_BATTERY_REG = 0x2159

def set_mode(sock: socket.socket, mode: str) -> None:
    import time
    out_val, chg_val = MODES[mode]
    write_register(sock, OUTPUT_PRIORITY_REG, out_val)
    write_register(sock, CHARGE_PRIORITY_REG, chg_val)
    print(f"Mode set to '{mode}' (output_priority={out_val}, charge_priority={chg_val})")

    if mode == "battery":
        bat_v     = read_status(sock)["battery_voltage_v"]
        threshold = read_single(sock, BACK_TO_BATTERY_REG) * 0.1
        if bat_v < threshold:
            print(f"  ⚠ Battery ({bat_v}V) is below back_to_battery threshold ({threshold}V).")
            print(f"    Inverter may stay on grid to protect the battery.")
            print(f"    Lower back_to_battery_v below {bat_v}V to force switch.")

    print("Waiting for inverter to react...", end="", flush=True)
    time.sleep(2)
    print(" done.")



def print_status(sock: socket.socket) -> None:
    out_raw = read_single(sock, OUTPUT_PRIORITY_REG)
    chg_raw = read_single(sock, CHARGE_PRIORITY_REG)
    status  = read_status(sock)

    print(f"\n  output_priority    {out_raw}  ({['Utility','Solar','SBU'].pop(out_raw) if out_raw < 3 else '?'})")
    print(f"  charge_priority    {chg_raw}")
    print(f"  working_mode       {status['working_mode']}  ({WORKING_MODE.get(status['working_mode'], '?')})")
    print(f"  charge_mode        {status['charge_mode']}  ({CHARGE_MODE.get(status['charge_mode'], '?')})")
    print(f"  battery_voltage_v  {status['battery_voltage_v']} V")
    print(f"  battery_charge_w   {status['battery_charge_w']} W")
    print(f"  battery_discharge_w {status['battery_discharge_w']} W")
    print(f"  load_w             {status['load_w']} W")


if __name__ == "__main__":
    import time
    MENU = {str(i + 1): name for i, name in enumerate(MODES)}

    with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=TIMEOUT) as sock:
        print(f"Connected to {SERVER_HOST}:{SERVER_PORT}")

        while True:
            print("\n── Inverter Status ──────────────────────")
            print_status(sock)

            print("\n── Select mode ──────────────────────────")
            for key, name in MENU.items():
                out_val, chg_val = MODES[name]
                print(f"  {key}) {name:<15} (output={out_val}, charge={chg_val})")
            print("  p) probe output_priority values (finds battery mode)")
            print("  r) refresh status")
            print("  q) quit")

            choice = input("\n> ").strip().lower()

            if choice == "q":
                print("Bye.")
                break
            elif choice == "r":
                continue
            elif choice == "p":
                print("\nProbing output_priority values 0–5 (charge_priority stays at 2)...")
                print(f"  {'value':<8} {'working_mode':<20} {'charge_mode'}")
                for val in range(6):
                    write_register(sock, OUTPUT_PRIORITY_REG, val)
                    time.sleep(1.5)
                    st = read_status(sock)
                    wm = WORKING_MODE.get(st["working_mode"], "?")
                    cm = CHARGE_MODE.get(st["charge_mode"], "?")
                    print(f"  {val:<8} {st['working_mode']} ({wm:<12})   {st['charge_mode']} ({cm})")
                # restore safe default
                write_register(sock, OUTPUT_PRIORITY_REG, 0)
                print("Restored output_priority=0 (Utility).")
            elif choice in MENU:
                set_mode(sock, MENU[choice])
            else:
                print("Invalid choice.")


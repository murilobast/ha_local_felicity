#!/usr/bin/env python3
"""
Read and decode Felicity inverter data over the TCP bridge.

This module keeps all write operations out of scope and focuses on reading the
full status and settings blocks using the register map defined in registers.py.
"""

from __future__ import annotations

import argparse
import json
import math
import socket
from dataclasses import asdict, dataclass
from typing import Any

from registers import (
    FIELD_ENUMS,
    SETTINGS_BLOCK_COUNT,
    SETTINGS_BLOCK_START,
    SETTINGS_REGISTERS,
    SIGNED_REGISTERS,
    STATUS_BLOCK_COUNT,
    STATUS_BLOCK_START,
    STATUS_REGISTERS,
)


SERVER_HOST = "10.0.0.10"
SERVER_PORT = 54321
TIMEOUT = 2.0
SLAVE_ADDRESS = 0x01


@dataclass(frozen=True)
class DecodedRegister:
    address: int
    address_hex: str
    name: str
    raw: int
    value: float | int
    unit: str
    note: str
    mapped: bool
    signed: bool
    label: str | None = None


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


def to_signed_16(raw: int) -> int:
    return raw if raw < 0x8000 else raw - 0x10000


def build_read_request(start_address: int, count: int) -> bytes:
    frame = bytes(
        [
            SLAVE_ADDRESS,
            0x03,
            (start_address >> 8) & 0xFF,
            start_address & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        ]
    )
    crc = crc16(frame)
    return frame + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def recv_exactly(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("Connection closed by bridge")
        chunks.extend(chunk)
    return bytes(chunks)


class ModbusBridgeClient:
    def __init__(self, host: str = SERVER_HOST, port: int = SERVER_PORT, timeout: float = TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def __enter__(self) -> "ModbusBridgeClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def _require_socket(self) -> socket.socket:
        if self.sock is None:
            raise RuntimeError("Client is not connected")
        return self.sock

    def send_request(self, frame: bytes) -> bytes:
        sock = self._require_socket()
        sock.sendall(frame)

        header = recv_exactly(sock, 3)
        slave, function_code, third = header

        if slave != SLAVE_ADDRESS:
            raise RuntimeError(f"Unexpected slave in response: 0x{slave:02X}")

        if function_code & 0x80:
            rest = recv_exactly(sock, 2)
            payload = header + rest
            self._validate_crc(payload)
            raise RuntimeError(
                f"Modbus exception: fn=0x{function_code:02X} code=0x{rest[0]:02X}"
            )

        if function_code != 0x03:
            raise RuntimeError(f"Unsupported function code in response: 0x{function_code:02X}")

        payload = header + recv_exactly(sock, third + 2)
        self._validate_crc(payload)
        return payload

    def read_holding_registers(self, start_address: int, count: int) -> list[int]:
        response = self.send_request(build_read_request(start_address, count))
        byte_count = response[2]
        expected_byte_count = count * 2
        if byte_count != expected_byte_count:
            raise RuntimeError(
                f"Unexpected byte count: got {byte_count}, expected {expected_byte_count}"
            )

        data = response[3 : 3 + byte_count]
        return [(data[i] << 8) | data[i + 1] for i in range(0, len(data), 2)]

    @staticmethod
    def _validate_crc(frame: bytes) -> None:
        expected = crc16(frame[:-2])
        actual = frame[-2] | (frame[-1] << 8)
        if actual != expected:
            raise RuntimeError(
                f"CRC mismatch: got 0x{actual:04X}, expected 0x{expected:04X}"
            )


def decode_register(
    address: int,
    raw_value: int,
    metadata: tuple[str, float | int, str, str] | None,
) -> DecodedRegister:
    signed = address in SIGNED_REGISTERS
    interpreted = to_signed_16(raw_value) if signed else raw_value

    if metadata is None:
        return DecodedRegister(
            address=address,
            address_hex=f"0x{address:04X}",
            name=f"reg_0x{address:04X}",
            raw=raw_value,
            value=interpreted,
            unit="",
            note="unmapped register",
            mapped=False,
            signed=signed,
        )

    name, scale, unit, note = metadata
    value = interpreted * scale
    if isinstance(value, float) and value.is_integer():
        value = int(value)

    enum_map = FIELD_ENUMS.get(name)
    label = enum_map.get(interpreted) if enum_map else None

    return DecodedRegister(
        address=address,
        address_hex=f"0x{address:04X}",
        name=name,
        raw=raw_value,
        value=value,
        unit=unit,
        note=note,
        mapped=True,
        signed=signed,
        label=label,
    )


def decode_block(
    start_address: int,
    words: list[int],
    metadata_by_address: dict[int, tuple[str, float | int, str, str]],
) -> list[DecodedRegister]:
    return [
        decode_register(start_address + offset, raw_value, metadata_by_address.get(start_address + offset))
        for offset, raw_value in enumerate(words)
    ]


def build_field_map(registers: list[DecodedRegister]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for register in registers:
        fields[register.name] = register.value
        if register.label is not None:
            fields[f"{register.name}_label"] = register.label
    return fields


def estimate_battery_percent(status_fields: dict[str, Any], settings_fields: dict[str, Any]) -> int | None:
    battery_voltage = status_fields.get("battery_voltage")
    cutoff_voltage = settings_fields.get("discharge_cutoff_voltage")
    full_voltage = settings_fields.get("float_charge_voltage")

    if not all(isinstance(value, (int, float)) for value in (battery_voltage, cutoff_voltage, full_voltage)):
        return None

    usable_span = full_voltage - cutoff_voltage
    if usable_span <= 0:
        return None

    ratio = (battery_voltage - cutoff_voltage) / usable_span
    clamped = max(0.0, min(1.0, ratio))
    return int(math.floor((clamped * 100.0) + 0.5))


def read_status(client: ModbusBridgeClient) -> dict[str, Any]:
    words = client.read_holding_registers(STATUS_BLOCK_START, STATUS_BLOCK_COUNT)
    registers = decode_block(STATUS_BLOCK_START, words, STATUS_REGISTERS)
    return {
        "block": "status",
        "start_address": f"0x{STATUS_BLOCK_START:04X}",
        "count": STATUS_BLOCK_COUNT,
        "fields": build_field_map(registers),
        "registers": [asdict(item) for item in registers],
    }


def read_settings(client: ModbusBridgeClient) -> dict[str, Any]:
    words = client.read_holding_registers(SETTINGS_BLOCK_START, SETTINGS_BLOCK_COUNT)
    registers = decode_block(SETTINGS_BLOCK_START, words, SETTINGS_REGISTERS)
    return {
        "block": "settings",
        "start_address": f"0x{SETTINGS_BLOCK_START:04X}",
        "count": SETTINGS_BLOCK_COUNT,
        "fields": build_field_map(registers),
        "registers": [asdict(item) for item in registers],
    }


def read_all(client: ModbusBridgeClient) -> dict[str, Any]:
    status = read_status(client)
    settings = read_settings(client)
    battery_percent_estimate = estimate_battery_percent(status["fields"], settings["fields"])

    if battery_percent_estimate is not None:
        status["fields"]["battery_percent_estimate"] = battery_percent_estimate
        status["fields"]["battery_percent_estimate_note"] = (
            "derived from battery_voltage between discharge_cutoff_voltage and float_charge_voltage"
        )

    return {
        "connection": {
            "host": client.host,
            "port": client.port,
            "slave_address": SLAVE_ADDRESS,
        },
        "status": status,
        "settings": settings,
    }


def render_text_block(block: dict[str, Any]) -> str:
    lines = [
        f"[{block['block']}] start={block['start_address']} count={block['count']}",
    ]
    derived_fields = {
        name: value
        for name, value in block.get("fields", {}).items()
        if name.endswith("_estimate") or name.endswith("_estimate_note")
    }
    if derived_fields:
        for name, value in derived_fields.items():
            lines.append(f"{name:<39} {value}")

    for register in block["registers"]:
        value = register["value"]
        label = f" ({register['label']})" if register["label"] else ""
        unit = f" {register['unit']}" if register["unit"] else ""
        mapping = "" if register["mapped"] else " [unmapped]"
        lines.append(
            f"{register['address_hex']} {register['name']:<28} raw={register['raw']:<6} "
            f"value={value}{unit}{label}{mapping}"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read and decode Felicity inverter status/settings blocks"
    )
    parser.add_argument(
        "--host",
        default=SERVER_HOST,
        help=f"TCP bridge host (default: {SERVER_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=SERVER_PORT,
        help=f"TCP bridge port (default: {SERVER_PORT})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=TIMEOUT,
        help=f"Socket timeout in seconds (default: {TIMEOUT})",
    )
    parser.add_argument(
        "--block",
        choices=("status", "settings", "all"),
        default="all",
        help="Which block to read",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable text",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    with ModbusBridgeClient(host=args.host, port=args.port, timeout=args.timeout) as client:
        if args.block == "status":
            payload = read_status(client)
        elif args.block == "settings":
            payload = read_settings(client)
        else:
            payload = read_all(client)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.block == "all":
        print(render_text_block(payload["status"]))
        print()
        print(render_text_block(payload["settings"]))
        return 0

    print(render_text_block(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

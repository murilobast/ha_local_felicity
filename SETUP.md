# Felicity Inverter - Development Setup

## Topology

```
[Felicity Inverter] --RS232--> [USB Adapter] ---> [Linux Server] --TCP/IP--> [Mac Dev]
                                                    10.0.0.10                 (socat PTY)
```

## Configuration

| Item             | Value              |
|------------------|--------------------|
| Server IP        | `10.0.0.10`        |
| TCP Port         | `54321`            |
| Serial port      | `/dev/ttyUSB0`     |
| Baud rate        | `2400`             |
| Mac PTY path     | `/tmp/ttyFelicity` |

## Starting the Bridge

### On the Server (10.0.0.10) — run once, keep alive
```bash
socat -d -d tcp-listen:54321,reuseaddr,fork /dev/ttyUSB0,b2400,rawer
```
> `reuseaddr,fork` allows the Mac to reconnect without restarting socat on the server.

### On the Mac (dev machine) — Terminal 1, keep open
```bash
socat -d -d pty,link=/tmp/ttyFelicity,rawer tcp:10.0.0.10:54321
```

### On the Mac — Terminal 2, run the test
```bash
cd ~/Projects/FelicityHA232
source .venv/bin/activate
python3 teste.py
```

## Warnings

- **Never open `screen` or another program on `/tmp/ttyFelicity` while the Python script is running** — two processes on the same serial port will cause a `device disconnected` error.
- The Mac-side `socat` **dies when `screen` is closed abruptly**. Just restart it.
- When deploying to the server, change in the code: `/tmp/ttyFelicity` → `/dev/ttyUSB0`

## Inverter Protocol (PI30/Voltronic)

- Commands always end with `\r` (Carriage Return, `0x0D`)
- Responses also end with `\r` — always use `read_until(b'\r')` in pyserial
- Most commands require a **CRC** appended before `\r` (e.g. `QPIGS`, `QPIRI`)
- `QPI` (Query Protocol ID) does **not** require CRC — useful for connectivity testing
- `(NAK` response = command received but rejected (missing or wrong CRC)
- `(PI30` response = protocol confirmed ✅

## Python Environment

```bash
# Create venv (already created at .venv/)
python3 -m venv .venv
source .venv/bin/activate
pip install pyserial
```

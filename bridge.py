#!/usr/bin/env python3
"""
Minimal TCP-to-serial bridge for Modbus RTU.
Run on the server: python3 bridge.py
Proxies raw bytes between a TCP port and a serial device.
No external dependencies — stdlib only.
"""

import os
import sys
import socket
import select
import termios

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE   = 2400
HOST        = "0.0.0.0"
TCP_PORT    = 54321

BAUD_MAP = {
    1200:  termios.B1200,
    2400:  termios.B2400,
    4800:  termios.B4800,
    9600:  termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
}


def open_serial(port: str, baudrate: int) -> int:
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

    attrs = termios.tcgetattr(fd)

    # iflag: disable all input processing
    attrs[0] = 0
    # oflag: disable all output processing
    attrs[1] = 0
    # cflag: 8 data bits, enable receiver, ignore modem lines
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    # lflag: raw mode — no echo, no signals, no canonical
    attrs[3] = 0

    baud = BAUD_MAP[baudrate]
    attrs[4] = baud  # input speed
    attrs[5] = baud  # output speed

    # Non-blocking reads
    attrs[6][termios.VMIN]  = 0
    attrs[6][termios.VTIME] = 0

    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)

    return fd


def serve():
    serial_fd = open_serial(SERIAL_PORT, BAUD_RATE)
    print(f"Opened {SERIAL_PORT} at {BAUD_RATE} baud")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, TCP_PORT))
    server.listen(1)
    print(f"Listening on {HOST}:{TCP_PORT} — waiting for client...")

    try:
        while True:
            client, addr = server.accept()
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print(f"Client connected: {addr}")

            termios.tcflush(serial_fd, termios.TCIOFLUSH)

            try:
                while True:
                    rlist, _, _ = select.select([client, serial_fd], [], [], 5.0)

                    if not rlist:
                        continue

                    if client in rlist:
                        data = client.recv(256)
                        if not data:
                            print(f"Client disconnected: {addr}")
                            break
                        os.write(serial_fd, data)

                    if serial_fd in rlist:
                        data = os.read(serial_fd, 256)
                        if data:
                            client.sendall(data)

            except (ConnectionResetError, BrokenPipeError):
                print(f"Client dropped: {addr}")
            finally:
                client.close()

    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.close()
        os.close(serial_fd)


if __name__ == "__main__":
    if not os.path.exists(SERIAL_PORT):
        print(f"Error: {SERIAL_PORT} not found")
        sys.exit(1)
    serve()

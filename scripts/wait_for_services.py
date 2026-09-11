#!/usr/bin/env python3
"""Wait for Phase-1 local infrastructure to accept requests."""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request


def qdrant_ready() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:6333/readyz", timeout=1) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def redis_ready() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=1) as sock:
            sock.sendall(b"*1\r\n$4\r\nPING\r\n")
            return b"PONG" in sock.recv(64)
    except OSError:
        return False


def main() -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if qdrant_ready() and redis_ready():
            print("qdrant and redis are ready")
            return
        time.sleep(1)
    raise SystemExit("timed out waiting for qdrant and redis")


if __name__ == "__main__":
    main()

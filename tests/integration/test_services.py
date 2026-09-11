import socket
import urllib.request

import pytest

pytestmark = pytest.mark.integration


def test_qdrant_ready_endpoint() -> None:
    with urllib.request.urlopen("http://127.0.0.1:6333/readyz", timeout=3) as response:
        assert response.status == 200


def test_redis_ping() -> None:
    with socket.create_connection(("127.0.0.1", 6379), timeout=3) as sock:
        sock.sendall(b"*1\r\n$4\r\nPING\r\n")
        assert b"PONG" in sock.recv(64)

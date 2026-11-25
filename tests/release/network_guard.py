"""Python audit hook for local-only release smoke tests."""

from __future__ import annotations

import sys


def deny_network(event: str, _args: tuple[object, ...]) -> None:
    if event in {
        "socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
        "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg",
    }:
        raise AssertionError(f"Unexpected network request: {event}")


sys.addaudithook(deny_network)

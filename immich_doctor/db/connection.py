from __future__ import annotations

import socket
from contextlib import closing

import psycopg


def can_connect(dsn: str, timeout_seconds: int) -> tuple[bool, str]:
    try:
        with closing(psycopg.connect(dsn, connect_timeout=timeout_seconds)):
            return True, "PostgreSQL connection established."
    except Exception as exc:  # pragma: no cover - exact driver errors vary by environment
        return False, f"PostgreSQL connection failed: {exc}"


def can_resolve_host(host: str) -> tuple[bool, str]:
    try:
        socket.getaddrinfo(host, None)
        return True, "Database hostname resolved."
    except socket.gaierror as exc:
        return False, f"Database hostname resolution failed: {exc}."


def can_reach_tcp(host: str, port: int, timeout_seconds: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True, "Database TCP connection succeeded."
    except OSError as exc:
        return False, f"Database TCP connection failed: {exc}."

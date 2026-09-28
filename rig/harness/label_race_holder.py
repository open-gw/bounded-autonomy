"""In-pod holder for the Q3 label-race experiment. Invoked by label_race.py."""

from __future__ import annotations

import json
import os
import socket
import sys
import time

HOLD_PATH = "/tmp/ba-label-race.json"
GO_PATH = "/tmp/ba-label-race.go"


def main() -> int:
    ip = sys.argv[1]
    port = int(sys.argv[2])
    s = socket.create_connection((ip, port), 5)
    s.settimeout(20)
    req1 = (
        b"POST /tools/call HTTP/1.1\r\n"
        b"Host: records\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 2\r\n"
        b"Connection: keep-alive\r\n"
        b"\r\n"
        b"{}"
    )
    s.sendall(req1)
    try:
        first = s.recv(4096)
    except OSError as exc:
        first = str(exc).encode()
    with open(HOLD_PATH, "w", encoding="utf-8") as fh:
        json.dump({"phase": "held", "first_ok": bool(first)}, fh)
    deadline = time.time() + 45
    while time.time() < deadline and not os.path.exists(GO_PATH):
        time.sleep(0.1)
    req2 = (
        b"POST /tools/call HTTP/1.1\r\n"
        b"Host: records\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 2\r\n"
        b"Connection: close\r\n"
        b"\r\n"
        b"{}"
    )
    held_ok = False
    held_err = ""
    try:
        s.sendall(req2)
        second = s.recv(4096)
        held_ok = bool(second)
    except OSError as exc:
        held_err = str(exc)
    s.close()
    new_ok = False
    new_err = ""
    try:
        nxt = socket.create_connection((ip, port), 3)
        nxt.close()
        new_ok = True
    except OSError as exc:
        new_err = str(exc)
    with open(HOLD_PATH, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "phase": "done",
                "first_ok": bool(first),
                "held_open_survived": held_ok,
                "held_err": held_err,
                "new_connection_ok": new_ok,
                "new_err": new_err,
            },
            fh,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

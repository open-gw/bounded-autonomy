from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from observer.tempo import fetch_spans, search_url


def test_search_url_includes_time_range():
    url = search_url("http://tempo:3200", '{ name="verify" }', limit=20, start=100, end=200)
    assert "start=100" in url
    assert "end=200" in url
    assert "limit=20" in url
    assert "name" in url


def test_fetch_spans_uses_otlp_nanoseconds_not_duration_ms(monkeypatch):
    traces = {
        "/api/search": {
            "traces": [
                {
                    "traceID": "aa",
                    "rootTraceName": "verify",
                    "durationMs": 2,
                    "spanSet": {
                        "spans": [
                            {
                                "spanID": "1",
                                "name": "verify",
                                "startTimeUnixNano": "1000000000",
                                "durationNanos": "2000000",
                            }
                        ]
                    },
                },
                {
                    "traceID": "bb",
                    "rootTraceName": "verify",
                    "durationMs": 2,
                    "spanSet": {
                        "spans": [
                            {
                                "spanID": "2",
                                "name": "verify",
                                "startTimeUnixNano": "2000000000",
                                "durationNanos": "2000000",
                            }
                        ]
                    },
                },
            ]
        },
        "/api/traces/aa": {
            "batches": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "verify",
                                    "startTimeUnixNano": "1000000000",
                                    "endTimeUnixNano": "1003125000",
                                    "attributes": [
                                        {"key": "task_id", "value": {"stringValue": "t1"}},
                                        {"key": "mode", "value": {"stringValue": "flat"}},
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        "/api/traces/bb": {
            "batches": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "verify",
                                    "startTimeUnixNano": "2000000000",
                                    "endTimeUnixNano": "2001875000",
                                    "attributes": [
                                        {"key": "task_id", "value": {"stringValue": "t1"}},
                                        {"key": "mode", "value": {"stringValue": "flat"}},
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        },
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            body = traces.get(path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        df = fetch_spans(
            task_id="t1",
            tempo=f"http://127.0.0.1:{port}",
            attempts=1,
            pause=0,
            start=0,
            end=10,
        )
    finally:
        server.shutdown()
    verify = df[df["name"] == "verify"]
    assert len(verify) == 2
    durations = sorted(verify["duration_ms"].tolist())
    assert durations[0] == 1.875
    assert durations[1] == 3.125
    assert durations[0] != durations[1]


def test_fetch_spans_drops_traces_outside_run_window():
    traces = {
        "/api/search": {
            "traces": [
                {"traceID": "old"},
                {"traceID": "now"},
            ]
        },
        "/api/traces/old": {
            "batches": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "verify",
                                    "startTimeUnixNano": "1000000000000",
                                    "endTimeUnixNano": "1000002000000",
                                    "attributes": [
                                        {"key": "task_id", "value": {"stringValue": "t1"}},
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        "/api/traces/now": {
            "batches": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "verify",
                                    "startTimeUnixNano": "2000000000000",
                                    "endTimeUnixNano": "2000001875000",
                                    "attributes": [
                                        {"key": "task_id", "value": {"stringValue": "t1"}},
                                    ],
                                },
                                {
                                    "name": "verify",
                                    "startTimeUnixNano": "2001000000000",
                                    "endTimeUnixNano": "2001003125000",
                                    "attributes": [
                                        {"key": "task_id", "value": {"stringValue": "t1"}},
                                    ],
                                },
                            ]
                        }
                    ]
                }
            ]
        },
    }
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            path = self.path.split("?", 1)[0]
            body = traces.get(path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        df = fetch_spans(
            task_id="t1",
            tempo=f"http://127.0.0.1:{port}",
            attempts=1,
            pause=0,
            start=1990,
            end=2010,
        )
    finally:
        server.shutdown()
    search = [p for p in seen if p.startswith("/api/search")]
    assert search
    assert "start=1990" in search[0]
    assert "end=2010" in search[0]
    verify = df[df["name"] == "verify"]
    assert len(verify) == 2
    epochs = sorted(verify["start_epoch"].tolist())
    assert epochs[0] == 2000.0
    assert epochs[1] == 2001.0

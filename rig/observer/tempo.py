"""Pull verify and run spans from Tempo into a DataFrame."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

TEMPO_DEFAULT = "http://tempo:3200"


def _get(url: str, timeout: float = 10.0) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def search_url(tempo: str, query: str, *, limit: int, start: int, end: int) -> str:
    q = urllib.parse.urlencode(
        {
            "q": query,
            "limit": str(limit),
            "start": str(int(start)),
            "end": str(int(end)),
        }
    )
    return f"{tempo.rstrip('/')}/api/search?{q}"


def search_traces(
    tempo: str,
    query: str,
    limit: int = 200,
    *,
    start: int | None = None,
    end: int | None = None,
) -> list[dict[str, Any]]:
    now = int(time.time())
    if end is None:
        end = now + 60
    if start is None:
        start = end - 7200
    raw = _get(search_url(tempo, query, limit=limit, start=start, end=end))
    doc = json.loads(raw.decode())
    return list(doc.get("traces") or [])


def _attr_value(val: Any) -> Any:
    if not isinstance(val, dict):
        return val
    if "stringValue" in val:
        return val.get("stringValue")
    if "boolValue" in val:
        return val.get("boolValue")
    if "intValue" in val:
        return val.get("intValue")
    if "doubleValue" in val:
        return val.get("doubleValue")
    return None


def _span_sets(trace: dict[str, Any]) -> list[dict[str, Any]]:
    sets = list(trace.get("spanSets") or trace.get("span_sets") or [])
    if trace.get("spanSet"):
        sets.append(trace["spanSet"])
    return sets


def _span_rows(trace: dict[str, Any], export: str = "tempo") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for span_set in _span_sets(trace):
        for span in span_set.get("spans") or []:
            name = str(span.get("name") or "")
            start = int(span.get("startTimeUnixNano") or span.get("startTimeUnixNanos") or 0)
            dur_ns = int(span.get("durationNanos") or 0)
            attrs = {}
            for kv in span.get("attributes") or []:
                attrs[kv.get("key")] = _attr_value(kv.get("value") or {})
            end = start + dur_ns if start else 0
            rows.append(
                {
                    "name": name,
                    "duration_ms": dur_ns / 1_000_000.0,
                    "mode": attrs.get("mode"),
                    "task_id": attrs.get("task_id"),
                    "start_epoch": start / 1e9 if start else None,
                    "end_epoch": end / 1e9 if end else None,
                    "export": export,
                }
            )
    return rows


def _rows_from_otlp(doc: dict[str, Any], task_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    batches = doc.get("batches") or doc.get("resourceSpans") or []
    for batch in batches:
        for ss in batch.get("scopeSpans") or batch.get("instrumentationLibrarySpans") or []:
            for span in ss.get("spans") or []:
                attrs = {}
                for kv in span.get("attributes") or []:
                    attrs[kv.get("key")] = _attr_value(kv.get("value") or {})
                if attrs.get("task_id") not in (None, "", task_id):
                    continue
                start = int(span.get("startTimeUnixNano") or 0)
                end = int(span.get("endTimeUnixNano") or 0)
                dur_ns = int(span.get("durationNanos") or 0)
                if end and start:
                    dur_ms = (end - start) / 1_000_000.0
                else:
                    dur_ms = dur_ns / 1_000_000.0
                rows.append(
                    {
                        "name": span.get("name") or "",
                        "duration_ms": dur_ms,
                        "mode": attrs.get("mode"),
                        "task_id": attrs.get("task_id") or task_id,
                        "start_epoch": start / 1e9 if start else None,
                        "end_epoch": end / 1e9 if end else None,
                        "export": "tempo",
                    }
                )
    return rows


def _in_window(row: dict[str, Any], start: int, end: int) -> bool:
    epoch = row.get("start_epoch")
    if epoch is None:
        return True
    return start <= float(epoch) <= end


def fetch_spans(
    *,
    task_id: str,
    tempo: str = TEMPO_DEFAULT,
    attempts: int = 12,
    pause: float = 1.0,
    start: int | None = None,
    end: int | None = None,
) -> pd.DataFrame:
    """Pull spans for ``task_id``. ``start``/``end`` are unix seconds.

    A retry that reuses the same ``task_id`` must pass this run's window so
    leftover traces from a SIGTERM'd attempt are not ingested.
    """
    queries = [
        f'{{ span.task_id="{task_id}" }}',
        f'{{ name="verify" && span.task_id="{task_id}" }}',
        '{ name="verify" }',
        '{ name="run" }',
    ]
    last = pd.DataFrame()
    now = int(time.time())
    if end is None:
        end = now + 60
    if start is None:
        start = end - 7200
    for _ in range(attempts):
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in queries:
            for tr in search_traces(tempo, query, start=start, end=end):
                tid = str(tr.get("traceID") or tr.get("traceId") or "")
                if tid and tid in seen:
                    continue
                if tid:
                    seen.add(tid)
                try:
                    raw = _get(f"{tempo.rstrip('/')}/api/traces/{tid}")
                    doc = json.loads(raw.decode())
                except Exception:
                    rows.extend(_span_rows(tr))
                    continue
                batches = doc.get("batches") or doc.get("resourceSpans") or []
                if batches:
                    rows.extend(_rows_from_otlp(doc, task_id))
                else:
                    rows.extend(_span_rows(tr))
        if task_id:
            rows = [r for r in rows if not r.get("task_id") or r.get("task_id") == task_id]
        rows = [r for r in rows if _in_window(r, start, end)]
        verify = [r for r in rows if r["name"] == "verify"]
        last = pd.DataFrame(rows)
        if len(verify) >= 2:
            return last
        time.sleep(pause)
    return last

"""Tracer for tool-server verify spans and the run root span."""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

_PROVIDER: TracerProvider | None = None


def tracer(service_name: str):
    global _PROVIDER
    endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
    )
    if _PROVIDER is None:
        _PROVIDER = TracerProvider(
            resource=Resource.create({"service.name": service_name})
        )
        exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
        _PROVIDER.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(_PROVIDER)
    return trace.get_tracer(service_name)


def force_flush() -> None:
    if _PROVIDER is not None:
        _PROVIDER.force_flush()

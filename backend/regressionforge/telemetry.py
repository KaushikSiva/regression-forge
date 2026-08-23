from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


class Telemetry:
    def __init__(self, path: Path, endpoint: str = ""):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": "regressionforge",
                    "service.version": "1.0.0",
                    "deployment.environment": "regression-demo",
                }
            )
        )
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                provider.add_span_processor(
                    SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
                )
            except Exception:
                pass
        try:
            trace.set_tracer_provider(provider)
        except Exception:
            pass
        self.tracer = trace.get_tracer("regressionforge.runner", "1.0.0")

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
        started = time.perf_counter()
        error = ""
        with self.tracer.start_as_current_span(name, attributes=attributes or {}) as current:
            try:
                yield current
            except Exception as exc:
                error = str(exc)
                current.record_exception(exc)
                current.set_status(trace.Status(trace.StatusCode.ERROR, error))
                raise
            finally:
                record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "span": name,
                    "trace_id": format(current.get_span_context().trace_id, "032x"),
                    "span_id": format(current.get_span_context().span_id, "016x"),
                    "status": "ERROR" if error else "OK",
                    "error": error,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "attributes": attributes or {},
                }
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, default=str, sort_keys=True) + "\n")

    @staticmethod
    def trace_id() -> str:
        return format(trace.get_current_span().get_span_context().trace_id, "032x")


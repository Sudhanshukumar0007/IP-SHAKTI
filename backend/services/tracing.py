from __future__ import annotations

import contextvars
import logging
import uuid

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get("-")
        return True


def new_trace_id() -> str:
    tid = uuid.uuid4().hex[:16]
    trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    return trace_id_var.get("-")


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='{"event":"%(name)s","level":"%(levelname)s","trace_id":"%(trace_id)s","msg":"%(message)s"}',
        )
    for handler in root.handlers:
        handler.addFilter(TraceIdFilter())

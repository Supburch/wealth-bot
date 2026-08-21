"""Per-request correlation ID for tracing one webhook request across its logs."""
import contextvars
import logging

# Default "-" marks log lines emitted outside a request context (startup, health, etc.).
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    """Stamp the current correlation ID onto every :class:`logging.LogRecord`."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True

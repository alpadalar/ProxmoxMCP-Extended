"""Secret redaction for logs and error messages (stdlib only).

Secrets (the API token, guest commands) are registered once and scrubbed from
every log record by :class:`RedactingFilter` and from error text by :func:`redact`.
"""
import logging
import threading
from collections import OrderedDict

__all__ = ["register_secret", "register_sensitive", "redact", "RedactingFilter"]

REDACTED = "[REDACTED]"
MIN_SECRET_LEN = 4
MAX_SENSITIVE = 256

_lock = threading.Lock()
_secrets: "set[str]" = set()
# Transient sensitive values (e.g. guest commands); bounded so memory cannot grow forever.
_sensitive: "OrderedDict[str, None]" = OrderedDict()


def register_secret(value: str) -> None:
    """Permanently register a secret; values shorter than 4 chars are ignored."""
    if isinstance(value, str) and len(value) >= MIN_SECRET_LEN:
        with _lock:
            _secrets.add(value)


def register_sensitive(value: str) -> None:
    """Register a bounded-lifetime sensitive value (oldest are evicted)."""
    if isinstance(value, str) and len(value) >= MIN_SECRET_LEN:
        with _lock:
            _sensitive[value] = None
            _sensitive.move_to_end(value)
            while len(_sensitive) > MAX_SENSITIVE:
                _sensitive.popitem(last=False)


def redact(text: str) -> str:
    """Replace every registered secret in ``text`` (longest first). Idempotent."""
    if not isinstance(text, str) or not text:
        return text
    with _lock:
        values = sorted(_secrets.union(_sensitive), key=len, reverse=True)
    for value in values:
        if value in text:
            text = text.replace(value, REDACTED)
    return text


class RedactingFilter(logging.Filter):
    """Scrub registered secrets from the message, args and exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact(message)
        record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True

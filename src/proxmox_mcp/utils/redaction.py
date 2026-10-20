"""Secret redaction for logs and error messages (stdlib only).

Only the configured API token is registered (bounded, process-wide). Caller-supplied
values must never be registered globally; use :func:`redact_local` for per-call scrubbing.
"""

import logging
import threading

__all__ = ["register_secret", "redact_local", "redact", "safe_error_message", "RedactingFilter"]

REDACTED = "[REDACTED]"
MIN_SECRET_LEN = 4
MIN_LOCAL_LEN = 8

_lock = threading.Lock()
_secrets: "set[str]" = set()


def register_secret(value: str) -> None:
    """Permanently register a secret; values shorter than 4 chars are ignored."""
    if isinstance(value, str) and len(value) >= MIN_SECRET_LEN:
        with _lock:
            _secrets.add(value)


def redact_local(text: str, *values: str) -> str:
    """Redact registered secrets plus ``values`` for this call only (nothing is stored).

    Values shorter than ``MIN_LOCAL_LEN`` are ignored so short caller input cannot
    mangle unrelated text.
    """
    if not isinstance(text, str) or not text:
        return text
    for value in sorted((v for v in values if isinstance(v, str)), key=len, reverse=True):
        if len(value) >= MIN_LOCAL_LEN:
            text = text.replace(value, REDACTED)
    return redact(text)


def redact(text: str) -> str:
    """Replace every registered secret in ``text`` (longest first). Idempotent."""
    if not isinstance(text, str) or not text:
        return text
    with _lock:
        values = sorted(_secrets, key=len, reverse=True)
    for value in values:
        if value in text:
            text = text.replace(value, REDACTED)
    return text


def safe_error_message(exc: BaseException) -> str:
    """Startup-safe error text: redacted, and without echoed input for validation errors."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            parts = [
                f"{'.'.join(str(x) for x in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
                for err in errors()
            ]
            return redact(f"{type(exc).__name__}: " + "; ".join(parts))
        except Exception:
            return type(exc).__name__
    return redact(str(exc))


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

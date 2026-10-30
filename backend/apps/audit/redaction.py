"""Keeps sensitive values out of the audit log and the application log files."""
import logging
import re

REDACTED = "[REDACTED]"

# Any key containing one of these words is redacted, e.g. "new_password", "ssn_full".
SENSITIVE_KEY_PARTS = ("password", "secret", "token", "ssn", "social_security", "document_number",
                       "passport_number", "licence_number", "license_number", "mrz", "cookie", "csrf")

# Patterns redacted from free text in log lines.
_SSN_PATTERN = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
_KEY_VALUE_PATTERN = re.compile(r"(?i)\b(password|secret|token|ssn)\b(\s*[=:]\s*)(\S+)")


def is_sensitive_key(key) -> bool:
    k = str(key).lower()
    return any(part in k for part in SENSITIVE_KEY_PARTS)


def scrub(value, depth: int = 0):
    """Return a copy of value with sensitive keys replaced. Works on nested dicts and lists."""
    if depth > 8:
        return REDACTED
    if isinstance(value, dict):
        return {k: (REDACTED if is_sensitive_key(k) else scrub(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v, depth + 1) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def scrub_text(text: str) -> str:
    text = _SSN_PATTERN.sub(REDACTED, text)
    return _KEY_VALUE_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)


class RedactingFilter(logging.Filter):
    """Logging filter: rewrites every log message through scrub_text before it is written."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        record.msg = scrub_text(message)
        record.args = ()
        return True

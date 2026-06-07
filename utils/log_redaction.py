"""Defense-in-depth logging redaction.

Scrubs secret values from log records before they reach any handler so that a
credential can never be written to a log file, even if some code path logs it
by mistake. This guards against incidents like an app password being written
to ``logs/magazine.log`` in plaintext.
"""
import logging
import os
import re

# Environment variable names whose values must never appear in logs.
SENSITIVE_ENV_KEYS = (
    "EMAIL_APP_PASSWORD",
    "SERVER_PASSWORD",
    "SECRET_KEY",
    "DYNAMICS_CLIENT_SECRET",
    "AZURE_CLIENT_SECRET",
    "DROPBOX_CLIENT_SECRET",
)

REDACTION = "***REDACTED***"

# Catches explicit "password: value" / "secret=value" style logging regardless
# of whether the exact value is known to us. No leading word boundary so it also
# matches compound keys like "client_secret=..."; the mandatory ":"/"=" separator
# immediately after the keyword keeps false positives low.
_KEYED_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key)"
    r"\s*[:=]\s*"
    r"(\"?)([^\s\"']+)\2"
)


class SecretRedactingFilter(logging.Filter):
    """Logging filter that replaces secret values with a placeholder.

    It redacts in two ways:
    1. Exact known secret values read from the environment.
    2. Anything that looks like a logged ``password:``/``secret=`` assignment.
    """

    def __init__(self, extra_secrets=None):
        super().__init__()
        self._secrets = self._collect_secrets(extra_secrets)

    @staticmethod
    def _collect_secrets(extra_secrets):
        secrets = set()
        for key in SENSITIVE_ENV_KEYS:
            value = os.getenv(key)
            # Ignore very short values to avoid mangling unrelated log text.
            if value and len(value) >= 4:
                secrets.add(value)
        for value in extra_secrets or ():
            if value and len(str(value)) >= 4:
                secrets.add(str(value))
        return secrets

    def _redact(self, text):
        if not text:
            return text
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, REDACTION)
        text = _KEYED_SECRET_PATTERN.sub(
            lambda m: f"{m.group(1)}{text[m.start(1) + len(m.group(1)):m.start(3)]}{REDACTION}",
            text,
        )
        return text

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = self._redact(message)
        if redacted != message:
            # Replace the fully rendered message and drop args so the
            # placeholders are not re-expanded by the handler.
            record.msg = redacted
            record.args = ()
        return True


def install_secret_redaction(logger=None, extra_secrets=None):
    """Attach :class:`SecretRedactingFilter` to a logger and its handlers.

    Defaults to the root logger so the filter applies process-wide. Safe to
    call multiple times; it will not add duplicate filters.
    """
    target = logger if logger is not None else logging.getLogger()

    def _already_installed(holder):
        return any(isinstance(f, SecretRedactingFilter) for f in holder.filters)

    if not _already_installed(target):
        target.addFilter(SecretRedactingFilter(extra_secrets))

    # Filters on a logger do not run for records produced by child loggers, so
    # also attach to handlers (which see every record they emit).
    for handler in target.handlers:
        if not _already_installed(handler):
            handler.addFilter(SecretRedactingFilter(extra_secrets))

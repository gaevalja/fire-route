"""Validated local configuration; .env is data, never shell code."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    pass


def read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            raise ConfigurationError(f"Invalid .env assignment at line {number}")
        value = value.strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ConfigurationError(f"Unclosed .env quote at line {number}")
            value = value[1:-1]
        result[key.strip()] = value
    return result


def http_url(value: str, name: str) -> str:
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError as exc:
        raise ConfigurationError(f"Invalid {name}") from exc
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment
            or any(ch.isspace() for ch in value)):
        raise ConfigurationError(f"{name} must be an HTTP(S) URL without credentials/query/fragment")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    cse_url: str = "http://127.0.0.1:8080"
    cse_base: str = "fire-route-dev"
    release: str = "4"
    admin_originator: str = "CAdmin"
    notification_url: str = "http://127.0.0.1:8000/onem2m/notify"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    request_timeout: float = 5.0
    startup_timeout: float = 60.0
    notification_timeout: float = 10.0
    sensor_ttl: float = 30.0
    max_clock_skew: float = 5.0
    ack_timeout: float = 10.0
    retry_limit: int = 2
    retention_seconds: int = 86400
    evidence_root: Path = Path("evidence")
    runtime_info: Path | None = None
    cse_mode: str = "real"
    mec_mode: str = "unavailable"
    demo_mode: str = "simulator"

    def __post_init__(self) -> None:
        http_url(self.cse_url, "CSE_BASE_URL")
        http_url(self.notification_url, "NOTIFICATION_PUBLIC_URL")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.cse_base):
            raise ConfigurationError("CSE_BASE_RESOURCE must be a single resource name")
        if self.release not in {"3", "4", "5"}:
            raise ConfigurationError("CSE_RELEASE must be an explicit supported profile (3, 4 or 5)")
        if not self.admin_originator or self.admin_originator in {"SET_ME", "VERIFY_INSTALLED_RELEASE"}:
            raise ConfigurationError("Set CSE_ORIGINATOR for the selected CSE")
        if any(ch in self.admin_originator for ch in "\r\n"):
            raise ConfigurationError("Invalid originator header")
        if self.cse_mode != "real" or self.mec_mode != "unavailable" or self.demo_mode != "simulator":
            raise ConfigurationError("P0 smoke supports real CSE + unavailable MEC + synthetic input only")
        if type(self.bind_port) is not int or not 0 < self.bind_port < 65536:
            raise ConfigurationError("Notification port out of range")
        import math
        for name in ("request_timeout", "startup_timeout", "notification_timeout", "sensor_ttl", "max_clock_skew", "ack_timeout"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ConfigurationError(f"{name} must be finite and positive")
        if (type(self.retry_limit) is not int or not 0 <= self.retry_limit <= 5
                or type(self.retention_seconds) is not int or self.retention_seconds < 60):
            raise ConfigurationError("Invalid retry or resource retention budget")
        if urlsplit(self.notification_url).path != "/onem2m/notify":
            raise ConfigurationError("P0 callback path must be /onem2m/notify")

    @classmethod
    def load(cls, env: dict[str, str] | None = None, dotenv: Path = Path(".env")) -> "Settings":
        values = read_dotenv(dotenv)
        values.update(os.environ if env is None else env)
        fields = {
            "CSE_BASE_URL": ("cse_url", str), "CSE_BASE_RESOURCE": ("cse_base", str),
            "CSE_RELEASE": ("release", str), "CSE_ORIGINATOR": ("admin_originator", str),
            "NOTIFICATION_PUBLIC_URL": ("notification_url", str),
            "NOTIFICATION_BIND_HOST": ("bind_host", str), "NOTIFICATION_BIND_PORT": ("bind_port", int),
            "REQUEST_TIMEOUT_SECONDS": ("request_timeout", float),
            "STARTUP_TIMEOUT_SECONDS": ("startup_timeout", float),
            "NOTIFICATION_TIMEOUT_SECONDS": ("notification_timeout", float),
            "SENSOR_TTL_SECONDS": ("sensor_ttl", float), "MAX_CLOCK_SKEW_SECONDS": ("max_clock_skew", float),
            "ACK_TIMEOUT_SECONDS": ("ack_timeout", float), "RETRY_LIMIT": ("retry_limit", int),
            "RESOURCE_RETENTION_SECONDS": ("retention_seconds", int),
            "EVIDENCE_ROOT": ("evidence_root", Path), "CSE_MODE": ("cse_mode", str),
            "MEC_MODE": ("mec_mode", str), "DEMO_MODE": ("demo_mode", str),
        }
        kwargs = {}
        for key, (field, converter) in fields.items():
            if key in values:
                try:
                    kwargs[field] = converter(values[key])
                except (ValueError, TypeError) as exc:
                    raise ConfigurationError(f"Invalid {key}") from exc
        if values.get("CSE_RUNTIME_INFO"):
            kwargs["runtime_info"] = Path(values["CSE_RUNTIME_INFO"])
        return cls(**kwargs)

    def public(self) -> dict:
        return {
            "cse_base": self.cse_base, "release": self.release,
            "cse_mode": self.cse_mode, "mec_mode": self.mec_mode, "data_origin": "SYNTHETIC",
            "request_timeout_seconds": self.request_timeout, "startup_timeout_seconds": self.startup_timeout,
            "notification_timeout_seconds": self.notification_timeout, "sensor_ttl_seconds": self.sensor_ttl,
            "max_clock_skew_seconds": self.max_clock_skew, "ack_timeout_seconds": self.ack_timeout,
            "retry_limit": self.retry_limit, "resource_retention_seconds": self.retention_seconds,
            "security_profile": "isolated_local_HTTP_header_identity_only",
        }

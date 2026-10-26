"""Groww Trading API authentication, single-mode selection, and secret redaction.

Official Groww authentication methods supported:
1. Direct Access Token (`GROWW_AUTH_MODE=access_token`):
   Uses `GROWW_ACCESS_TOKEN` directly (`GrowwAPI(access_token)`). Expires daily at 06:00 AM IST.
2. TOTP Flow (`GROWW_AUTH_MODE=totp`):
   Uses `GROWW_API_KEY` (TOTP token) and `GROWW_TOTP_SECRET` (via `pyotp.TOTP(secret).now()`)
   or `GROWW_TOTP_CODE`, calling `GrowwAPI.get_access_token(api_key=..., totp=...)`.
3. API Key + Secret Flow (`GROWW_AUTH_MODE=api_key_secret`):
   Uses `GROWW_API_KEY` and `GROWW_API_SECRET` (requires daily approval on Groww Cloud portal),
   calling `GrowwAPI.get_access_token(api_key=..., secret=...)`.

Safety rule:
* Exactly ONE authentication mode is selected at startup.
* If that mode fails authentication, `ProviderAuthError` is raised immediately.
  The runtime NEVER silently falls back to another authentication method.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import inspect
import re
from typing import Any

from app.providers.base import ProviderAuthError, ProviderError, ProviderUnavailableError


class GrowwAuthMode(StrEnum):
    """Explicit Groww authentication mode selected at startup."""

    ACCESS_TOKEN = "access_token"
    TOTP = "totp"
    API_KEY_SECRET = "api_key_secret"
    NONE = "none"


_JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[^\s\"',;]+")
_KV_SECRET_PATTERN = re.compile(
    r"(?i)((?:access_token|api_key|api_secret|secret|totp|totp_secret|groww_access_token|groww_api_key|groww_api_secret|groww_totp_secret|authorization)\s*[=:]\s*)[^\s\"',;]+"
)

_AUTH_ERROR_KEYWORDS: tuple[str, ...] = (
    "authentication",
    "authorisation",
    "authorization",
    "unauthorised",
    "unauthorized",
    "invalid token",
    "token expired",
    "expired token",
    "invalid api key",
    "invalid totp",
    "invalid secret",
    "ga005",
    "401",
    "403",
)


def redact_groww_secrets(text: str | None, *, secrets: tuple[str, ...] = ()) -> str:
    """Redact Groww tokens, API keys, secrets, TOTP secrets/codes, and JWTs from any string."""
    if not text:
        return ""
    out = str(text)
    for secret in secrets:
        cleaned = secret.strip() if secret else ""
        if len(cleaned) >= 4:
            out = out.replace(cleaned, "[REDACTED]")
    out = _JWT_PATTERN.sub("[REDACTED_JWT]", out)
    out = _BEARER_PATTERN.sub(lambda m: f"{m.group(1)}[REDACTED]", out)
    out = _KV_SECRET_PATTERN.sub(lambda m: f"{m.group(1)}[REDACTED]", out)
    return out


def generate_groww_checksum(secret: str, timestamp_epoch_sec: str | int) -> str:
    """Generate SHA-256 checksum of `secret + str(timestamp_epoch_sec)` per Groww cURL spec."""
    clean_secret = secret.strip()
    ts_str = str(timestamp_epoch_sec).strip()
    if not clean_secret or not ts_str:
        raise ValueError("Both secret and timestamp_epoch_sec are required to generate checksum")
    payload = f"{clean_secret}{ts_str}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_groww_auth_exception(exc: BaseException | str) -> bool:
    """Return True if an exception or error message indicates a Groww auth/permission failure."""
    cls_name = exc.__class__.__name__.lower() if isinstance(exc, BaseException) else ""
    if "authentication" in cls_name or "authorisation" in cls_name or "authorization" in cls_name:
        return True
    code = getattr(exc, "code", None)
    if code and str(code).upper() in {"GA005", "401", "403"}:
        return True
    text = str(exc).lower()
    return any(k in text for k in _AUTH_ERROR_KEYWORDS)


@dataclass(frozen=True)
class GrowwCredentials:
    """Server-side Groww credentials container with strict single-mode selection and redacted repr."""

    auth_mode: str = ""
    access_token: str = ""
    api_key: str = ""
    api_secret: str = ""
    totp_secret: str = ""
    totp_code: str = ""

    def secret_values(self) -> tuple[str, ...]:
        vals = (
            self.access_token.strip(),
            self.api_key.strip(),
            self.api_secret.strip(),
            self.totp_secret.strip(),
            self.totp_code.strip(),
        )
        return tuple(v for v in vals if v)

    def select_auth_mode(self) -> GrowwAuthMode:
        """Determine the single explicit authentication mode configured at startup.

        Raises ProviderAuthError if an explicit mode is requested but its required
        credentials are missing, or if multiple distinct authentication modes are
        simultaneously populated without an explicit `auth_mode` selector.
        """
        explicit = self.auth_mode.strip().lower()
        has_token = bool(self.access_token.strip())
        has_key = bool(self.api_key.strip())
        has_secret = bool(self.api_secret.strip())
        has_totp = bool(self.totp_secret.strip() or self.totp_code.strip())

        if explicit and explicit != "auto":
            if explicit == GrowwAuthMode.ACCESS_TOKEN.value:
                if not has_token:
                    raise ProviderAuthError(
                        "GROWW_AUTH_MODE is set to 'access_token', but GROWW_ACCESS_TOKEN is empty."
                    )
                return GrowwAuthMode.ACCESS_TOKEN
            if explicit == GrowwAuthMode.TOTP.value:
                if not (has_key and has_totp):
                    raise ProviderAuthError(
                        "GROWW_AUTH_MODE is set to 'totp', but GROWW_API_KEY or GROWW_TOTP_SECRET/GROWW_TOTP_CODE is missing."
                    )
                return GrowwAuthMode.TOTP
            if explicit == GrowwAuthMode.API_KEY_SECRET.value:
                if not (has_key and has_secret):
                    raise ProviderAuthError(
                        "GROWW_AUTH_MODE is set to 'api_key_secret', but GROWW_API_KEY or GROWW_API_SECRET is missing."
                    )
                return GrowwAuthMode.API_KEY_SECRET
            if explicit == GrowwAuthMode.NONE.value:
                return GrowwAuthMode.NONE
            raise ProviderAuthError(
                f"Unsupported GROWW_AUTH_MODE {self.auth_mode!r}. Expected 'access_token', 'totp', or 'api_key_secret'."
            )

        # When auth_mode is blank or 'auto', ensure there is no ambiguous multi-mode configuration
        configured_modes: list[GrowwAuthMode] = []
        if has_token:
            configured_modes.append(GrowwAuthMode.ACCESS_TOKEN)
        if has_key and has_totp:
            configured_modes.append(GrowwAuthMode.TOTP)
        if has_key and has_secret:
            configured_modes.append(GrowwAuthMode.API_KEY_SECRET)

        if len(configured_modes) > 1:
            mode_names = ", ".join(m.value for m in configured_modes)
            raise ProviderAuthError(
                f"Multiple Groww authentication modes are populated ({mode_names}). "
                "Set GROWW_AUTH_MODE explicitly to 'access_token', 'totp', or 'api_key_secret' "
                "so the server never guesses or falls back between auth flows."
            )
        if len(configured_modes) == 1:
            return configured_modes[0]

        if has_key or has_secret or has_totp:
            raise ProviderAuthError(
                "Incomplete Groww credentials configured. Provide either GROWW_ACCESS_TOKEN, "
                "or (GROWW_API_KEY + GROWW_TOTP_SECRET), or (GROWW_API_KEY + GROWW_API_SECRET)."
            )
        return GrowwAuthMode.NONE

    @property
    def is_configured(self) -> bool:
        try:
            return self.select_auth_mode() is not GrowwAuthMode.NONE
        except ProviderAuthError:
            return False

    def __repr__(self) -> str:
        return (
            f"GrowwCredentials(auth_mode={self.auth_mode!r}, "
            f"access_token={'[REDACTED]' if self.access_token.strip() else '[EMPTY]'}, "
            f"api_key={'[REDACTED]' if self.api_key.strip() else '[EMPTY]'}, "
            f"api_secret={'[REDACTED]' if self.api_secret.strip() else '[EMPTY]'}, "
            f"totp_secret={'[REDACTED]' if self.totp_secret.strip() else '[EMPTY]'})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class GrowwSdkCompatibilityReport:
    """Result of inspecting the installed growwapi package."""

    installed: bool
    compatible: bool
    sdk_version: str | None
    has_groww_api: bool
    has_groww_feed: bool
    missing_api_methods: tuple[str, ...]
    missing_feed_methods: tuple[str, ...]
    detail: str


REQUIRED_GROWW_API_METHODS: tuple[str, ...] = (
    "get_quote",
    "get_ltp",
    "get_ohlc",
    "get_instrument_by_groww_symbol",
    "get_instrument_by_exchange_and_trading_symbol",
)

REQUIRED_GROWW_FEED_METHODS: tuple[str, ...] = (
    "subscribe_index_value",
    "get_index_value",
    "unsubscribe_index_value",
    "consume",
)


def verify_groww_sdk_compatibility(
    api_cls: type | None = None,
    feed_cls: type | None = None,
) -> GrowwSdkCompatibilityReport:
    """Verify that `growwapi` (or injected classes) exposes required API and Feed methods."""
    sdk_version: str | None = None
    if api_cls is None or feed_cls is None:
        try:
            import growwapi  # type: ignore[import-not-found]

            sdk_version = getattr(growwapi, "__version__", "unknown")
            api_cls = api_cls or getattr(growwapi, "GrowwAPI", None)
            feed_cls = feed_cls or getattr(growwapi, "GrowwFeed", None)
        except ImportError:
            return GrowwSdkCompatibilityReport(
                installed=False,
                compatible=False,
                sdk_version=None,
                has_groww_api=False,
                has_groww_feed=False,
                missing_api_methods=(),
                missing_feed_methods=(),
                detail="growwapi package is not installed in the current Python environment.",
            )

    if api_cls is None or feed_cls is None:
        return GrowwSdkCompatibilityReport(
            installed=True,
            compatible=False,
            sdk_version=sdk_version,
            has_groww_api=api_cls is not None,
            has_groww_feed=feed_cls is not None,
            missing_api_methods=REQUIRED_GROWW_API_METHODS if api_cls is None else (),
            missing_feed_methods=REQUIRED_GROWW_FEED_METHODS if feed_cls is None else (),
            detail="growwapi is missing GrowwAPI or GrowwFeed class.",
        )

    missing_api = [
        m for m in REQUIRED_GROWW_API_METHODS if not callable(getattr(api_cls, m, None))
    ]
    # Also check historical candles method (get_historical_candles in >=1.0.0 or get_historical_candle_data)
    if not (
        callable(getattr(api_cls, "get_historical_candles", None))
        or callable(getattr(api_cls, "get_historical_candle_data", None))
    ):
        missing_api.append("get_historical_candles")

    missing_feed = [
        m for m in REQUIRED_GROWW_FEED_METHODS if not callable(getattr(feed_cls, m, None))
    ]

    compatible = not missing_api and not missing_feed
    detail = (
        "GrowwAPI and GrowwFeed methods verified."
        if compatible
        else f"Incompatible growwapi SDK: missing_api={tuple(missing_api)}, missing_feed={tuple(missing_feed)}"
    )
    return GrowwSdkCompatibilityReport(
        installed=True,
        compatible=compatible,
        sdk_version=sdk_version,
        has_groww_api=True,
        has_groww_feed=True,
        missing_api_methods=tuple(missing_api),
        missing_feed_methods=tuple(missing_feed),
        detail=detail,
    )


def _generate_totp_code(totp_secret: str) -> str:
    try:
        import pyotp  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProviderAuthError(
            "pyotp package is required for GROWW_AUTH_MODE='totp' (pip install pyotp)."
        ) from exc
    try:
        code = str(pyotp.TOTP(totp_secret.strip()).now()).strip()
    except Exception as exc:
        raise ProviderAuthError("Failed to generate TOTP code from GROWW_TOTP_SECRET.") from exc
    if not code or not code.isdigit():
        raise ProviderAuthError("Generated TOTP code is invalid.")
    return code


def authenticate_groww_client(
    credentials: GrowwCredentials,
    *,
    api_cls: type | None = None,
    totp_generator: Callable[[str], str] | None = None,
) -> tuple[Any, GrowwAuthMode]:
    """Authenticate and return `(groww_client, selected_mode)` using strictly one mode.

    Never falls back to another authentication mode if the selected mode fails.
    """
    mode = credentials.select_auth_mode()
    if mode is GrowwAuthMode.NONE:
        raise ProviderAuthError("Groww credentials are not configured.")

    if api_cls is None:
        try:
            from growwapi import GrowwAPI  # type: ignore[import-not-found]

            api_cls = GrowwAPI
        except ImportError as exc:
            raise ProviderUnavailableError(
                "growwapi package is not installed (pip install growwapi)."
            ) from exc

    secrets = credentials.secret_values()

    try:
        if mode is GrowwAuthMode.ACCESS_TOKEN:
            token = credentials.access_token.strip()
            if not token:
                raise ProviderAuthError("GROWW_ACCESS_TOKEN is empty.")
            return api_cls(token), mode

        get_token_fn = getattr(api_cls, "get_access_token", None)
        if not callable(get_token_fn):
            raise ProviderUnavailableError(
                "Installed GrowwAPI class does not expose get_access_token()."
            )

        if mode is GrowwAuthMode.TOTP:
            totp_code = credentials.totp_code.strip()
            if not totp_code:
                gen = totp_generator or _generate_totp_code
                totp_code = gen(credentials.totp_secret.strip())
            resolved_token = get_token_fn(
                api_key=credentials.api_key.strip(),
                totp=totp_code,
            )
        elif mode is GrowwAuthMode.API_KEY_SECRET:
            resolved_token = get_token_fn(
                api_key=credentials.api_key.strip(),
                secret=credentials.api_secret.strip(),
            )
        else:
            raise ProviderAuthError(f"Unsupported Groww auth mode: {mode}")

        if isinstance(resolved_token, dict):
            resolved_token = resolved_token.get("token") or resolved_token.get("access_token")

        if not resolved_token or not str(resolved_token).strip():
            raise ProviderAuthError(
                f"Groww {mode.value} authentication returned an empty access token."
            )

        return api_cls(str(resolved_token).strip()), mode
    except ProviderError:
        raise
    except Exception as exc:
        redacted_msg = redact_groww_secrets(str(exc), secrets=secrets)
        raise ProviderAuthError(
            f"Groww authentication failed in '{mode.value}' mode: {redacted_msg}"
        ) from exc

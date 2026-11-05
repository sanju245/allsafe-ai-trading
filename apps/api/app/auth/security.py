"""Cryptographic password hashing, HMAC session tokens, JWKS verification, TOTP, and anti-spoofing IP policy."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import threading
import time
from typing import Any, Callable

from fastapi import Request

PERMANENT_SUPER_ADMIN_ID = "00000000-0000-4000-a000-000000000001"
PBKDF2_ALGORITHM = "pbkdf2_sha256"
DEFAULT_PBKDF2_ITERATIONS = 600_000
DEFAULT_TRUSTED_PROXY_CIDRS = (
    "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7"
)

_EPHEMERAL_RUNTIME_SECRET = secrets.token_hex(32)


def get_signing_secret(configured_secret: str = "") -> bytes:
    """Return the configured HMAC signing secret or a process-local 256-bit random secret."""
    cleaned = (configured_secret or "").strip()
    if cleaned:
        return cleaned.encode("utf-8")
    return _EPHEMERAL_RUNTIME_SECRET.encode("utf-8")


def hash_password(password: str, *, iterations: int = DEFAULT_PBKDF2_ITERATIONS, salt: str | None = None) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with a 16-byte random salt.

    Format: pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>
    Plaintext passwords are never stored.
    """
    if not password:
        raise ValueError("Password must not be empty.")
    salt_hex = salt if salt is not None else secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_hex.encode("utf-8"),
        int(iterations),
    )
    return f"{PBKDF2_ALGORITHM}${int(iterations)}${salt_hex}${dk.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash in constant time."""
    if not password or not encoded_hash:
        return False
    parts = encoded_hash.strip().split("$")
    if len(parts) != 4 or parts[0] != PBKDF2_ALGORITHM:
        return False
    try:
        iterations = int(parts[1])
        salt_hex = parts[2]
        expected_hex = parts[3].lower()
    except ValueError:
        return False
    if iterations < 10_000 or not salt_hex or len(expected_hex) != 64:
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_hex.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(dk.hex().lower(), expected_hex)


def validate_password_strength(password: str) -> str:
    """Validate password complexity requirements."""
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one digit.")
    if not re.search(r"[^A-Za-z0-9\s]", password):
        raise ValueError("Password must contain at least one special character.")
    return password


def normalize_ip_string(raw_ip: str | None, *, strict: bool = False) -> str:
    """Normalize a raw IP string from proxy headers or sockets into a canonical IPv4/IPv6 string.

    Handles:
    * Comma-separated proxy lists (`X-Forwarded-For: client, proxy1`)
    * Quoted strings and `for=` prefixes (`Forwarded: for="[2001:db8::1]:54321"`)
    * Bracketed IPv6 with port (`[2001:db8::1]:54321` -> `2001:db8::1`)
    * IPv4 with port (`203.0.113.5:54321` -> `203.0.113.5`)
    * IPv6 zone IDs (`fe80::1%eth0` -> `fe80::1`)
    * IPv4-mapped IPv6 addresses (`::ffff:203.0.113.5` -> `203.0.113.5`)
    * When `strict=True`, returns `""` if the candidate is not a valid IPv4 or IPv6 address.
    """
    if not raw_ip:
        return ""
    candidate = raw_ip.strip()
    if "," in candidate:
        candidate = candidate.split(",")[0].strip()
    if candidate.lower().startswith("for="):
        candidate = candidate[4:].strip()
    candidate = candidate.strip("\"'")
    if not candidate:
        return ""

    # Bracketed IPv6, optionally with port: [2001:db8::1]:8080 or [::ffff:203.0.113.5]:443
    if candidate.startswith("["):
        end_bracket = candidate.find("]")
        if end_bracket == -1:
            return "" if strict else candidate
        rest = candidate[end_bracket + 1 :].strip()
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return "" if strict else candidate
        candidate = candidate[1:end_bracket]
    elif candidate.count(":") == 1 and "." in candidate:
        # IPv4 with port: 203.0.113.5:54321
        host_part, port_part = candidate.rsplit(":", 1)
        if port_part.isdigit():
            candidate = host_part
        elif strict:
            return ""

    # Strip IPv6 zone index if present (e.g., fe80::1%lo0)
    if "%" in candidate:
        candidate = candidate.split("%", 1)[0]

    try:
        addr = ipaddress.ip_address(candidate)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(addr)
    except ValueError:
        return "" if strict else candidate


def is_ip_in_cidr_list(ip_str: str | None, cidr_spec: str | None) -> bool:
    """Return True if `ip_str` falls within any IP or CIDR network in `cidr_spec`."""
    if not ip_str or not cidr_spec:
        return False
    norm_ip = normalize_ip_string(ip_str, strict=True)
    if not norm_ip:
        return False
    try:
        caller_addr = ipaddress.ip_address(norm_ip)
        if isinstance(caller_addr, ipaddress.IPv6Address) and caller_addr.ipv4_mapped is not None:
            caller_addr = caller_addr.ipv4_mapped
    except ValueError:
        return False

    for raw_token in cidr_spec.split(","):
        tok = raw_token.strip()
        if not tok:
            continue
        if tok in {"*", "0.0.0.0/0", "::/0"}:
            return True
        try:
            if "/" in tok:
                net = ipaddress.ip_network(tok, strict=False)
                if caller_addr.version == net.version and caller_addr in net:
                    return True
            else:
                target_addr = ipaddress.ip_address(normalize_ip_string(tok, strict=True))
                if isinstance(target_addr, ipaddress.IPv6Address) and target_addr.ipv4_mapped is not None:
                    target_addr = target_addr.ipv4_mapped
                if caller_addr == target_addr:
                    return True
        except ValueError:
            continue
    return False


def is_trusted_proxy_peer(
    peer_host: str | None,
    *,
    trusted_proxy_cidrs: str = DEFAULT_TRUSTED_PROXY_CIDRS,
) -> bool:
    """Return True if the immediate socket peer is a trusted reverse proxy or local test harness."""
    if not peer_host:
        return True
    cleaned = peer_host.strip().lower()
    if cleaned in {"testclient", "localhost", "127.0.0.1", "::1"}:
        return True
    return is_ip_in_cidr_list(cleaned, trusted_proxy_cidrs)


def validate_and_normalize_allowed_ip(
    allowed_ip: str | None,
    *,
    is_super_admin: bool = False,
) -> str | None:
    """Validate and normalize an allowed IP / CIDR specification.

    * Super Admin always retains `"*"` (global access from any legitimate IP).
    * `None`, `""`, `"*"`, `"any"`, `"global"`, `"0.0.0.0/0"`, `"::/0"` normalize to `"*"`
      or `None` (unrestricted global access) when empty.
    * Comma-separated IPv4/IPv6 addresses or CIDR networks are validated via `ipaddress`.
    """
    if is_super_admin:
        return "*"
    if allowed_ip is None:
        return None
    cleaned = allowed_ip.strip()
    if not cleaned:
        return None
    if cleaned.lower() in {"*", "any", "global", "0.0.0.0/0", "::/0"}:
        return "*"

    normalized_tokens: list[str] = []
    for raw_token in cleaned.split(","):
        tok = raw_token.strip()
        if not tok:
            continue
        if tok.lower() in {"*", "any", "global", "0.0.0.0/0", "::/0"}:
            return "*"
        try:
            if "/" in tok:
                net = ipaddress.ip_network(tok, strict=False)
                normalized_tokens.append(str(net))
            else:
                norm_tok = normalize_ip_string(tok, strict=True)
                if not norm_tok:
                    raise ValueError(f"Invalid IP '{tok}'")
                addr = ipaddress.ip_address(norm_tok)
                normalized_tokens.append(str(addr))
        except ValueError as exc:
            raise ValueError(
                f"Invalid IP address or CIDR block '{tok}'. Use a valid IPv4/IPv6 address, CIDR range, or '*' for global access."
            ) from exc

    if not normalized_tokens:
        return None
    return ", ".join(normalized_tokens)


def _extract_valid_xff_hops(request: Request) -> list[str]:
    """Collect all valid normalized IP hops across all X-Forwarded-For header instances."""
    raw_headers: list[str] = []
    if hasattr(request.headers, "getlist"):
        raw_headers = list(request.headers.getlist("x-forwarded-for"))
    else:
        single = request.headers.get("x-forwarded-for", "")
        if single:
            raw_headers = [single]

    hops: list[str] = []
    for header_val in raw_headers:
        for part in header_val.split(","):
            tok = part.strip()
            if not tok or tok.lower() == "unknown":
                continue
            norm = normalize_ip_string(tok, strict=True)
            if norm:
                hops.append(norm)
    return hops


def extract_client_ip(
    request: Request,
    *,
    trust_proxy_headers: bool | None = None,
    trusted_proxy_hops: int | None = None,
    trusted_proxy_cidrs: str | None = None,
) -> str:
    """Extract and normalize the caller's IP address with anti-spoofing proxy trust enforcement.

    Security & Anti-Spoofing Rules:
    1. Resolve proxy trust configuration from explicit arguments or `request.app.state.auth_store.settings`.
    2. Inspect the immediate socket peer (`request.client.host`). If `trust_proxy_headers` is False OR
       the immediate socket peer is an untrusted external IP (outside `trusted_proxy_cidrs`), ignore all
       client-supplied forwarded headers and return the verified socket peer IP.
    3. When `X-Forwarded-For` contains multiple hops (or duplicate `X-Forwarded-For` headers), parse only
       strictly valid IP addresses and walk right-to-left (from the hop appended by the trusted ingress proxy),
       skipping up to `trusted_proxy_hops` internal proxy addresses so a client prepending a spoofed IP
       (`X-Forwarded-For: spoofed_allowed_ip, actual_client_ip`) cannot bypass customer IP allowlists.
    4. Malformed header tokens (e.g., non-IP strings, out-of-range octets) are discarded rather than trusted.
    """
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    store = getattr(state, "auth_store", None) if state is not None else None
    settings = getattr(store, "settings", None) if store is not None else None

    effective_trust_proxy = (
        trust_proxy_headers
        if trust_proxy_headers is not None
        else getattr(settings, "trust_proxy_headers", True)
    )
    effective_hops = (
        trusted_proxy_hops
        if trusted_proxy_hops is not None
        else max(1, int(getattr(settings, "trusted_proxy_hops", 1)))
    )
    effective_cidrs = (
        trusted_proxy_cidrs
        if trusted_proxy_cidrs is not None
        else getattr(settings, "trusted_proxy_cidrs", DEFAULT_TRUSTED_PROXY_CIDRS)
    )

    peer_host = request.client.host if (request.client and request.client.host) else "127.0.0.1"
    peer_norm = normalize_ip_string(peer_host, strict=True) or "127.0.0.1"

    # If proxy headers are disabled or the socket peer itself is an untrusted public client, ignore headers
    if not effective_trust_proxy or not is_trusted_proxy_peer(
        peer_host, trusted_proxy_cidrs=effective_cidrs
    ):
        return peer_norm

    # 1. Evaluate X-Forwarded-For (handles single, comma-chained, and duplicate headers safely)
    xff_hops = _extract_valid_xff_hops(request)
    if xff_hops:
        if len(xff_hops) == 1:
            return xff_hops[0]
        # Walk right-to-left skipping up to `effective_hops` trusted internal proxies
        skipped = 0
        for idx in range(len(xff_hops) - 1, -1, -1):
            candidate_ip = xff_hops[idx]
            if (
                skipped < effective_hops
                and idx > 0
                and is_ip_in_cidr_list(candidate_ip, effective_cidrs)
            ):
                skipped += 1
                continue
            return candidate_ip
        return xff_hops[-1]

    # 2. Evaluate single-IP edge headers set by Cloudflare / CDN / ingress proxy
    for header_name in ("cf-connecting-ip", "true-client-ip", "x-real-ip"):
        raw_val = request.headers.get(header_name, "").strip()
        if raw_val and raw_val.lower() != "unknown":
            # Take rightmost valid token if comma-separated
            tokens = [
                normalize_ip_string(p.strip(), strict=True)
                for p in raw_val.split(",")
                if p.strip()
            ]
            valid_tokens = [t for t in tokens if t]
            if valid_tokens:
                return valid_tokens[-1]

    # 3. Evaluate RFC 7239 Forwarded header
    forwarded_header = request.headers.get("forwarded", "").strip()
    if forwarded_header:
        valid_forwarded: list[str] = []
        for entry in forwarded_header.split(","):
            for segment in entry.split(";"):
                seg = segment.strip()
                if seg.lower().startswith("for="):
                    normalized = normalize_ip_string(seg, strict=True)
                    if normalized:
                        valid_forwarded.append(normalized)
        if valid_forwarded:
            return valid_forwarded[-1]

    return peer_norm


def is_client_ip_allowed(
    client_ip: str | None,
    allowed_ip_spec: str | None,
    *,
    is_super_admin: bool = False,
    role: str = "user",
    global_admin_ip_enabled: bool = True,
) -> bool:
    """Verify whether `client_ip` is permitted by `allowed_ip_spec`.

    IP-Independent Admin Access Policy:
    * The Super Admin (`is_super_admin=True`) is ALWAYS allowed from any IPv4/IPv6 address globally.
    * Administrators (`role in ('admin', 'super_admin')`) with `global_admin_ip_enabled=True`
      can ALWAYS log in and maintain active sessions from ANY legitimate IP address globally
      (Wi-Fi, mobile hotspot, cellular CGNAT, VPN, IPv4, or IPv6), even if an older fixed IP
      was previously stored in `allowed_ip_spec`.
    * Any account with `allowed_ip_spec in (None, '', '*', 'any', 'global', '0.0.0.0/0', '::/0')`
      has unrestricted global IP access.
    * If a specific IP or CIDR allowlist is configured on a customer account (or on a non-super
      admin when `global_admin_ip_enabled=False`), it is evaluated against the normalized `client_ip`.
    """
    if is_super_admin:
        return True
    if role in {"admin", "super_admin"} and global_admin_ip_enabled:
        return True
    if not allowed_ip_spec:
        return True
    cleaned_spec = allowed_ip_spec.strip()
    if not cleaned_spec or cleaned_spec.lower() in {"*", "any", "global", "0.0.0.0/0", "::/0"}:
        return True
    if not client_ip:
        return False

    normalized_caller = normalize_ip_string(client_ip, strict=True)
    if not normalized_caller:
        return False
    try:
        caller_addr = ipaddress.ip_address(normalized_caller)
        if isinstance(caller_addr, ipaddress.IPv6Address) and caller_addr.ipv4_mapped is not None:
            caller_addr = caller_addr.ipv4_mapped
    except ValueError:
        return False

    for raw_token in cleaned_spec.split(","):
        tok = raw_token.strip()
        if not tok:
            continue
        if tok.lower() in {"*", "any", "global", "0.0.0.0/0", "::/0"}:
            return True
        try:
            if "/" in tok:
                net = ipaddress.ip_network(tok, strict=False)
                if caller_addr.version == net.version and caller_addr in net:
                    return True
            else:
                norm_target = normalize_ip_string(tok, strict=True)
                if not norm_target:
                    continue
                target_addr = ipaddress.ip_address(norm_target)
                if isinstance(target_addr, ipaddress.IPv6Address) and target_addr.ipv4_mapped is not None:
                    target_addr = target_addr.ipv4_mapped
                if caller_addr == target_addr:
                    return True
        except ValueError:
            continue
    return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode((segment + padding).encode("ascii"))


def create_session_token(
    *,
    user_id: str,
    username: str,
    email: str,
    role: str,
    is_super_admin: bool,
    secret_key: str = "",
    ttl_seconds: int = 28800,
    now_epoch: int | None = None,
    jti: str | None = None,
) -> tuple[str, str, int]:
    """Create a signed HMAC-SHA256 session token returning `(token, jti, exp_epoch)`."""
    iat = int(now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp())
    exp = iat + max(60, int(ttl_seconds))
    token_jti = jti or secrets.token_hex(16)
    payload = {
        "jti": token_jti,
        "sub": user_id,
        "username": username,
        "email": email,
        "role": role,
        "is_super_admin": bool(is_super_admin),
        "iat": iat,
        "exp": exp,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    signing_input = f"as_v1.{payload_b64}".encode("ascii")
    sig = hmac.new(get_signing_secret(secret_key), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"as_v1.{payload_b64}.{sig_b64}", token_jti, exp


def verify_session_token(
    token: str,
    *,
    secret_key: str = "",
    now_epoch: int | None = None,
) -> dict[str, Any] | None:
    """Verify an HMAC-SHA256 session token and return its claims dict if valid and unexpired."""
    if not token:
        return None
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != "as_v1":
        return None
    payload_b64, sig_b64 = parts[1], parts[2]
    signing_input = f"as_v1.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(get_signing_secret(secret_key), signing_input, hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        return None
    if not hmac.compare_digest(actual_sig, expected_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    now_ts = int(now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp())
    exp = payload.get("exp")
    if not isinstance(exp, int) or now_ts >= exp:
        return None
    nbf = payload.get("nbf")
    if isinstance(nbf, int) and now_ts < nbf:
        return None
    return payload


class JWKSCache:
    """Thread-safe JWKS key cache with TTL expiration, unknown-kid refresh throttling, and RSA/ECDSA/HMAC verification."""

    def __init__(
        self,
        *,
        jwks_fetcher: Callable[[], dict[str, Any]] | None = None,
        cache_ttl_seconds: float = 3600.0,
        refresh_cooldown_seconds: float = 30.0,
    ) -> None:
        self._lock = threading.RLock()
        self._fetcher = jwks_fetcher
        self.cache_ttl_seconds = max(10.0, float(cache_ttl_seconds))
        self.refresh_cooldown_seconds = max(1.0, float(refresh_cooldown_seconds))
        self._keys_by_kid: dict[str, dict[str, Any]] = {}
        self._cached_at_epoch: float = 0.0
        self._last_refresh_attempt_epoch: float = 0.0
        self.refresh_count: int = 0
        self.throttled_refresh_count: int = 0

    def load_jwks(self, jwks_payload: dict[str, Any], *, now_epoch: float | None = None) -> None:
        """Populate the cache from a standard `{"keys": [...]}` JWKS dictionary."""
        ts = float(now_epoch if now_epoch is not None else time.time())
        keys = jwks_payload.get("keys", []) if isinstance(jwks_payload, dict) else []
        mapped: dict[str, dict[str, Any]] = {}
        for item in keys:
            if isinstance(item, dict) and isinstance(item.get("kid"), str) and item["kid"].strip():
                mapped[item["kid"].strip()] = dict(item)
        with self._lock:
            self._keys_by_kid = mapped
            self._cached_at_epoch = ts
            self._last_refresh_attempt_epoch = ts

    def get_key(self, kid: str, *, now_epoch: float | None = None) -> dict[str, Any] | None:
        """Retrieve a JWK by `kid`, performing a throttled refresh on cache miss or TTL expiry."""
        if not kid or not kid.strip():
            return None
        cleaned_kid = kid.strip()
        ts = float(now_epoch if now_epoch is not None else time.time())
        with self._lock:
            is_expired = (
                not self._keys_by_kid
                or (ts - self._cached_at_epoch) >= self.cache_ttl_seconds
            )
            if not is_expired and cleaned_kid in self._keys_by_kid:
                return self._keys_by_kid[cleaned_kid]

            # Cache miss (unknown kid) or TTL expired -> check refresh throttle cooldown
            if self._fetcher is None:
                return self._keys_by_kid.get(cleaned_kid) if not is_expired else None

            if (
                self._last_refresh_attempt_epoch > 0.0
                and (ts - self._last_refresh_attempt_epoch) < self.refresh_cooldown_seconds
            ):
                self.throttled_refresh_count += 1
                return self._keys_by_kid.get(cleaned_kid) if not is_expired else None

            self._last_refresh_attempt_epoch = ts
            self.refresh_count += 1
            try:
                fresh_jwks = self._fetcher()
                if isinstance(fresh_jwks, dict):
                    self.load_jwks(fresh_jwks, now_epoch=ts)
            except Exception:
                # If upstream JWKS fetch fails, fail closed on unknown kid
                return None

            return self._keys_by_kid.get(cleaned_kid)


def _verify_jwk_signature(
    alg: str,
    jwk: dict[str, Any],
    signing_input: bytes,
    signature: bytes,
) -> bool:
    """Verify a JWT signature against a JWK (`RS256`, `ES256`, or `HS256`) using `cryptography` or stdlib."""
    kty = str(jwk.get("kty", "")).upper()
    jwk_alg = str(jwk.get("alg", alg)).upper()
    if jwk_alg != alg:
        return False

    if alg == "HS256" and kty == "OCT":
        k_b64 = str(jwk.get("k", ""))
        if not k_b64:
            return False
        secret_bytes = _b64url_decode(k_b64)
        expected = hmac.new(secret_bytes, signing_input, hashlib.sha256).digest()
        return hmac.compare_digest(signature, expected)

    if alg == "RS256" and kty == "RSA":
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding, rsa

        n_int = int.from_bytes(_b64url_decode(str(jwk["n"])), "big")
        e_int = int.from_bytes(_b64url_decode(str(jwk["e"])), "big")
        pub_key = rsa.RSAPublicNumbers(e_int, n_int).public_key()
        try:
            pub_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    if alg == "ES256" and kty == "EC":
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

        x_int = int.from_bytes(_b64url_decode(str(jwk["x"])), "big")
        y_int = int.from_bytes(_b64url_decode(str(jwk["y"])), "big")
        pub_key = ec.EllipticCurvePublicNumbers(x_int, y_int, ec.SECP256R1()).public_key()
        if len(signature) == 64:
            r_int = int.from_bytes(signature[:32], "big")
            s_int = int.from_bytes(signature[32:], "big")
            der_sig = encode_dss_signature(r_int, s_int)
        else:
            der_sig = signature
        try:
            pub_key.verify(der_sig, signing_input, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False

    return False


def verify_jwt_with_jwks_or_secret(
    token: str,
    *,
    jwks_cache: JWKSCache | None = None,
    hmac_secret: str = "",
    now_epoch: int | None = None,
) -> dict[str, Any] | None:
    """Verify a standard 3-part JWT (`header.payload.signature`) using `jwks_cache` (`kid`) or `hmac_secret`.

    Enforces:
    * Rejects `"alg": "none"` or unsupported algorithms.
    * Prevents algorithm confusion: if `jwks_cache` is used with a `kid`, verifies the key type matches `alg`.
    * Rejects unknown `kid` (with refresh throttling enforced by `JWKSCache`).
    * Rejects expired (`now >= exp`) or premature (`now < nbf`) tokens.
    * Strips any untrusted client-writable `user_metadata.role` / `user_metadata.is_super_admin` fields.
    """
    if not token:
        return None
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] == "as_v1":
        return None
    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        signature = _b64url_decode(sig_b64)
    except Exception:
        return None
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return None

    alg = str(header.get("alg", "")).upper()
    if alg not in {"HS256", "RS256", "ES256"}:
        return None

    now_ts = int(now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp())
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or now_ts >= int(exp):
        return None
    nbf = payload.get("nbf")
    if isinstance(nbf, (int, float)) and now_ts < int(nbf):
        return None

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    kid = header.get("kid")

    verified = False
    if isinstance(kid, str) and kid.strip() and jwks_cache is not None:
        jwk = jwks_cache.get_key(kid.strip(), now_epoch=now_ts)
        if jwk is None:
            return None
        verified = _verify_jwk_signature(alg, jwk, signing_input, signature)
    elif alg == "HS256" and hmac_secret.strip() and not kid:
        expected = hmac.new(hmac_secret.strip().encode("utf-8"), signing_input, hashlib.sha256).digest()
        verified = hmac.compare_digest(signature, expected)
    else:
        return None

    if not verified:
        return None

    # Sanitize client-mutable user_metadata so it can never be used for role/privilege escalation
    sanitized = dict(payload)
    if isinstance(sanitized.get("user_metadata"), dict):
        um = dict(sanitized["user_metadata"])
        um.pop("role", None)
        um.pop("is_super_admin", None)
        um.pop("allowed_ip", None)
        sanitized["user_metadata"] = um
    return sanitized


def verify_totp_code(totp_secret: str, code: str | None) -> bool:
    """Verify an optional 6-digit RFC 6238 TOTP code if a secret is configured."""
    cleaned_secret = (totp_secret or "").strip()
    if not cleaned_secret:
        return True
    if not code or not code.strip():
        return False
    cleaned_code = code.strip().replace(" ", "")
    try:
        import pyotp  # type: ignore

        totp = pyotp.TOTP(cleaned_secret)
        return bool(totp.verify(cleaned_code, valid_window=1))
    except Exception:
        # Pure-Python RFC 6238 fallback if pyotp is not installed in the test environment
        import struct

        try:
            normalized = cleaned_secret.upper()
            pad = "=" * ((8 - len(normalized) % 8) % 8)
            key = base64.b32decode(normalized + pad, casefold=True)
        except Exception:
            return False
        now_step = int(time.time() // 30)
        for offset in (-1, 0, 1):
            msg = struct.pack(">Q", now_step + offset)
            digest = hmac.new(key, msg, hashlib.sha1).digest()
            idx = digest[-1] & 0x0F
            binary = struct.unpack(">I", digest[idx : idx + 4])[0] & 0x7FFFFFFF
            candidate = str(binary % 1_000_000).zfill(6)
            if hmac.compare_digest(candidate, cleaned_code):
                return True
        return False

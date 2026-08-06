"""Authentication config loading with precedence: CLI flags > env vars > ~/.plane_api file.

Also supports self-hosted instances behind Cloudflare Access: optional
CF-Access service-token credentials, plus a fallback env file
($PLANE_ENV_FILE, default ~/.config/zettabyte/plane.env) shared with other
tooling.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from planecli.exceptions import AuthenticationError

CONFIG_FILE = Path.home() / ".plane_api"
DEFAULT_ENV_FILE = Path.home() / ".config" / "zettabyte" / "plane.env"

_FIELD_MAP = {
    "base_url": "PLANE_BASE_URL",
    "api_key": "PLANE_API_KEY",
    "workspace": "PLANE_WORKSPACE",
}


@dataclass
class Config:
    base_url: str
    api_key: str
    workspace: str
    cf_access_client_id: str | None = None
    cf_access_client_secret: str | None = None


def _parse_kv_file(path: Path) -> dict[str, str]:
    """Read key=value pairs from a config/env file (lowercased keys)."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip().lower()] = value.strip().strip('"').strip("'")
    return values


def _read_config_file() -> dict[str, str]:
    """Read key=value pairs from ~/.plane_api."""
    return _parse_kv_file(CONFIG_FILE)


def _read_env_file() -> dict[str, str]:
    """Read the shared env file ($PLANE_ENV_FILE or ~/.config/zettabyte/plane.env).

    Its keys are env-style (PLANE_API_KEY=...), so after lowercasing they are
    mapped onto config-file keys. PLANE_WORKSPACE_SLUG is accepted as an alias
    for the workspace slug.
    """
    path = Path(os.environ.get("PLANE_ENV_FILE") or DEFAULT_ENV_FILE).expanduser()
    raw = _parse_kv_file(path)
    values: dict[str, str] = {}
    mapping = {
        "plane_base_url": "base_url",
        "plane_api_key": "api_key",
        "plane_workspace": "workspace",
        "plane_workspace_slug": "workspace",
        "cf_access_client_id": "cf_access_client_id",
        "cf_access_client_secret": "cf_access_client_secret",
    }
    for key, target in mapping.items():
        if key in raw and target not in values:
            values[target] = raw[key]
    return values


def _normalize_base_url(base_url: str) -> str:
    """Strip a trailing /api/v1 — the SDK appends it itself."""
    base_url = base_url.rstrip("/")
    if base_url.endswith("/api/v1"):
        base_url = base_url[: -len("/api/v1")]
    return base_url.rstrip("/")


def save_config(
    base_url: str,
    api_key: str,
    workspace: str,
    cf_access_client_id: str | None = None,
    cf_access_client_secret: str | None = None,
) -> None:
    """Save config to ~/.plane_api with restricted permissions."""
    content = f"base_url={base_url}\napi_key={api_key}\nworkspace={workspace}\n"
    if cf_access_client_id and cf_access_client_secret:
        content += (
            f"cf_access_client_id={cf_access_client_id}\n"
            f"cf_access_client_secret={cf_access_client_secret}\n"
        )
    CONFIG_FILE.write_text(content)
    CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600


def load_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    workspace: str | None = None,
) -> Config:
    """Load config with precedence: explicit args > env vars > ~/.plane_api > env file."""
    file_values = _read_config_file()
    env_file_values = _read_env_file()

    def resolve(explicit: str | None, env_var: str, key: str) -> str | None:
        return (
            explicit
            or os.environ.get(env_var)
            or file_values.get(key)
            or env_file_values.get(key)
        )

    resolved_base_url = resolve(base_url, "PLANE_BASE_URL", "base_url")
    resolved_api_key = resolve(api_key, "PLANE_API_KEY", "api_key")
    resolved_workspace = (
        workspace
        or os.environ.get("PLANE_WORKSPACE")
        or os.environ.get("PLANE_WORKSPACE_SLUG")
        or file_values.get("workspace")
        or env_file_values.get("workspace")
    )
    resolved_cf_id = resolve(None, "CF_ACCESS_CLIENT_ID", "cf_access_client_id")
    resolved_cf_secret = resolve(None, "CF_ACCESS_CLIENT_SECRET", "cf_access_client_secret")

    if not resolved_base_url:
        raise AuthenticationError(
            "Missing base URL. Set PLANE_BASE_URL or run 'planecli configure'."
        )
    if not resolved_api_key:
        raise AuthenticationError("Missing API key. Set PLANE_API_KEY or run 'planecli configure'.")
    if not resolved_workspace:
        raise AuthenticationError(
            "Missing workspace slug. Set PLANE_WORKSPACE or run 'planecli configure'."
        )

    return Config(
        base_url=_normalize_base_url(resolved_base_url),
        api_key=resolved_api_key,
        workspace=resolved_workspace,
        cf_access_client_id=resolved_cf_id,
        cf_access_client_secret=resolved_cf_secret,
    )

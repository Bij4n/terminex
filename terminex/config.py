"""TOML config loader for terminex with XDG-style defaults."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    base_currency: str = "USD"
    refresh_interval: float = 10.0
    active_tab: str = "fx"
    coincap_api_key: str = ""


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "terminex" / "config.toml"


def load(path: Path | None = None) -> Config:
    p = path or config_path()
    if not p.exists():
        return _with_env(Config())
    try:
        with p.open("rb") as f:
            data = tomllib.load(f)
    except OSError as exc:
        print(
            f"terminex: could not read config at {p}: {exc}",
            file=sys.stderr,
        )
        return _with_env(Config())
    except tomllib.TOMLDecodeError as exc:
        print(
            f"terminex: ignoring malformed config at {p}: {exc}",
            file=sys.stderr,
        )
        return _with_env(Config())

    cfg = Config(
        base_currency=_value(
            data, "base_currency", "USD", parse_currency_code, p
        ),
        refresh_interval=_value(
            data, "refresh_interval", 10.0, parse_interval, p
        ),
        active_tab=_value(data, "active_tab", "fx", _parse_tab, p),
        coincap_api_key=_coincap_key(data, p),
    )
    return _with_env(cfg)


VALID_TABS = ("fx", "crypto", "commodity", "watchlist")


def parse_currency_code(value: object) -> str:
    """Return an upper-case three-letter code, or raise ValueError."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{3}", value):
        raise ValueError("expected a three-letter currency code like USD")
    return value.upper()


def parse_interval(value: object) -> float:
    """Return a positive number of seconds, or raise ValueError."""
    if isinstance(value, bool):
        raise ValueError("expected a number of seconds")
    try:
        seconds = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError("expected a number of seconds") from None
    if not seconds > 0 or seconds == float("inf"):
        raise ValueError("expected a positive number of seconds")
    return seconds


def _parse_tab(value: object) -> str:
    if not isinstance(value, str) or value.lower() not in VALID_TABS:
        raise ValueError(f"expected one of {', '.join(VALID_TABS)}")
    return value.lower()


def _warn(path: Path, key: str, value: object, reason: str, default: object) -> None:
    print(
        f"terminex: ignoring {key} = {value!r} in {path} ({reason}); "
        f"using {default!r}",
        file=sys.stderr,
    )


def _value(data: dict, key: str, default, parse, path: Path):
    if key not in data:
        return default
    try:
        return parse(data[key])
    except ValueError as exc:
        _warn(path, key, data[key], str(exc), default)
        return default


def _coincap_key(data: dict, path: Path) -> str:
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        _warn(path, "providers", providers, "expected a table", {})
        return ""
    crypto = providers.get("crypto", {})
    if not isinstance(crypto, dict):
        _warn(path, "providers.crypto", crypto, "expected a table", {})
        return ""
    key = crypto.get("api_key", "")
    if not isinstance(key, str):
        _warn(path, "providers.crypto.api_key", key, "expected a string", "")
        return ""
    return key


def _with_env(cfg: Config) -> Config:
    """Environment variables override file values."""
    key = os.environ.get("TERMINEX_COINCAP_KEY")
    if key:
        cfg = Config(
            base_currency=cfg.base_currency,
            refresh_interval=cfg.refresh_interval,
            active_tab=cfg.active_tab,
            coincap_api_key=key,
        )
    return cfg

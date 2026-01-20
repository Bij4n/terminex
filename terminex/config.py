"""TOML config loader for terminex with XDG-style defaults."""

from __future__ import annotations

import os
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

    providers = data.get("providers") or {}
    crypto = providers.get("crypto") or {}

    cfg = Config(
        base_currency=str(data.get("base_currency", "USD")).upper(),
        refresh_interval=float(data.get("refresh_interval", 10.0)),
        active_tab=str(data.get("active_tab", "fx")).lower(),
        coincap_api_key=str(crypto.get("api_key", "")),
    )
    return _with_env(cfg)


def _with_env(cfg: Config) -> Config:
    """Environment variables override file values."""
    key = os.environ.get("TERMINEX_COINCAP_KEY")
    if key and not cfg.coincap_api_key:
        cfg = Config(
            base_currency=cfg.base_currency,
            refresh_interval=cfg.refresh_interval,
            active_tab=cfg.active_tab,
            coincap_api_key=key,
        )
    return cfg

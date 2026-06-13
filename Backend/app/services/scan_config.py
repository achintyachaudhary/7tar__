"""Portable scan configuration — build, validate, parse, and apply to screener jobs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.services.scan_definitions import SCAN_DEFINITIONS, get_scan_definition

SCAN_CONFIG_VERSION = 1
EXPORT_BUNDLE_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_scan_config(
    scan_type: str,
    *,
    scan_params: dict[str, Any] | None = None,
    display_filters: dict[str, Any] | None = None,
    universe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a versioned scan_config snapshot for persistence and export."""
    defn = get_scan_definition(scan_type) or {}
    return {
        "version": SCAN_CONFIG_VERSION,
        "scan_type": scan_type,
        "name": defn.get("name", scan_type),
        "created_at": _now_iso(),
        "core_criteria": defn.get("core_criteria", []),
        "scan_params": dict(scan_params or {}),
        "display_filters": dict(display_filters or {}),
        "universe": dict(universe or {}),
    }


def parse_ws_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Normalize scan:start payload — supports legacy ui_filters and new scan_config."""
    if filters.get("scan_config"):
        cfg = filters["scan_config"]
        if isinstance(cfg, dict):
            return cfg
    # Legacy envelope
    scan_params: dict[str, Any] = {}
    if filters.get("min_market_cap_cr") is not None:
        scan_params["min_market_cap_cr"] = filters["min_market_cap_cr"]
    if filters.get("max_market_cap_cr") is not None:
        scan_params["max_market_cap_cr"] = filters["max_market_cap_cr"]
    if filters.get("require_volume_confirmation") is not None:
        scan_params["require_volume_confirmation"] = filters["require_volume_confirmation"]
    for k, v in (filters.get("scan_params") or {}).items():
        scan_params[k] = v
    return build_scan_config(
        str(filters.get("scan_type") or ""),
        scan_params=scan_params,
        display_filters=filters.get("ui_filters") or filters.get("display_filters") or {},
        universe={
            "min_market_cap_cr": filters.get("min_market_cap_cr"),
            "max_market_cap_cr": filters.get("max_market_cap_cr"),
        },
    )


def config_to_job_filters(scan_config: dict[str, Any]) -> dict[str, Any]:
    """Extract job_manager universe + options from scan_config."""
    scan_type = scan_config.get("scan_type", "")
    params = dict(scan_config.get("scan_params") or {})
    universe = scan_config.get("universe") or {}

    min_cap = universe.get("min_market_cap_cr", params.pop("min_market_cap_cr", None))
    max_cap = universe.get("max_market_cap_cr", params.pop("max_market_cap_cr", None))

    out: dict[str, Any] = {
        "scan_type": scan_type,
        "min_market_cap_cr": min_cap,
        "max_market_cap_cr": max_cap,
        "scan_config": scan_config,
    }
    if params.get("require_volume_confirmation") is not None:
        out["require_volume_confirmation"] = bool(params["require_volume_confirmation"])
    return out


def screener_options_from_config(scan_config: dict[str, Any]) -> dict[str, Any]:
    """Options dict passed into each per-symbol screener function."""
    return dict(scan_config.get("scan_params") or {})


def validate_scan_config(cfg: dict[str, Any]) -> list[str]:
    """Return a list of validation errors (empty = ok)."""
    errors: list[str] = []
    if cfg.get("version") not in (SCAN_CONFIG_VERSION, None):
        errors.append(f"Unsupported scan_config version: {cfg.get('version')}")
    scan_type = cfg.get("scan_type")
    if not scan_type or scan_type not in SCAN_DEFINITIONS:
        errors.append(f"Unknown scan_type: {scan_type}")
        return errors
    defn = SCAN_DEFINITIONS[scan_type]
    allowed = {f["id"] for f in defn.get("param_schema", [])}
    allowed |= {"min_market_cap_cr", "max_market_cap_cr"}
    for key in (cfg.get("scan_params") or {}):
        if key not in allowed:
            errors.append(f"Unknown scan_param '{key}' for {scan_type}")
    return errors


def export_all_profiles(cached_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build portable export bundle from scan_result_cache rows."""
    profiles: list[dict[str, Any]] = []
    for row in cached_rows:
        filt = row.get("filter") or {}
        cfg = filt.get("scan_config")
        if not cfg:
            # Legacy: synthesize minimal config
            cfg = build_scan_config(
                row.get("scan_type", ""),
                scan_params={
                    k: filt.get(k)
                    for k in ("min_market_cap_cr", "max_market_cap_cr", "require_volume_confirmation")
                    if filt.get(k) is not None
                },
                display_filters=filt.get("ui_filters") or {},
                universe={
                    "min_market_cap_cr": filt.get("min_market_cap_cr"),
                    "max_market_cap_cr": filt.get("max_market_cap_cr"),
                },
            )
            cfg["legacy"] = True
        profile = dict(cfg)
        profile["last_scanned_at"] = row.get("last_scanned_at")
        profile["match_count"] = len(row.get("matches") or [])
        profiles.append(profile)
    return {
        "version": EXPORT_BUNDLE_VERSION,
        "exported_at": _now_iso(),
        "app": "gcc-Goldium",
        "profiles": profiles,
    }


def parse_import_bundle(raw: str | dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Parse JSON import bundle; returns (bundle, errors)."""
    errors: list[str] = []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError) as exc:
        return {}, [f"Invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return {}, ["Root must be a JSON object"]

    version = data.get("version", 1)
    if version != EXPORT_BUNDLE_VERSION:
        errors.append(f"Unsupported bundle version {version} (expected {EXPORT_BUNDLE_VERSION})")

    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        return {}, ["Missing 'profiles' array"]

    valid_profiles: list[dict[str, Any]] = []
    for i, p in enumerate(profiles):
        if not isinstance(p, dict):
            errors.append(f"Profile {i} is not an object")
            continue
        perrs = validate_scan_config(p)
        if perrs:
            errors.extend([f"Profile {i} ({p.get('scan_type')}): {e}" for e in perrs])
        else:
            valid_profiles.append(p)

    bundle = {**data, "profiles": valid_profiles}
    return bundle, errors

"""Portable scan configuration: definitions, export, import, and replay."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import crud
from app.db.database import SessionLocal
from app.services import notifier
from app.services.job_manager import SCAN_REGISTRY, is_scan_running, start_scan
from app.services.scan_config import (
    build_scan_config,
    config_to_job_filters,
    export_all_profiles,
    parse_import_bundle,
    validate_scan_config,
)
from app.services.scan_definitions import get_scan_definition, list_scan_definitions

scan_config_router = APIRouter(prefix="/api/scan-config")


class ImportBundleRequest(BaseModel):
    bundle: dict[str, Any] | str


class RunProfileRequest(BaseModel):
    scan_config: dict[str, Any]


class SaveParamsRequest(BaseModel):
    scan_config: dict[str, Any]


def _ws_broadcast_callback():
    """Thread-safe broadcast for background scan starts."""
    from app.api.ws_hub import broadcast_sync

    def on_message(msg: dict[str, Any]) -> None:
        broadcast_sync(msg)

    return on_message


@scan_config_router.get("/definitions")
def get_definitions() -> dict[str, Any]:
    return {"definitions": list_scan_definitions()}


@scan_config_router.get("/definitions/{scan_type}")
def get_definition(scan_type: str) -> dict[str, Any]:
    defn = get_scan_definition(scan_type)
    if not defn:
        raise HTTPException(status_code=404, detail=f"Unknown scan type: {scan_type}")
    return defn


@scan_config_router.get("/export")
def export_profiles() -> dict[str, Any]:
    """Export all saved scan profiles from scan_result_cache."""
    rows: list[dict[str, Any]] = []
    with SessionLocal() as db:
        for scan_type in SCAN_REGISTRY:
            cached = crud.get_scan_result_cache(db, scan_type)
            if cached and cached.get("last_scanned_at"):
                rows.append(cached)
    return export_all_profiles(rows)


@scan_config_router.post("/import")
def import_profiles(req: ImportBundleRequest) -> dict[str, Any]:
    """Validate a portable JSON bundle (does not run scans)."""
    bundle, errors = parse_import_bundle(req.bundle)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "profile_count": len(bundle.get("profiles", [])),
        "profiles": bundle.get("profiles", []),
    }


@scan_config_router.put("/{scan_type}/params")
def save_params(scan_type: str, req: SaveParamsRequest) -> dict[str, Any]:
    """Persist scanner parameters from a screener without running a scan."""
    if scan_type not in SCAN_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown scan type: {scan_type}")

    cfg = dict(req.scan_config)
    cfg.setdefault("scan_type", scan_type)
    if cfg.get("scan_type") != scan_type:
        raise HTTPException(status_code=400, detail="scan_type mismatch")

    errors = validate_scan_config(cfg)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    with SessionLocal() as db:
        crud.save_scan_params(db, scan_type, cfg)
    return {"saved": True, "scan_type": scan_type}


@scan_config_router.post("/run")
def run_profile(req: RunProfileRequest) -> dict[str, Any]:
    """Start a scan from a portable scan_config (e.g. imported on a friend's machine)."""
    cfg = req.scan_config
    errors = validate_scan_config(cfg)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    scan_type = cfg["scan_type"]
    if scan_type not in SCAN_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown scan type: {scan_type}")
    if is_scan_running(scan_type):
        raise HTTPException(status_code=409, detail=f"{scan_type} scan already running")

    job_filters = config_to_job_filters(cfg)
    job_filters["scan_config"] = cfg
    started = start_scan(scan_type, job_filters, _ws_broadcast_callback())
    return {"started": started, "scan_type": scan_type}


@scan_config_router.post("/email-export")
def email_export_bundle() -> dict[str, Any]:
    """Email today's scan filter profiles as JSON to the user."""
    with SessionLocal() as db:
        rows = []
        for scan_type in SCAN_REGISTRY:
            cached = crud.get_scan_result_cache(db, scan_type)
            if cached and cached.get("last_scanned_at"):
                rows.append(cached)
    bundle = export_all_profiles(rows)
    html = (
        "<p>Your scanner filter profiles are attached below as JSON.</p>"
        "<p>Import this file on another machine via <strong>Scan Profiles → Import</strong> "
        "to replay the same filters.</p>"
        f"<pre style='font-size:11px;overflow:auto;max-height:400px'>"
        f"{json.dumps(bundle, indent=2)}</pre>"
    )
    ok = notifier.send_email(
        subject=f"[Scanners] Filter profiles export ({len(bundle.get('profiles', []))} scans)",
        html=html,
    )
    return {"sent": ok, "profiles": len(bundle.get("profiles", []))}

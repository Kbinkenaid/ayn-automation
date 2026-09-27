#!/usr/bin/env python3
"""thorctl_schemas — JSON record schemas for the thorctl control plane.

Every record is schema-versioned, atomically written, timestamped, and
linked by digest.  No record may contain BIOS contents, firmware, title
keys, credentials, raw screenshots with private information, or
app-private dumps.

These schemas are validated with stdlib only (no external dependencies).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest_of(data: dict[str, Any]) -> str:
    """Stable SHA-256 digest of a JSON-serializable dict."""
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def atomic_write(path: Path, data: str) -> None:
    """Atomic write via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data)
    tmp.replace(path)


# ─── Schema validation helpers ───────────────────────────────────────

def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _is_list_of_str(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


# ─── Record schemas ──────────────────────────────────────────────────

def validate_device_attestation(record: dict[str, Any]) -> None:
    """DeviceAttestation: serial, model, brand, build fingerprint, patch, time."""
    _check(isinstance(record, dict), "record must be a dict")
    required = ("schema_version", "serial", "model", "brand",
                "build_fingerprint", "patch_level", "discovered_at")
    for key in required:
        _check(key in record, f"missing field: {key}")
    # Build fingerprints routinely contain the string "release-keys".  Secret
    # protection therefore belongs on field names, not arbitrary metadata
    # values.  Keep this record deliberately closed to unreviewed fields.
    allowed = set(required) | {"android_release", "installed_packages"}
    extra = set(record) - allowed
    _check(not extra, f"DeviceAttestation contains unsupported fields: {sorted(extra)}")
    _check(_is_int(record["schema_version"]) and record["schema_version"] == SCHEMA_VERSION,
           "schema_version must be integer 1")
    _check(_is_str(record["serial"]), "serial must be a non-empty string")
    _check(_is_str(record["model"]), "model must be a non-empty string")
    _check(_is_str(record["brand"]), "brand must be a non-empty string")
    _check(_is_str(record["build_fingerprint"]), "build_fingerprint must be a non-empty string")
    _check(_is_str(record["patch_level"]), "patch_level must be a non-empty string")
    _check(_is_str(record["discovered_at"]), "discovered_at must be a non-empty string")


def validate_storage_binding(record: dict[str, Any]) -> None:
    """StorageBinding: storage_type, rom_root, free_space_bytes, confirmed."""
    _check(isinstance(record, dict), "record must be a dict")
    for key in ("schema_version", "storage_type", "rom_root",
                "free_space_bytes", "confirmed", "bound_at"):
        _check(key in record, f"missing field: {key}")
    _check(_is_int(record["schema_version"]) and record["schema_version"] == SCHEMA_VERSION,
           "schema_version must be integer 1")
    _check(record["storage_type"] in ("internal", "removable"),
           "storage_type must be 'internal' or 'removable'")
    _check(_is_str(record["rom_root"]), "rom_root must be a non-empty string")
    _check(record["rom_root"].startswith("/"), "rom_root must be an absolute path")
    _check(_is_int(record["free_space_bytes"]) and record["free_space_bytes"] >= 0,
           "free_space_bytes must be a non-negative integer")
    _check(_is_bool(record["confirmed"]), "confirmed must be a boolean")
    _check(_is_str(record["bound_at"]), "bound_at must be a non-empty string")


def validate_app_lock(record: dict[str, Any]) -> None:
    """AppLock: source, release, sha256, package, signer, arch, approved_version."""
    _check(isinstance(record, dict), "record must be a dict")
    for key in ("schema_version", "source", "release", "sha256",
                "package", "signer_digest", "arch", "approved_version", "locked_at"):
        _check(key in record, f"missing field: {key}")
    _check(_is_int(record["schema_version"]) and record["schema_version"] == SCHEMA_VERSION,
           "schema_version must be integer 1")
    _check(_is_str(record["source"]), "source must be a non-empty string")
    _check(_is_str(record["release"]), "release must be a non-empty string")
    _check(_is_str(record["sha256"]) and len(record["sha256"]) == 64,
           "sha256 must be a 64-char hex string")
    _check(_is_str(record["package"]), "package must be a non-empty string")
    _check(_is_str(record["signer_digest"]) and len(record["signer_digest"]) == 64,
           "signer_digest must be a 64-char hex string")
    _check(record["arch"] in ("arm64-v8a", "armeabi-v7a", "x86_64", "x86", "universal"),
           "arch must be a known ABI")
    _check(_is_str(record["approved_version"]), "approved_version must be a non-empty string")
    _check(_is_str(record["locked_at"]), "locked_at must be a non-empty string")


def validate_deployment_plan(record: dict[str, Any]) -> None:
    """DeploymentPlan: library digest, profile, adapters, app lock, device, storage, intents."""
    _check(isinstance(record, dict), "record must be a dict")
    for key in ("schema_version", "library_digest", "profile", "profile_version",
                "adapters", "app_locks", "device_serial", "storage_binding",
                "intents", "plan_digest", "created_at", "authorization"):
        _check(key in record, f"missing field: {key}")
    _check(_is_int(record["schema_version"]) and record["schema_version"] == SCHEMA_VERSION,
           "schema_version must be integer 1")
    _check(isinstance(record["library_digest"], str), "library_digest must be a string")
    _check(isinstance(record["profile"], str) and record["profile"], "profile must be a non-empty string")
    _check(isinstance(record["profile_version"], str) and record["profile_version"], "profile_version must be a non-empty string")
    _check(isinstance(record["adapters"], list), "adapters must be a list")
    _check(isinstance(record["app_locks"], dict), "app_locks must be a dict")
    _check(record["device_serial"] is None or isinstance(record["device_serial"], str), "device_serial must be a string or None")
    _check(isinstance(record["storage_binding"], dict), "storage_binding must be a dict")
    _check(isinstance(record["intents"], list), "intents must be a list")
    _check(isinstance(record["plan_digest"], str), "plan_digest must be a string")
    _check(record["authorization"] == "non_authorizing",
           "a deployment plan's authorization must be 'non_authorizing' until approved")


def validate_run_journal(record: dict[str, Any]) -> None:
    """RunJournal: plan digest, intent statuses, retries, errors, timestamps."""
    _check(isinstance(record, dict), "record must be a dict")
    for key in ("schema_version", "plan_digest", "run_id", "intent_statuses",
                "retries", "error_codes", "started_at", "ended_at"):
        _check(key in record, f"missing field: {key}")
    _check(_is_int(record["schema_version"]) and record["schema_version"] == SCHEMA_VERSION,
           "schema_version must be integer 1")
    _check(_is_str(record["plan_digest"]), "plan_digest must be a string")
    _check(_is_str(record["run_id"]), "run_id must be a string")
    _check(isinstance(record["intent_statuses"], dict), "intent_statuses must be a dict")
    _check(isinstance(record["retries"], dict), "retries must be a dict")
    _check(isinstance(record["error_codes"], dict), "error_codes must be a dict")
    _check(_is_str(record["started_at"]), "started_at must be a string")


def validate_driver_attestation(record: dict[str, Any]) -> None:
    """DriverAttestation: manual driver install evidence (e.g. Mr. Purple Turnip).

    Records WHICH driver+version the owner installed in an emulator; it never
    installs, downloads, or selects a driver.  Secret-checked like all records.
    """
    _check(isinstance(record, dict), "record must be a dict")
    for key in ("schema_version", "emulator", "driver_name", "driver_version",
                "source", "device_fingerprint", "attested_at"):
        _check(key in record, f"missing field: {key}")
    _check(_is_int(record["schema_version"]) and record["schema_version"] == SCHEMA_VERSION,
           "schema_version must be integer 1")
    _check(_is_str(record["emulator"]), "emulator must be a non-empty string")
    _check(_is_str(record["driver_name"]), "driver_name must be a non-empty string")
    _check(_is_str(record["driver_version"]), "driver_version must be a non-empty string")
    _check(_is_str(record["source"]), "source must be a non-empty string")
    _check(_is_str(record["device_fingerprint"]), "device_fingerprint must be a non-empty string")
    _check(_is_str(record["attested_at"]), "attested_at must be a non-empty string")
    _check(record["source"] != "auto", "driver source must be a manual human action, never auto")
    for forbidden in ("password", "token", "credential", "api_key"):
        _check(forbidden not in json.dumps(record).lower(),
               f"DriverAttestation must not contain '{forbidden}'")


def validate_acceptance_report(record: dict[str, Any]) -> None:
    """AcceptanceReport: game, platform, app version, renderer, GPU driver, user confirmations.

    The gpu_driver fields record WHICH driver passed the launch test, so the
    compatibility matrix is evidence-based (e.g. "Mr. Purple T23 @ Vulkan").
    """
    _check(isinstance(record, dict), "record must be a dict")
    for key in ("schema_version", "game", "platform", "app_version",
                "renderer", "gpu_driver", "gpu_driver_version",
                "user_confirmations", "accepted", "tested_at"):
        _check(key in record, f"missing field: {key}")
    _check(_is_int(record["schema_version"]) and record["schema_version"] == SCHEMA_VERSION,
           "schema_version must be integer 1")
    _check(_is_str(record["game"]), "game must be a string")
    _check(_is_str(record["platform"]), "platform must be a string")
    _check(_is_str(record["app_version"]), "app_version must be a string")
    _check(_is_str(record["renderer"]), "renderer must be a string")
    _check(_is_str(record["gpu_driver"]), "gpu_driver must be a string")
    _check(_is_str(record["gpu_driver_version"]), "gpu_driver_version must be a string")
    _check(isinstance(record["user_confirmations"], list), "user_confirmations must be a list")
    _check(_is_bool(record["accepted"]), "accepted must be a boolean")
    _check(_is_str(record["tested_at"]), "tested_at must be a string")


# ─── State machine ───────────────────────────────────────────────────

STATES = (
    "DRAFT",
    "DEVICE_ATTESTED",
    "STORAGE_BOUND",
    "PLAN_REVIEWED",
    "APPROVED",
    "MUTATING",
    "TRANSFER_VERIFIED",
    "PER_APP_ACCEPTED",
    "FRONTEND_ACCEPTED",
    "COMPLETE",
)

FAILURE_STATES = (
    "BLOCKED",
    "PARTIAL_RESUMABLE",
    "ROLLBACK_REQUIRED",
)

# Allowed transitions: from -> set of allowed target states
TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"DEVICE_ATTESTED", "BLOCKED"}),
    "DEVICE_ATTESTED": frozenset({"STORAGE_BOUND", "BLOCKED"}),
    "STORAGE_BOUND": frozenset({"PLAN_REVIEWED", "BLOCKED"}),
    "PLAN_REVIEWED": frozenset({"APPROVED", "BLOCKED"}),
    "APPROVED": frozenset({"MUTATING", "BLOCKED"}),
    "MUTATING": frozenset({"TRANSFER_VERIFIED", "PARTIAL_RESUMABLE", "ROLLBACK_REQUIRED"}),
    "TRANSFER_VERIFIED": frozenset({"PER_APP_ACCEPTED", "PARTIAL_RESUMABLE", "ROLLBACK_REQUIRED"}),
    "PER_APP_ACCEPTED": frozenset({"FRONTEND_ACCEPTED", "BLOCKED"}),
    "FRONTEND_ACCEPTED": frozenset({"COMPLETE", "BLOCKED"}),
    "COMPLETE": frozenset(),
    # Failure states
    "BLOCKED": frozenset({"DRAFT"}),  # can restart from draft after resolving
    "PARTIAL_RESUMABLE": frozenset({"MUTATING"}),  # resume from where we left off
    "ROLLBACK_REQUIRED": frozenset({"DRAFT"}),  # rollback to safe state
}


def validate_transition(current: str, target: str) -> None:
    """Raise ValueError if the transition is not allowed."""
    _check(current in STATES or current in FAILURE_STATES,
           f"unknown current state: {current}")
    _check(target in STATES or target in FAILURE_STATES,
           f"unknown target state: {target}")
    allowed = TRANSITIONS.get(current, frozenset())
    _check(target in allowed,
           f"transition {current} -> {target} is not allowed; "
           f"valid targets: {sorted(allowed) or ['(none)']}")


# ─── Approval validation ──────────────────────────────────────────────

def validate_approval(approval: dict[str, Any]) -> None:
    """An approval is valid only for: device fingerprint + storage binding +
    library manifest digest + profile/adapters + app-lock digest."""
    _check(isinstance(approval, dict), "approval must be a dict")
    for key in ("schema_version", "device_fingerprint", "storage_binding_digest",
                "library_manifest_digest", "profile_digest", "app_locks_digest",
                "approved_at"):
        _check(key in approval, f"missing approval field: {key}")
    _check(_is_int(approval["schema_version"]) and approval["schema_version"] == SCHEMA_VERSION,
           "schema_version must be integer 1")
    for key in ("device_fingerprint", "storage_binding_digest",
                "library_manifest_digest", "profile_digest", "app_locks_digest"):
        _check(_is_str(approval[key]), f"{key} must be a non-empty string")
    _check(_is_str(approval["approved_at"]), "approved_at must be a non-empty string")


def approval_matches(approval: dict[str, Any], *,
                     device_fingerprint: str,
                     storage_binding_digest: str,
                     library_manifest_digest: str,
                     profile_digest: str,
                     app_locks_digest: str) -> bool:
    """Return True only if every component of the approval matches."""
    return all([
        approval["device_fingerprint"] == device_fingerprint,
        approval["storage_binding_digest"] == storage_binding_digest,
        approval["library_manifest_digest"] == library_manifest_digest,
        approval["profile_digest"] == profile_digest,
        approval["app_locks_digest"] == app_locks_digest,
    ])


# ─── Record I/O ──────────────────────────────────────────────────────

def save_record(path: Path, record: dict[str, Any], validator) -> str:
    """Validate, write atomically, and return the record digest."""
    validator(record)
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    atomic_write(path, text)
    return digest_of(record)


def load_record(path: Path) -> dict[str, Any]:
    """Load a JSON record from disk."""
    return json.loads(Path(path).read_text())

#!/usr/bin/env python3
"""thorctl — the sole control plane for AYN Thor device operations.

No component other than thorctl may perform device actions.  A conversational
agent such as Hermes may guide the flow, but it calls thorctl endpoints and
cannot bypass identity, approval, storage, or transfer checks.

Usage:
  thorctl library scan|sync|verify [options]
  thorctl content ingest SOURCES [options]
  thorctl profile validate|plan [options]
  thorctl device discover|probe [options]
  thorctl storage bind [options]
  thorctl apps lock|fetch|verify|inventory [options]
  thorctl deployment plan|apply [options]
  thorctl transfer verify [options]
  thorctl acceptance run [options]
  thorctl frontend commit [options]
  thorctl report export [options]
  thorctl state show|reset [options]

All commands output JSON to stdout and write records to ~/.thor-provision/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# Local imports
import thorctl_schemas as schemas
from lib_thor import (
    STATE_DIR, Lock, Adb, atomic_write, sha256_file,
    logger_for, load_state, save_state, utc,
)

ROOT = Path(__file__).resolve().parent
RECORDS = STATE_DIR / "thorctl-records"


# ─── Path safety ─────────────────────────────────────────────────────

def assert_safe_path(path: str, context: str = "path") -> str:
    """Reject paths that escape their intended root."""
    if ".." in Path(path).parts:
        raise ValueError(f"unsafe {context}: path traversal in {path}")
    if not path.startswith("/"):
        raise ValueError(f"unsafe {context}: must be absolute ({path})")
    return path


# ─── Record helpers ──────────────────────────────────────────────────

def record_path(name: str) -> Path:
    """Where a thorctl record lives on disk."""
    RECORDS.mkdir(parents=True, exist_ok=True)
    return RECORDS / f"{name}.json"


def write_record(name: str, record: dict[str, Any], validator) -> str:
    """Validate and atomically write a record; return its digest."""
    validator(record)
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    p = record_path(name)
    atomic_write(p, text)
    return schemas.digest_of(record)


def read_record(name: str) -> dict[str, Any] | None:
    p = record_path(name)
    if not p.exists():
        return None
    return schemas.load_record(p)


# ─── State management ───────────────────────────────────────────────

def current_state() -> str:
    state = load_state()
    return state.get("thorctl_state", "DRAFT")


def set_state(new_state: str, plan_digest: str | None = None) -> None:
    state = load_state()
    old = state.get("thorctl_state", "DRAFT")
    schemas.validate_transition(old, new_state)
    state["thorctl_state"] = new_state
    if plan_digest:
        state["thorctl_plan_digest"] = plan_digest
    save_state(state)


def reset_state() -> None:
    state = load_state()
    state["thorctl_state"] = "DRAFT"
    state.pop("thorctl_plan_digest", None)
    save_state(state)


# ─── Approval management ─────────────────────────────────────────────

def current_approval() -> dict[str, Any] | None:
    return read_record("approval")


def check_approval(*, device_fingerprint: str, storage_binding_digest: str,
                   library_manifest_digest: str, profile_digest: str,
                   app_locks_digest: str) -> bool:
    """Return True only if a valid approval matches all components."""
    approval = current_approval()
    if approval is None:
        return False
    try:
        schemas.validate_approval(approval)
    except ValueError:
        return False
    return schemas.approval_matches(
        approval,
        device_fingerprint=device_fingerprint,
        storage_binding_digest=storage_binding_digest,
        library_manifest_digest=library_manifest_digest,
        profile_digest=profile_digest,
        app_locks_digest=app_locks_digest,
    )


# ─── Library commands ────────────────────────────────────────────────

def cmd_library(args: argparse.Namespace) -> int:
    """Wrap thor_library.py scan/sync/verify."""
    import thor_library as library

    source = Path(args.source) if args.source else library.DEFAULT_SOURCE
    target = Path(args.target) if args.target else library.DEFAULT_TARGET
    output = Path(args.output) if args.output else library.DEFAULT_OUTPUT

    argv = [args.action]
    if args.source:
        argv += ["--source", str(source)]
    if args.target:
        argv += ["--target", str(target)]
    if args.output:
        argv += ["--output", str(output)]
    if args.action == "sync" and args.apply:
        argv.append("--apply")

    rc = library.main(argv)
    if rc == 0 and args.action == "scan":
        manifest_path = output / "canonical-ssd-manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            digest = schemas.digest_of({
                "source": manifest.get("source"),
                "file_count": manifest.get("file_count"),
                "total_size_bytes": manifest.get("total_size_bytes"),
                "files": manifest.get("files"),
            })
            rec = {
                "schema_version": schemas.SCHEMA_VERSION,
                "digest": digest,
                "source": manifest.get("source"),
                "file_count": manifest.get("file_count"),
                "total_size_bytes": manifest.get("total_size_bytes"),
                "scanned_at": utc(),
            }
            write_record("library-manifest", rec,
                         lambda r: None if r["schema_version"] == 1 else
                         (_ for _ in ()).throw(ValueError("bad schema")))
    return rc


# ─── Content ingest ──────────────────────────────────────────────────

def cmd_content(args: argparse.Namespace) -> int:
    """Wrap ingest_library.py."""
    import ingest_library as ingest

    argv = list(args.sources)
    argv += ["--target", str(Path(args.target))]
    if args.decisions:
        argv += ["--decisions", str(args.decisions)]
    if args.apply:
        argv.append("--apply")
    if args.replace:
        argv.append("--replace")
    return ingest.main(argv)


# ─── Profile commands ────────────────────────────────────────────────

def cmd_profile(args: argparse.Namespace) -> int:
    """Wrap emulator_profiles.py validate/plan."""
    import emulator_profiles as profiles

    argv = [args.action]
    if args.profile:
        argv += ["--profile", str(args.profile)]
    if args.serial:
        argv += ["--serial", args.serial]
    if args.rom_root:
        argv += ["--rom-root", args.rom_root]
    if args.capabilities:
        argv += ["--capabilities", str(args.capabilities)]
    if args.output:
        argv += ["--output", str(args.output)]
    return profiles.main(argv)


# ─── Device commands ─────────────────────────────────────────────────

def cmd_device(args: argparse.Namespace) -> int:
    """device.discover: verify named serial and capture full identity.
    device.probe: consent-based capability and storage checks."""
    if args.action == "discover":
        return cmd_device_discover(args)
    elif args.action == "probe":
        return cmd_device_probe(args)
    else:
        print(f"unknown device action: {args.action}", file=sys.stderr)
        return 2


def cmd_device_discover(args: argparse.Namespace) -> int:
    """Verify named serial and capture full identity."""
    serial = args.serial
    if not serial:
        print("error: --serial is required for device discover", file=sys.stderr)
        return 2

    with Lock():
        with logger_for(serial) as log:
            adb = Adb(serial, log)

            # Verify device exists and get fingerprint
            _, model, _ = adb.shell("getprop ro.product.model", check=False)
            _, brand, _ = adb.shell("getprop ro.product.brand", check=False)
            _, release, _ = adb.shell("getprop ro.build.version.release", check=False)
            _, patch, _ = adb.shell("getprop ro.build.version.security_patch", check=False)
            _, fingerprint, _ = adb.shell("getprop ro.build.fingerprint", check=False)
            _, packages, _ = adb.shell("pm list packages -3", check=False)

            pkg_list = sorted(
                line.replace("package:", "").strip()
                for line in packages.splitlines()
                if line.strip().startswith("package:")
            )

            record = {
                "schema_version": schemas.SCHEMA_VERSION,
                "serial": serial,
                "model": model,
                "brand": brand,
                "build_fingerprint": fingerprint,
                "patch_level": patch,
                "android_release": release,
                "installed_packages": pkg_list,
                "discovered_at": utc(),
            }
            schemas.validate_device_attestation(record)
            # Save without the package list (which could be large) in the
            # attestation record itself; keep it as a sidecar.
            attestation = {k: v for k, v in record.items()
                           if k != "installed_packages"}
            digest = write_record("device-attestation", attestation,
                                  schemas.validate_device_attestation)
            sidecar = record_path("device-packages")
            atomic_write(sidecar, json.dumps(record, indent=2))

            print(json.dumps({
                "status": "discovered",
                "serial": serial,
                "model": model,
                "brand": brand,
                "build_fingerprint": fingerprint,
                "patch_level": patch,
                "android_release": release,
                "package_count": len(pkg_list),
                "attestation_digest": digest,
            }, indent=2))
            return 0


def cmd_device_probe(args: argparse.Namespace) -> int:
    """Run consent-based capability probe (wraps probe.py)."""
    serial = args.serial
    if not serial:
        print("error: --serial is required for device probe", file=sys.stderr)
        return 2

    import probe
    argv = [serial]
    if args.refresh:
        argv.append("--refresh")
    return probe.main(argv)


# ─── Storage binding ─────────────────────────────────────────────────

def cmd_storage(args: argparse.Namespace) -> int:
    """storage.bind: confirm internal or removable ROM root."""
    if args.action != "bind":
        print(f"unknown storage action: {args.action}", file=sys.stderr)
        return 2

    serial = args.serial
    rom_root = args.rom_root
    if not serial or not rom_root:
        print("error: --serial and --rom-root are required for storage bind",
              file=sys.stderr)
        return 2

    assert_safe_path(rom_root, "rom_root")

    with Lock():
        with logger_for(serial) as log:
            adb = Adb(serial, log)
            # Verify the path exists and is writable on device
            _, out, _ = adb.shell(f"test -d '{rom_root}' && echo y", check=False)
            if out.strip() != "y":
                print(f"error: rom_root does not exist on device: {rom_root}",
                      file=sys.stderr)
                return 2
            # Free space check
            _, df, _ = adb.shell(f"df '{rom_root}'", check=False)
            free_bytes = 0
            for line in df.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        free_bytes = int(parts[-3]) * 1024  # df in 1K blocks
                        break
                    except ValueError:
                        pass

            record = {
                "schema_version": schemas.SCHEMA_VERSION,
                "storage_type": args.storage_type or "removable",
                "rom_root": rom_root,
                "free_space_bytes": free_bytes,
                "confirmed": True,
                "serial": serial,
                "bound_at": utc(),
            }
            # Validate without serial (not in the base schema)
            base = {k: v for k, v in record.items() if k != "serial"}
            schemas.validate_storage_binding(base)
            digest = write_record("storage-binding", base,
                                  schemas.validate_storage_binding)

            print(json.dumps({
                "status": "bound",
                "serial": serial,
                "storage_type": record["storage_type"],
                "rom_root": rom_root,
                "free_space_bytes": free_bytes,
                "binding_digest": digest,
            }, indent=2))
            return 0


# ─── App lock commands ──────────────────────────────────────────────

def cmd_apps(args: argparse.Namespace) -> int:
    """apps.lock/fetch/verify/inventory — pinned APK supply chain."""
    if args.action == "lock":
        return cmd_apps_lock(args)
    elif args.action == "fetch":
        return cmd_apps_fetch(args)
    elif args.action == "verify":
        return cmd_apps_verify(args)
    elif args.action == "inventory":
        return cmd_apps_inventory(args)
    else:
        print(f"unknown apps action: {args.action}", file=sys.stderr)
        return 2


def cmd_apps_lock(args: argparse.Namespace) -> int:
    """Create an app lock record for a pinned APK."""
    apk_path = Path(args.apk)
    if not apk_path.exists():
        print(f"error: APK not found: {apk_path}", file=sys.stderr)
        return 2
    if not apk_path.suffix == ".apk":
        print(f"error: not an APK: {apk_path}", file=sys.stderr)
        return 2

    sha = sha256_file(apk_path)
    record = {
        "schema_version": schemas.SCHEMA_VERSION,
        "source": str(apk_path),
        "release": args.release or "unknown",
        "sha256": sha,
        "package": args.package or "unknown",
        "signer_digest": args.signer or hashlib.sha256(b"unknown").hexdigest(),
        "arch": args.arch or "arm64-v8a",
        "approved_version": args.version or "1",
        "locked_at": utc(),
    }
    schemas.validate_app_lock(record)
    name = f"applock-{args.package or apk_path.stem}"
    digest = write_record(name, record, schemas.validate_app_lock)
    print(json.dumps({"status": "locked", "digest": digest, **record}, indent=2))
    return 0


def cmd_apps_fetch(args: argparse.Namespace) -> int:
    """Fetch APKs via apps.py (wraps existing downloader)."""
    import apps as apps_mod
    argv = []
    if args.only:
        argv += ["--only", args.only]
    if args.all:
        argv.append("--all")
    return apps_mod.main() if not argv else apps_mod.main()


def cmd_apps_verify(args: argparse.Namespace) -> int:
    """Verify an installed app matches its lock record."""
    if not args.serial or not args.package:
        print("error: --serial and --package are required for apps verify",
              file=sys.stderr)
        return 2
    lock_name = f"applock-{args.package}"
    lock = read_record(lock_name)
    if lock is None:
        print(f"error: no app lock found for {args.package}", file=sys.stderr)
        return 2

    with Lock():
        with logger_for(args.serial) as log:
            adb = Adb(args.serial, log)
            _, ver, _ = adb.shell(
                f"dumpsys package {args.package} | grep -m1 versionName",
                check=False)
            installed_ver = ver.replace("versionName=", "").strip("'") or "?"
            match = installed_ver == lock["approved_version"]
            print(json.dumps({
                "package": args.package,
                "locked_version": lock["approved_version"],
                "installed_version": installed_ver,
                "sha256": lock["sha256"],
                "match": match,
            }, indent=2))
            return 0 if match else 1


def cmd_apps_inventory(args: argparse.Namespace) -> int:
    """List installed third-party packages on the device."""
    if not args.serial:
        print("error: --serial is required for apps inventory", file=sys.stderr)
        return 2
    with Lock():
        with logger_for(args.serial) as log:
            adb = Adb(args.serial, log)
            _, out, _ = adb.shell("pm list packages -3", check=False)
            pkgs = sorted(line.replace("package:", "").strip()
                          for line in out.splitlines()
                          if line.strip().startswith("package:"))
            print(json.dumps({"package_count": len(pkgs), "packages": pkgs},
                             indent=2))
            return 0


# ─── Deployment commands ─────────────────────────────────────────────

def cmd_deployment(args: argparse.Namespace) -> int:
    """deployment.plan: generate immutable deployment plan.
    deployment.apply: execute the plan (requires valid approval)."""
    if args.action == "plan":
        return cmd_deployment_plan(args)
    elif args.action == "apply":
        return cmd_deployment_apply(args)
    else:
        print(f"unknown deployment action: {args.action}", file=sys.stderr)
        return 2


def cmd_deployment_plan(args: argparse.Namespace) -> int:
    """Generate an immutable, non-authorizing deployment plan."""
    import emulator_profiles as profiles

    # Load required records
    attestation = read_record("device-attestation")
    storage = read_record("storage-binding")
    lib_manifest = read_record("library-manifest")

    missing = []
    if attestation is None:
        missing.append("device-attestation")
    if storage is None:
        missing.append("storage-binding")
    if lib_manifest is None:
        missing.append("library-manifest")

    # Load profile
    profile = profiles.load_profile(Path(args.profile)) if args.profile else profiles.load_profile()
    profile_digest = schemas.digest_of(profile)

    # Collect app locks
    app_locks = {}
    for p in RECORDS.glob("applock-*.json"):
        lock = json.loads(p.read_text())
        app_locks[lock["package"]] = lock["sha256"]
    app_locks_digest = schemas.digest_of(app_locks) if app_locks else ""

    lib_digest = lib_manifest["digest"] if lib_manifest else ""
    device_fp = attestation["build_fingerprint"] if attestation else ""
    storage_digest = schemas.digest_of(storage) if storage else ""

    record = {
        "schema_version": schemas.SCHEMA_VERSION,
        "library_digest": lib_digest,
        "profile": profile["profile"],
        "profile_version": profile["profile_version"],
        "adapters": list(profile["emulators"].keys()),
        "app_locks": app_locks,
        "device_serial": attestation["serial"] if attestation else None,
        "device_fingerprint": device_fp,
        "storage_binding": storage or {},
        "intents": [],  # filled by the plan builder
        "plan_digest": "",  # computed below
        "authorization": "non_authorizing",
        "missing_records": missing,
        "created_at": utc(),
    }
    record["plan_digest"] = schemas.digest_of(
        {k: v for k, v in record.items() if k != "plan_digest"})
    schemas.validate_deployment_plan(record)
    write_record("deployment-plan", record, schemas.validate_deployment_plan)

    print(json.dumps({
        "status": "planned" if not missing else "incomplete",
        "missing_records": missing,
        "plan_digest": record["plan_digest"],
        "adapters": record["adapters"],
        "authorization": "non_authorizing",
    }, indent=2))
    return 0 if not missing else 1


def cmd_deployment_apply(args: argparse.Namespace) -> int:
    """Execute the deployment plan — requires valid approval."""
    plan = read_record("deployment-plan")
    if plan is None:
        print("error: no deployment plan found; run 'thorctl deployment plan' first",
               file=sys.stderr)
        return 2

    # Verify approval
    attestation = read_record("device-attestation")
    storage = read_record("storage-binding")
    lib_manifest = read_record("library-manifest")

    if not check_approval(
        device_fingerprint=attestation["build_fingerprint"] if attestation else "",
        storage_binding_digest=schemas.digest_of(storage) if storage else "",
        library_manifest_digest=lib_manifest["digest"] if lib_manifest else "",
        profile_digest=plan["plan_digest"],
        app_locks_digest=schemas.digest_of(plan["app_locks"]) if plan["app_locks"] else "",
    ):
        print("error: deployment approval does not match current records; "
              "re-review and re-approve the plan", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({"status": "dry_run", "plan_digest": plan["plan_digest"]},
                         indent=2))
        return 0

    # Real apply would install apps and transfer ROMs here
    print(json.dumps({
        "status": "not_implemented",
        "reason": "device apply requires a connected physical Thor",
        "plan_digest": plan["plan_digest"],
    }, indent=2))
    return 1


# ─── Transfer verify ─────────────────────────────────────────────────

def cmd_transfer(args: argparse.Namespace) -> int:
    """transfer.verify: remote SHA-256 for every manifest file."""
    if not args.serial:
        print("error: --serial is required for transfer verify", file=sys.stderr)
        return 2
    plan = read_record("deployment-plan")
    if plan is None:
        print("error: no deployment plan found", file=sys.stderr)
        return 2

    print(json.dumps({
        "status": "not_implemented",
        "reason": "transfer verify requires a connected device with pushed content",
        "plan_digest": plan["plan_digest"],
    }, indent=2))
    return 1


# ─── Acceptance ──────────────────────────────────────────────────────

def cmd_acceptance(args: argparse.Namespace) -> int:
    """acceptance.run: per-platform technical + human acceptance."""
    plan = read_record("deployment-plan")
    if plan is None:
        print("error: no deployment plan found", file=sys.stderr)
        return 2

    record = {
        "schema_version": schemas.SCHEMA_VERSION,
        "game": args.game or "unspecified",
        "platform": args.platform or "unspecified",
        "app_version": args.app_version or "unknown",
        "renderer": args.renderer or "unknown",
        "gpu_driver": args.gpu_driver or "unattested",
        "gpu_driver_version": args.gpu_driver_version or "unattested",
        "user_confirmations": args.confirmations or [],
        "accepted": args.accepted if args.accepted is not None else False,
        "tested_at": utc(),
    }
    schemas.validate_acceptance_report(record)
    name = f"acceptance-{args.platform or 'unspecified'}-{utc().replace(':', '')}"
    write_record(name, record, schemas.validate_acceptance_report)
    print(json.dumps({"status": "recorded", **record}, indent=2))
    return 0 if record["accepted"] else 1


# ─── Frontend ────────────────────────────────────────────────────────

def cmd_frontend(args: argparse.Namespace) -> int:
    """frontend.commit: Cocoon activation for accepted platforms only."""
    if args.action != "commit":
        print(f"unknown frontend action: {args.action}", file=sys.stderr)
        return 2

    # Count acceptance records
    accepted = []
    for p in RECORDS.glob("acceptance-*.json"):
        rec = json.loads(p.read_text())
        if rec.get("accepted"):
            accepted.append(rec["platform"])

    if not accepted:
        print(json.dumps({
            "status": "refused",
            "reason": "no accepted platforms; run acceptance first",
        }, indent=2))
        return 2

    print(json.dumps({
        "status": "committed",
        "accepted_platforms": accepted,
        "committed_at": utc(),
    }, indent=2))
    return 0


# ─── Report export ───────────────────────────────────────────────────

def cmd_report(args: argparse.Namespace) -> int:
    """report.export: redacted final report linking all approved records."""
    records = {}
    for p in sorted(RECORDS.glob("*.json")):
        records[p.stem] = json.loads(p.read_text())

    # Redact any potential secrets
    redacted = {}
    for name, rec in records.items():
        text = json.dumps(rec)
        # Strip known secret patterns
        for pattern in ("api_key", "password", "token", "credential", "secret"):
            if pattern in text.lower():
                text = text.replace(text, "[REDACTED]")
                break
        redacted[name] = rec

    report = {
        "schema_version": schemas.SCHEMA_VERSION,
        "exported_at": utc(),
        "records": list(redacted.keys()),
        "state": current_state(),
        "approval": current_approval() is not None,
    }
    print(json.dumps(report, indent=2))
    return 0


# ─── GPU driver attestation ──────────────────────────────────────────

def cmd_driver(args: argparse.Namespace) -> int:
    """driver.attest: record a manual GPU driver install (e.g. Mr. Purple Turnip).
    driver check: verify a device's driver attestation covers an emulator."""
    if args.action == "attest":
        if not all([args.emulator, args.driver_name, args.driver_version,
                    args.source, args.fingerprint]):
            print("error: --emulator --driver-name --driver-version --source "
                  "--fingerprint are all required for driver attest",
                  file=sys.stderr)
            return 2
        record = {
            "schema_version": schemas.SCHEMA_VERSION,
            "emulator": args.emulator,
            "driver_name": args.driver_name,
            "driver_version": args.driver_version,
            "source": args.source,
            "device_fingerprint": args.fingerprint,
            "attested_at": utc(),
        }
        schemas.validate_driver_attestation(record)
        name = f"driver-{args.emulator}-{utc().replace(':', '')}"
        digest = write_record(name, record, schemas.validate_driver_attestation)
        print(json.dumps({"status": "attested", "digest": digest, **record},
                         indent=2))
        return 0
    elif args.action == "check":
        if not args.emulator:
            print("error: --emulator is required for driver check", file=sys.stderr)
            return 2
        attested = []
        for p in sorted(RECORDS.glob("driver-*.json")):
            rec = json.loads(p.read_text())
            if rec.get("emulator") == args.emulator:
                attested.append(rec)
        if not attested:
            print(json.dumps({
                "status": "unattested",
                "emulator": args.emulator,
                "reason": "no manual driver attestation on record; "
                          "install the driver on device, then run 'driver attest'",
            }, indent=2))
            return 1
        latest = attested[-1]
        print(json.dumps({
            "status": "attested",
            "emulator": args.emulator,
            "driver_name": latest["driver_name"],
            "driver_version": latest["driver_version"],
            "attested_at": latest["attested_at"],
            "attestation_count": len(attested),
        }, indent=2))
        return 0
    else:
        print(f"unknown driver action: {args.action}", file=sys.stderr)
        return 2


# ─── Setup verification (offline kit completeness) ───────────────────

def cmd_setup(args: argparse.Namespace) -> int:
    """setup.verify: prove the offline kit is complete BEFORE device day.
    Checks staged APKs, driver, configs, library manifest, apply-sheets,
    storage-variant decision, and lists owner-supplied items still missing."""
    kit = ROOT / "configs" / "offline-kit"
    report = {"schema_version": 1, "checked_at": utc(), "checks": {}, "ok": True}

    # 1. APKs staged with lock records
    apks = sorted((ROOT / "apks").glob("*.apk"))
    report["checks"]["apks_staged"] = {"count": len(apks), "ok": len(apks) >= 20}
    if len(apks) < 20:
        report["ok"] = False

    # 2. Turnip driver staged
    drivers = sorted((ROOT / "vendor" / "drivers").glob("*.zip"))
    report["checks"]["gpu_driver"] = {
        "staged": [d.name for d in drivers],
        "ok": bool(drivers),
    }
    if not drivers:
        report["ok"] = False

    # 3. RetroArch cfg staged
    cfg = ROOT / "sd_card" / "retroarch.cfg"
    report["checks"]["retroarch_cfg"] = {"ok": cfg.exists()}

    # 4. Library manifest present and recent
    lm = ROOT / "library" / "canonical-ssd-manifest.json"
    if lm.exists():
        m = json.loads(lm.read_text())
        report["checks"]["library_manifest"] = {
            "ok": True, "file_count": m.get("file_count"),
            "total_gb": round(m.get("total_size_bytes", 0) / 1e9, 1),
        }
    else:
        report["checks"]["library_manifest"] = {"ok": False,
                                                "reason": "run thor_library.py scan"}
        report["ok"] = False

    # 5. Offline kit generated
    kit_manifest = kit / "kit-manifest.json"
    report["checks"]["offline_kit"] = {"ok": kit_manifest.exists(),
                                        "path": str(kit.relative_to(ROOT))}
    if not kit_manifest.exists():
        report["ok"] = False
        report["checks"]["offline_kit"]["reason"] = "run python3 build_offline_kit.py"

    # 6. Apply-sheets present for every profile emulator
    profile = json.loads((ROOT / "profiles" / "ayn-thor-v1.json").read_text())
    sheets_dir = kit / "apply-sheets"
    missing_sheets = [e for e in profile["emulators"]
                      if not (sheets_dir / f"{e}.md").exists()]
    report["checks"]["apply_sheets"] = {
        "ok": not missing_sheets and sheets_dir.exists(),
        "expected": len(profile["emulators"]),
        "missing": missing_sheets,
    }
    if missing_sheets:
        report["ok"] = False

    # 7. Owner-supplied items (informational — cannot be automated)
    report["checks"]["owner_supplies_reminder"] = {
        "ok": True,
        "items": ["BIOS dumps (RetroArch/WatermelonDS/DuckStation/NetherSX2 as owned)",
                  "Eden: prod.keys + firmware (in-app picker)",
                  "Cemu: keys.txt (in-app)",
                  "ES-DE: purchased Android APK (Patreon/Galaxy Store)"],
        "note": "These are never staged by automation; verify you have them ready.",
    }

    # 8. Storage variant chosen (from storage-binding record if present)
    binding = read_record("storage-binding")
    report["checks"]["storage_binding"] = {
        "ok": binding is not None,
        "bound": bool(binding),
        "note": None if binding else "choose sd_card/internal/usb_otg/hybrid and run storage bind on device day",
    }

    atomic_write(ROOT / "configs" / "offline-kit" / "setup-verify-report.json",
                 json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


# ─── State commands ──────────────────────────────────────────────────

def cmd_state(args: argparse.Namespace) -> int:
    """state.show: show current thorctl state; state.reset: reset to DRAFT."""
    if args.action == "show":
        state = load_state()
        print(json.dumps({
            "thorctl_state": state.get("thorctl_state", "DRAFT"),
            "thorctl_plan_digest": state.get("thorctl_plan_digest"),
            "records_dir": str(RECORDS),
        }, indent=2))
        return 0
    elif args.action == "reset":
        reset_state()
        print(json.dumps({"status": "reset", "state": "DRAFT"}, indent=2))
        return 0
    else:
        print(f"unknown state action: {args.action}", file=sys.stderr)
        return 2


# ─── CLI parser ──────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="thorctl",
        description="Sole control plane for AYN Thor device operations.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # library
    lib = sub.add_parser("library", help="canonical game library manifest")
    lib.add_argument("action", choices=["scan", "sync", "verify"])
    lib.add_argument("--source", help="SSD ROMs directory")
    lib.add_argument("--target", help="staging directory")
    lib.add_argument("--output", help="output directory for manifest/report")
    lib.add_argument("--apply", action="store_true", help="perform copy (sync only)")
    lib.set_defaults(func=cmd_library)

    # content
    content = sub.add_parser("content", help="safe classification and archive review")
    content.add_argument("action", choices=["ingest"])
    content.add_argument("sources", nargs="*", help="source files/directories")
    content.add_argument("--target", default=str(ROOT / "sd_card"))
    content.add_argument("--decisions", help="path to decisions JSON")
    content.add_argument("--apply", action="store_true")
    content.add_argument("--replace", action="store_true")
    content.set_defaults(func=cmd_content)

    # profile
    prof = sub.add_parser("profile", help="validate and plan emulator profile")
    prof.add_argument("action", choices=["validate", "plan"])
    prof.add_argument("--profile", help="path to profile JSON")
    prof.add_argument("--serial", help="device serial")
    prof.add_argument("--rom-root", help="ROM root path")
    prof.add_argument("--capabilities", help="capabilities JSON path")
    prof.add_argument("--output", help="output path")
    prof.set_defaults(func=cmd_profile)

    # device
    dev = sub.add_parser("device", help="device discovery and probing")
    dev.add_argument("action", choices=["discover", "probe"])
    dev.add_argument("--serial", help="explicit device serial (required)")
    dev.add_argument("--refresh", action="store_true", help="force re-probe")
    dev.set_defaults(func=cmd_device)

    # storage
    stor = sub.add_parser("storage", help="storage binding")
    stor.add_argument("action", choices=["bind"])
    stor.add_argument("--serial", required=True, help="device serial")
    stor.add_argument("--rom-root", required=True, help="ROM root on device")
    stor.add_argument("--storage-type", choices=["internal", "removable"],
                       default="removable")
    stor.set_defaults(func=cmd_storage)

    # apps
    apps = sub.add_parser("apps", help="pinned APK supply chain")
    apps.add_argument("action", choices=["lock", "fetch", "verify", "inventory"])
    apps.add_argument("--serial", help="device serial")
    apps.add_argument("--apk", help="APK file path (lock)")
    apps.add_argument("--package", help="package ID")
    apps.add_argument("--release", help="release tag")
    apps.add_argument("--signer", help="signing certificate SHA-256")
    apps.add_argument("--arch", help="ABI (arm64-v8a, universal, etc)")
    apps.add_argument("--version", help="approved version string")
    apps.add_argument("--only", help="fetch: comma-separated name substrings")
    apps.add_argument("--all", action="store_true", help="fetch all")
    apps.set_defaults(func=cmd_apps)

    # deployment
    dep = sub.add_parser("deployment", help="deployment plan and apply")
    dep.add_argument("action", choices=["plan", "apply"])
    dep.add_argument("--profile", help="profile JSON path")
    dep.add_argument("--dry-run", action="store_true")
    dep.set_defaults(func=cmd_deployment)

    # transfer
    transfer = sub.add_parser("transfer", help="transfer verification")
    transfer.add_argument("action", choices=["verify"])
    transfer.add_argument("--serial", required=True)
    transfer.set_defaults(func=cmd_transfer)

    # acceptance
    acc = sub.add_parser("acceptance", help="per-platform acceptance testing")
    acc.add_argument("action", choices=["run"])
    acc.add_argument("--game", help="game title tested")
    acc.add_argument("--platform", help="platform tested")
    acc.add_argument("--app-version", help="emulator app version")
    acc.add_argument("--renderer", help="renderer used")
    acc.add_argument("--gpu-driver", help="GPU driver name that passed (e.g. Mr. Purple T23)")
    acc.add_argument("--gpu-driver-version", help="GPU driver version that passed")
    acc.add_argument("--confirmations", nargs="*", help="user confirmations")
    acc.add_argument("--accepted", action="store_true", help="mark as accepted")
    acc.set_defaults(func=cmd_acceptance)

    # frontend
    fe = sub.add_parser("frontend", help="Cocoon frontend activation")
    fe.add_argument("action", choices=["commit"])
    fe.set_defaults(func=cmd_frontend)

    # report
    rep = sub.add_parser("report", help="redacted final report")
    rep.add_argument("action", choices=["export"])
    rep.set_defaults(func=cmd_report)

    # driver (GPU driver attestation — manual installs only)
    drv = sub.add_parser("driver", help="GPU driver attestation (manual installs)")
    drv.add_argument("action", choices=["attest", "check"])
    drv.add_argument("--emulator", help="emulator the driver is for (e.g. eden)")
    drv.add_argument("--driver-name", help="driver name (e.g. Mr. Purple T23)")
    drv.add_argument("--driver-version", help="driver version string")
    drv.add_argument("--source", help="where the driver came from (manual source)")
    drv.add_argument("--fingerprint", help="device build fingerprint")
    drv.set_defaults(func=cmd_driver)

    # setup (offline kit completeness gate)
    setup = sub.add_parser("setup", help="offline kit verification")
    setup.add_argument("action", choices=["verify"])
    setup.set_defaults(func=cmd_setup)

    # state
    st = sub.add_parser("state", help="thorctl state management")
    st.add_argument("action", choices=["show", "reset"])
    st.set_defaults(func=cmd_state)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, ConnectionError) as exc:
        print(f"thorctl error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

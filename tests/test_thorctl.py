"""Tests for thorctl — the control plane.

Verifies that invalid records, concurrent runs, expired/mismatched approvals,
and malformed paths all fail closed.  No physical device or ADB is required.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import thorctl_schemas as schemas
import thorctl


class SchemaValidationTests(unittest.TestCase):
    """Schema validation must reject invalid records."""

    def test_device_attestation_rejects_missing_serial(self):
        rec = {"schema_version": 1, "model": "Thor", "brand": "AYN",
               "build_fingerprint": "fp", "patch_level": "2026-01",
               "discovered_at": "2026-01-01T00:00:00Z"}
        with self.assertRaises(ValueError):
            schemas.validate_device_attestation(rec)

    def test_device_attestation_rejects_wrong_schema_version(self):
        rec = {"schema_version": 2, "serial": "abc", "model": "Thor",
               "brand": "AYN", "build_fingerprint": "fp",
               "patch_level": "2026-01", "discovered_at": "now"}
        with self.assertRaises(ValueError):
            schemas.validate_device_attestation(rec)

    def test_device_attestation_rejects_secrets(self):
        rec = {"schema_version": 1, "serial": "abc", "model": "Thor",
               "brand": "AYN", "build_fingerprint": "fp",
               "patch_level": "2026-01", "discovered_at": "now",
               "bios": "secret"}
        with self.assertRaises(ValueError):
            schemas.validate_device_attestation(rec)

    def test_device_attestation_allows_standard_release_keys_fingerprint(self):
        rec = {"schema_version": 1, "serial": "abc", "model": "Thor",
               "brand": "AYN",
               "build_fingerprint": "AYN/kalama/kalama:13/TQ3A/release-keys",
               "patch_level": "2026-01", "discovered_at": "now"}
        schemas.validate_device_attestation(rec)

    def test_storage_binding_rejects_invalid_type(self):
        rec = {"schema_version": 1, "storage_type": "usb",
               "rom_root": "/storage/card", "free_space_bytes": 1000,
               "confirmed": True, "bound_at": "now"}
        with self.assertRaises(ValueError):
            schemas.validate_storage_binding(rec)

    def test_storage_binding_rejects_relative_path(self):
        rec = {"schema_version": 1, "storage_type": "removable",
               "rom_root": "relative/path", "free_space_bytes": 1000,
               "confirmed": True, "bound_at": "now"}
        with self.assertRaises(ValueError):
            schemas.validate_storage_binding(rec)

    def test_app_lock_rejects_short_sha256(self):
        rec = {"schema_version": 1, "source": "local", "release": "v1",
               "sha256": "abc", "package": "com.test", "signer_digest": "x",
               "arch": "arm64-v8a", "approved_version": "1.0",
               "locked_at": "now"}
        with self.assertRaises(ValueError):
            schemas.validate_app_lock(rec)

    def test_app_lock_rejects_unknown_arch(self):
        rec = {"schema_version": 1, "source": "local", "release": "v1",
               "sha256": "a" * 64, "package": "com.test",
               "signer_digest": "b" * 64, "arch": "mips",
               "approved_version": "1.0", "locked_at": "now"}
        with self.assertRaises(ValueError):
            schemas.validate_app_lock(rec)

    def test_deployment_plan_must_be_non_authorizing(self):
        rec = {"schema_version": 1, "library_digest": "abc",
               "profile": "ayn-thor", "profile_version": "1.1.0",
               "adapters": [], "app_locks": {}, "device_serial": "x",
               "storage_binding": {}, "intents": [], "plan_digest": "d",
               "created_at": "now", "authorization": "authorized"}
        with self.assertRaises(ValueError):
            schemas.validate_deployment_plan(rec)


class StateMachineTests(unittest.TestCase):
    """State machine must reject invalid transitions."""

    def test_valid_forward_transition(self):
        schemas.validate_transition("DRAFT", "DEVICE_ATTESTED")
        schemas.validate_transition("DEVICE_ATTESTED", "STORAGE_BOUND")
        schemas.validate_transition("STORAGE_BOUND", "PLAN_REVIEWED")
        schemas.validate_transition("PLAN_REVIEWED", "APPROVED")

    def test_skip_transition_rejected(self):
        with self.assertRaises(ValueError):
            schemas.validate_transition("DRAFT", "APPROVED")

    def test_complete_is_terminal(self):
        with self.assertRaises(ValueError):
            schemas.validate_transition("COMPLETE", "DRAFT")

    def test_rollback_required_can_go_to_draft(self):
        schemas.validate_transition("ROLLBACK_REQUIRED", "DRAFT")

    def test_partial_resumable_can_resume_mutating(self):
        schemas.validate_transition("PARTIAL_RESUMABLE", "MUTATING")

    def test_unknown_state_rejected(self):
        with self.assertRaises(ValueError):
            schemas.validate_transition("UNKNOWN", "DRAFT")


class ApprovalTests(unittest.TestCase):
    """Approval validation and matching."""

    def _valid_approval(self):
        return {
            "schema_version": 1,
            "device_fingerprint": "fp-abc",
            "storage_binding_digest": "sb-123",
            "library_manifest_digest": "lm-456",
            "profile_digest": "pd-789",
            "app_locks_digest": "al-000",
            "approved_at": "2026-01-01T00:00:00Z",
        }

    def test_valid_approval_passes(self):
        schemas.validate_approval(self._valid_approval())

    def test_missing_field_rejected(self):
        a = self._valid_approval()
        del a["app_locks_digest"]
        with self.assertRaises(ValueError):
            schemas.validate_approval(a)

    def test_matching_approval_returns_true(self):
        a = self._valid_approval()
        self.assertTrue(schemas.approval_matches(
            a, device_fingerprint="fp-abc",
            storage_binding_digest="sb-123",
            library_manifest_digest="lm-456",
            profile_digest="pd-789",
            app_locks_digest="al-000"))

    def test_mismatched_approval_returns_false(self):
        a = self._valid_approval()
        self.assertFalse(schemas.approval_matches(
            a, device_fingerprint="WRONG",
            storage_binding_digest="sb-123",
            library_manifest_digest="lm-456",
            profile_digest="pd-789",
            app_locks_digest="al-000"))


class PathSafetyTests(unittest.TestCase):
    """Path safety must reject traversal and relative paths."""

    def test_traversal_rejected(self):
        with self.assertRaises(ValueError):
            thorctl.assert_safe_path("/storage/../escape", "rom_root")

    def test_relative_rejected(self):
        with self.assertRaises(ValueError):
            thorctl.assert_safe_path("relative/path", "rom_root")

    def test_absolute_accepted(self):
        self.assertEqual("/storage/card/ROMs",
                         thorctl.assert_safe_path("/storage/card/ROMs", "rom_root"))


class RecordIOTests(unittest.TestCase):
    """Record I/O must be atomic and round-trip correctly."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.records_dir = self.root / "records"
        self.records_dir.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_write_and_read_record(self):
        rec = {"schema_version": 1, "serial": "abc", "model": "Thor",
               "brand": "AYN", "build_fingerprint": "fp",
               "patch_level": "2026-01", "discovered_at": "now"}
        path = self.records_dir / "test.json"
        digest = schemas.save_record(path, rec, schemas.validate_device_attestation)
        loaded = schemas.load_record(path)
        self.assertEqual(loaded["serial"], "abc")
        self.assertEqual(digest, schemas.digest_of(rec))

    def test_write_rejects_invalid_record(self):
        rec = {"schema_version": 1}  # missing fields
        path = self.records_dir / "bad.json"
        with self.assertRaises(ValueError):
            schemas.save_record(path, rec, schemas.validate_device_attestation)
        self.assertFalse(path.exists())


class ConcurrentLockTests(unittest.TestCase):
    """The Lock must prevent concurrent execution."""

    def setUp(self):
        self.old_state_dir = thorctl.STATE_DIR
        self.temp = tempfile.TemporaryDirectory()
        thorctl.STATE_DIR = Path(self.temp.name)

    def tearDown(self):
        thorctl.STATE_DIR = self.old_state_dir
        self.temp.cleanup()

    def test_lock_prevents_concurrent_run(self):
        from lib_thor import Lock, STATE_DIR
        lock = Lock()
        lock.__enter__()
        try:
            with self.assertRaises(SystemExit):
                Lock().__enter__()
        finally:
            lock.__exit__(None, None, None)


class DeploymentPlanTests(unittest.TestCase):
    """Deployment plan must be non-authorizing and report missing records."""

    def setUp(self):
        self.old_state_dir = thorctl.STATE_DIR
        self.old_records = thorctl.RECORDS
        self.temp = tempfile.TemporaryDirectory()
        thorctl.STATE_DIR = Path(self.temp.name)
        thorctl.RECORDS = thorctl.STATE_DIR / "thorctl-records"
        thorctl.RECORDS.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        thorctl.STATE_DIR = self.old_state_dir
        thorctl.RECORDS = self.old_records
        self.temp.cleanup()

    def test_plan_without_records_reports_incomplete(self):
        args = MagicMock()
        args.profile = None
        with patch.object(thorctl, "read_record", return_value=None):
            rc = thorctl.cmd_deployment_plan(args)
        self.assertEqual(1, rc)

    def test_plan_authorization_is_never_authorizing(self):
        """A forged plan cannot self-authorize."""
        args = MagicMock()
        args.profile = None
        attestation = {"schema_version": 1, "serial": "abc", "model": "Thor",
                        "brand": "AYN", "build_fingerprint": "fp",
                        "patch_level": "2026-01", "discovered_at": "now"}
        storage = {"schema_version": 1, "storage_type": "removable",
                    "rom_root": "/storage/card", "free_space_bytes": 1000,
                    "confirmed": True, "bound_at": "now"}
        lib_manifest = {"schema_version": 1, "digest": "abc",
                         "source": "/test", "file_count": 0,
                         "total_size_bytes": 0, "scanned_at": "now"}

        # Even with all records present, the plan must be non_authorizing
        def mock_read(name):
            if name == "device-attestation":
                return attestation
            elif name == "storage-binding":
                return storage
            elif name == "library-manifest":
                return lib_manifest
            return None

        with patch.object(thorctl, "read_record", side_effect=mock_read), \
             patch("emulator_profiles.load_profile", return_value={
                 "schema_version": 1, "profile": "ayn-thor",
                 "profile_version": "1.1.0", "emulators": {},
                 "acceptance": [], "rom_root": "${ROM_ROOT}"}):
            rc = thorctl.cmd_deployment_plan(args)

        plan = json.loads(thorctl.record_path("deployment-plan").read_text())
        self.assertEqual("non_authorizing", plan["authorization"])


class ApplyWithoutApprovalTests(unittest.TestCase):
    """deployment.apply must refuse without a valid approval."""

    def setUp(self):
        self.old_state_dir = thorctl.STATE_DIR
        self.old_records = thorctl.RECORDS
        self.temp = tempfile.TemporaryDirectory()
        thorctl.STATE_DIR = Path(self.temp.name)
        thorctl.RECORDS = thorctl.STATE_DIR / "thorctl-records"
        thorctl.RECORDS.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        thorctl.STATE_DIR = self.old_state_dir
        thorctl.RECORDS = self.old_records
        self.temp.cleanup()

    def test_apply_without_plan_returns_error(self):
        args = MagicMock()
        args.dry_run = False
        rc = thorctl.cmd_deployment_apply(args)
        self.assertEqual(2, rc)

    def test_apply_without_approval_returns_error(self):
        # Write a plan but no approval
        plan = {"schema_version": 1, "library_digest": "x",
                "profile": "ayn-thor", "profile_version": "1.1.0",
                "adapters": [], "app_locks": {}, "device_serial": "s",
                "storage_binding": {}, "intents": [], "plan_digest": "d",
                "created_at": "now", "authorization": "non_authorizing"}
        thorctl.write_record("deployment-plan", plan,
                             schemas.validate_deployment_plan)
        args = MagicMock()
        args.dry_run = False
        rc = thorctl.cmd_deployment_apply(args)
        self.assertEqual(2, rc)


class FrontendCommitTests(unittest.TestCase):
    """frontend.commit must refuse without accepted platforms."""

    def setUp(self):
        self.old_records = thorctl.RECORDS
        self.temp = tempfile.TemporaryDirectory()
        thorctl.RECORDS = Path(self.temp.name)
        thorctl.RECORDS.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        thorctl.RECORDS = self.old_records
        self.temp.cleanup()

    def test_commit_without_acceptance_refused(self):
        args = MagicMock()
        args.action = "commit"
        rc = thorctl.cmd_frontend(args)
        self.assertEqual(2, rc)


class StateManagementTests(unittest.TestCase):
    """State transitions through thorctl."""

    def setUp(self):
        self.old_state_dir = thorctl.STATE_DIR
        self.temp = tempfile.TemporaryDirectory()
        thorctl.STATE_DIR = Path(self.temp.name)

    def tearDown(self):
        thorctl.STATE_DIR = self.old_state_dir
        self.temp.cleanup()

    def test_reset_goes_to_draft(self):
        thorctl.reset_state()
        self.assertEqual("DRAFT", thorctl.current_state())

    def test_invalid_transition_rejected(self):
        from lib_thor import save_state
        state = {}
        state["thorctl_state"] = "DRAFT"
        save_state(state)
        # DRAFT -> APPROVED is not valid
        with self.assertRaises(ValueError):
            thorctl.set_state("APPROVED")


class DriverAttestationTests(unittest.TestCase):
    """DriverAttestation: manual GPU driver evidence, never auto-install."""

    def _valid(self):
        return {
            "schema_version": 1,
            "emulator": "eden",
            "driver_name": "Mr. Purple T23",
            "driver_version": "v34",
            "source": "manual: installed via Eden GPU driver manager on device",
            "device_fingerprint": "ayn/thor/thor:14/UP1A/x",
            "attested_at": "2026-08-28T00:00:00Z",
        }

    def test_valid_attestation_passes(self):
        schemas.validate_driver_attestation(self._valid())

    def test_missing_fields_rejected(self):
        rec = self._valid()
        del rec["driver_version"]
        with self.assertRaises(ValueError):
            schemas.validate_driver_attestation(rec)

    def test_auto_source_rejected(self):
        rec = self._valid()
        rec["source"] = "auto"
        with self.assertRaises(ValueError):
            schemas.validate_driver_attestation(rec)

    def test_secrets_rejected(self):
        rec = self._valid()
        rec["driver_name"] = "driver with password=abc"
        with self.assertRaises(ValueError):
            schemas.validate_driver_attestation(rec)

    def test_acceptance_requires_gpu_driver_fields(self):
        rec = {
            "schema_version": 1, "game": "Smash", "platform": "switch",
            "app_version": "0.2.1", "renderer": "vulkan",
            "user_confirmations": [], "accepted": True,
            "tested_at": "now",
        }
        with self.assertRaises(ValueError):  # missing gpu_driver fields
            schemas.validate_acceptance_report(rec)
        rec.update({"gpu_driver": "Mr. Purple T23", "gpu_driver_version": "v34"})
        schemas.validate_acceptance_report(rec)


if __name__ == "__main__":
    unittest.main()

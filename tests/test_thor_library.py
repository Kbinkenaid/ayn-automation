import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import thor_library as library


class ThorLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "ssd" / "ROMs"
        self.target = self.root / "stage" / "ROMs"
        self.output = self.root / "output"
        (self.source / "switch").mkdir(parents=True)
        (self.source / "BIOS").mkdir()
        (self.source / "_extras").mkdir()
        (self.source / "__MACOSX").mkdir()
        (self.source / "switch" / "Game.nsp").write_bytes(b"canonical game")
        (self.source / "switch" / "systeminfo.txt").write_text("not a game")
        (self.source / "BIOS" / "prod.keys").write_text("secret")
        (self.source / "_extras" / "asset.zip").write_bytes(b"not copied")
        (self.source / "__MACOSX" / "asset.nsp").write_bytes(b"not copied")

    def tearDown(self):
        self.temp.cleanup()

    def test_scan_excludes_support_assets_and_writes_human_listing(self):
        manifest = library.scan(self.source)
        self.assertEqual(1, manifest["file_count"])
        self.assertEqual("switch/Game.nsp", manifest["files"][0]["path"])
        self.assertIn("Total storage size", library.render_listing(manifest))

    def test_md_root_and_nested_files_are_ignored_but_platform_zip_is_retained(self):
        (self.source / "genesis").mkdir()
        (self.source / "genesis" / "Readme.MD").write_text("ignore me")
        (self.source / "switch" / "nested").mkdir()
        (self.source / "switch" / "nested" / "asset.nsp").write_bytes(b"nested")
        (self.source / "switch" / "portable-game.zip").write_bytes(b"rom archive")
        (self.source / "root-game.nsp").write_bytes(b"unclassified")
        manifest = library.scan(self.source)
        self.assertEqual({"switch/Game.nsp", "switch/portable-game.zip"}, {f["path"] for f in manifest["files"]})

    def test_default_sync_is_dry_run_and_apply_is_idempotent(self):
        rc = library.main(["sync", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(0, rc)
        self.assertFalse((self.target / "switch" / "Game.nsp").exists())
        report = json.loads((self.output / "sync-report.json").read_text())
        self.assertEqual("dry_run", report["mode"])
        self.assertEqual("copy", report["plan"][0]["action"])

        rc = library.main(["sync", "--apply", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(0, rc)
        self.assertEqual(b"canonical game", (self.target / "switch" / "Game.nsp").read_bytes())
        plan = library.build_plan(library.scan(self.source), self.target)
        self.assertEqual("skip", plan[0]["action"])

    def test_different_target_is_atomically_replaced_without_deleting_extras(self):
        destination = self.target / "switch" / "Game.nsp"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"outdated")
        extra = self.target / "switch" / "keep-me.txt"
        extra.write_text("unmanaged")
        rc = library.main(["sync", "--apply", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(0, rc)
        self.assertEqual(b"canonical game", destination.read_bytes())
        self.assertTrue(extra.exists())

    def test_partial_copy_resumes_and_verify_reports_missing_files(self):
        destination = self.target / "switch" / "Game.nsp"
        destination.parent.mkdir(parents=True)
        partial, state = library.partial_paths(destination)
        partial.write_bytes(b"canonical")
        state.write_text(json.dumps({"sha256": library.sha256_file(self.source / "switch" / "Game.nsp"),
                                     "size_bytes": len(b"canonical game")}))
        rc = library.main(["sync", "--apply", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(0, rc)
        self.assertEqual(b"canonical game", destination.read_bytes())
        destination.unlink()
        rc = library.main(["verify", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(1, rc)
        report = json.loads((self.output / "verify-report.json").read_text())
        self.assertEqual("copy", report["plan"][0]["action"])

    def test_verify_fails_when_staging_differs(self):
        rc = library.main(["verify", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(1, rc)

    def test_verify_fails_for_replace_and_conflict_actions(self):
        destination = self.target / "switch" / "Game.nsp"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"old")
        rc = library.main(["verify", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(1, rc)
        destination.unlink()
        destination.mkdir()
        rc = library.main(["verify", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(1, rc)
        report = json.loads((self.output / "verify-report.json").read_text())
        self.assertEqual("conflict", report["plan"][0]["action"])

    def test_target_and_partial_symlinks_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        link_parent = self.root / "linked-stage"
        link_parent.symlink_to(outside, target_is_directory=True)
        rc = library.main(["sync", "--apply", "--source", str(self.source), "--target", str(link_parent / "ROMs"), "--output", str(self.output)])
        self.assertEqual(2, rc)

        destination = self.target / "switch" / "Game.nsp"
        destination.parent.mkdir(parents=True)
        partial, _ = library.partial_paths(destination)
        partial.symlink_to(outside / "payload")
        manifest = library.scan(self.source)
        plan = library.build_plan(manifest, self.target)
        _, errors = library.apply_plan(self.source, self.target, plan)
        self.assertIn("unsafe symlink in partial-copy path", errors[0]["error"])

    def test_target_lock_reports_clear_concurrent_operation_error(self):
        with library.TargetLock(self.output, self.target):
            rc = library.main(["sync", "--source", str(self.source), "--target", str(self.target), "--output", str(self.output)])
        self.assertEqual(2, rc)

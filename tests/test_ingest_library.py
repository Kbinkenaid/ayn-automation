import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ingest_library as ingest
from platform_classifier import classify, load_map


class ClassificationTests(unittest.TestCase):
    def setUp(self): self.mapping = load_map()

    def test_ambiguous_iso_is_held_for_review(self):
        result = classify(Path("Mystery.iso"), platform_map=self.mapping)
        self.assertIsNone(result.platform)
        self.assertEqual("needs_review", result.confidence)
        self.assertIn("ps2", result.candidates)

    def test_platform_folder_or_explicit_decision_resolves_iso(self):
        contextual = classify(Path("ps2/Game.iso"), platform_map=self.mapping)
        explicit = classify(Path("Mystery.iso"), decisions={"Mystery.iso": "gc"}, platform_map=self.mapping)
        self.assertEqual(("ps2", "contextual"), (contextual.platform, contextual.confidence))
        self.assertEqual(("gc", "explicit"), (explicit.platform, explicit.confidence))

    def test_switch_and_wii_formats_are_unambiguous(self):
        expected = {"Game.nsp": "switch", "Cart.xci": "switch", "Wii.wbfs": "wii", "WiiU.wua": "wiiu"}
        self.assertEqual(expected, {name: classify(Path(name), platform_map=self.mapping).platform for name in expected})
        self.assertEqual("needs_review", classify(Path("Disc.rvz"), platform_map=self.mapping).confidence)
        self.assertEqual("gc", classify(Path("gc/Disc.rvz"), platform_map=self.mapping).platform)

    def test_text_and_markdown_are_ignored(self):
        self.assertEqual("ignored", classify(Path("notes.MD"), platform_map=self.mapping).confidence)
        self.assertEqual("ignored", classify(Path("system.txt"), platform_map=self.mapping).confidence)

    def test_metadata_cannot_be_overridden(self):
        result = classify(Path("notes.md"), decisions={"notes.md": "switch"}, platform_map=self.mapping)
        self.assertEqual((None, "ignored"), (result.platform, result.confidence))

    def test_noncanonical_explicit_platform_is_not_accepted(self):
        result = classify(Path("Game.iso"), decisions={"Game.iso": "../../escape"}, platform_map=self.mapping)
        self.assertEqual((None, "needs_review"), (result.platform, result.confidence))


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.target = self.root / "target"

    def tearDown(self): self.temp.cleanup()

    def test_dry_run_then_apply_requires_explicit_platform_for_iso(self):
        source = self.root / "Game.iso"; source.write_bytes(b"owned game")
        manifest = self.root / "report.json"
        self.assertEqual(1, ingest.main([str(source), "--target", str(self.target), "--manifest", str(manifest)]))
        data = json.loads(manifest.read_text()); self.assertEqual("needs_review", data["records"][0]["status"])
        decisions = self.root / "decisions.json"; decisions.write_text(json.dumps({"schema_version": 1, "decisions": {"Game.iso": "ps2"}}))
        self.assertEqual(0, ingest.main([str(source), "--target", str(self.target), "--decisions", str(decisions), "--apply"]))
        self.assertEqual(b"owned game", (self.target / "ROMs" / "ps2" / "Game.iso").read_bytes())

    def test_directory_is_not_copied_but_its_game_files_are_and_metadata_is_ignored(self):
        source = self.root / "input"; nested = source / "nested"; nested.mkdir(parents=True)
        (source / "Game.nsp").write_bytes(b"switch"); (source / "notes.md").write_text("ignored"); (nested / "Hidden.nsp").write_bytes(b"no")
        self.assertEqual(0, ingest.main([str(source), "--target", str(self.target), "--apply"]))
        self.assertTrue((self.target / "ROMs" / "switch" / "Game.nsp").exists())
        self.assertTrue((self.target / "ROMs" / "switch" / "Hidden.nsp").exists())

    def test_unsafe_archive_is_rejected_before_extraction(self):
        archive = self.root / "bad.zip"; archive.write_bytes(b"not inspected")
        members = [{"path": "../escape.nsp", "size": 1, "folder": False, "attributes": ""}]
        with patch.object(ingest, "list_archive", return_value=members), patch.object(ingest, "extract_member") as extraction:
            records = ingest.archive_records(archive, self.target, {}, load_map(), apply=True)
        self.assertEqual("rejected_unsafe_archive", records[0]["status"])
        extraction.assert_not_called()

    def test_nested_archive_game_needs_review_not_basename_extraction(self):
        archive = self.root / "nested.zip"; archive.write_bytes(b"not inspected")
        members = [{"path": "folder/Game.nsp", "size": 1, "folder": False, "attributes": ""}]
        with patch.object(ingest, "list_archive", return_value=members), patch.object(ingest, "extract_member") as extraction:
            records = ingest.archive_records(archive, self.target, {}, load_map(), apply=True)
        self.assertEqual("needs_review", records[0]["status"])
        extraction.assert_not_called()

    def test_multiple_playable_archive_members_are_never_auto_extracted(self):
        archive = self.root / "two.zip"; archive.write_bytes(b"not inspected")
        members = [{"path": "One.nsp", "size": 1, "folder": False, "attributes": ""}, {"path": "Two.nsp", "size": 1, "folder": False, "attributes": ""}]
        with patch.object(ingest, "list_archive", return_value=members), patch.object(ingest, "extract_member") as extraction:
            records = ingest.archive_records(archive, self.target, {}, load_map(), apply=True)
        self.assertEqual("needs_review", records[0]["status"])
        extraction.assert_not_called()

    def test_nested_playable_member_counts_toward_archive_review(self):
        archive = self.root / "two.zip"; archive.write_bytes(b"not inspected")
        members = [{"path": "Top.nsp", "size": 1, "folder": False, "attributes": ""}, {"path": "nested/Other.nsp", "size": 1, "folder": False, "attributes": ""}]
        with patch.object(ingest, "list_archive", return_value=members), patch.object(ingest, "extract_member") as extraction:
            records = ingest.archive_records(archive, self.target, {}, load_map(), apply=True)
        self.assertEqual("needs_review", records[0]["status"]); extraction.assert_not_called()

    def test_exact_archive_member_selection_allows_only_selected_member(self):
        archive = self.root / "two.zip"; archive.write_bytes(b"not inspected")
        members = [{"path": "One.iso", "size": 1, "folder": False, "attributes": ""}, {"path": "Two.iso", "size": 1, "folder": False, "attributes": ""}]
        selected = {"__archive_members__": {"two.zip": {"member": "Two.iso", "platform": "ps2"}}}
        extracted = self.root / "Two.iso"; extracted.write_bytes(b"x")
        with patch.object(ingest, "list_archive", return_value=members), patch.object(ingest, "extract_member", return_value=extracted) as extraction:
            records = ingest.archive_records(archive, self.target, selected, load_map(), apply=False)
        self.assertEqual("planned", records[0]["status"]); extraction.assert_called_once_with(archive, "Two.iso", ANY)

    def test_different_existing_destination_requires_replace(self):
        source = self.root / "Game.nsp"; source.write_bytes(b"new")
        destination = self.target / "ROMs" / "switch" / "Game.nsp"; destination.parent.mkdir(parents=True); destination.write_bytes(b"old")
        record = ingest.copy_if_approved(source, self.target, classify(source, platform_map=load_map()), apply=True)
        self.assertEqual("conflict", record["status"]); self.assertEqual(b"old", destination.read_bytes())
        record = ingest.copy_if_approved(source, self.target, classify(source, platform_map=load_map()), apply=True, replace=True)
        self.assertEqual("replaced", record["status"]); self.assertEqual(b"new", destination.read_bytes())

    def test_dangerous_loose_file_is_rejected_even_with_decision(self):
        source = self.root / "payload.exe"; source.write_bytes(b"no")
        record = ingest.copy_if_approved(source, self.target, classify(source, decisions={"payload.exe": "ps2"}, platform_map=load_map()), apply=True)
        self.assertEqual("rejected_dangerous_or_archive", record["status"])

    def test_symlinked_rom_root_is_rejected(self):
        source = self.root / "Game.nsp"; source.write_bytes(b"new")
        outside = self.root / "outside"; outside.mkdir(); self.target.mkdir(); (self.target / "ROMs").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "must not be a symlink"):
            ingest.destination(self.target, source, classify(source, platform_map=load_map()))

    def test_symlinked_platform_directory_is_rejected(self):
        source = self.root / "Game.nsp"; source.write_bytes(b"new")
        bios = self.target / "BIOS"; bios.mkdir(parents=True)
        (self.target / "ROMs").mkdir()
        (self.target / "ROMs" / "switch").symlink_to("../BIOS", target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "platform directory"):
            ingest.destination(self.target, source, classify(source, platform_map=load_map()))

import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import emulator_profiles as profiles

class EmulatorProfileTests(unittest.TestCase):
    def test_shipped_profile_validates(self):
        p = profiles.load_profile()
        self.assertIn("eden", p["emulators"])
        self.assertIn("azahar", p["emulators"])
        self.assertIn("retroarch", p["emulators"])
    def test_no_serial_never_authorizes_deploy(self):
        report = profiles.plan(profiles.load_profile())
        self.assertFalse(report["plan_ready"])
        self.assertEqual("non_authorizing", report["authorization"])
    def test_required_capability_is_enforced(self):
        report = profiles.plan(profiles.load_profile(), "thor-1", {"sd_writable": {"ok": False}})
        self.assertFalse(report["plan_ready"])
        self.assertEqual(["sd_writable"], report["missing_capabilities"])
    def test_invalid_path_rejected(self):
        data = profiles.load_profile(); data["emulators"]["eden"]["rom_paths"] = ["/tmp/switch"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.json"; path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): profiles.load_profile(path)

    def test_forged_capabilities_never_authorize_a_deploy(self):
        report = profiles.plan(profiles.load_profile(), "thor-1", {"sd_writable": {"ok": True}}, "/storage/ABCD/ROMs")
        self.assertTrue(report["plan_ready"])
        self.assertEqual("non_authorizing", report["authorization"])
        self.assertIn("this plan never authorizes deployment", report["guardrails"])

    def test_normalized_paths_cannot_escape_selected_root(self):
        self.assertEqual("/storage/card/ROMs/psx", profiles.resolve_under_root("/storage/card/ROMs", "${ROM_ROOT}/psx"))
        with self.assertRaises(ValueError): profiles.resolve_under_root("/storage/card/ROMs", "${ROM_ROOT}/../../escape")

    def test_transcript_specific_settings_are_present(self):
        emu = profiles.load_profile()["emulators"]
        self.assertTrue(emu["azahar"]["recommended"]["disable_right_eye_render"])
        self.assertEqual("none", emu["melonds"]["recommended"]["exit_hotkey"])
        self.assertEqual("before_start", emu["dolphin"]["recommended"]["shader_compilation"])
        self.assertFalse(emu["cemu"]["recommended"]["controller_overlay"])
        self.assertEqual("CRT-Lottes", emu["duckstation"]["recommended"]["shader"])
        self.assertFalse(emu["nethersx2"]["recommended"]["on_screen_controls"])
        self.assertFalse(emu["ppsspp"]["recommended"]["on_screen_controls"])

    def test_profile_rejects_wrong_schema_type(self):
        data = profiles.load_profile(); data["schema_version"] = "1"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.json"; path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): profiles.load_profile(path)

    def test_profile_rejects_template_traversal_at_load(self):
        data = profiles.load_profile(); data["emulators"]["eden"]["rom_paths"] = ["${ROM_ROOT}/../switch"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.json"; path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): profiles.load_profile(path)

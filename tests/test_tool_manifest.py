"""The manifest and update feed must be what S2P's update check expects."""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import _paths

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tool_manifest", REPO / "scripts" / "tool_manifest.py")
tool_manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool_manifest)

TOOLS = {"S2P-Joystick-Macro": REPO / "macro" / "s2p_macro" / "__init__.py"}


class ToolManifestTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def test_manifest_carries_the_tool_version(self):
        sys.path.insert(0, str(REPO / "macro"))
        self.addCleanup(sys.path.remove, str(REPO / "macro"))
        from s2p_macro import __version__

        path = tool_manifest.write_manifest(
            "S2P-Joystick-Macro", TOOLS["S2P-Joystick-Macro"], self.folder)
        self.assertEqual(path.name, "S2P-Joystick-Macro.s2p.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], __version__)
        self.assertEqual(data["format"], "s2p-extension")
        self.assertTrue(data["update_url"].startswith("https://github.com/duoduo-88/S2P-Extensions/"))
        self.assertTrue(data["update_url"].endswith("/releases/latest/download/s2p-extensions-updates.json"))

    def test_feed_lists_every_tool_with_the_release_page(self):
        manifests = [tool_manifest.write_manifest(name, version_file, self.folder)
                     for name, version_file in TOOLS.items()]
        feed = tool_manifest.feed("0.2.0", manifests)
        self.assertEqual(feed["format"], "s2p-extension-updates")
        self.assertEqual(set(feed["tools"]), set(TOOLS))
        for entry in feed["tools"].values():
            self.assertEqual(entry["url"], "https://github.com/duoduo-88/S2P-Extensions/releases/tag/v0.2.0")

    @unittest.skipIf(_paths.s2p_source() is None, "S2P-XInput-Lite source not found")
    def test_s2p_reads_the_manifest_and_feed(self):
        source = str(_paths.s2p_source())
        if source not in sys.path:
            sys.path.insert(0, source)
        import extension_updates

        exe = self.folder / "S2P-Joystick-Macro.exe"
        exe.write_bytes(b"MZ")
        manifest = tool_manifest.write_manifest("S2P-Joystick-Macro", TOOLS["S2P-Joystick-Macro"], self.folder)
        current = extension_updates.read_tool_manifest(exe)
        newer = json.loads(manifest.read_text(encoding="utf-8"))
        newer["version"] = "99.0.0"
        newer_path = self.folder / "newer.s2p.json"
        newer_path.write_text(json.dumps(newer), encoding="utf-8")
        body = json.dumps(tool_manifest.feed("99.0.0", [newer_path])).encode("utf-8")

        def opener(request, timeout):
            self.assertEqual(request.full_url, tool_manifest.UPDATE_URL)
            return io.BytesIO(body)

        result = extension_updates.check_tool_updates(
            {"m": str(exe)}, user_agent="test", opener=opener)["m"]
        self.assertEqual((result.state, result.current, result.latest),
                         (extension_updates.UPDATE_AVAILABLE, current.version, "99.0.0"))
        self.assertTrue(result.url.endswith("/releases/tag/v99.0.0"))


if __name__ == "__main__":
    unittest.main()

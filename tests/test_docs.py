"""Relative links and images in the documentation must point at real files."""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
SKIP_DIRS = {".git", "build", "dist", ".ruff_cache"}


def markdown_files():
    for path in REPO.rglob("*.md"):
        if not SKIP_DIRS.intersection(path.relative_to(REPO).parts):
            yield path


def heading_anchor(heading):
    """GitHub's anchor for a heading: lower case, punctuation dropped."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


class DocumentationLinkTests(unittest.TestCase):
    def test_relative_links_and_anchors_resolve(self):
        broken = []
        for doc in markdown_files():
            relative = doc.relative_to(REPO)
            if relative.parts[0] == "release":
                continue  # written for the zip layout; checked below
            for target in LINK.findall(doc.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path_part, _, anchor = target.partition("#")
                file = (doc.parent / path_part).resolve() if path_part else doc
                if not file.exists():
                    broken.append(f"{relative}: {target}")
                    continue
                if anchor and file.suffix == ".md":
                    headings = re.findall(r"^#+ (.+)$", file.read_text(encoding="utf-8"), re.M)
                    if anchor not in {heading_anchor(h) for h in headings}:
                        broken.append(f"{relative}: {target} (no such heading)")
        self.assertEqual(broken, [])

    def test_readmes_in_the_zip_only_link_to_shipped_files_or_online(self):
        # The zip holds S2P-Extensions/README*.md and S2P-Joystick-Macro/ with
        # its EXE and READMEs; the user guides stay online.
        zip_files = {
            "README.md", "README_zh-TW.md",
            "S2P-Joystick-Macro/README.md", "S2P-Joystick-Macro/README_zh-TW.md",
        }
        shipped = {
            "release/README.md": "", "release/README_zh-TW.md": "",
            "macro/README.md": "S2P-Joystick-Macro/",
            "macro/README_zh-TW.md": "S2P-Joystick-Macro/",
        }
        online = "https://github.com/duoduo-88/S2P-Extensions/blob/main/"
        broken = []
        for source, folder in shipped.items():
            for target in LINK.findall((REPO / source).read_text(encoding="utf-8")):
                if target.startswith(online):
                    path = target[len(online):].partition("#")[0]
                    if not (REPO / path).is_file():
                        broken.append(f"{source}: {target} (not in the repo)")
                    continue
                if target.startswith(("http://", "https://")):
                    continue
                inside = Path(folder + target.partition("#")[0]).as_posix()
                parts = []
                for part in inside.split("/"):
                    if part == "..":
                        parts = parts[:-1]
                    elif part not in ("", "."):
                        parts.append(part)
                if "/".join(parts) not in zip_files:
                    broken.append(f"{source}: {target} (not in the zip)")
        self.assertEqual(broken, [])

    def test_every_tool_has_a_guide_in_both_languages(self):
        for guide in ("USER_GUIDE.md", "USER_GUIDE_zh-TW.md"):
            self.assertTrue((REPO / "manual" / guide).is_file(), guide)
            self.assertTrue((REPO / "macro" / "manual" / guide).is_file(), guide)


if __name__ == "__main__":
    unittest.main()

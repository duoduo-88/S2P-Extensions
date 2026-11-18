"""Write the files S2P-XInput-Lite reads to check tools for updates.

    python scripts/tool_manifest.py manifest <tool name> <version file> <output folder>
    python scripts/tool_manifest.py feed <release version> <output file> <manifest>...

``manifest`` writes ``<tool name>.s2p.json`` next to the tool's EXE.  ``feed``
writes the update feed attached to every GitHub release; the manifests point
at it through GitHub's "latest release" download link.  Format: S2P-XInput-Lite
``docs/extensions-ipc.md``, "Tool manifest and updates".
"""

import json
import re
import sys
from pathlib import Path

REPOSITORY = "https://github.com/duoduo-88/S2P-Extensions"
FEED_NAME = "s2p-extensions-updates.json"
UPDATE_URL = f"{REPOSITORY}/releases/latest/download/{FEED_NAME}"
MANIFEST_SUFFIX = ".s2p.json"
VERSION = re.compile(r'^__version__\s*=\s*"(\d+\.\d+\.\d+)"', re.M)


def read_version(version_file):
    match = VERSION.search(Path(version_file).read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"No __version__ in {version_file}")
    return match.group(1)


def manifest(name, version):
    return {
        "format": "s2p-extension",
        "name": name,
        "version": version,
        "update_url": UPDATE_URL,
        "homepage": REPOSITORY,
    }


def write_manifest(name, version_file, folder):
    path = Path(folder) / f"{name}{MANIFEST_SUFFIX}"
    data = manifest(name, read_version(version_file))
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def feed(release_version, manifests):
    page = f"{REPOSITORY}/releases/tag/v{release_version}"
    tools = {}
    for path in manifests:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        tools[data["name"]] = {"version": data["version"], "url": page}
    return {"format": "s2p-extension-updates", "release": release_version, "tools": tools}


def main(argv):
    if len(argv) == 4 and argv[0] == "manifest":
        print(write_manifest(*argv[1:]))
    elif len(argv) >= 4 and argv[0] == "feed":
        output = Path(argv[2])
        output.write_text(json.dumps(feed(argv[1], argv[3:]), indent=2) + "\n", encoding="utf-8")
        print(output)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

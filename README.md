# S2P-Extensions

[繁體中文](README_zh-TW.md) · [User Guide](manual/USER_GUIDE.md) · [S2P-Joystick-Macro](macro/README.md) · [Developing tools](docs/development.md) · [S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite)

Optional extension tools for [S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite).
Each tool is an independent program that submits input or reads controller
state through S2P's Extensions interface (a Windows named pipe, protocol v1).
S2P stays the only virtual XInput controller, and it works normally without
any of these tools.

| Folder | Contents | Status |
|---|---|---|
| `sdk/` | Shared IPC client (`s2p_ext`), standard library only | Available |
| `macro/` | S2P-Joystick-Macro: record, play back and edit controller button and stick input | Available (v0.1.0) |
| `manual/` | Shared user guide; each tool's own guide is in its folder (`macro/manual/`) | Available |
| `docs/` | Developer documentation | Available |
| `release/`, `scripts/` | Release zip READMEs, the packaging script and the playback timing measurement | Available |
| `tests/` | Unit tests and integration tests against S2P | Available |

A multi-device input tool and further examples are not implemented yet; their
folders will be added when work on them starts.

## Responsibility

These extension tools are provided by this project and released separately
from the S2P-XInput-Lite main program. You are responsible for how you use
them and for the results. Some games and online services prohibit external
input or automation; check their rules before use. This project provides no
feature to bypass any anti-cheat system.

## Release package

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_release.ps1
```

This runs the tests, builds every tool, and writes
`dist\S2P-Extensions-<VERSION>.zip`. The zip holds one `S2P-Extensions\`
folder with the user READMEs from `release/` and a subfolder per tool
(`S2P-Extensions\S2P-Joystick-Macro\S2P-Joystick-Macro.exe` and its READMEs).
The release version is in `VERSION`.

## Tests

```powershell
python -m unittest discover -s tests
```

`tests/test_s2p_integration.py` connects to S2P-XInput-Lite's real pipe
server. It needs the S2P-XInput-Lite source next to this folder
(`..\S2P-XInput-Lite\src`) or the `S2P_XINPUT_LITE_SRC` environment variable;
otherwise it is skipped.

`scripts/measure_playback_timing.py` measures macro playback timing through
S2P's merge path (opt-in, about 16 minutes); results are in
[docs/playback-timing.md](docs/playback-timing.md).

## Developing a new tool

See [docs/development.md](docs/development.md).

## License

S2P-Extensions is licensed under the [GNU General Public License v3.0](LICENSE),
the same license as S2P-XInput-Lite. You may use, modify and redistribute it
under those terms; a modified version you distribute must also be released
under GPL-3.0 with its source code.

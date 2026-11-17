# S2P-Extensions

[繁體中文](README_zh-TW.md) · [S2P-Joystick-Macro](macro/README.md) · [Developing tools](docs/development.md) · [S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite)

Optional extension tools for [S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite).
Each tool is an independent program that submits input or reads controller
state through S2P's Extensions interface (a Windows named pipe, protocol v1).
S2P stays the only virtual XInput controller, and it works normally without
any of these tools.

| Folder | Contents | Status |
|---|---|---|
| `sdk/` | Shared IPC client (`s2p_ext`), standard library only | Available |
| `macro/` | S2P-Joystick-Macro: record, play back and edit controller button and stick input | Available (v0.1.0) |
| `docs/` | Developer documentation | Available |
| `tests/` | Unit tests and integration tests against S2P | Available |

A multi-device input tool and further examples are not implemented yet; their
folders will be added when work on them starts.

## Responsibility

These extension tools are provided by this project and released separately
from the S2P-XInput-Lite main program. You are responsible for how you use
them and for the results. Some games and online services prohibit external
input or automation; check their rules before use. This project provides no
feature to bypass any anti-cheat system.

## Tests

```powershell
python -m unittest discover -s tests
```

`tests/test_s2p_integration.py` connects to S2P-XInput-Lite's real pipe
server. It needs the S2P-XInput-Lite source next to this folder
(`..\S2P-XInput-Lite\src`) or the `S2P_XINPUT_LITE_SRC` environment variable;
otherwise it is skipped.

## Developing a new tool

See [docs/development.md](docs/development.md).

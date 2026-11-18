# S2P-Extensions

[繁體中文](README_zh-TW.md) · [S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite) · [Source](https://github.com/duoduo-88/S2P-Extensions)

Optional extension tools for [S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite).
Each folder holds one independent tool that submits input or reads controller
state through S2P's Extensions interface. S2P stays the only virtual XInput
controller, and it works normally without any of these tools.

## User guides

The user guides are online:

- [S2P-Extensions User Guide](https://github.com/duoduo-88/S2P-Extensions/blob/main/manual/USER_GUIDE.md): installing,
  connecting tools in S2P, permissions and troubleshooting.
- Each tool has its own guide:

| Folder | Tool | Guide |
|---|---|---|
| `S2P-Joystick-Macro\` | Record, play back and edit controller button and stick input | [User Guide](https://github.com/duoduo-88/S2P-Extensions/blob/main/macro/manual/USER_GUIDE.md) |

## How to use

1. Put the whole `S2P-Extensions` folder anywhere. Each tool keeps its
   settings in its own folder.
2. In S2P-XInput-Lite, open **Extensions**, check **Enable Extensions**, select
   **Add Tool...**, and choose the tool's EXE. Up to 4 tools can be enabled at
   the same time.
3. Grant the permissions the tool needs under **Permissions**, then choose
   **Open**.
4. Enabled tools start in the background when the S2P connection starts, and
   they close together with S2P.
5. Keep each tool's `.s2p.json` file next to its EXE. S2P's **Check for
   Updates** reads it to find newer versions.

## Responsibility

These extension tools are provided by this project and released separately
from the S2P-XInput-Lite main program. You are responsible for how you use
them and for the results. Some games and online services prohibit external
input or automation; check their rules before use. This project provides no
feature to bypass any anti-cheat system.

## License

S2P-Extensions is licensed under the [GNU General Public License v3.0](LICENSE),
the same license as S2P-XInput-Lite. You may use, modify and redistribute it
under those terms; a modified version you distribute must also be released
under GPL-3.0 with its source code.

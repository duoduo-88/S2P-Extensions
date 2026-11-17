# Developing extension tools

[繁體中文](development_zh-TW.md) · [S2P-Extensions](../README.md)

The full protocol is described in S2P-XInput-Lite's
[`docs/extensions-ipc.md`](https://github.com/duoduo-88/S2P-XInput-Lite/blob/v0.8.2/docs/extensions-ipc.md)
(protocol v1, Traditional Chinese). This page shows how to build a tool with
`sdk/s2p_ext`.

## Minimal example

```python
import time
from s2p_ext import AutoConnection, ExtensionClient

def factory():
    # Declare only the permissions and sticks you need to avoid conflicts.
    return ExtensionClient("My Tool", "0.1.0", capabilities=("input",), sticks=())

connection = AutoConnection(factory, on_change=lambda state, detail: print(state, detail))
connection.start()
while connection.client is None:
    time.sleep(0.2)

client = connection.client
client.send_state(["A"])      # hold A; resend every 250 ms while holding it for over 1 s (heartbeat)
time.sleep(0.1)
client.send_state([])         # release
connection.stop()             # sends bye; S2P clears this tool's input
```

## Rules at a glance

| Topic | Rule |
|---|---|
| Identification | The user must add the tool's EXE to S2P's Extensions list. A tool started by S2P is identified by a one-time token in an environment variable. |
| Permissions | `input` submits input (allowed by default in S2P); `read` reads controller state (off by default in S2P). |
| Sticks | Declare the sticks you need exclusively in hello's `sticks`. If another tool already claims one, the connection is refused (`conflict`). |
| Heartbeat | While holding input, send a message at least every 1000 ms, or S2P clears the input (the connection stays). |
| Merging | Buttons are ORed, triggers take the larger value, and the physical stick has priority. |
| Reading | `get_input` returns S2P's output from before extension input is merged, so a tool never reads back its own input. |
| Errors | S2P closes the connection after replying with `error`; `AutoConnection` retries automatically. |
| Background start | When S2P starts an enabled tool by itself, it sets `S2P_EXTENSION_BACKGROUND=1`; the tool should not show a window. |
| Single instance | **Open** starts the tool again; the tool should bring back its existing window instead of starting a second copy. |

## Releasing

- Develop in Python and package a single EXE with PyInstaller (example:
  `macro/build.ps1`).
- On first launch, explain clearly what the tool does, who is responsible for
  its use, and that games may have rules against it.
- Do not create a virtual controller, do not use DLL injection or hooks, and
  add no anti-cheat bypass of any kind.

## Testing tips

- Unit-test with fake `send` / `get_input` functions in place of S2P (see
  `tests/test_engine.py`).
- Integration-test against S2P's `ExtensionManager` and a real pipe (see
  `tests/test_s2p_integration.py`).
- On real hardware, use S2P's built-in **Gamepad Test** to watch the merged
  XInput output.

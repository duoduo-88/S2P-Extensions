# S2P-Joystick-Macro

[繁體中文](README_zh-TW.md) · [S2P-Extensions](../README.md)

An independent extension tool for S2P-XInput-Lite that records controller
button and stick input and plays it back later. It submits input through
S2P's Extensions interface; it does not create a virtual controller of its
own and does not modify S2P.

## Notice

- You are responsible for how you use this tool and for the results.
- Some games and online services prohibit macros, automation or external
  input. Check their rules before use; using it where it is not allowed may
  get your account restricted.
- This tool contains no feature to bypass any anti-cheat system.
- The first launch shows this notice; choose **I understand** to start.

## Install and connect

1. Put `S2P-Joystick-Macro.exe` in any folder. Macros and settings are kept
   next to it in `macros\` and `settings.json`.
2. In S2P-XInput-Lite, open **Extensions**, check **Enable Extensions**, select
   **Add Tool...**, and choose `S2P-Joystick-Macro.exe`.
3. To record, select it in the list and check **Allow reading controller
   state** under **Permissions** (off by default). The tool reconnects by
   itself after a permission change.
4. Open the tool: run the EXE, or choose **Open** in S2P's Extensions list or
   notification area menu. When **Status** shows **Connected to S2P**, it is
   ready. While S2P is not running, the tool waits and retries.

## Running in the background

- The X button does not quit: the window goes to the notification area, the
  tool stays connected to S2P, and controller triggers keep working.
- Click the notification area icon or choose **Show** to bring the window
  back; right-click it and choose **Quit** to close the tool and disconnect.
- Only one copy runs at a time. While it runs in the background, launching the
  EXE again or choosing **Open** in S2P brings back the existing window.
- Once the tool is enabled in S2P, S2P starts it in the background whenever
  the connection starts (straight to the notification area, no window). The
  notice is still shown on first use.
- Closing S2P-XInput-Lite closes the tool too: playback stops and all of its
  input is released. Restarting only the S2P connection keeps it running.

## Window

- **Left**: the macro list, with **New**, **Rename**, **Delete**,
  **Import...** and **Export...** below it.
- **Top right**: the step table. Each row is one button / trigger / stick
  state and how long it is held.
- **Middle right**: recording and playback.
- **Bottom right**: status (connection and current progress) and the 中／En
  language switch.

## Recording

1. Select **Record**. A **● Recording…** entry appears in the list at once,
   and the step table shows what is recorded as it happens. Timing starts at
   the first input, so idle time before it is not recorded.
2. Use the physical controller, then select **Stop** or press Esc.
3. The new macro is named **Rec date time**; you can rename it.

Recording captures S2P's output after curves, gyro and button mapping, and
never includes input sent by extension tools (so it does not record its own
playback). Only buttons and triggers are recorded by default; check **Record
sticks** to record the sticks too.

## Playback

- Select a macro and choose **Play**. Esc or **Stop** ends playback at any
  time and releases every input immediately.
- **Repeat**: 0 repeats until stopped.
- **Speed**: 0.25x to 2x.
- **Loop gap ms**: how long all input is released between repeats, so a
  repeated button counts as a new press in the game.
- **Sticks**: when a macro moves a stick, the tool takes control of that
  stick from S2P only while it plays and gives it back afterwards. If another
  extension tool is using that stick, the stick moves are skipped and the
  status area says so.
- You can still use the physical controller during playback: buttons are
  combined, and a moving physical stick takes priority over the macro.

## Controller trigger

1. Select a macro, choose **Set Trigger...**, and check the controller buttons
   to hold together (for example BACK + R_STK).
2. Check **Controller trigger** (on by default).
3. Hold that combination on the controller to start playback; press it again
   while it plays to stop.

- It needs **Allow reading controller state** in S2P's Extensions list; the
  status area says so when the permission is missing.
- Trigger buttons still reach the game, so choose a combination the game does
  not use, ideally two or more buttons.
- A combination can belong to only one macro. When several match at once,
  the one with the most buttons wins.
- Triggers are not detected while recording.

## Editing

In the step table you can add, edit (double-click), delete, and move steps up
or down. Keep each step at least 16 ms so games always see it. Every change is
saved immediately. Macro files are JSON (`"format": "s2p-macro"`) and can be
shared with **Import...** / **Export...**.

## Run from source

```powershell
cd macro
python -m s2p_macro
```

Only the Python 3.11+ standard library (with Tkinter) is needed. To build the
EXE: `powershell -ExecutionPolicy Bypass -File macro\build.ps1`.

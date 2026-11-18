"""S2P-Joystick-Macro: record and play controller input through S2P-XInput-Lite."""

from __future__ import annotations

import os
import queue
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from s2p_ext import AutoConnection, ExtensionClient

from . import __version__
from .engine import MacroPlayer, MacroRecorder, TriggerMonitor
from .i18n import NOTICE, Translator
from .model import BUTTON_ORDER, Macro, MacroFormatError, MacroLibrary, Step
from .settings import GAME_INPUT_RATES, SPEEDS, AppSettings, data_directory
from .single_instance import SingleInstance
from .tooltip_layout import wrap_tooltip_text
from .tray import SystemTrayIcon

APP_NAME = "S2P-Joystick-Macro"  # product name; never translated
APP_TITLE = f"{APP_NAME} v{__version__}"
ASSETS = Path(__file__).resolve().parent / "assets"
REJECT_REASON = {
    "unauthorized": "未授權（請先把此工具加入 S2P 的擴充工具清單）",
    "conflict": "與其他擴充工具搶同一支搖桿",
    "permission_denied": "S2P 未給予任何權限",
    "user_disconnected": "已在 S2P 中手動中斷",
    "already_connected": "此工具已有另一份在執行",
    "unsupported_protocol": "協定版本不相容",
}
STICK_LABEL = {"left": "左搖桿", "right": "右搖桿"}
COLORS = {"connected": "#138A36", "connecting": "#D97A00", "rejected": "#C62828"}
STICK_CLAIM_TIMEOUT = 3.0
# Steps shorter than the selected game input rate's GAME_INPUT_RATES value may
# be missed by the game; they are shown in this color.
SHORT_STEP_COLOR = "#B45309"
GAME_INPUT_HELP = (
    "遊戲每秒讀取手把幾次，不一定等於畫面 FPS；例如格鬥遊戲常固定每秒 60 次。\n\n"
    "短於下列長度的步驟會以橘色標示：30 Hz 為 66 ms，60 Hz 為 33 ms，144 Hz 以上為 16 ms。\n\n"
    "不確定時選 60 Hz，或用巨集實測：\n"
    "1. 播放 20 次 10 ms 的短按，循環間隔 100 ms 以上，並比該動作的冷卻時間長。\n"
    "2. 數遊戲做出反應的次數，例如角色跳了幾下、開了幾槍。\n"
    "3. 約 6 次有反應是 30 Hz，約 12 次是 60 Hz，20 次都有反應是 144 Hz 以上。"
)
BACKGROUND_ENV = "S2P_EXTENSION_BACKGROUND"  # set by S2P when it starts us itself


def started_in_background():
    """S2P starts enabled tools with the connection; then stay in the tray."""
    return os.environ.get(BACKGROUND_ENV) == "1" or "--background" in sys.argv[1:]


def center_window(window, parent=None):
    """Place a window centered on its parent, or on the screen."""
    window.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    if parent is not None and parent.winfo_viewable():
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    else:
        x = (window.winfo_screenwidth() - width) // 2
        y = (window.winfo_screenheight() - height) // 3
    window.geometry(f"+{max(0, x)}+{max(0, y)}")


def _work_area(widget):
    """Usable area (taskbar excluded) of the monitor showing ``widget``."""
    try:
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MonitorInfo)]
        monitor = user32.MonitorFromWindow(widget.winfo_toplevel().winfo_id(), 2)  # NEAREST
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
            return work.left, work.top, work.right, work.bottom
    except (AttributeError, OSError):
        pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


class HelpTip:
    """S2P's "?" help: a framed "?" whose text shows while it is hovered.

    Same look and placement as S2P-XInput-Lite's ``create_help``/``ToolTip``:
    a 320 px bubble to the lower right of the "?", moved to the other side
    when it would leave the monitor's work area.
    """

    WRAP = 320
    MARGIN = 5

    def __init__(self, parent, text):
        self.text = text
        self.label = tk.Label(parent, text="?", width=2, relief="solid", borderwidth=1,
                              cursor="question_arrow")
        self._window = None
        self.label.bind("<Enter>", lambda _event: self.show(), add="+")
        self.label.bind("<Leave>", lambda _event: self.hide(), add="+")
        self.label.bind("<Destroy>", lambda _event: self.hide(), add="+")

    @property
    def shown(self):
        return self._window is not None

    def show(self):
        if self._window is not None:
            return
        owner = self.label.winfo_toplevel()
        window = tk.Toplevel(owner)
        window.withdraw()
        window.wm_overrideredirect(True)
        window.transient(owner)
        left, top, right, bottom = _work_area(self.label)
        label = tk.Label(window, text="", justify="left", relief="solid", borderwidth=1,
                         padx=8, pady=6, wraplength=0)
        # Wrapped like S2P's help so numbers keep their units and punctuation
        # never starts a line (Tk's own wrapping breaks Chinese text badly).
        measure = tkfont.Font(font=label.cget("font")).measure
        label.configure(text=wrap_tooltip_text(
            self.text, min(self.WRAP, max(160, right - left - 32)), measure))
        label.pack()
        window.update_idletasks()
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        anchor_x, anchor_y = self.label.winfo_rootx(), self.label.winfo_rooty()
        x = anchor_x + 25
        y = anchor_y + max(25, self.label.winfo_height() + 5)
        if x + width > right - self.MARGIN:
            x = anchor_x - width - self.MARGIN
        if y + height > bottom - self.MARGIN:
            y = anchor_y - height - self.MARGIN
        x = max(left + self.MARGIN, min(x, max(left + self.MARGIN, right - width - self.MARGIN)))
        y = max(top + self.MARGIN, min(y, max(top + self.MARGIN, bottom - height - self.MARGIN)))
        window.wm_geometry(f"+{x}+{y}")
        window.deiconify()
        self._window = window

    def hide(self):
        window, self._window = self._window, None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass


def bring_to_front(window):
    """Restore a minimized window and make it the foreground window.

    Works when the second copy started by S2P's Open passed on its right to
    take the foreground (see single_instance.allow_foreground_handoff).
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = int(window.wm_frame(), 16)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    except (AttributeError, OSError, ValueError, tk.TclError):
        pass


def make_icon(master, kind, size, color):
    """Small centered record/play/stop glyph; text glyphs sit low in Tk buttons."""
    image = tk.PhotoImage(master=master, width=size, height=size)
    radius = (size - 1) / 2.0
    for row in range(size):
        if kind == "record":
            dy = row - radius
            span = (radius * radius - dy * dy) ** 0.5 if abs(dy) <= radius else -1
            left, right = round(radius - span), round(radius + span) + 1
        elif kind == "play":
            half = size / 2.0
            reach = (1 - abs(row + 0.5 - half) / half) * (size * 0.9)
            left, right = round(size * 0.1), round(size * 0.1 + reach)
        else:  # stop
            inset = round(size * 0.12)
            left, right = inset, size - inset
            if row < inset or row >= size - inset:
                continue
        if right > left:
            image.put(color, to=(left, row, right, row + 1))
    return image


def default_tray(app):
    return SystemTrayIcon(
        APP_TITLE,
        show_label=app.tr("顯示"),
        exit_label=app.tr("結束"),
        icon_path=ASSETS / "icon.ico",
    )


class MacroApp:
    def __init__(self, root, data_dir=None, connection_factory=AutoConnection,
                 tray_factory=default_tray, show_requests=None, start_hidden=None):
        self.root = root
        self._show_requests = show_requests if show_requests is not None else queue.SimpleQueue()
        self._hidden = False
        self.data_dir = Path(data_dir) if data_dir else data_directory()
        self.settings_path = self.data_dir / "settings.json"
        self.settings = AppSettings.load(self.settings_path)
        self.library = MacroLibrary(self.data_dir / "macros")
        self.tr = Translator(self.settings.language)
        self.macro = None
        self.recorder = None
        self.player = MacroPlayer(self._send_step, self._release)
        self._player_progress = None
        self._player_finished = None
        self._pending_play = None
        self._wanted_sticks = ()
        self._trigger_monitor = None
        self._trigger_events = queue.SimpleQueue()
        self._triggers = {}
        self._connection_state = ("connecting", "")
        # Closing S2P closes this tool too (a connector restart does not).
        self.connection = connection_factory(
            self._make_client, self._on_connection,
            on_host_exit=lambda: self._show_requests.put("exit"),
        )
        self._status = ()  # ((source text, values), ...), translated when shown
        self._play_warning = ()
        self._tick_job = None
        self._shown_steps = []
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        root.title(APP_TITLE)
        self._set_window_icon()
        # 480 px plus the Game input rate row, so the smallest window still
        # shows as many step rows as before that row was added.
        root.minsize(int(640 * self.scale), int(512 * self.scale))
        # X keeps the tool running (and connected) in the notification area,
        # so controller triggers still work; Exit there really quits.
        root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        root.bind("<Escape>", lambda _event: self.stop_all())
        self.body = None
        if start_hidden is None:
            start_hidden = started_in_background()
        # The notice must be seen once, so only start hidden after it was accepted.
        start_hidden = start_hidden and self.settings.notice_accepted
        if start_hidden:
            root.withdraw()  # avoid a flash of the window before it goes to the tray
        self.build()
        center_window(root)
        if not self.settings.notice_accepted and not self.show_notice():
            self.root.after_idle(self.close)
            return
        self.tray = tray_factory(self) if tray_factory else None
        if self.tray is not None and not self.tray.start():
            self.tray = None
        if start_hidden:
            if self.tray is not None and self.tray.show():
                self._hidden = True
            else:
                root.deiconify()  # no tray: a hidden window could not be reached
        self.connection.start()
        self._tick_job = self.root.after(100, self._tick)

    def _set_window_icon(self):
        # Several sizes so Windows uses the redrawn 16 px art in the title bar
        # instead of shrinking the large image (which blurs the pixel art).
        try:
            self._icons = [
                tk.PhotoImage(master=self.root, file=str(ASSETS / f"icon{size}.png"))
                for size in (64, 32, 16)
            ]
            self.root.iconphoto(True, *self._icons)
            self._icon = self._icons[0]
        except tk.TclError:
            self._icons = []
            self._icon = None

    # -- connection -------------------------------------------------------------

    def _make_client(self):
        # Sticks are claimed only while a macro that moves them is playing,
        # so other extension tools can use the sticks the rest of the time.
        return ExtensionClient(
            APP_NAME, __version__, capabilities=("input", "read"),
            sticks=list(self._wanted_sticks),
        )

    def _on_connection(self, state, detail):
        # Background thread: only store; the Tk timer renders it.
        self._connection_state = (state, detail)

    @property
    def client(self):
        client = self.connection.client
        return client if client is not None and client.connected else None

    def _claim_sticks(self, sticks):
        sticks = tuple(side for side in ("left", "right") if side in sticks)
        if sticks != self._wanted_sticks:
            self._wanted_sticks = sticks
            self.connection.reconnect()

    def _send_step(self, step, sticks):
        client = self.client
        if client is None:
            raise ConnectionError(self.tr("尚未連接 S2P-XInput-Lite。"))
        client.send_state(
            step.buttons, lt=step.lt, rt=step.rt,
            left=step.left if "left" in sticks else None,
            right=step.right if "right" in sticks else None,
        )

    def _release(self):
        client = self.client
        if client is not None:
            client.release_all()

    # -- UI construction ----------------------------------------------------------

    def _px(self, value):
        return int(value * self.scale)

    def build(self):
        if self.body is not None:
            self.body.destroy()
        tr = self.tr
        size = max(9, self._px(10)) | 1
        self._images = {
            "record": make_icon(self.root, "record", size, "#C62828"),
            "play": make_icon(self.root, "play", size, "#138A36"),
            "stop": make_icon(self.root, "stop", size, "#444444"),
        }
        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self.body = body

        # -- left: one tall macro list ------------------------------------------
        left = ttk.LabelFrame(body, text=tr("巨集"), padding=8)
        left.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1, uniform="macro_buttons")
        left.columnconfigure(1, weight=1, uniform="macro_buttons")
        self.macro_list = tk.Listbox(left, width=18, exportselection=False, activestyle="none")
        self.macro_list.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.macro_list.bind("<<ListboxSelect>>", lambda _event: self.select_macro())
        ttk.Button(left, text=tr("新增"), command=self.new_macro).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for row, pair in enumerate((
            (("重新命名", self.rename_macro), ("刪除", self.delete_macro)),
            (("匯入...", self.import_macro), ("匯出...", self.export_macro)),
        ), start=2):
            for column, (text, command) in enumerate(pair):
                ttk.Button(left, text=tr(text), command=command).grid(
                    row=row, column=column, sticky="ew", pady=(6, 0),
                    padx=(0, 3) if column == 0 else (3, 0),
                )

        # -- right top: steps -------------------------------------------------
        steps = ttk.LabelFrame(body, text=tr("步驟"), padding=8)
        steps.grid(row=0, column=1, sticky="nsew")
        steps.columnconfigure(0, weight=1)
        steps.rowconfigure(0, weight=1)
        columns = (
            ("index", "#", 30, "e"), ("start", "開始", 52, "e"), ("duration", "持續 ms", 58, "e"),
            ("buttons", "按鍵", 88, "w"), ("lt", "LT", 30, "e"), ("rt", "RT", 30, "e"),
            ("left", "左搖桿", 74, "w"), ("right", "右搖桿", 74, "w"),
        )
        self.step_tree = ttk.Treeview(
            steps, columns=tuple(key for key, *_ in columns), show="headings",
            selectmode="extended", height=12,
        )
        for key, heading, width, anchor in columns:
            self.step_tree.heading(key, text=tr(heading), anchor=anchor)
            self.step_tree.column(
                key, width=self._px(width), minwidth=self._px(28), anchor=anchor,
                stretch=key == "buttons",
            )
        scroll = ttk.Scrollbar(steps, orient="vertical", command=self.step_tree.yview)
        self.step_tree.configure(yscrollcommand=scroll.set)
        self.step_tree.tag_configure("short", foreground=SHORT_STEP_COLOR)
        self.step_tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.step_tree.bind("<Double-1>", lambda _event: self.edit_step())
        step_buttons = ttk.Frame(steps)
        step_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for text, command in (
            ("新增", self.add_step), ("編輯", self.edit_step), ("刪除", self.delete_steps),
            ("上移", lambda: self.move_step(-1)), ("下移", lambda: self.move_step(1)),
        ):
            ttk.Button(step_buttons, text=tr(text), width=6, command=command).pack(
                side="left", padx=(0, 4))
        self.summary_label = ttk.Label(step_buttons, text="")
        self.summary_label.pack(side="right")
        # Own line so it stays readable at the minimum window width.
        rate_row = ttk.Frame(steps)
        rate_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(rate_row, text=tr("遊戲讀取輸入")).pack(side="left")
        self._rate_labels = {hz: self._rate_label(hz) for hz in GAME_INPUT_RATES}
        self.game_input_var = tk.StringVar(value=self._rate_labels[self.settings.game_input_hz])
        rate_box = ttk.Combobox(
            rate_row, width=10, state="readonly", textvariable=self.game_input_var,
            values=list(self._rate_labels.values()),
        )
        rate_box.pack(side="left", padx=(6, 4))
        self.rate_help = HelpTip(rate_row, tr(GAME_INPUT_HELP))
        self.rate_help.label.pack(side="left", padx=(0, 12))
        rate_box.bind("<<ComboboxSelected>>", lambda _event: self.set_game_input_rate())
        self.short_label = ttk.Label(rate_row, text="", foreground=SHORT_STEP_COLOR)
        self.short_label.pack(side="left")

        # -- right middle: record / play ------------------------------------
        controls = ttk.LabelFrame(body, text=tr("錄製與播放"), padding=8)
        controls.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        row = ttk.Frame(controls)
        row.pack(fill="x")
        self.record_button = ttk.Button(
            row, text=tr("錄製"), image=self._images["record"], compound="left",
            command=self.start_recording,
        )
        self.record_button.pack(side="left")
        self.play_button = ttk.Button(
            row, text=tr("播放"), image=self._images["play"], compound="left",
            command=self.start_playback,
        )
        self.play_button.pack(side="left", padx=(6, 0))
        self.stop_button = ttk.Button(
            row, text=tr("停止"), image=self._images["stop"], compound="left",
            command=self.stop_all,
        )
        self.stop_button.pack(side="left", padx=(6, 0))
        self.record_sticks_var = tk.BooleanVar(value=self.settings.record_sticks)
        ttk.Checkbutton(
            row, text=tr("錄製搖桿"), variable=self.record_sticks_var,
            command=self._save_options,
        ).pack(side="left", padx=(14, 0))

        row = ttk.Frame(controls)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text=tr("重複次數")).pack(side="left")
        self.loops_var = tk.StringVar(value=str(self.settings.loops))
        ttk.Spinbox(row, from_=0, to=9999, width=5, textvariable=self.loops_var,
                    command=self._save_options).pack(side="left", padx=(6, 0))
        ttk.Label(row, text=tr("（0 = 不停重複）"), foreground="#666666").pack(
            side="left", padx=(4, 12))
        ttk.Label(row, text=tr("速度")).pack(side="left")
        self.speed_var = tk.StringVar(value=f"{self.settings.speed:g}x")
        speed_box = ttk.Combobox(
            row, width=5, state="readonly", textvariable=self.speed_var,
            values=[f"{speed:g}x" for speed in SPEEDS],
        )
        speed_box.pack(side="left", padx=(6, 12))
        speed_box.bind("<<ComboboxSelected>>", lambda _event: self._save_options())
        ttk.Label(row, text=tr("循環間隔 ms")).pack(side="left")
        self.gap_var = tk.StringVar(value=str(self.settings.loop_gap_ms))
        ttk.Spinbox(row, from_=0, to=5000, increment=10, width=5, textvariable=self.gap_var,
                    command=self._save_options).pack(side="left", padx=(6, 0))

        row = ttk.Frame(controls)
        row.pack(fill="x", pady=(8, 0))
        self.trigger_enabled_var = tk.BooleanVar(value=self.settings.trigger_enabled)
        ttk.Checkbutton(
            row, text=tr("啟用手把觸發"), variable=self.trigger_enabled_var,
            command=self._save_options,
        ).pack(side="left")
        ttk.Label(row, text=tr("觸發鍵")).pack(side="left", padx=(14, 0))
        self.trigger_label = ttk.Label(row, text="")
        self.trigger_label.pack(side="left", padx=(6, 0))
        # Right after the current combination, not pushed to the far edge.
        ttk.Button(row, text=tr("設定觸發鍵..."), command=self.edit_trigger).pack(
            side="left", padx=(12, 0))

        # -- right bottom: status ---------------------------------------------
        status = ttk.LabelFrame(body, text=tr("狀態"), padding=8)
        status.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, text=tr("連線")).grid(row=0, column=0, sticky="w")
        self.connection_label = tk.Label(status, text="", anchor="w")
        self.connection_label.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(
            status, text="En" if self.settings.language == "zh" else "中",
            width=4, command=self.toggle_language,
        ).grid(row=0, column=2, sticky="e")
        ttk.Label(status, text=tr("目前")).grid(row=1, column=0, sticky="nw", pady=(4, 0))
        # Two fixed lines: status changes never resize or re-flow the window.
        self.status_label = ttk.Label(
            status, text=tr("就緒"), anchor="nw", justify="left",
            wraplength=self._px(430),
        )
        self.status_label.grid(row=1, column=1, columnspan=2, sticky="new", padx=(8, 0), pady=(4, 0))
        status.rowconfigure(1, minsize=self._px(36))
        ttk.Label(
            status, foreground="#666666",
            text=tr("提示：Esc 可立即停止播放。使用前請確認遊戲與服務規範，使用後果由使用者自行負責。"),
            wraplength=self._px(500), justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        self.refresh_macro_list(self.settings.last_macro)
        self._render_connection()

    def hide_to_tray(self):
        """Hide the window but keep running; quit when no tray is available."""
        if self.tray is None or not self.tray.show():
            self.close()
            return
        self.root.withdraw()
        self._hidden = True
        if not self.settings.tray_hint_shown:
            self.settings.tray_hint_shown = True
            self._persist_settings()
            messagebox.showinfo(
                APP_TITLE,
                self.tr("S2P-Joystick-Macro 會在系統匣繼續執行，手把觸發仍然有效。\n"
                        "在系統匣圖示按右鍵選「結束」才會完全關閉。"),
            )

    def show_window(self):
        if self.tray is not None:
            self.tray.hide()
        self._hidden = False
        self.root.deiconify()
        if self.root.state() == "iconic":
            self.root.state("normal")  # minimized: restore it
        self.root.lift()
        bring_to_front(self.root)
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def _handle_window_requests(self):
        while True:
            try:
                request = self._show_requests.get_nowait()
            except queue.Empty:
                break
            if request == "exit":
                self.close()  # S2P closed: stop playback, release input, quit
                return
            self.show_window()
        if self.tray is None:
            return
        while True:
            action = self.tray.get_action()
            if action is None:
                return
            if action == "show":
                self.show_window()
            elif action == "exit":
                self.close()
                return

    # -- status line (kept as source text so a language switch re-translates it) --

    def _set_status(self, text="", **values):
        self._status = ((text, values),) if text else ()

    def _add_status(self, text, **values):
        if text:
            self._status += ((text, values),)

    def _status_is(self, text):
        return len(self._status) == 1 and self._status[0][0] == text

    @property
    def status_text(self):
        lines = []
        for text, values in self._status:
            shown = {key: value() if callable(value) else value for key, value in values.items()}
            lines.append(self.tr(text).format(**shown))
        return "\n".join(lines)

    def _stick_names(self, sides):
        names = [self.tr(STICK_LABEL[side]) for side in sorted(sides)]
        return ("、" if self.tr.language == "zh" else " and ").join(names)

    def toggle_language(self):
        self.settings.language = "en" if self.settings.language == "zh" else "zh"
        self.tr.language = self.settings.language
        self._persist_settings()
        if self.tray is not None:
            self.tray.update_labels(self.tr("顯示"), self.tr("結束"))
        self._shown_steps = []
        self.build()

    def _dialog(self, title):
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        if self._icon is not None:
            dialog.iconphoto(False, *self._icons)
        return dialog

    def _show_dialog(self, dialog, focus=None):
        center_window(dialog, self.root)
        dialog.deiconify()
        dialog.grab_set()
        (focus or dialog).focus_set()
        self.root.wait_window(dialog)

    def show_notice(self):
        tr = self.tr
        notice = NOTICE[self.settings.language]
        dialog = self._dialog(tr("使用聲明"))
        frame = ttk.Frame(dialog, padding=(18, 16))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        # English wraps at a fixed width; Chinese lines are already short.
        wrap = self._px(440) if self.settings.language == "en" else 0
        row = 0
        for line in notice["intro"]:
            ttk.Label(frame, text=line, wraplength=wrap, justify="left").grid(
                row=row, column=0, columnspan=2, sticky="w")
            row += 1
        ttk.Separator(frame).grid(row=row, column=0, columnspan=2, sticky="ew", pady=10)
        row += 1
        ttk.Label(frame, text=notice["heading"]).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        row += 1
        for number, item in enumerate(notice["items"], start=1):
            ttk.Label(frame, text=f"{number}.").grid(
                row=row, column=0, sticky="ne", padx=(8, 6), pady=1)
            ttk.Label(frame, text=item, wraplength=wrap, justify="left").grid(
                row=row, column=1, sticky="w", pady=1)
            row += 1
        accepted = tk.BooleanVar(value=False)
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(16, 0))

        def accept():
            accepted.set(True)
            dialog.destroy()

        ttk.Button(buttons, text=tr("結束"), command=dialog.destroy).pack(side="right")
        ok = ttk.Button(buttons, text=tr("我已了解"), command=accept)
        ok.pack(side="right", padx=(0, 6))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self._show_dialog(dialog, ok)
        if accepted.get():
            self.settings.notice_accepted = True
            self._persist_settings()
        return accepted.get()

    def _message(self, kind, text, title=APP_TITLE):
        getattr(messagebox, kind)(title, text, parent=self.root)

    # -- settings ---------------------------------------------------------------

    def _persist_settings(self):
        try:
            self.settings.save(self.settings_path)
        except OSError:
            pass

    @property
    def short_step_ms(self):
        """Shortest step the game always reads at the selected input rate."""
        return GAME_INPUT_RATES[self.settings.game_input_hz]

    def _rate_label(self, hz):
        return self.tr("{hz} Hz 以上").format(hz=hz) if hz == max(GAME_INPUT_RATES) else f"{hz} Hz"

    def set_game_input_rate(self, hz=None):
        if hz is None:
            labels = {label: rate for rate, label in self._rate_labels.items()}
            hz = labels.get(self.game_input_var.get(), self.settings.game_input_hz)
        self.settings.game_input_hz = hz
        self.game_input_var.set(self._rate_labels[hz])
        self._persist_settings()
        # Redraw every row with the new limit; a recording redraws on its next tick.
        self._shown_steps = []
        if self.recorder is None:
            self.refresh_steps()

    def _save_options(self):
        try:
            self.settings.loops = max(0, min(9999, int(self.loops_var.get())))
        except ValueError:
            pass
        try:
            self.settings.loop_gap_ms = max(0, min(5000, int(self.gap_var.get())))
        except ValueError:
            pass
        try:
            self.settings.speed = float(self.speed_var.get().rstrip("x"))
        except ValueError:
            pass
        self.settings.record_sticks = bool(self.record_sticks_var.get())
        self.settings.trigger_enabled = bool(self.trigger_enabled_var.get())
        self._persist_settings()

    # -- macros -------------------------------------------------------------------

    def refresh_macro_list(self, select=None):
        self._triggers = self.library.triggers()
        if self._trigger_monitor is not None:
            self._trigger_monitor.set_triggers(self._triggers)
        names = self.library.names()
        self.macro_list.delete(0, "end")
        for name in names:
            self.macro_list.insert("end", name)
        if select in names:
            index = names.index(select)
            self.macro_list.selection_set(index)
            self.macro_list.see(index)
        self.select_macro()

    def select_macro(self):
        if self.recorder is not None:
            return  # the live recording owns the step table
        selection = self.macro_list.curselection()
        self.macro = None
        if selection:
            name = self.macro_list.get(selection[0])
            try:
                self.macro = self.library.load(name)
            except (OSError, MacroFormatError) as exc:
                self._message("showerror", self.tr("無法讀取巨集：{error}").format(error=exc))
            else:
                self.settings.last_macro = name
                self._persist_settings()
        self.refresh_steps()
        self._show_trigger()

    def _show_trigger(self):
        trigger = self.macro.trigger if self.macro else ()
        self.trigger_label.configure(
            text=" + ".join(trigger) if trigger else self.tr("未設定"),
            foreground="" if trigger else "#888888",
        )

    def edit_trigger(self):
        if self.macro is None or self._busy():
            if self.macro is None:
                self._message("showinfo", self.tr("請先選擇一個巨集。"))
            return
        tr = self.tr
        dialog = self._dialog(tr("設定觸發鍵"))
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=tr("同時按住這些手把按鍵即播放「{name}」，播放中再按一次則停止。")
                  .format(name=self.macro.name), wraplength=self._px(420),
                  justify="left").grid(row=0, column=0, sticky="w")
        grid = ttk.Frame(frame)
        grid.grid(row=1, column=0, sticky="w", pady=(10, 0))
        pressed = {}
        for index, name in enumerate(BUTTON_ORDER):
            pressed[name] = tk.BooleanVar(value=name in self.macro.trigger)
            ttk.Checkbutton(grid, text=name, variable=pressed[name]).grid(
                row=index // 5, column=index % 5, sticky="w", padx=(0, 12), pady=1)
        ttk.Label(
            frame, foreground="#666666", justify="left", wraplength=self._px(420),
            text=tr("觸發鍵仍會傳給遊戲，請選擇遊戲中用不到的組合（建議兩個以上按鍵，例如 BACK + R_STK）。"),
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))
        result = []

        def accept(clear=False):
            chosen = () if clear else tuple(name for name, var in pressed.items() if var.get())
            for other, buttons in self._triggers.items():
                if chosen and other != self.macro.name and set(buttons) == set(chosen):
                    messagebox.showwarning(
                        tr("設定觸發鍵"),
                        tr("這組觸發鍵已用於「{name}」。").format(name=other), parent=dialog,
                    )
                    return
            result.append(chosen)
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(buttons, text=tr("清除"), command=lambda: accept(clear=True)).pack(side="left")
        ttk.Button(buttons, text=tr("取消"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=tr("確定"), command=accept).pack(side="right", padx=(0, 6))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._show_dialog(dialog)
        if result:
            self.macro.trigger = result[0]
            self._save_macro()
            self.refresh_macro_list(self.macro.name)

    def _save_macro(self):
        try:
            self.library.save(self.macro)
        except OSError as exc:
            self._message("showerror", self.tr("無法儲存巨集：{error}").format(error=exc))

    def _ask_name(self, initial=""):
        tr = self.tr
        dialog = self._dialog(tr("巨集名稱"))
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=tr("請輸入巨集名稱：")).pack(anchor="w")
        value = tk.StringVar(value=initial)
        entry = ttk.Entry(frame, textvariable=value, width=32)
        entry.pack(fill="x", pady=(6, 10))
        entry.select_range(0, "end")
        result = []

        def accept():
            result.append(value.get().strip())
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text=tr("取消"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=tr("確定"), command=accept).pack(side="right", padx=(0, 6))
        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._show_dialog(dialog, entry)
        name = result[0] if result else ""
        if not name:
            return None
        if name != initial and self.library.exists(name):
            self._message("showwarning", tr("已有同名巨集。"))
            return None
        return name

    def _unique_name(self, base):
        name, number = base, 2
        while self.library.exists(name):
            name = f"{base} ({number})"
            number += 1
        return name

    def new_macro(self):
        if self._busy():
            return
        name = self._ask_name()
        if name:
            self.macro = Macro(name, [])
            self._save_macro()
            self.refresh_macro_list(name)

    def rename_macro(self):
        if self.macro is None or self._busy():
            return
        name = self._ask_name(self.macro.name)
        if name and name != self.macro.name:
            self.library.rename(self.macro.name, name)
            self.refresh_macro_list(name)

    def delete_macro(self):
        if self.macro is None or self._busy():
            return
        if messagebox.askyesno(
            APP_TITLE, self.tr("確定要刪除「{name}」嗎？").format(name=self.macro.name),
            parent=self.root,
        ):
            self.library.delete(self.macro.name)
            self.refresh_macro_list()

    def import_macro(self):
        if self._busy():
            return
        path = filedialog.askopenfilename(
            parent=self.root, title=self.tr("匯入..."),
            filetypes=((self.tr("巨集檔案"), "*.json"), (self.tr("所有檔案"), "*.*")),
        )
        if not path:
            return
        try:
            macro = MacroLibrary.load_file(path)
        except (OSError, MacroFormatError) as exc:
            self._message("showerror", self.tr("無法讀取巨集：{error}").format(error=exc))
            return
        macro.name = self._unique_name(macro.name)
        self.macro = macro
        self._save_macro()
        self.refresh_macro_list(macro.name)

    def export_macro(self):
        if self.macro is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title=self.tr("匯出..."), defaultextension=".json",
            initialfile=self.library.path_for(self.macro.name).name,
            filetypes=((self.tr("巨集檔案"), "*.json"),),
        )
        if path:
            try:
                MacroLibrary.write_file(self.macro, path)
            except OSError as exc:
                self._message("showerror", self.tr("無法儲存巨集：{error}").format(error=exc))

    # -- steps --------------------------------------------------------------------

    @staticmethod
    def _row(index, start, step):
        return (
            index + 1, f"{start / 1000:.3f}", step.duration_ms,
            " + ".join(step.buttons) or "—", step.lt or "", step.rt or "",
            f"{step.left[0]}, {step.left[1]}" if step.uses_stick("left") else "",
            f"{step.right[0]}, {step.right[1]}" if step.uses_stick("right") else "",
        )

    def refresh_steps(self, select=(), steps=None, follow=False):
        """Show ``steps`` (default: the selected macro); only changed rows are redrawn."""
        tree = self.step_tree
        steps = list(self.macro.steps if self.macro else []) if steps is None else list(steps)
        shown = self._shown_steps
        keep = 0
        while keep < min(len(shown), len(steps)) and shown[keep] == steps[keep]:
            keep += 1
        for item in tree.get_children()[keep:]:
            tree.delete(item)
        # While recording (follow) the last step is still growing: not short yet.
        settled = len(steps) - 1 if follow else len(steps)
        start = sum(step.duration_ms for step in steps[:keep])
        for index in range(keep, len(steps)):
            short = index < settled and steps[index].duration_ms < self.short_step_ms
            tree.insert("", "end", iid=str(index), values=self._row(index, start, steps[index]),
                        tags=("short",) if short else ())
            start += steps[index].duration_ms
        self._shown_steps = steps[:settled]  # a growing last row is always redrawn
        total = sum(step.duration_ms for step in steps)
        if follow and steps:
            tree.see(str(len(steps) - 1))
        for index in select:
            if tree.exists(str(index)):
                tree.selection_add(str(index))
                tree.see(str(index))
        self.summary_label.configure(text=self.tr("共 {count} 步，總長 {seconds:.2f} 秒").format(
            count=len(steps), seconds=total / 1000,
        ))
        short = sum(step.duration_ms < self.short_step_ms for step in steps[:settled])
        self.short_label.configure(text=self.tr("橘色 {short} 步：短於 {ms} ms").format(
            short=short, ms=self.short_step_ms) if short else "")

    def _selected_steps(self):
        return sorted(int(item) for item in self.step_tree.selection())

    def _busy(self):
        return (
            self.player.running or self._pending_play is not None
            or (self.recorder is not None and self.recorder.running)
        )

    def add_step(self):
        if self.macro is None or self._busy():
            return
        selected = self._selected_steps()
        position = selected[-1] + 1 if selected else len(self.macro.steps)
        step = self.edit_step_dialog(Step(100))
        if step is not None:
            self.macro.steps.insert(position, step)
            self._save_macro()
            self.refresh_steps((position,))

    def edit_step(self):
        selected = self._selected_steps()
        if self.macro is None or not selected or self._busy():
            return
        index = selected[0]
        step = self.edit_step_dialog(self.macro.steps[index])
        if step is not None:
            self.macro.steps[index] = step
            self._save_macro()
            self.refresh_steps((index,))

    def delete_steps(self):
        selected = self._selected_steps()
        if self.macro is None or not selected or self._busy():
            return
        for index in reversed(selected):
            del self.macro.steps[index]
        self._save_macro()
        self.refresh_steps((min(selected[0], len(self.macro.steps) - 1),))

    def move_step(self, offset):
        selected = self._selected_steps()
        if self.macro is None or len(selected) != 1 or self._busy():
            return
        index, target = selected[0], selected[0] + offset
        if not 0 <= target < len(self.macro.steps):
            return
        steps = self.macro.steps
        steps[index], steps[target] = steps[target], steps[index]
        self._save_macro()
        self.refresh_steps((target,))

    def edit_step_dialog(self, step):
        tr = self.tr
        dialog = self._dialog(tr("編輯步驟"))
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        duration = tk.StringVar(value=str(step.duration_ms))
        ttk.Label(frame, text=tr("持續時間（ms）")).grid(row=0, column=0, sticky="w")
        duration_box = ttk.Spinbox(frame, from_=1, to=600000, increment=10, width=10,
                                   textvariable=duration)
        duration_box.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(frame, text=tr("遊戲每秒讀取輸入 {rate}：每個步驟建議至少 {ms} ms，太短可能讀不到。").format(
            rate=self._rate_labels[self.settings.game_input_hz], ms=self.short_step_ms),
                  foreground="#666666").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 8))
        ttk.Label(frame, text=tr("按鍵")).grid(row=2, column=0, sticky="nw")
        grid = ttk.Frame(frame)
        grid.grid(row=2, column=1, columnspan=3, sticky="w", padx=(8, 0))
        pressed = {}
        for index, name in enumerate(BUTTON_ORDER):
            pressed[name] = tk.BooleanVar(value=name in step.buttons)
            ttk.Checkbutton(grid, text=name, variable=pressed[name]).grid(
                row=index // 5, column=index % 5, sticky="w", padx=(0, 10))
        ttk.Label(grid, text=tr("可勾選多個按鍵，代表同時按住。"), foreground="#666666").grid(
            row=(len(BUTTON_ORDER) + 4) // 5, column=0, columnspan=5, sticky="w", pady=(2, 0))
        values = {}
        for row, (label, keys, low, high) in enumerate((
            ("LT / RT", (("lt", step.lt), ("rt", step.rt)), 0, 255),
            ("左搖桿 X / Y", (("lx", step.left[0]), ("ly", step.left[1])), -32768, 32767),
            ("右搖桿 X / Y", (("rx", step.right[0]), ("ry", step.right[1])), -32768, 32767),
        ), start=3):
            ttk.Label(frame, text=tr(label)).grid(row=row, column=0, sticky="w", pady=(8, 0))
            for column, (key, value) in enumerate(keys, start=1):
                values[key] = tk.StringVar(value=str(value))
                ttk.Spinbox(frame, from_=low, to=high, width=8, textvariable=values[key]).grid(
                    row=row, column=column, sticky="w", padx=(8, 0), pady=(8, 0))
        result = []

        def accept():
            try:
                numbers = {key: int(var.get()) for key, var in values.items()}
                result.append(Step(
                    int(duration.get()),
                    tuple(name for name, var in pressed.items() if var.get()),
                    numbers["lt"], numbers["rt"],
                    (numbers["lx"], numbers["ly"]), (numbers["rx"], numbers["ry"]),
                ))
            except (ValueError, MacroFormatError) as exc:
                messagebox.showerror(tr("編輯步驟"), tr("步驟無效：{error}").format(error=exc),
                                     parent=dialog)
                return
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=4, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text=tr("取消"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=tr("確定"), command=accept).pack(side="right", padx=(0, 6))
        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._show_dialog(dialog, duration_box)
        return result[0] if result else None

    # -- record / play --------------------------------------------------------------

    def _require(self, capability, message):
        client = self.client
        if client is None:
            self._message("showwarning", self.tr("尚未連接 S2P-XInput-Lite。"))
            return None
        if capability not in client.granted:
            self._message("showwarning", self.tr(message))
            return None
        return client

    def start_recording(self):
        if self._busy():
            return
        client = self._require(
            "read",
            "S2P 未允許此工具讀取控制器狀態，無法錄製。\n"
            "請在 S2P 的「擴充工具」清單選取此工具，勾選「允許讀取控制器狀態」。",
        )
        if client is None:
            return
        self._save_options()
        self.recorder = MacroRecorder(client.get_input, record_sticks=self.settings.record_sticks)
        self.recorder.start()
        # Show the new recording in the list right away; steps fill in live.
        self.macro_list.selection_clear(0, "end")
        self.macro_list.insert("end", self.tr("● 錄製中…"))
        self.macro_list.selection_set("end")
        self.macro_list.see("end")
        self.refresh_steps(steps=[])

    def _finish_recording(self):
        recorder, self.recorder = self.recorder, None
        steps = recorder.stop()
        if recorder.error is not None and not steps:
            self._set_status("錄製中斷：{error}", error=recorder.error)
            self.refresh_macro_list(self.settings.last_macro)
            return
        if not steps:
            self._set_status("沒有錄到任何輸入。")
            self.refresh_macro_list(self.settings.last_macro)
            return
        name = self._unique_name(time.strftime("Rec %Y-%m-%d %H-%M-%S"))
        self.macro = Macro(name, steps)
        self._save_macro()
        self.refresh_macro_list(name)
        self._set_status("已錄製「{name}」，共 {count} 步", name=name, count=len(steps))
        if recorder.frames_missed:
            self._add_status(
                "錄製時未讀到 {missed}/{total} 幀，極短的變化可能沒錄到。",
                missed=recorder.frames_missed, total=recorder.frames_total)
        if recorder.error is not None:
            self._add_status("錄製中斷：{error}", error=recorder.error)

    def start_playback(self):
        if self._busy():
            return
        if self.macro is None:
            self._message("showinfo", self.tr("請先選擇一個巨集。"))
            return
        if not self.macro.steps:
            self._message("showinfo", self.tr("巨集沒有任何步驟。"))
            return
        if self._require("input", "S2P 未允許此工具提交輸入，無法播放。") is None:
            return
        self._save_options()
        needed = self.macro.sticks_used()
        if needed - self.client.granted_sticks:
            # Claim the sticks this macro moves, then play once reconnected.
            self._claim_sticks(needed)
            self._pending_play = time.monotonic() + STICK_CLAIM_TIMEOUT
            self._set_status("正在取得搖桿控制權…")
            return
        self._begin_playback()

    def _begin_playback(self):
        self._pending_play = None
        client = self.client
        if client is None:
            self._set_status("尚未連接 S2P-XInput-Lite。")
            self._claim_sticks(())
            return
        sticks = client.granted_sticks
        skipped = self.macro.sticks_used() - sticks
        warning = ()
        if skipped:
            warning = ((
                "{sticks}正由其他擴充工具控制，播放時會略過搖桿動作。",
                {"sticks": lambda: self._stick_names(skipped)},
            ),)
        self._player_progress = None
        self._player_finished = None
        self._play_total = len(self.macro.steps)
        self._play_warning = warning
        self._status = warning
        self.player.play(
            self.macro.steps, loops=self.settings.loops, speed=self.settings.speed,
            sticks=sticks, loop_gap_ms=self.settings.loop_gap_ms,
            on_progress=self._on_progress, on_finished=self._on_finished,
        )

    def _check_pending_play(self):
        if self._pending_play is None:
            return
        state, _detail = self._connection_state
        client = self.client
        claimed = client is not None and set(self._wanted_sticks) <= client.granted_sticks
        if claimed or time.monotonic() >= self._pending_play or state == "rejected":
            if not claimed:
                # Another tool owns the stick: play without it.
                self._claim_sticks(())
                if self.client is None:
                    self._pending_play = time.monotonic() + STICK_CLAIM_TIMEOUT
                    return
            self._begin_playback()

    def _update_trigger_monitor(self):
        """Run the trigger watcher only when it can and should do something."""
        client = self.client
        wanted = (
            self.settings.trigger_enabled and bool(self._triggers) and self.recorder is None
            and client is not None and "read" in client.granted
        )
        monitor = self._trigger_monitor
        if monitor is not None and (
            not wanted or not monitor.running or monitor.source != client.get_input
        ):
            monitor.stop()
            self._trigger_monitor = monitor = None
        if wanted and monitor is None:
            monitor = TriggerMonitor(client.get_input, self._trigger_events.put)
            monitor.set_triggers(self._triggers)
            monitor.start()
            self._trigger_monitor = monitor

    def _handle_triggers(self):
        while True:
            try:
                name = self._trigger_events.get_nowait()
            except queue.Empty:
                return
            playing = self.player.running or self._pending_play is not None
            if playing:
                # The same combination stops what is playing.
                self.stop_all()
                continue
            if self._busy() or name not in self._triggers:
                continue
            names = self.macro_list.get(0, "end")
            if name in names:
                self.macro_list.selection_clear(0, "end")
                self.macro_list.selection_set(names.index(name))
                self.macro_list.see(names.index(name))
                self.select_macro()
                if self.macro is not None and self.macro.name == name:
                    self.start_playback()

    def _trigger_note(self):
        client = self.client
        if not self.settings.trigger_enabled or not self._triggers:
            return ""
        if client is not None and "read" not in client.granted:
            return self.tr("手把觸發需要在 S2P 允許「讀取控制器狀態」。")
        return ""

    def _on_progress(self, loop, index):
        self._player_progress = (loop, index)

    def _on_finished(self, completed, error):
        self._player_finished = (completed, error)

    def stop_all(self):
        if self._pending_play is not None:
            self._pending_play = None
            self._claim_sticks(())
            self._set_status("播放已停止")
        if self.player.running:
            self.player.stop()
            self._set_status("播放已停止")
        if self.recorder is not None:
            self._finish_recording()

    # -- periodic UI update -----------------------------------------------------------

    def _render_connection(self):
        state, detail = self._connection_state
        client = self.client
        if state == "connected" and client is not None:
            permissions = " / ".join(
                self.tr(label) for key, label in (("input", "輸入"), ("read", "讀取"))
                if key in client.granted
            )
            text = self.tr("已連接 S2P（{permissions}）").format(permissions=permissions)
            sticks = client.granted_sticks
            if sticks:
                text += " · " + " / ".join(self.tr(STICK_LABEL[side]) for side in sorted(sticks))
        elif state == "rejected":
            reason = REJECT_REASON.get(detail, detail)
            text = self.tr("S2P 拒絕連線：{reason}").format(reason=self.tr(reason))
        else:
            state = "connecting"
            text = self.tr("等待 S2P-XInput-Lite…")
        self.connection_label.configure(text=f"● {text}", fg=COLORS[state])

    def _tick(self):
        self._tick_job = None
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        self._handle_window_requests()
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        self._render_connection()
        self._check_pending_play()
        self._update_trigger_monitor()
        self._handle_triggers()
        recording = self.recorder is not None
        if recording:
            if not self.recorder.running:
                self._finish_recording()
                recording = False
            else:
                self.refresh_steps(steps=self.recorder.preview_steps(), follow=True)
                if self.recorder.first_input_at is None:
                    self._set_status("錄製中：等待第一個輸入…")
                elif self.recorder.frames_missed:
                    self._set_status(
                        "錄製中：{seconds:.1f} 秒，{count} 次變化，未讀到 {missed} 幀",
                        seconds=self.recorder.elapsed, count=self.recorder.change_count,
                        missed=self.recorder.frames_missed)
                else:
                    self._set_status(
                        "錄製中：{seconds:.1f} 秒，{count} 次變化",
                        seconds=self.recorder.elapsed, count=self.recorder.change_count)
        if self.player.running and self._player_progress is not None:
            loop, index = self._player_progress
            self._set_status(
                "播放中：第 {loop} 次，第 {step}/{total} 步",
                loop=loop, step=index + 1, total=self._play_total)
            self._status += self._play_warning
        if self._player_finished is not None and not self.player.running:
            completed, error = self._player_finished
            self._player_finished = None
            if error is not None:
                self._set_status("播放中斷：{error}", error=error)
            elif not self._status_is("播放已停止"):
                self._set_status("播放完成（{loops} 次）", loops=completed)
            self._claim_sticks(())  # give the sticks back to other tools
        busy = self._busy()
        self.record_button.state(["disabled"] if busy else ["!disabled"])
        self.play_button.state(["disabled"] if busy else ["!disabled"])
        self.stop_button.state(["!disabled"] if busy else ["disabled"])
        text = self.status_text or self.tr("就緒")
        note = self._trigger_note()
        if note and not busy:
            text = f"{text}\n{note}"
        self.status_label.configure(text=text)
        self._tick_job = self.root.after(50, self._tick)

    def close(self):
        try:
            self.stop_all()  # playback always releases its input first
            self._save_options()
        finally:
            if self._trigger_monitor is not None:
                self._trigger_monitor.stop()
            if getattr(self, "tray", None) is not None:
                self.tray.stop()
                self.tray = None
            self.connection.stop()
            if self._tick_job is not None:
                self.root.after_cancel(self._tick_job)
                self._tick_job = None
            self.root.destroy()


def enable_dpi_awareness():
    """Render crisply on high-DPI displays instead of being bitmap-scaled."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def main():
    requests = queue.SimpleQueue()
    instance = SingleInstance(lambda: requests.put("show"))
    if not instance.acquire():
        return  # the running copy shows its window instead
    try:
        enable_dpi_awareness()
        root = tk.Tk()
        MacroApp(root, show_requests=requests)
        root.mainloop()
    finally:
        instance.release()


if __name__ == "__main__":
    main()

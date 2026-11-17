"""Traditional Chinese source strings with English translations."""

EN = {
    "連線": "Connection",
    "等待 S2P-XInput-Lite…": "Waiting for S2P-XInput-Lite…",
    "已連接 S2P（{permissions}）": "Connected to S2P ({permissions})",
    "S2P 拒絕連線：{reason}": "S2P refused the connection: {reason}",
    "輸入": "input",
    "讀取": "read",
    "巨集": "Macros",
    "新增": "New",
    "重新命名": "Rename",
    "刪除": "Delete",
    "匯入...": "Import...",
    "匯出...": "Export...",
    "步驟": "Steps",
    "編輯": "Edit",
    "上移": "Up",
    "下移": "Down",
    "開始": "Start",
    "持續 ms": "Hold ms",
    "按鍵": "Buttons",
    "左搖桿": "Left stick",
    "右搖桿": "Right stick",
    "共 {count} 步，總長 {seconds:.2f} 秒": "{count} steps, {seconds:.2f} s total",
    "錄製與播放": "Record and play",
    "錄製": "Record",
    "播放": "Play",
    "停止": "Stop",
    "狀態": "Status",
    "目前": "Now",
    "● 錄製中…": "● Recording…",
    "正在取得搖桿控制權…": "Taking control of the sticks…",
    "錄製搖桿": "Record sticks",
    "啟用手把觸發": "Controller trigger",
    "顯示": "Show",
    "S2P-Joystick-Macro 會在系統匣繼續執行，手把觸發仍然有效。\n"
    "在系統匣圖示按右鍵選「結束」才會完全關閉。": (
        "S2P-Joystick-Macro keeps running in the notification area, and controller "
        "triggers keep working.\nRight-click its icon there and choose Quit to close it."
    ),
    "觸發鍵": "Trigger",
    "未設定": "not set",
    "設定觸發鍵...": "Set Trigger...",
    "設定觸發鍵": "Set Trigger",
    "清除": "Clear",
    "同時按住這些手把按鍵即播放「{name}」，播放中再按一次則停止。": (
        "Hold these controller buttons together to play \"{name}\"; press them again while it "
        "plays to stop."
    ),
    "觸發鍵仍會傳給遊戲，請選擇遊戲中用不到的組合（建議兩個以上按鍵，例如 BACK + R_STK）。": (
        "Trigger buttons still reach the game, so pick a combination the game does not use "
        "(two or more buttons, for example BACK + R_STK)."
    ),
    "這組觸發鍵已用於「{name}」。": "This combination is already used by \"{name}\".",
    "手把觸發需要在 S2P 允許「讀取控制器狀態」。": (
        "Controller triggers need \"Allow reading controller state\" in S2P."
    ),
    "重複次數": "Repeat",
    "（0 = 不停重複）": "(0 = until stopped)",
    "速度": "Speed",
    "循環間隔 ms": "Loop gap ms",
    "就緒": "Ready",
    "錄製中：等待第一個輸入…": "Recording: waiting for the first input…",
    "錄製中：{seconds:.1f} 秒，{count} 次變化": "Recording: {seconds:.1f} s, {count} changes",
    "播放中：第 {loop} 次，第 {step}/{total} 步": "Playing: pass {loop}, step {step}/{total}",
    "播放完成（{loops} 次）": "Playback finished ({loops} passes)",
    "播放已停止": "Playback stopped",
    "已錄製「{name}」，共 {count} 步": "Recorded \"{name}\" with {count} steps",
    "沒有錄到任何輸入。": "No input was recorded.",
    "錄製中斷：{error}": "Recording interrupted: {error}",
    "播放中斷：{error}": "Playback interrupted: {error}",
    "{sticks}正由其他擴充工具控制，播放時會略過搖桿動作。": (
        "Another extension tool controls the {sticks}; stick moves are skipped."
    ),
    "尚未連接 S2P-XInput-Lite。": "Not connected to S2P-XInput-Lite.",
    "S2P 未允許此工具讀取控制器狀態，無法錄製。\n請在 S2P 的「擴充工具」清單選取此工具，勾選「允許讀取控制器狀態」。": (
        "S2P does not allow this tool to read controller state, so it cannot record.\n"
        "In S2P's Extensions list, select this tool and check \"Allow reading controller state\"."
    ),
    "S2P 未允許此工具提交輸入，無法播放。": "S2P does not allow this tool to submit input, so it cannot play.",
    "請先選擇一個巨集。": "Select a macro first.",
    "巨集沒有任何步驟。": "The macro has no steps.",
    "巨集名稱": "Macro name",
    "請輸入巨集名稱：": "Enter a macro name:",
    "已有同名巨集。": "A macro with this name already exists.",
    "確定要刪除「{name}」嗎？": "Delete \"{name}\"?",
    "無法讀取巨集：{error}": "Could not read the macro: {error}",
    "無法儲存巨集：{error}": "Could not save the macro: {error}",
    "巨集檔案": "Macro files",
    "所有檔案": "All files",
    "編輯步驟": "Edit step",
    "持續時間（ms）": "Duration (ms)",
    "左搖桿 X / Y": "Left stick X / Y",
    "右搖桿 X / Y": "Right stick X / Y",
    "確定": "OK",
    "取消": "Cancel",
    "步驟無效：{error}": "Invalid step: {error}",
    "建議每個步驟至少 16 ms，遊戲才一定讀得到。": "Keep each step at least 16 ms so games always see it.",
    "使用聲明": "Notice",
    "我已了解": "I understand",
    "結束": "Quit",
    "提示：Esc 可立即停止播放。使用前請確認遊戲與服務規範，使用後果由使用者自行負責。": (
        "Tip: Esc stops playback immediately. Check game and service rules before use; you are "
        "responsible for how you use this tool."
    ),
    "重複的權限設定或衝突": "permission or conflict",
    "未授權（請先把此工具加入 S2P 的擴充工具清單）": (
        "unauthorized (add this tool to S2P's Extensions list first)"
    ),
    "與其他擴充工具搶同一支搖桿": "another extension tool controls the same stick",
    "S2P 未給予任何權限": "S2P granted no permission",
    "已在 S2P 中手動中斷": "disconnected manually in S2P",
    "此工具已有另一份在執行": "another copy of this tool is running",
    "協定版本不相容": "incompatible protocol version",
}

# The notice is laid out as short items: Tk cannot wrap Chinese text that has
# no spaces, so every Chinese line is short enough to fit on its own.
NOTICE = {
    "zh": {
        "intro": (
            "S2P-Joystick-Macro 是 S2P-XInput-Lite 的獨立擴充工具。",
            "透過 S2P 的擴充工具介面錄製與播放手把輸入，本身不建立虛擬手把。",
        ),
        "heading": "使用前請確認：",
        "items": (
            "使用本工具產生的操作與結果，由使用者自行負責。",
            "部分遊戲或線上服務禁止巨集、自動化或外部輸入，請先確認規範。",
            "在不允許的情況下使用，可能導致帳號受限。",
            "本工具不包含任何規避反作弊系統的功能。",
            "隨時可按 Esc 或「停止」結束播放。",
            "本工具停止、關閉或當機時，S2P 會立即釋放它的所有輸入。",
        ),
    },
    "en": {
        "intro": (
            "S2P-Joystick-Macro is an independent extension tool for S2P-XInput-Lite.",
            "It records and plays back controller input through S2P's Extensions "
            "interface and does not create a virtual controller of its own.",
        ),
        "heading": "Before you use it:",
        "items": (
            "You are responsible for how you use this tool and for the results.",
            "Some games and online services prohibit macros, automation or external "
            "input; check their rules first.",
            "Using it where it is not allowed may get your account restricted.",
            "This tool contains no feature to bypass any anti-cheat system.",
            "Press Esc or Stop to end playback at any time.",
            "When this tool stops, closes or crashes, S2P releases all of its input "
            "immediately.",
        ),
    },
}


class Translator:
    def __init__(self, language="zh"):
        self.language = language

    def __call__(self, text):
        if self.language == "en":
            return EN.get(text, text)
        return text

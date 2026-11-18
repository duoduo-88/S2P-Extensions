# 開發擴充工具

[English](development.md) · [S2P-Extensions](../README_zh-TW.md)

完整協定：S2P-XInput-Lite [`docs/extensions-ipc_zh-TW.md`](https://github.com/duoduo-88/S2P-XInput-Lite/blob/v0.8.2/docs/extensions-ipc_zh-TW.md)（協定 v1）。本文件說明如何用 `sdk/s2p_ext` 開發工具。

## 最小範例

```python
import time
from s2p_ext import AutoConnection, ExtensionClient

def factory():
    # 只宣告真正需要的權限與搖桿，避免和其他工具衝突
    return ExtensionClient("My Tool", "0.1.0", capabilities=("input",), sticks=())

connection = AutoConnection(factory, on_change=lambda state, detail: print(state, detail))
connection.start()
while connection.client is None:
    time.sleep(0.2)

client = connection.client
client.send_state(["A"])      # 按住 A；按住超過 1 秒時每 250 ms 重送一次（心跳）
time.sleep(0.1)
client.send_state([])         # 放開
connection.stop()             # 送出 bye；S2P 清除此工具輸入
```

## 規則摘要

| 項目 | 規則 |
|---|---|
| 辨識 | 使用者必須把工具 EXE 加入 S2P 的擴充工具清單；由 S2P 啟動時以環境變數權杖辨識 |
| 權限 | `input` 提交輸入（S2P 預設允許）；`read` 讀取控制器狀態（S2P 預設關閉） |
| 搖桿 | hello 的 `sticks` 宣告要獨占的搖桿；與其他工具重複時連線被拒（`conflict`） |
| 心跳 | 有輸入時至少每 1000 ms 送一則訊息，否則 S2P 清除輸入（連線保留） |
| 合併 | 按鍵 OR、扳機取最大值、搖桿實體優先 |
| 讀取 | `get_input` 回傳 S2P 合併擴充輸入「之前」的輸出，工具不會讀回自己的輸入 |
| 錯誤 | S2P 回覆 `error` 後會中斷連線；`AutoConnection` 會自動重試 |
| 背景啟動 | S2P 自動啟動已啟用工具時設 `S2P_EXTENSION_BACKGROUND=1`，工具應不跳出視窗 |
| 單一執行個體 | 「開啟」會再次啟動工具；工具應叫回原本的視窗而不是開第二份。新啟動的那份由 S2P 啟動，可以切換前景視窗，原本在執行的那份不行，所以新的那份要先呼叫 `AllowSetForegroundWindow(ASFW_ANY)` 再通知原本那份，然後結束。原本那份即使最小化或藏在系統匣，也要還原視窗、移到最前面並取得焦點。範例：`macro/s2p_macro/single_instance.py` 與 `MacroApp.show_window` |
| 更新檢查（必要） | 在 EXE 旁附上 `<EXE 名稱>.s2p.json`，寫明工具的 `name`、`version` 與 HTTPS 的 `update_url`，S2P 的 **檢查更新** 才能找到新版本。格式見 [工具清單檔與更新](https://github.com/duoduo-88/S2P-XInput-Lite/blob/v0.8.2/docs/extensions-ipc_zh-TW.md#工具清單檔與更新)。 |
| 跟著 S2P 關閉 | `welcome` 帶有 `host_pid`（S2P 視窗程序）。給 `AutoConnection` 傳 `on_host_exit`（內部使用 `ProcessExitWatcher`），觸發時結束工具；只重新啟動連線不會觸發 |

## 發佈

- 以 Python 開發，用 PyInstaller 打包成單一 EXE（範例：`macro/build.ps1`）。
- 把工具加進 `scripts/package_release.ps1` 的 `$tools` 清單，發佈 zip 的 `S2P-Extensions\` 內就會有它自己的資料夾。
  建置輸出放在 `dist\<工具名>\`，內含 `<工具名>.exe`、`README.md`、`README_zh-TW.md`；並在 `release/README*.md` 列出。
- 建置時依工具版本產生清單檔（範例：`macro/build.ps1` 中的 `scripts/tool_manifest.py manifest`），並放進 zip 內工具的資料夾。
  `scripts/package_release.ps1` 會再產生列出所有工具的 `dist\s2p-extensions-updates.json`；每次發佈 GitHub release
  都要把它和 zip 一起附上，因為所有清單檔的 `update_url` 都指向最新 release 的這個檔案。
- 在 `<原始碼資料夾>/manual/` 撰寫工具自己的手冊 `USER_GUIDE.md` 與 `USER_GUIDE_zh-TW.md`，截圖放在
  `manual/assets/`，並加入 `manual/USER_GUIDE*.md` 的工具清單。所有工具共通的內容（在 S2P 新增工具、權限、
  連線狀態）寫在共用手冊，不要寫進工具手冊。手冊不放進發佈 zip，所以會放進 zip 的 README 要用完整 GitHub 網址連到手冊。
- 第一次啟動時清楚說明用途、責任歸屬與遊戲規範注意事項。
- 不建立虛擬手把、不使用 DLL 注入或 Hook、不加入任何反作弊規避功能。

## 測試建議

- 單元測試用假的 `send`／`get_input` 取代 S2P（見 `tests/test_engine.py`）。
- 整合測試直接啟動 S2P 的 `ExtensionManager` 與真實 pipe（見 `tests/test_s2p_integration.py`）。
- 實機驗證請用 S2P 內建的「手把測試」觀察合併後的 XInput 輸出。
- 輸入要等 S2P 下一份報告與遊戲下一幀才會被讀到；步驟最短可以多短，見 [playback-timing_zh-TW.md](playback-timing_zh-TW.md) 的量測。

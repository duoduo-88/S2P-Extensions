# 開發擴充工具

完整協定：S2P-XInput-Lite `docs/extensions-ipc.md`（協定 v1）。本文件說明如何用 `sdk/s2p_ext` 開發工具。

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
| 單一執行個體 | 「開啟」會再次啟動工具；工具應叫回原本的視窗而不是開第二份 |

## 發佈

- 以 Python 開發，用 PyInstaller 打包成單一 EXE（範例：`macro/build.ps1`）。
- 第一次啟動時清楚說明用途、責任歸屬與遊戲規範注意事項。
- 不建立虛擬手把、不使用 DLL 注入或 Hook、不加入任何反作弊規避功能。

## 測試建議

- 單元測試用假的 `send`／`get_input` 取代 S2P（見 `tests/test_engine.py`）。
- 整合測試直接啟動 S2P 的 `ExtensionManager` 與真實 pipe（見 `tests/test_s2p_integration.py`）。
- 實機驗證請用 S2P 內建的「手把測試」觀察合併後的 XInput 輸出。

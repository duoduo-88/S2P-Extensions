# S2P-Extensions

[English](README.md) · [使用手冊](manual/USER_GUIDE_zh-TW.md) · [S2P-Joystick-Macro](macro/README_zh-TW.md) · [開發擴充工具](docs/development_zh-TW.md) · [S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite)

[S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite) 的選用擴充工具集合。每個工具都是獨立程式，
透過 S2P 的「擴充工具」介面（Windows Named Pipe，協定 v1）提交輸入或讀取控制器狀態；
S2P 仍是唯一的虛擬 XInput 手把輸出。S2P 不需要這些工具也能正常運作。

| 目錄 | 內容 | 狀態 |
|---|---|---|
| `sdk/` | 共用 IPC Client（`s2p_ext`），只用標準函式庫 | 可用 |
| `macro/` | S2P-Joystick-Macro：錄製、播放、編輯手把按鍵與搖桿操作 | 可用（v0.1.0） |
| `manual/` | 共用使用手冊；各工具的手冊在各自資料夾內（`macro/manual/`） | 可用 |
| `docs/` | 開發文件 | 可用 |
| `release/`、`scripts/` | 發佈 zip 內的說明文件與打包腳本 | 可用 |
| `tests/` | 單元測試與搭配 S2P 的整合測試 | 可用 |

多設備輸入工具與其他範例尚未實作，目錄會在開始實作時才建立。

## 責任歸屬

擴充工具由本專案提供，與 S2P-XInput-Lite 主程式分開發佈。使用擴充工具所產生的操作與結果由使用者自行負責；
部分遊戲或線上服務禁止外部輸入或自動化操作，使用前請先確認相關規範。本專案不提供任何規避反作弊系統的功能。

## 發佈套件

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_release.ps1
```

會先跑測試、建置每個工具，再產生 `dist\S2P-Extensions-v<VERSION>.zip`。zip 內只有一個 `S2P-Extensions\`
資料夾，裡面是 `release/` 的使用說明，以及每個工具各自的子資料夾
（例如 `S2P-Extensions\S2P-Joystick-Macro\S2P-Joystick-Macro.exe` 與它的說明）。發佈版本號寫在 `VERSION`。

## 測試

```powershell
python -m unittest discover -s tests
```

`tests/test_s2p_integration.py` 會連到 S2P-XInput-Lite 的真實 pipe 伺服器；需要把 S2P-XInput-Lite 原始碼放在
本資料夾旁（`..\S2P-XInput-Lite\src`），或設定環境變數 `S2P_XINPUT_LITE_SRC`，否則自動略過。

## 開發新工具

見 [docs/development_zh-TW.md](docs/development_zh-TW.md)。

# S2P-Extensions

[English](README.md) · [S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite) · [原始碼](https://github.com/duoduo-88/S2P-Extensions)

[S2P-XInput-Lite](https://github.com/duoduo-88/S2P-XInput-Lite) 的選用擴充工具。每個資料夾是一個獨立工具，
透過 S2P 的「擴充工具」介面送出輸入或讀取控制器狀態；S2P 仍是唯一的虛擬 XInput 手把，不需要這些工具也能正常運作。

## 使用手冊

使用手冊放在線上：

- [S2P-Extensions 使用手冊](https://github.com/duoduo-88/S2P-Extensions/blob/main/manual/USER_GUIDE_zh-TW.md)：安裝、在 S2P 連接工具、權限與疑難排解。
- 每個工具各有自己的手冊：

| 資料夾 | 工具 | 手冊 |
|---|---|---|
| `S2P-Joystick-Macro\` | 錄製、播放、編輯手把按鍵與搖桿操作 | [使用手冊](https://github.com/duoduo-88/S2P-Extensions/blob/main/macro/manual/USER_GUIDE_zh-TW.md) |

## 使用方式

1. 把整個 `S2P-Extensions` 資料夾放在任意位置（各工具的設定會存在自己的資料夾內）。
2. 開啟 S2P-XInput-Lite →「擴充工具」，勾選「啟用擴充工具」，按「新增工具...」選擇要用的工具 EXE。
   最多可同時啟用 4 個工具。
3. 依各工具說明在「權限」勾選需要的權限，再按「開啟」。
4. 已啟用的工具會在 S2P 連線開始時自動於背景啟動；關閉 S2P 時，工具也會一起關閉。
5. 請讓每個工具的 `.s2p.json` 檔和 EXE 放在一起，S2P 的「檢查更新」會讀取它來尋找新版本。

## 責任歸屬

擴充工具由本專案提供，與 S2P-XInput-Lite 主程式分開發佈。使用擴充工具所產生的操作與結果由使用者自行負責；
部分遊戲或線上服務禁止外部輸入或自動化操作，使用前請先確認相關規範。本專案不提供任何規避反作弊系統的功能。

## 授權

S2P-Extensions 採用 [GNU General Public License v3.0](LICENSE) 授權，與 S2P-XInput-Lite 相同。
你可以依此條款使用、修改與再散布；散布修改後的版本時，也必須以 GPL-3.0 授權並提供原始碼。

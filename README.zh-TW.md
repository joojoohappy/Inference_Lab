# Inference Lab

**學會它、跑起來、看懂它、改進它。**

[English](README.md)

Inference Lab 是一個在本機執行的互動式工作台，用來學習 AI 推論工程。你會在自己的電腦上跑真的模型、用誠實的方法做
benchmark、閱讀實際執行的程式碼、一次只改一個變數做比較，最後用證據為你的決策辯護。每個數字都會標示來源，沒有任何模擬結果。

![實驗室](docs/screenshots/zh-TW-lab.png)

## 示範影片

[![Inference Lab 示範影片（3:33）](docs/media/demo-poster.jpg)]

https://github.com/user-attachments/assets/87d40f50-78f2-4b11-9b2d-35761728d2e1




## 快速開始（CPU，可離線）

需求：Python 3.10 以上（已在 3.13 測試）、Node 20 以上（已在 22 測試，用來建置 UI）。

```bash
git clone <this repo> inference-lab && cd inference-lab
python -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu    # 有 GPU 的話請改裝對應的 CUDA 版本
pip install -e ".[inference,dev]"
(cd frontend && npm ci && npm run build)
inference-lab ui            # → http://127.0.0.1:8765
```

介面預設為**英文**。請用右上角的語言切換按鈕切換成繁體中文；你的選擇會記在這台電腦上，切換語言不會影響你的進度。
程式碼、指令參數、模型 ID、設定鍵和路徑都保留原文，不會被翻譯。

## 裡面有什麼

| 區域 | 你可以做的事 |
|---|---|
| **實驗室** | 掃描你的機器，查看任務、技能和最近的結果 |
| **模型車庫** | 用 ID 或網址檢查 Hugging Face 模型（只讀中繼資料）、估算記憶體、檢查相容性；經你核准才會下載；試跑推論 |
| **任務控制中心** | 七個任務，從「認識你的機器」到「為你的決策辯護」 |
| **程式碼探索** | 閱讀每個步驟實際執行的原始碼，附行號範圍與四種解說深度 |
| **研究檔案館** | 一手來源（論文、官方文件）與查核紀錄；KV cache 與延遲/吞吐量互動圖解 |
| **實驗競技場** | 啟動伺服器、跑 benchmark、比較兩次執行、查看根據證據的建議 |
| **工程日誌** | 每一次實驗與執行（包含失敗的）、筆記、匯入/匯出、中英文報告 |

模式：**觀察**（看核准的流程自動執行）、**引導**（你自己執行每一步，有提示）、**專家**（直接給所有參數）。
三種模式使用同一套執行與驗證引擎。

## 資料來源標示

| 標示 | 意義 |
|---|---|
| `LIVE_MEASURED`（現場實測） | 在這台機器上由這個 repository 的程式碼量測 |
| `IMPORTED`（匯入，來源未驗證） | 從結構正確、checksum 相符的檔案匯入；**來源沒有經過驗證** |
| `DEMO_SAMPLE`（示範資料） | 教學用的合成資料，絕不當作證據 |
| `NOT_RUN`（未執行） | 沒有執行（通常是缺少 GPU 等能力） |
| `FAILED`（失敗） | 有執行但失敗；會保留並顯示 |

報告只會把「現場實測」的結果當作結論。checksum 相符只代表匯入的檔案在匯出後沒被改過，不能證明數字真的量測過，
因為任何人都能自己寫一筆紀錄再算出 checksum。所以匯入的紀錄會在報告中另列一節並標示，比較時也會出現警告。
要採用別人的 benchmark，請先在自己的機器上重跑。

benchmark 請求必須回傳 HTTP 200、串流出生成文字，並以 `[DONE]` 結尾，才算成功。token 數取自伺服器回報的 `usage`；
伺服器沒有回報時，TPOT 和 tokens/s 會留空，不會用 chunk 數來估計。

## 命令列

命令列和介面使用同一套動作：

```bash
inference-lab hardware
inference-lab prepare-tiny
inference-lab infer --prompt "The KV cache stores" --max-new-tokens 16
inference-lab bench --concurrency 1 --trials 3
inference-lab bench --concurrency 4 --trials 3
inference-lab experiments
inference-lab compare <baseline-id> <candidate-id>
inference-lab report <id> <id> --lang zh-TW
```

## GPU 路徑（選用）

如果有 NVIDIA GPU、NVIDIA Container Toolkit 和 Docker，任務 04 可以啟動 vLLM（`vllm/vllm-openai`，只綁定 127.0.0.1）。
請參考 `docker/vllm/docker-compose.yml`。建置環境沒有 GPU，所以這條路徑**沒有實際執行過**。沒有 GPU 時，
這些步驟會顯示為「未執行」，不會卡住你的進度。

## 透過 llmbench 使用 llama.cpp（CPU 或 Adreno GPU）

如果 llm-inference-bench 專案（llmbench）放在這個 repo 旁邊，Inference Lab 會直接使用它的 llama.cpp 執行檔
（`tools/llama-cpu`、`tools/llama-adreno`）和 GGUF 模型（`models/*.gguf`），不會複製或修改。放在別處時請設定
`INFERENCE_LAB_LLMBENCH_DIR`。模型名稱寫成 `gguf:<檔名>`。

```bash
inference-lab bench --kind llamacpp-adreno --model gguf:qwen3-4b-instruct-2507-Q4_0 --port 8870 --max-tokens 64
```

實驗競技場也有這兩個引擎。在 Snapdragon X 筆電上的實測結果請見 [docs/LOCAL_TEST_REPORT.md](docs/LOCAL_TEST_REPORT.md)。

## 部署：單一使用者、只在本機

Inference Lab 是本機、單一使用者的工作台，**沒有身分驗證、沒有每人資料隔離、也沒有工作配額**：任何連得到這個
port 的人都能讀取你的實驗、啟動耗資源的工作、重設你的進度。Host header 檢查只能擋網頁發起的 DNS rebinding，
不是存取控制。

* 預設只監聽 `127.0.0.1`。若要綁定其他位址，`inference-lab ui` 必須加上 `--allow-remote`
  （或設定 `INFERENCE_LAB_ALLOW_REMOTE=1`），否則會拒絕啟動。
* 使用 Docker 時只發布到 loopback：`docker run -p 127.0.0.1:8765:8765 ...`。
* 不要放到公開網路或公開的反向代理後面。若要給多人使用，必須先做身分驗證、每人資料隔離、工作配額與隔離的 worker。

每個動作都有時間上限。超過上限，或呼叫 `POST /api/runs/{id}/cancel` 時，這次執行會立即標為失敗，
較長的動作（benchmark、啟動伺服器）會在下一個檢查點停止。單次 `generate` 或已經開始的下載無法中斷，
會在背景跑完，但結果會被捨棄。同時最多執行 `INFERENCE_LAB_MAX_CONCURRENT_RUNS` 個動作（預設 4）。

## 選用的 AI 家教

不需要任何付費 API，家教也能運作（使用人工整理的解說和 docstring）。若要接上模型，請看英文 README 的
「Optional AI tutor」一節的環境變數設定。AI 永遠不會決定任務是否完成、不會拿到 shell，而且只會收到去除密鑰後的文字。

## 測試

```bash
pytest                                   # 後端：共 162 個測試；沒有 GPU 或 llmbench 時有 4 個標為 NOT RUN 並略過
cd frontend && npm test                  # 元件與 i18n 測試
npm run i18n:check                       # 檢查 en / zh-TW 的 key 是否一致
npx playwright test                      # 真實瀏覽器：語言、完整任務流程、核准機制、截圖
```

GitHub Actions（`.github/workflows/ci.yml`）會在每次 push 和 pull request 執行後端測試、前端 build／單元測試／i18n
檢查、Playwright 流程與 Docker 映像建置。GPU 和 llama.cpp 測試需要 CI 沒有的硬體，在 CI 中會標為 NOT RUN，
改由有日期的手動報告 [docs/LOCAL_TEST_REPORT.md](docs/LOCAL_TEST_REPORT.md) 記錄。各份報告中的測試數量反映當時的程式碼與機器。

## 文件

設計文件在 `docs/`（英文）：架構稽核、架構、任務結構、執行與驗證、程式碼探索、實驗流程、已知限制、路線圖與實作報告。

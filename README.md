# Goldium — NSE Stock Screener

Monorepo with a **FastAPI backend** and **React frontend** that screens Nifty 50 stocks using yfinance and technical indicators (RSI, MACD, SMA).

**Not financial advice.** For education and screening only.

## Project layout

```
Goldium/
├── Backend/          # FastAPI + yfinance screener API
└── frontend/         # React dashboard (Vite)
```

## Setup

### Backend

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Run (two terminals)

**Terminal 1 — API (port 8000):**

```bash
cd Backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — React (port 5173):**

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** for the dashboard. API docs: **http://127.0.0.1:8000/docs**

The Vite dev server proxies `/api` and `/health` to the backend.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness check |
| `GET /api/indices` | Available watchlists (Nifty 50/100/200/500, all NSE EQ) |
| `GET /api/scan?index=nifty50&min_score=5&limit=100` | Scan selected index for bullish stocks |
| `GET /api/stock/{symbol}` | Single stock detail (e.g. `RELIANCE.NS`) |
| `GET /api/ipo?months=2` | Recent IPO listings (1–2 months) with listing performance |
| `GET /api/ipo-research/...` | IPO ML dataset + scikit-learn runs — see [docs/IPO_RESEARCH.md](docs/IPO_RESEARCH.md) |
| `GET /api/market-indices` | NIFTY / BANKNIFTY / SENSEX quotes (1Y bars cached in DB) |
| `GET /api/market-indices/{id}/chart` | 1Y daily chart (`nifty`, `banknifty`, `sensex`) |
| `GET /api/ipo/{symbol}/llm-research` | Cached IPO subscription JSON (from LLM) |
| `POST /api/ipo/{symbol}/llm-research` | Generate via LLM, validate, store in SQLite |

## Screener filters

All five screeners (Year Breakout, Multi-Year Breakout, Darvas Box, Golden, Weekly)
share a liquidity gate — `min_price` (default ₹20) and `min_avg_turnover_cr`
(default ₹1 Cr over 20 sessions) — so penny/illiquid names are rejected before
pattern logic runs. Additional per-screener filters (RSI band, SMA50/SMA200
uptrend, breakout freshness, YoY growth minimums, 52-week-high proximity) are
configurable from each screener page; parameter schemas live in
`Backend/app/services/scan_definitions.py` and render in the UI automatically.
Every rejection carries a human-readable reason visible in the scan log.

## IPO intel (GMP + subscriptions)

`/ipo-intel` shows grey-market premium and live bidding data scraped with a
headless browser (Playwright) from InvestorGain and Chittorgarh.
Run it manually with **Scrape now** or let the daily `ipo_intel` schedule
(10:15 IST, Schedule page) refresh it. After `pip install`, the scraper
uses your installed **Chrome** or **Edge** automatically — no separate browser
download. If neither is available, run `playwright install chromium` once.

Optional: `SCRAPER_BROWSER_CHANNEL` (`chrome`, `msedge`, or `chromium`) to
force a specific browser; `SCRAPER_PROXY` (e.g. `http://proxy:8080`) for a
proxy.

## Data vendors

Every externally sourced feature routes through the vendor registry
(`Backend/app/services/vendors/registry.py`); swap a feature's source by
setting its env override (e.g. `VENDOR_FUNDAMENTALS=yfinance`) and
restarting. The **Settings → Data sources** panel shows the live
feature → vendor map.

The Upstox Analytics API (set `UPSTOX_ANALYTICS_TOKEN` in `Backend/.env`,
read-only token from https://account.upstox.com/developer/apps) powers:
fundamentals (quarterly income statements), shareholding pattern, stock news
for followed symbols, and the authoritative IPO catalog used to verify
scraped GMP rows (fuzzy name match → "✓ Upstox" badge on `/ipo-intel`).
Follow a stock from its detail modal (🔔) to feed the dashboard News widget.

## Configuration

- Indicator thresholds: `Backend/app/config.py`
- Index symbols: fetched from NSE archives (`nsearchives.nseindia.com`), cached 24h in `Backend/data/cache/`
- Scan `index` values: `nifty50`, `nifty100`, `nifty200`, `nifty500`, `nse_all`
- CORS origins: set `CORS_ORIGINS` (default allows Vite on port 5173)
- **IPO LLM research** (Gemini by default):
  - `GEMINI_API_KEY` — required for `POST /api/ipo/{symbol}/llm-research`
  - `GEMINI_MODEL` — optional (default `gemini-2.5-flash`; avoid `gemini-2.0-flash` if you hit 429 quota errors)
  - `LLM_PROVIDER` — optional (default `gemini`; swap provider in `Backend/app/services/llm/` later)

Copy `Backend/.env.example` to `Backend/.env` and set `GEMINI_API_KEY`. The API loads this file on startup via `python-dotenv`.

## Limitations

- Nifty 50 scan ~1–2 min; Nifty 500 several minutes; **all NSE (~2100 stocks) can take 30–60+ minutes**.
- Scan results cached 15 minutes per index on the backend.
- yfinance data may be delayed or incomplete.

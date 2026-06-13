# Stock AI (`lm/`)

Self-contained RAG stock-analysis service. Completely separate from `Backend/` and `frontend/`.

**Components**

| Component | What it provides |
|---|---|
| Ollama `deepseek-r1:1.5b` | Generates the analysis report |
| Ollama `qwen3-embedding` | Embeds questions and news for semantic search |
| Qdrant (`stock_news` collection) | Retrieves relevant news/document chunks |
| Postgres `gcc_revamp` (reused from `Backend/.env`) | Prices, fundamentals, holdings from the screener tables |
| FastAPI + built-in UI | `/api/*` endpoints and the search UI at `/` |

## Run

Use the existing Backend venv — it has all dependencies installed (the system
pip index is not always reachable, so prefer this interpreter):

```powershell
cd C:\Users\chauach\Downloads\gcc\lm
$py = "..\Backend\.venv\Scripts\python.exe"

& $py scripts\check_services.py      # verify ollama / qdrant / db
& $py scripts\ingest_news.py         # seed Qdrant with sample news (once)

& $py -m uvicorn app.main:app --port 8010 --reload
```

Open **http://localhost:8010** — search a stock (e.g. `RELIANCE`), pick it from
the dropdown, optionally type a question, press **Analyze**.

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Status of ollama, qdrant, and which DB is in use |
| `GET /api/stocks/search?q=rel` | Symbol/company autocomplete |
| `POST /api/analyze` `{"symbol": "TCS", "question": "..."} ` | Full report: DB data + RAG context + LLM analysis |
| `POST /api/ask` `{"question": "..."}` | Free-form RAG question over the news collection |
| `POST /api/news/ingest` `{"ticker","title","text","source","date"}` | Add a document to Qdrant |
| `GET /api/pulse/news?limit=30` | Zerodha Pulse headlines with AI summaries + last-run status |
| `POST /api/pulse/refresh` | Manually fetch the Pulse feed and summarize new items now |
| `GET /api/admin/check` / `POST /api/admin/ingest-samples` | Component checks / sample news (also buttons in the UI) |
| `GET /api/inspect/overview` | Which Postgres lm uses + databases on the server + table row counts + Qdrant collection stats |
| `GET /api/inspect/vectors?offset=&limit=` | Browse embedded documents with a preview of each stored embedding vector |
| `GET /api/inspect/pg-table/{table}?offset=&limit=` | Browse rows of an lm/screener table (whitelisted) |

## Configuration (`lm/.env`)

- `DATABASE_URL` — leave unset to reuse the Backend's database (`Backend/.env` → Postgres `gcc_revamp`, where the 2.1M-row price history lives). Set it to point anywhere else, e.g. the empty `stock_ai` DB once you load data into it. Check `/api/health` to see which source is active.
- `OLLAMA_MODEL` — swap to a bigger model (e.g. `deepseek-r1:32b`) any time for better reports.
- `LM_PORT` — default 8010 so it never collides with the main backend (8000) or frontend dev ports.

Helper scripts: `scripts/inspect_dbs.py` and `scripts/probe_backend_db.py` show
what tables/rows each database holds; `scripts/smoke_test.py` runs an
end-to-end API test against a running server.

## Viewing the data in the React UI

The frontend **Database Explorer** page (⚙ settings → Database) has a
**"🤖 Stock AI — Vectors & DB"** tab that calls the `/inspect/*` endpoints above
through the `/lm-api` proxy. It shows the active Postgres (`gcc_revamp`, shared
with the main app), every database on the server (so the empty `stock_ai` is
visible too), the lm-managed tables with row counts (browsable), and the Qdrant
embeddings — each document expandable to preview its actual 4096-dim vector.

## Zerodha Pulse news (AI-summarized, scheduled)

On startup, and every `PULSE_REFRESH_MINUTES` (default 30), the service pulls
https://pulse.zerodha.com/feed.php, summarizes up to `PULSE_MAX_ITEMS` (default 10)
new headlines with the local LLM, and stores them in `lm_pulse_news` /
`lm_pulse_runs` tables in the stock database. The React dashboard's
"Pulse News — AI Summarized" widget shows them with the source name, an ✨ AI
badge, and a **⟳ Fetch now** button for manual runs.

## Adding your own news

Create a JSON list of `{ticker, title, text, source, date}` objects and run
`python scripts/ingest_news.py --file mynews.json`, or POST to `/api/news/ingest`.

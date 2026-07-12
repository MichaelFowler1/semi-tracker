# Semiconductor tracker (SMH ∪ SOXX)

A small local Flask app that tracks every stock held by the SMH (VanEck) and
SOXX (iShares) semiconductor ETFs — deduplicated, so overlapping names appear
once with a "Both" badge — and shows valuation and analyst growth metrics in a
sortable dashboard.

## Run it

```powershell
cd C:\Users\Micke\semi-tracker
.venv\Scripts\python.exe app.py
```

Then open http://127.0.0.1:5057

## Columns

| Column | Source | Notes |
|---|---|---|
| P/E | Yahoo Finance | trailing twelve months |
| Fwd P/E | Yahoo Finance | price / next-year consensus EPS |
| PEG | Yahoo Finance | trailing PEG ratio |
| Growth 1Y | Yahoo Finance | analyst consensus next-year EPS growth (`+1y`), Finviz "EPS next Y" as fallback |
| Growth 5Y | Finviz | "EPS next 5Y" — annualized long-term analyst estimate |

"—" means the metric doesn't exist for that stock — usually negative or
near-zero earnings (P/E and PEG are undefined then), or no analyst long-term
estimate.

## Design decisions (why it's built this way)

- **Why Finviz for 5-year growth:** Yahoo stopped publishing long-term (5-yr)
  growth estimates for nearly all tickers after switching data providers in
  2024 — verified empirically before building. Finviz's "EPS next 5Y" is the
  standard free replacement.
- **Why holdings are scraped, not hardcoded:** ETF constituents change on
  rebalances. Each refresh pulls the current holdings from
  stockanalysis.com's ETF pages, so the list stays correct without edits.
- **Why a cache file (`data/cache.json`):** a full refresh makes ~60 HTTP
  requests and takes about a minute (Finviz is fetched slowly on purpose —
  it rate-limits scrapers). Caching means restarts are instant, and you only
  refetch when you click "Refresh data".
- **Why no API keys:** everything comes from public pages/endpoints
  (yfinance scrapes Yahoo's own JSON API). Trade-off: these are unofficial
  sources, so a site redesign can break a column until the regex/field name
  is updated.

## Files

- `fetcher.py` — data layer: holdings scrape, Yahoo + Finviz fetch, cache write.
  Also runnable standalone: `.venv\Scripts\python.exe fetcher.py`
- `app.py` — Flask server + tiny JSON API (`/api/data`, `/api/refresh`)
- `templates/index.html` — the dashboard (vanilla JS, no build step)
- `data/cache.json` — last fetched snapshot with timestamp

"""Data layer for the semiconductor tracker.

Sources:
- Holdings:  stockanalysis.com ETF holdings pages (SMH, SOXX)
- Valuation: Yahoo Finance via yfinance — price, market cap, trailing P/E,
  forward P/E, PEG, next-year EPS growth
- 5y growth: Finviz "EPS next 5Y" — Yahoo discontinued long-term growth
  estimates in 2024, so this column needs a second source

A refresh runs in a background thread (started by app.py), reports progress
through the module-level `progress` dict, and writes the result to
data/cache.json so restarts don't refetch.
"""

import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
import yfinance as yf

DATA_FILE = Path(__file__).parent / "data" / "cache.json"
ETFS = ("SMH", "SOXX")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
# Non-holding links that appear on the holdings page with the same href shape
NAV_LINKS = {"SCREENER", "COMPARE", "INDUSTRY"}
FINVIZ_DELAY_S = 0.7  # stay polite; finviz rate-limits aggressive scrapers

progress = {"running": False, "phase": "", "done": 0, "total": 0, "error": None}
_progress_lock = threading.Lock()


def _tick(**kwargs):
    with _progress_lock:
        progress.update(**kwargs)


def _tick_done():
    with _progress_lock:
        progress["done"] += 1


def fetch_holdings(etf: str) -> list:
    url = f"https://stockanalysis.com/etf/{etf.lower()}/holdings/"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    syms = re.findall(r'href="/stocks/([a-zA-Z.\-]+)/"', r.text)
    seen = dict.fromkeys(s.upper() for s in syms)
    # The page mixes nav links (screener, earnings-calendar, …) into the same
    # href shape; real tickers are 1-5 letters plus an optional class suffix.
    return [s for s in seen
            if s not in NAV_LINKS and re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", s)]


def fetch_yahoo(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    info = t.info

    growth_1y = None
    try:
        ge = t.growth_estimates
        if ge is not None and "+1y" in ge.index:
            v = ge.loc["+1y", "stockTrend"]
            if v is not None and not math.isnan(v):
                growth_1y = float(v)
    except Exception:
        pass

    return {
        "name": info.get("shortName") or info.get("longName") or symbol,
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "peg": info.get("trailingPegRatio"),
        "growth_1y": growth_1y,
    }


def fetch_finviz(symbol: str) -> dict:
    """Return {'growth_5y': float|None, 'growth_1y': float|None} as fractions."""
    r = requests.get(f"https://finviz.com/quote.ashx?t={symbol}",
                     headers=UA, timeout=30)
    r.raise_for_status()
    table = r.text.split("snapshot-table2", 1)
    if len(table) < 2:
        return {"growth_5y": None, "growth_1y": None}
    cells = re.findall(r"<td[^>]*>(.*?)</td>", table[1], re.S)
    texts = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

    def pct_after(label):
        # Finviz lays the table out as label/value cell pairs; some labels
        # (EPS next Y) appear twice — once as dollars, once as percent.
        for i, txt in enumerate(texts[:-1]):
            if txt == label and texts[i + 1].endswith("%"):
                try:
                    return float(texts[i + 1].rstrip("%")) / 100.0
                except ValueError:
                    return None
        return None

    return {"growth_5y": pct_after("EPS next 5Y"),
            "growth_1y": pct_after("EPS next Y")}


def load_cache():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return None


def refresh():
    with _progress_lock:
        if progress["running"]:
            return
        progress.update(running=True, phase="holdings", done=0, total=0,
                        error=None)
    try:
        holdings = {etf: fetch_holdings(etf) for etf in ETFS}
        symbols = sorted(set().union(*holdings.values()))

        _tick(phase="yahoo", total=len(symbols), done=0)

        def yahoo_safe(sym):
            try:
                return fetch_yahoo(sym)
            except Exception:
                return {"name": sym, "price": None, "market_cap": None,
                        "pe": None, "forward_pe": None, "peg": None,
                        "growth_1y": None}
            finally:
                _tick_done()

        with ThreadPoolExecutor(max_workers=8) as ex:
            yahoo = dict(zip(symbols, ex.map(yahoo_safe, symbols)))

        _tick(phase="finviz", total=len(symbols), done=0)
        finviz = {}
        for sym in symbols:
            try:
                finviz[sym] = fetch_finviz(sym)
            except Exception:
                finviz[sym] = {"growth_5y": None, "growth_1y": None}
            _tick_done()
            time.sleep(FINVIZ_DELAY_S)

        rows = []
        for sym in symbols:
            y, f = yahoo[sym], finviz[sym]
            rows.append({
                "symbol": sym,
                "etfs": [etf for etf in ETFS if sym in holdings[etf]],
                **y,
                # Yahoo's analyst consensus first, finviz as fallback
                "growth_1y": y["growth_1y"] if y["growth_1y"] is not None
                             else f["growth_1y"],
                "growth_5y": f["growth_5y"],
            })

        DATA_FILE.parent.mkdir(exist_ok=True)
        DATA_FILE.write_text(json.dumps({
            "updated": datetime.now(timezone.utc).isoformat(),
            "rows": rows,
        }, indent=1))
    except Exception as e:
        _tick(error=f"{type(e).__name__}: {e}")
    finally:
        _tick(running=False, phase="")


if __name__ == "__main__":
    refresh()
    if progress["error"]:
        raise SystemExit(progress["error"])
    print(f"Wrote {DATA_FILE}")

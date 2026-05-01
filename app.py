from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import time
import threading

app = Flask(__name__)
CORS(app)

# Simple in-memory cache — avoids re-hitting Yahoo for same ticker
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 600  # 10 minutes

def get_cached(ticker):
    with _cache_lock:
        entry = _cache.get(ticker)
        if entry and (time.time() - entry['ts']) < CACHE_TTL:
            return entry['data']
    return None

def set_cached(ticker, data):
    with _cache_lock:
        _cache[ticker] = {'data': data, 'ts': time.time()}

def fetch_with_retry(ticker, retries=3, delay=2):
    last_err = None
    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            info = t.info
            if not info or len(info) < 5:
                raise ValueError("Empty response from Yahoo — likely rate limited")
            return t, info
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    raise last_err

@app.route("/")
def index():
    return jsonify({"status": "dead simple money API running"})

@app.route("/api/quote")
def quote():
    ticker = request.args.get("ticker", "").upper().strip()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400

    cached = get_cached(ticker)
    if cached:
        return jsonify(cached)

    try:
        t, info = fetch_with_retry(ticker)

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return jsonify({"error": f"No price data for {ticker} — check the symbol"}), 404

        name = info.get("longName") or info.get("shortName") or ticker
        shares_b = round((info.get("sharesOutstanding") or 0) / 1e9, 3)

        fcf_b = None
        try:
            cf = t.cashflow
            if cf is not None and not cf.empty:
                op_cf = None
                capex = None
                for label in cf.index:
                    l = str(label).lower()
                    if "operating" in l and "cash" in l:
                        op_cf = float(cf.loc[label].iloc[0])
                    if "capital expenditure" in l or "capex" in l:
                        capex = float(cf.loc[label].iloc[0])
                if op_cf is not None and capex is not None:
                    fcf_b = round((op_cf + capex) / 1e9, 2)
                elif op_cf is not None:
                    fcf_b = round(op_cf / 1e9, 2)
        except Exception:
            pass

        if fcf_b is None:
            fcf_info = info.get("freeCashflow")
            if fcf_info:
                fcf_b = round(fcf_info / 1e9, 2)

        total_debt = info.get("totalDebt") or 0
        cash = info.get("totalCash") or 0
        net_debt_b = round((total_debt - cash) / 1e9, 2)

        suggested_g1 = None
        rev_growth = info.get("revenueGrowth")
        if rev_growth:
            suggested_g1 = round(rev_growth * 100, 1)

        market_cap_b = round((info.get("marketCap") or 0) / 1e9, 1)

        result = {
            "ticker": ticker,
            "name": name,
            "price": round(float(price), 2),
            "shares_b": shares_b,
            "fcf_b": fcf_b,
            "net_debt_b": net_debt_b,
            "market_cap_b": market_cap_b,
            "suggested_g1": suggested_g1,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
        }

        set_cached(ticker, result)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import requests
import time
import threading

app = Flask(__name__)
CORS(app)

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/api/v3"

# In-memory cache — 10 min TTL
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 600

def get_cached(ticker):
    with _cache_lock:
        entry = _cache.get(ticker)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL:
            return entry["data"]
    return None

def set_cached(ticker, data):
    with _cache_lock:
        _cache[ticker] = {"data": data, "ts": time.time()}

def fmp_get(path, params={}):
    params["apikey"] = FMP_KEY
    r = requests.get(f"{FMP_BASE}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

@app.route("/")
def index():
    return jsonify({"status": "dead simple money API running"})

@app.route("/api/quote")
def quote():
    ticker = request.args.get("ticker", "").upper().strip()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400
    if not FMP_KEY:
        return jsonify({"error": "FMP_API_KEY not set in environment"}), 500

    cached = get_cached(ticker)
    if cached:
        return jsonify(cached)

    try:
        # Profile — price, name, shares, market cap
        profile_data = fmp_get(f"/profile/{ticker}")
        if not profile_data or isinstance(profile_data, dict) and "Error" in str(profile_data):
            return jsonify({"error": f"No data for {ticker}"}), 404
        p = profile_data[0] if isinstance(profile_data, list) else profile_data

        price = p.get("price")
        if not price:
            return jsonify({"error": f"No price found for {ticker}"}), 404

        name = p.get("companyName") or ticker
        shares_b = round((p.get("sharesOutstanding") or 0) / 1e9, 3)
        market_cap_b = round((p.get("mktCap") or 0) / 1e9, 1)
        sector = p.get("sector") or ""
        industry = p.get("industry") or ""
        beta = p.get("beta")

        # Key metrics — FCF per share, net debt
        fcf_b = None
        net_debt_b = None
        suggested_g1 = None

        try:
            km = fmp_get(f"/key-metrics/{ticker}", {"limit": 1})
            if km and isinstance(km, list) and len(km) > 0:
                k = km[0]
                fcf_ps = k.get("freeCashFlowPerShare")
                if fcf_ps and shares_b:
                    fcf_b = round(fcf_ps * shares_b, 2)
                net_debt_ps = k.get("netDebtToEBITDA")  # fallback
                rev_ps = k.get("revenuePerShare")
        except Exception:
            pass

        # Cash flow statement for FCF fallback
        if fcf_b is None:
            try:
                cf = fmp_get(f"/cash-flow-statement/{ticker}", {"limit": 1})
                if cf and isinstance(cf, list) and len(cf) > 0:
                    c = cf[0]
                    op_cf = c.get("operatingCashFlow") or 0
                    capex = c.get("capitalExpenditure") or 0
                    fcf_b = round((op_cf + capex) / 1e9, 2)
            except Exception:
                pass

        # Balance sheet for net debt
        try:
            bs = fmp_get(f"/balance-sheet-statement/{ticker}", {"limit": 1})
            if bs and isinstance(bs, list) and len(bs) > 0:
                b = bs[0]
                total_debt = (b.get("shortTermDebt") or 0) + (b.get("longTermDebt") or 0)
                cash = (b.get("cashAndCashEquivalents") or 0) + (b.get("shortTermInvestments") or 0)
                net_debt_b = round((total_debt - cash) / 1e9, 2)
        except Exception:
            pass

        # Revenue growth for suggested g1
        try:
            inc = fmp_get(f"/income-statement/{ticker}", {"limit": 3})
            if inc and isinstance(inc, list) and len(inc) >= 2:
                rev_new = inc[0].get("revenue") or 0
                rev_old = inc[-1].get("revenue") or 1
                yrs = len(inc) - 1
                if rev_old > 0 and yrs > 0:
                    cagr = ((rev_new / rev_old) ** (1 / yrs) - 1) * 100
                    suggested_g1 = round(cagr, 1)
        except Exception:
            pass

        result = {
            "ticker": ticker,
            "name": name,
            "price": round(float(price), 2),
            "shares_b": shares_b,
            "fcf_b": fcf_b,
            "net_debt_b": net_debt_b,
            "market_cap_b": market_cap_b,
            "suggested_g1": suggested_g1,
            "sector": sector,
            "industry": industry,
            "beta": beta,
        }

        set_cached(ticker, result)
        return jsonify(result)

    except requests.HTTPError as e:
        return jsonify({"error": f"FMP API error: {e.response.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

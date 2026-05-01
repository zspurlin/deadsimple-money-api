from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return jsonify({"status": "dead simple money API running"})

@app.route("/api/quote")
def quote():
    ticker = request.args.get("ticker", "").upper().strip()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400

    try:
        t = yf.Ticker(ticker)
        info = t.info
        cf = t.cashflow

        if not info or info.get("regularMarketPrice") is None:
            return jsonify({"error": f"No data found for {ticker}"}), 404

        # Current price
        price = info.get("currentPrice") or info.get("regularMarketPrice")

        # Company name
        name = info.get("longName") or info.get("shortName") or ticker

        # Shares outstanding (in billions)
        shares_raw = info.get("sharesOutstanding") or 0
        shares_b = round(shares_raw / 1e9, 3)

        # Free Cash Flow — trailing 12mo from cash flow statement
        fcf_b = None
        try:
            if cf is not None and not cf.empty:
                # yfinance cashflow rows vary — try common labels
                op_cf = None
                capex = None
                for label in cf.index:
                    l = str(label).lower()
                    if "operating" in l and "cash" in l:
                        op_cf = float(cf.loc[label].iloc[0])
                    if "capital expenditure" in l or "capex" in l:
                        capex = float(cf.loc[label].iloc[0])

                if op_cf is not None and capex is not None:
                    fcf_raw = op_cf + capex  # capex is negative in yfinance
                    fcf_b = round(fcf_raw / 1e9, 2)
                elif op_cf is not None:
                    fcf_b = round(op_cf / 1e9, 2)
        except Exception:
            pass

        # Fallback: use freeCashflow from info
        if fcf_b is None:
            fcf_info = info.get("freeCashflow")
            if fcf_info:
                fcf_b = round(fcf_info / 1e9, 2)

        # Net debt = total debt - cash (in billions)
        total_debt = info.get("totalDebt") or 0
        cash = info.get("totalCash") or 0
        net_debt_b = round((total_debt - cash) / 1e9, 2)

        # Historical revenue growth (3yr CAGR) as suggested g1
        suggested_g1 = None
        try:
            rev_growth = info.get("revenueGrowth")
            if rev_growth:
                suggested_g1 = round(rev_growth * 100, 1)
        except Exception:
            pass

        # Market cap for reference
        market_cap_b = round((info.get("marketCap") or 0) / 1e9, 1)

        return jsonify({
            "ticker": ticker,
            "name": name,
            "price": round(price, 2),
            "shares_b": shares_b,
            "fcf_b": fcf_b,
            "net_debt_b": net_debt_b,
            "market_cap_b": market_cap_b,
            "suggested_g1": suggested_g1,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

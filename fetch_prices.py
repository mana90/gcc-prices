import requests
import json
from datetime import datetime

def get_yahoo_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    res = requests.get(url).json()
    return res["chart"]["result"][0]["meta"]["regularMarketPrice"]

def get_currency():
    url = "https://api.exchangerate.host/latest?base=USD"
    return requests.get(url).json()["rates"]

data = {
    "last_updated": datetime.utcnow().isoformat(),

    "oil": {
        "brent": get_yahoo_price("BZ=F"),
        "wti": get_yahoo_price("CL=F")
    },

    "metals": {
        "gold_usd": get_yahoo_price("GC=F")
    },

    "currency": {}
}

rates = get_currency()

# GCC currencies
for code in ["AED", "SAR", "QAR", "KWD", "BHD", "OMR"]:
    data["currency"][f"USD_{code}"] = rates.get(code)

# Save JSON
with open("prices.json", "w") as f:
    json.dump(data, f, indent=2)

print("✅ prices.json updated")
import requests
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import os

# ------------------------
# Step 1: Fetch currency rates (USD -> GCC)
# ------------------------
def get_currency():
    url = "https://open.er-api.com/v6/latest/USD"
    try:
        res = requests.get(url)
        data = res.json()
        return data.get("rates", {})
    except:
        print("Currency API failed")
        return {}

# ------------------------
# Step 2: Yahoo price (Oil / fallback gold)
# ------------------------
def get_yahoo_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        print(f"Unable to provide value for {symbol}")
        return None

# ------------------------
# Step 3A: Gold from Gulf News (AED per gram)
# ------------------------
def get_gold_all_karats_aed():
    karats_needed = ["24", "22", "21", "18", "14"]
    results = {}

    try:
        url = "https://gulfnews.com/gold-forex"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.find_all("tr")

        for row in rows:
            cols = [c.text.strip() for c in row.find_all("td")]
            if len(cols) >= 2:
                label = cols[0]
                price_text = cols[1].replace(",", "").strip()
                for k in karats_needed:
                    if k in label:
                        if price_text in ["-", "", "0"]:
                            continue
                        try:
                            price = float(price_text)
                            if price > 50:  # sanity check
                                results[f"{k}K"] = price
                        except:
                            continue
        return results
    except Exception as e:
        print("Unable to provide gold values:", e)
    return {}

# ------------------------
# Step 3B: Gold fallback (USD per gram)
# ------------------------
def get_gold_usd_per_gram():
    gold_oz = get_yahoo_price("GC=F")  # Gold futures
    if gold_oz:
        return gold_oz / 31.1035  # ounce → gram
    return None

# ------------------------
# Step 4: Oil prices
# ------------------------
def get_oil_prices_usd():
    brent = get_yahoo_price("BZ=F")
    wti = get_yahoo_price("CL=F")
    return brent, wti

# ------------------------
# Step 5: Fuel prices for UAE (all types)
# ------------------------
def get_uae_fuel_prices_aed():
    results = {}
    try:
        url = "https://gulfnews.com/gold-forex"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.find_all("tr")
        fuel_types = ["Super 98", "Special 95", "Eplus 91", "Diesel"]
        for row in rows:
            cols = [c.text.strip() for c in row.find_all("td")]
            if len(cols) >= 2 and cols[0] in fuel_types:
                try:
                    price = float(cols[1].replace(",", ""))
                    results[cols[0]] = price
                except:
                    continue
        return results
    except Exception as e:
        print("Unable to provide fuel values:", e)
    return {}

# ------------------------
# Step 6: Build JSON
# ------------------------
def build_gcc_prices():
    rates = get_currency()
    if not rates:
        print("Failed to get currency rates")
        return

    gcc = ["AED", "SAR", "QAR", "KWD", "BHD", "OMR"]

    # Prepare JSON
    data = {
        "last_updated": datetime.utcnow().isoformat(),
        "oil": {},
        "metals": {},
        "fuel": {},
        "currency": {}
    }

    # Currency
    for c in gcc:
        if c in rates:
            data["currency"][f"USD_{c}"] = rates[c]

    # Oil
    brent_usd, wti_usd = get_oil_prices_usd()
    if brent_usd:
        data["oil"]["brent"] = {c: round(brent_usd * rates[c], 2) for c in gcc if c in rates}
    if wti_usd:
        data["oil"]["wti"] = {c: round(wti_usd * rates[c], 2) for c in gcc if c in rates}

    # Gold
    gold_data = get_gold_all_karats_aed()
    if gold_data:
        data["metals"]["gold_per_gram"] = {}
        for karat, aed_price in gold_data.items():
            data["metals"]["gold_per_gram"][karat] = {}
            for c in gcc:
                if c == "AED":
                    data["metals"]["gold_per_gram"][karat]["AED"] = round(aed_price, 2)
                elif c in rates:
                    usd_value = aed_price / rates["AED"]
                    converted = usd_value * rates[c]
                    data["metals"]["gold_per_gram"][karat][c] = round(converted, 2)
    else:
        print("Unable to provide gold values")

    # Fuel
    uae_fuel = get_uae_fuel_prices_aed()
    if uae_fuel:
        data["fuel"] = {}
        for fuel_type, aed_price in uae_fuel.items():
            data["fuel"][fuel_type] = {}
            for c in gcc:
                if c == "AED":
                    data["fuel"][fuel_type]["AED"] = round(aed_price, 2)
                elif c in rates:
                    usd_value = aed_price / rates["AED"]
                    converted = usd_value * rates[c]
                    data["fuel"][fuel_type][c] = round(converted, 2)
    else:
        print("Unable to provide fuel values")

    # Save prices.json
    with open("prices.json", "w") as f:
        json.dump(data, f, indent=2)
    print("✅ prices.json updated")

    # ------------------------
    # Update history.json
    # ------------------------
    update_history(data)

# ------------------------
# Step 7: History
# ------------------------
HISTORY_FILE = "history.json"
MAX_DAYS = 90  # 3 months

def update_history(new_data):
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    else:
        history = {}

    today = datetime.utcnow().date().isoformat()
    history["last_updated"] = new_data["last_updated"]

    def update_category(cat_name):
        if cat_name not in history:
            history[cat_name] = {}
        for item, values in new_data.get(cat_name, {}).items():
            if item not in history[cat_name]:
                history[cat_name][item] = {}
            history[cat_name][item][today] = values
            # Remove older than 90 days
            keys_to_remove = [d for d in history[cat_name][item]
                              if datetime.fromisoformat(d) < datetime.utcnow() - timedelta(days=MAX_DAYS)]
            for k in keys_to_remove:
                del history[cat_name][item][k]

    for category in ["oil", "metals", "fuel"]:
        update_category(category)

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    print("📊 history.json updated")

# ------------------------
# Run
# ------------------------
if __name__ == "__main__":
    build_gcc_prices()

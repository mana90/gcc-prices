import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup

# ------------------------
# Config
# ------------------------
GCC_CURRENCIES = ["AED", "SAR", "QAR", "KWD", "BHD", "OMR"]
HISTORY_MAX_DAYS = 90  # Keep 3 months of daily data

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
        print("⚠️ Currency API failed")
        return {}

# ------------------------
# Step 2: Fetch commodity price in USD (Yahoo)
# ------------------------
def get_yahoo_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        return None

# ------------------------
# Step 3A: Scrape gold prices from Gulf News (AED per gram)
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
                            if price > 50:
                                results[f"{k}K"] = price
                        except:
                            continue
        return results
    except Exception as e:
        print("⚠️ Gold scrape error:", e)
    return {}

# ------------------------
# Step 3B: Fallback gold price (USD per gram)
# ------------------------
def get_gold_usd_per_gram():
    gold_oz = get_yahoo_price("GC=F")  # Gold futures
    if gold_oz:
        return gold_oz / 31.1035  # Convert ounce → gram
    return None

# ------------------------
# Step 4: Fetch oil prices in USD
# ------------------------
def get_oil_prices_usd():
    brent = get_yahoo_price("BZ=F")  # Brent
    wti = get_yahoo_price("CL=F")    # WTI
    return brent, wti

# ------------------------
# Step 5: Scrape UAE fuel prices (AED per liter)
# ------------------------
def get_uae_fuel_prices_aed():
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
                label = cols[0].lower()
                price_text = cols[1].replace(",", "").strip()
                if price_text in ["-", "", "0"]:
                    continue
                try:
                    price = float(price_text)
                    if "e95" in label:
                        results["E95"] = price
                    elif "e98" in label:
                        results["E98"] = price
                    elif "diesel" in label:
                        results["Diesel"] = price
                except:
                    continue
        return results
    except Exception as e:
        print("⚠️ Fuel scrape error:", e)
    return {}

# ------------------------
# Step 6: Build JSON + update history
# ------------------------
def build_gcc_prices():
    rates = get_currency()
    if not rates:
        print("⚠️ Failed to fetch currency rates. Exiting")
        return

    timestamp = datetime.utcnow().isoformat()
    data = {
        "last_updated": timestamp,
        "oil": {},
        "metals": {},
        "fuel": {},
        "currency": {}
    }

    # ------------------------
    # Currency
    # ------------------------
    for c in GCC_CURRENCIES:
        if c in rates:
            data["currency"][f"USD_{c}"] = rates[c]

    # ------------------------
    # Oil
    # ------------------------
    brent_usd, wti_usd = get_oil_prices_usd()
    if brent_usd:
        data["oil"]["brent"] = {c: round(brent_usd * rates[c], 2) for c in GCC_CURRENCIES if c in rates}
    if wti_usd:
        data["oil"]["wti"] = {c: round(wti_usd * rates[c], 2) for c in GCC_CURRENCIES if c in rates}

    # ------------------------
    # Gold (multi-karat)
    # ------------------------
    gold_aed = get_gold_all_karats_aed()
    if not gold_aed:
        fallback_usd = get_gold_usd_per_gram()
        if fallback_usd:
            gold_aed["24K"] = fallback_usd * rates.get("AED", 3.6725)

    if gold_aed:
        data["metals"]["gold_per_gram"] = {}
        for karat, aed_price in gold_aed.items():
            data["metals"]["gold_per_gram"][karat] = {}
            for c in GCC_CURRENCIES:
                if c == "AED":
                    data["metals"]["gold_per_gram"][karat]["AED"] = round(aed_price, 2)
                elif c in rates:
                    usd_value = aed_price / rates["AED"]
                    converted = usd_value * rates[c]
                    data["metals"]["gold_per_gram"][karat][c] = round(converted, 2)

    # ------------------------
    # Fuel (UAE only → convert to GCC)
    # ------------------------
    uae_fuel = get_uae_fuel_prices_aed()
    if uae_fuel:
        data["fuel"] = {}
        for fuel_type, price_aed in uae_fuel.items():
            data["fuel"][fuel_type] = {}
            for c in GCC_CURRENCIES:
                if c == "AED":
                    data["fuel"][fuel_type]["AED"] = round(price_aed, 2)
                elif c in rates:
                    usd_value = price_aed / rates["AED"]
                    converted = usd_value * rates[c]
                    data["fuel"][fuel_type][c] = round(converted, 2)

    # ------------------------
    # Update history
    # ------------------------
    try:
        with open("prices.json", "r") as f:
            old_data = json.load(f)
    except:
        old_data = {}

    if "history" not in old_data:
        old_data["history"] = {"gold": [], "oil": [], "currency": [], "fuel": []}

    # Gold history
    gold_entry = {"timestamp": timestamp}
    for karat, values in data.get("metals", {}).get("gold_per_gram", {}).items():
        gold_entry[karat] = values
    old_data["history"]["gold"].append(gold_entry)
    old_data["history"]["gold"] = old_data["history"]["gold"][-HISTORY_MAX_DAYS:]

    # Oil history
    oil_entry = {"timestamp": timestamp}
    for oil_type, values in data.get("oil", {}).items():
        oil_entry[oil_type] = values
    old_data["history"]["oil"].append(oil_entry)
    old_data["history"]["oil"] = old_data["history"]["oil"][-HISTORY_MAX_DAYS:]

    # Currency history
    currency_entry = {"timestamp": timestamp}
    for code, value in data.get("currency", {}).items():
        currency_entry[code] = value
    old_data["history"]["currency"].append(currency_entry)
    old_data["history"]["currency"] = old_data["history"]["currency"][-HISTORY_MAX_DAYS:]

    # Fuel history
    fuel_entry = {"timestamp": timestamp}
    for fuel_type, values in data.get("fuel", {}).items():
        fuel_entry[fuel_type] = values
    old_data["history"]["fuel"].append(fuel_entry)
    old_data["history"]["fuel"] = old_data["history"]["fuel"][-HISTORY_MAX_DAYS:]

    # Update last_updated + current data
    old_data.update(data)

    # ------------------------
    # Save JSON
    # ------------------------
    with open("prices.json", "w") as f:
        json.dump(old_data, f, indent=2)

    print("✅ prices.json updated with history")

# ------------------------
# Run
# ------------------------
if __name__ == "__main__":
    build_gcc_prices()

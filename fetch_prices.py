import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup

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
        print(f"Error fetching {symbol}")
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
        print("Gold scrape error:", e)

    print("⚠️ Failed to scrape gold")
    return {}

# ------------------------
# Step 3B: Gold fallback (USD per ounce)
# ------------------------
def get_gold_usd_per_gram():
    gold_oz = get_yahoo_price("GC=F")  # Gold futures
    if gold_oz:
        return gold_oz / 31.1035  # ounce → gram
    return None

# ------------------------
# Step 4: Oil prices
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

                    if "super" in label:
                        results["super_98"] = price
                    elif "special" in label:
                        results["special_95"] = price
                    elif "eplus" in label:
                        results["eplus_91"] = price
                    elif "diesel" in label:
                        results["diesel"] = price

                except:
                    continue

        return results

    except Exception as e:
        print("Fuel scrape error:", e)

    print("⚠️ Failed to scrape fuel")
    return {}

# ------------------------
# Step 5: Build JSON
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
        "currency": {}
    }

    # ------------------------
    # Currency
    # ------------------------
    for c in gcc:
        if c in rates:
            data["currency"][f"USD_{c}"] = rates[c]

    # ------------------------
    # Oil
    # ------------------------
    # ------------------------
    # Fuel (UAE → GCC conversion)
    # ------------------------
    fuel_data = get_uae_fuel_prices_aed()

    if fuel_data:
        data["fuel"] = {}

        for fuel_type, aed_price in fuel_data.items():
            data["fuel"][fuel_type] = {}

            for c in gcc:
                if c == "AED":
                    data["fuel"][fuel_type]["AED"] = round(aed_price, 2)
                elif c in rates:
                    usd_value = aed_price / rates["AED"]
                    converted = usd_value * rates[c]
                    data["fuel"][fuel_type][c] = round(converted, 2)

    else:
        print("⚠️ Fuel data unavailable")

    # ------------------------
    # Gold (SMART LOGIC)
    # ------------------------

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
        print("⚠️ Gold pricing fetch failed — fallback not implemented for multi-karat yet")

    # ------------------------
    # Save
    # ------------------------
    with open("prices.json", "w") as f:
        json.dump(data, f, indent=2)

    print("✅ prices.json updated")

# ------------------------
# Run
# ------------------------
if __name__ == "__main__":
    build_gcc_prices()

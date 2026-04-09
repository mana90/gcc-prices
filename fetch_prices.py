import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path

# ------------------------
# Config
# ------------------------
FREE_CRYPTO_API_KEY = "t3o6k1r63ciqsprlbat6"
FREE_CRYPTO_URL = "https://api.freecryptoapi.com/v1/getData"
CRYPTO_SYMBOLS = ["BTC", "ETH", "BNB", "SOL", "XRP"]
GCC_CURRENCIES = ["AED", "SAR", "QAR", "KWD", "BHD", "OMR"]
HISTORY_FILE = "history.json"
MAX_ENTRIES = 180  # ~3 months if running every 12 hours

# ------------------------
# Step 1: Fetch currency rates (USD -> GCC)
# ------------------------
def get_currency():
    url = "https://open.er-api.com/v6/latest/USD"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        return data.get("rates", {})
    except Exception as e:
        print(f"Currency API failed: {e}")
        return {}

# ------------------------
# Step 2: Yahoo price (Oil / fallback gold)
# ------------------------
def get_yahoo_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as e:
        print(f"Unable to get Yahoo price for {symbol}: {e}")
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
        res = requests.get(url, headers=headers, timeout=10)
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
        print(f"Unable to get gold values: {e}")
    return {}

# ------------------------
# Step 4: Oil prices
# ------------------------
def get_oil_prices_usd():
    brent = get_yahoo_price("BZ=F")
    wti = get_yahoo_price("CL=F")
    return brent, wti

# ------------------------
# Step 5: Fuel prices for UAE
# ------------------------
def get_uae_fuel_prices_aed():
    results = {}
    try:
        url = "https://gulfnews.com/gold-forex"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
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
        print(f"Unable to get fuel values: {e}")
    return {}

# ------------------------
# Step 6: Crypto prices from FreeCryptoAPI
# Fetches USD price per coin, converts to all GCC currencies
# ------------------------
def get_single_crypto(symbol, rates):
    try:
        headers = {
            "Authorization": f"Bearer {FREE_CRYPTO_API_KEY}",
            "Accept": "application/json"
        }
        params = {"symbol": symbol}
        res = requests.get(FREE_CRYPTO_URL, headers=headers, params=params, timeout=15)

        if res.status_code != 200:
            print(f"FreeCryptoAPI HTTP {res.status_code} for {symbol}: {res.text}")
            return None

        data = res.json()

        # API returns status as string "true"/"false"
        status = str(data.get("status", "false")).lower()
        if status != "true":
            print(f"FreeCryptoAPI error for {symbol}: {data.get('error', 'Unknown error')}")
            return None

        coin = data.get("data", {})
        if symbol in coin:
            coin = coin[symbol]
        if not coin:
            print(f"FreeCryptoAPI: No data for {symbol}")
            return None

        usd_price = float(coin.get("price", 0))
        if usd_price == 0:
            print(f"FreeCryptoAPI: Zero price for {symbol}")
            return None

        change_24h = float(coin.get("change_24h") or 0)
        change_7d  = float(coin.get("change_7d") or 0)
        market_cap = float(coin.get("market_cap") or 0)
        volume_24h = float(coin.get("volume_24h") or 0)
        name       = coin.get("name", symbol)

        # Convert USD price to all GCC currencies
        converted = {}
        for c in GCC_CURRENCIES:
            if c in rates:
                converted[c] = round(usd_price * rates[c], 2)

        return {
            "name": name,
            "usd_price": round(usd_price, 2),
            "percent_change_24h": round(change_24h, 2),
            "percent_change_7d": round(change_7d, 2),
            "market_cap_usd": round(market_cap, 2),
            "volume_24h_usd": round(volume_24h, 2),
            "prices": converted
        }

    except Exception as e:
        print(f"FreeCryptoAPI fetch failed for {symbol}: {e}")
        return None


def get_crypto_prices(rates):
    crypto = {}
    for symbol in CRYPTO_SYMBOLS:
        result = get_single_crypto(symbol, rates)
        if result:
            crypto[symbol] = result
            print(f"✅ {symbol}: USD {result['usd_price']}")
        else:
            print(f"⚠️ {symbol}: skipped")

    if crypto:
        print(f"✅ Crypto fetched: {list(crypto.keys())}")
    else:
        print("⚠️ No crypto data fetched")

    return crypto

# ------------------------
# Step 7: Build full JSON
# ------------------------
def build_gcc_prices():
    rates = get_currency()
    if not rates:
        print("❌ Failed to get currency rates — aborting")
        return

    data = {
        "last_updated": datetime.utcnow().isoformat(),
        "oil": {},
        "metals": {},
        "fuel": {},
        "currency": {},
        "crypto": {}
    }

    # Currency
    for c in GCC_CURRENCIES:
        if c in rates:
            data["currency"][f"USD_{c}"] = rates[c]

    # Oil
    brent_usd, wti_usd = get_oil_prices_usd()
    if brent_usd:
        data["oil"]["brent"] = {c: round(brent_usd * rates[c], 2) for c in GCC_CURRENCIES if c in rates}
    if wti_usd:
        data["oil"]["wti"] = {c: round(wti_usd * rates[c], 2) for c in GCC_CURRENCIES if c in rates}

    # Gold
    gold_data = get_gold_all_karats_aed()
    if gold_data:
        data["metals"]["gold_per_gram"] = {}
        for karat, aed_price in gold_data.items():
            data["metals"]["gold_per_gram"][karat] = {}
            for c in GCC_CURRENCIES:
                if c == "AED":
                    data["metals"]["gold_per_gram"][karat]["AED"] = round(aed_price, 2)
                elif c in rates:
                    usd_value = aed_price / rates["AED"]
                    converted = usd_value * rates[c]
                    data["metals"]["gold_per_gram"][karat][c] = round(converted, 2)
    else:
        print("⚠️ Gold data unavailable")

    # Fuel
    uae_fuel = get_uae_fuel_prices_aed()
    if uae_fuel:
        data["fuel"] = {}
        for fuel_type, aed_price in uae_fuel.items():
            data["fuel"][fuel_type] = {}
            for c in GCC_CURRENCIES:
                if c == "AED":
                    data["fuel"][fuel_type]["AED"] = round(aed_price, 2)
                elif c in rates:
                    usd_value = aed_price / rates["AED"]
                    converted = usd_value * rates[c]
                    data["fuel"][fuel_type][c] = round(converted, 2)
    else:
        print("⚠️ Fuel data unavailable")

    # Crypto
    crypto_data = get_crypto_prices(rates)
    if crypto_data:
        data["crypto"] = crypto_data
    else:
        print("⚠️ Crypto data unavailable")

    # Save prices.json
    with open("prices.json", "w") as f:
        json.dump(data, f, indent=2)
    print("✅ prices.json updated")

    # Update history.json
    update_history(data)

# ------------------------
# Step 8: History
# ------------------------
def update_history(new_data):
    history_path = Path(HISTORY_FILE)
    history = []

    if history_path.exists():
        try:
            with open(history_path, "r") as f:
                history = json.load(f)
                if not isinstance(history, list):
                    history = []
        except (json.JSONDecodeError, Exception) as e:
            print(f"⚠️ Could not read history.json, starting fresh: {e}")
            history = []

    # Build history snapshot — structured for iOS app consumption
    history_entry = {
        "last_updated": new_data.get("last_updated"),
        "metals":   new_data.get("metals", {}),
        "fuel":     new_data.get("fuel", {}),
        "currency": new_data.get("currency", {}),
        "oil":      new_data.get("oil", {}),
        "crypto":   new_data.get("crypto", {})
    }

    history.append(history_entry)

    # Keep only the last MAX_ENTRIES
    if len(history) > MAX_ENTRIES:
        history = history[-MAX_ENTRIES:]

    try:
        with open(history_path, "w") as f:
            json.dump(history, f, indent=2)
        print(f"📊 history.json updated ({len(history)} entries total)")
    except Exception as e:
        print(f"❌ Failed to write to history.json: {e}")

# ------------------------
# Run
# ------------------------
if __name__ == "__main__":
    build_gcc_prices()

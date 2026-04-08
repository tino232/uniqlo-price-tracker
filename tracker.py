import json
import os
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID        = os.environ["CHAT_ID"]
URLS_FILE      = "urls.json"
STATE_FILE     = "state.json"

# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"[Telegram error] {e}")

# ── Fetch product via Uniqlo API ───────────────────────────────────────────────
def extract_product_id(url: str):
    """Extract product code and color/size from URL."""
    match = re.search(r'/products/([A-Z0-9\-]+)', url)
    product_code = match.group(1) if match else None

    params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    color_code = params.get("colorCode", "")
    size_code  = params.get("sizeCode", "")
    return product_code, color_code, size_code

def fetch_product_data(url: str):
    """
    Fetch product info from Uniqlo VN API.
    Returns dict with keys: name, selling_price, compare_price, on_sale, in_stock
    """
    product_code, color_code, size_code = extract_product_id(url)
    if not product_code:
        return None

    # Strip trailing variant suffix (e.g. -000, -001) for API call
    base_code = re.sub(r'-\d{3}$', '', product_code)

    api_url = (
        f"https://www.uniqlo.com/vn/api/commerce/v5/vn/products/{product_code}"
        f"/price-groups/00/details?includePromotion=true&httpFailure=true"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.uniqlo.com/",
    }

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        print(f"[Fetch error] {url} → {e}")
        # Fallback: scrape the product page HTML
        return fetch_product_html(url)

    try:
        result = data.get("result", {})
        name = result.get("name", product_code)

        # Price info
        prices = result.get("prices", [{}])
        price_info = prices[0] if prices else {}
        selling = price_info.get("base", {}).get("value", 0)
        compare = price_info.get("was",  {}).get("value", 0)

        # Stock: find the matching color+size SKU
        skus = result.get("stocks", [])
        in_stock = True  # default
        for sku in skus:
            sku_color = sku.get("color", {}).get("code", "")
            sku_size  = sku.get("size",  {}).get("code", "")
            if (not color_code or sku_color == color_code) and \
               (not size_code  or sku_size  == size_code):
                in_stock = sku.get("quantity", 0) > 0
                break

        return {
            "name":          name,
            "selling_price": int(selling),
            "compare_price": int(compare),
            "on_sale":       compare > 0 and compare > selling,
            "in_stock":      in_stock,
        }
    except Exception as e:
        print(f"[Parse error] {url} → {e}")
        return fetch_product_html(url)

def fetch_product_html(url: str):
    """Fallback: scrape HTML page for price info."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "vi-VN,vi;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8")
    except Exception as e:
        print(f"[HTML fetch error] {url} → {e}")
        return None

    # Selling price
    sell_match = re.search(r'"price"\s*:\s*"?([\d,]+)"?', html)
    # Compare price (strikethrough / was price)
    comp_match = re.search(r'"originalPrice"\s*:\s*"?([\d,]+)"?', html)
    # Product name
    name_match = re.search(r'<title>(.*?)</title>', html)
    # Stock
    stock_match = re.search(r'"availability"\s*:\s*"([^"]+)"', html)

    selling = int(sell_match.group(1).replace(",", "")) if sell_match else 0
    compare = int(comp_match.group(1).replace(",", "")) if comp_match else 0
    name    = name_match.group(1).strip() if name_match else url
    stock_str = stock_match.group(1) if stock_match else "InStock"
    in_stock  = "OutOfStock" not in stock_str

    return {
        "name":          name,
        "selling_price": selling,
        "compare_price": compare,
        "on_sale":       compare > 0 and compare > selling,
        "in_stock":      in_stock,
    }

# ── State helpers ─────────────────────────────────────────────────────────────
def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Format helpers ────────────────────────────────────────────────────────────
def fmt_price(p: int) -> str:
    return f"{p:,}₫".replace(",", ".")

def short_url(url: str) -> str:
    m = re.search(r'/products/([^?]+)', url)
    return m.group(1) if m else url

# ── Main check logic ──────────────────────────────────────────────────────────
def run_check():
    urls_data = load_json(URLS_FILE)
    urls: list = urls_data.get("urls", [])

    if not urls:
        print("No URLs to track.")
        send_telegram("⚠️ Uniqlo Tracker: Không có URL nào để theo dõi.")
        return

    state: dict = load_json(STATE_FILE)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    changed = False

    for url in urls:
        print(f"Checking: {url}")
        info = fetch_product_data(url)
        if info is None:
            print(f"  → Could not fetch data, skipping.")
            continue

        key = url
        prev = state.get(key, {})

        name          = info["name"]
        selling       = info["selling_price"]
        compare       = info["compare_price"]
        on_sale       = info["on_sale"]
        in_stock      = info["in_stock"]

        prev_selling  = prev.get("selling_price")
        prev_compare  = prev.get("compare_price")
        prev_on_sale  = prev.get("on_sale")
        prev_in_stock = prev.get("in_stock")

        msgs = []

        # ── Stock alert (one-time) ──────────────────────────────────────────
        if prev_in_stock is not None and prev_in_stock != in_stock:
            if in_stock:
                msgs.append(f"✅ <b>CÒN HÀNG TRỞ LẠI</b>")
            else:
                msgs.append(f"❌ <b>HẾT HÀNG</b>")

        # ── Sale status change (immediate alert) ───────────────────────────
        if prev_on_sale is not None and prev_on_sale != on_sale:
            if on_sale:
                msgs.append(
                    f"🏷️ <b>BẮT ĐẦU SALE!</b>\n"
                    f"   Giá sale: {fmt_price(selling)}\n"
                    f"   Giá gốc:  <s>{fmt_price(compare)}</s>"
                )
            else:
                msgs.append(f"🔔 Sale đã kết thúc — Giá hiện tại: {fmt_price(selling)}")

        # ── Price change (3-day scheduled check) ───────────────────────────
        elif prev_selling is not None and prev_selling != selling:
            direction = "⬇️ GIẢM" if selling < prev_selling else "⬆️ TĂNG"
            msgs.append(
                f"💰 Giá {direction}\n"
                f"   Trước: {fmt_price(prev_selling)}\n"
                f"   Sau:   {fmt_price(selling)}"
            )

        if msgs:
            stock_label = "✅ Còn hàng" if in_stock else "❌ Hết hàng"
            body = "\n".join(msgs)
            text = (
                f"🛍️ <b>Uniqlo Price Alert</b> — {now}\n\n"
                f"<b>{name}</b>\n"
                f"{stock_label}\n\n"
                f"{body}\n\n"
                f"🔗 <a href=\"{url}\">{short_url(url)}</a>"
            )
            send_telegram(text)
            print(f"  → Alert sent.")

        # Update state
        state[key] = {
            "name":          name,
            "selling_price": selling,
            "compare_price": compare,
            "on_sale":       on_sale,
            "in_stock":      in_stock,
            "last_checked":  now,
        }
        changed = True
        time.sleep(2)  # polite delay between requests

    if changed:
        save_json(STATE_FILE, state)
        print("State saved.")

if __name__ == "__main__":
    run_check()

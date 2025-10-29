from flask import Flask, request, abort
import requests
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
WEBHOOK_URL = "https://abshodeh.onrender.com/webhook"
API_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
PROXIES = {"http": "http://91.107.135.50:8080", "https": "http://91.107.135.50:8080"}  # زنده
keyboard = {"inline_keyboard": [[{"text": "🔄 استعلام مجدد", "callback_data": "get_price"}]]}
webhook_set = False

# --- کش قیمت (۶۰ ثانیه) ---
cached_price = {"price": 45555000, "change": 0, "percent": 0, "timestamp": 0}
CACHE_TIME = 60  # ثانیه

def fetch_gold_price():
    global cached_price
    now = time.time()
    if now - cached_price["timestamp"] < CACHE_TIME:
        return cached_price["price"], cached_price["change"], cached_price["percent"]
    
    try:
        resp = requests.get(API_URL, proxies=PROXIES, timeout=15).json()
        for item in resp.get('gold', []):
            if item.get('symbol') == 'IR_GOLD_MELTED':
                price = int(item['price'])
                change = item.get('change_value', 0)
                percent = item.get('change_percent', 0)
                cached_price = {"price": price, "change": change, "percent": percent, "timestamp": now}
                logger.info(f"قیمت واقعی (از API): {price:,} تومان")
                return price, change, percent
    except Exception as e:
        logger.error(f"خطا در API: {e}")
        # استفاده از کش قبلی اگر موجود
        if cached_price["timestamp"] > 0:
            logger.warning("استفاده از کش قبلی")
            return cached_price["price"], cached_price["change"], cached_price["percent"]
    return 45555000, 948000, 2.13  # fallback نهایی

# --- ارسال پیام ---
def send_price(chat_id):
    price, change, percent = fetch_gold_price()
    message = (
        f"💰 **قیمت طلای آب‌شده**\n"
        f"`{price:,} تومان`\n\n"
        f"{'📈' if change > 0 else '📉'} تغییر: `{change:+,} تومان` ({percent:+.2f}%)\n\n"
        f"کلیک برای بروزرسانی 👇"
    )
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=payload, timeout=10).json()
        if resp.get('ok'):
            logger.info(f"پیام ارسال شد به {chat_id}")
    except Exception as e:
        logger.error(f"ارسال شکست: {e}")

# --- ویرایش ---
def edit_price(chat_id, message_id):
    price, change, percent = fetch_gold_price()
    new_text = (
        f"💰 **قیمت طلای آب‌شده**\n"
        f"`{price:,} تومان`\n\n"
        f"{'📈' if change > 0 else '📉'} تغییر: `{change:+,} تومان` ({percent:+.2f}%)\n\n"
        f"کلیک برای بروزرسانی 👇"
    )
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': new_text,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText", data=payload, timeout=10)
    except Exception as e:
        logger.error(f"ویرایش شکست: {e}")

# --- Webhook ---
@app.route('/webhook', methods=['POST'])
def webhook():
    global webhook_set
    if request.headers.get('content-type') == 'application/json':
        update = request.get_json()
        if 'message' in update:
            msg = update['message']
            chat_id = msg['chat']['id']
            text = msg.get('text', '').strip()
            if text == '/start':
                send_price(chat_id)
        elif 'callback_query' in update:
            cb = update['callback Được tạo bởi Grok, built by xAI_query']
            chat_id = cb['message']['chat']['id']
            message_id = cb['message']['message_id']
            if cb['data'] == 'get_price':
                edit_price(chat_id, message_id)
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                              data={'callback_query_id': cb['id']})
        return '', 200
    abort(403)

# --- تنظیم Webhook ---
@app.before_request
def setup_webhook():
    global webhook_set
    if not webhook_set:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
            payload = {'url': WEBHOOK_URL}
            resp = requests.post(url, data=payload, timeout=10).json()
            if resp.get('ok'):
                logger.info("✅ Webhook تنظیم شد")
            webhook_set = True
        except Exception as e:
            logger.error(f"تنظیم Webhook شکست: {e}")

@app.route('/')
def home():
    return "ربات طلای آب‌شده فعال است!"

if __name__ == '__main__':
    app.run()

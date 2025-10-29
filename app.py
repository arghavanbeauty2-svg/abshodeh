from flask import Flask
import requests
import json
import logging
import threading
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

API_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
last_update_id = 0
polling_running = False

# --- پروکسی زنده ---
PROXIES = {"http": "http://91.241.21.17:9812", "https": "http://91.241.21.17:9812"}

# --- keyboard ---
keyboard = {"inline_keyboard": [[{"text": "🔄 استعلام مجدد", "callback_data": "get_price"}]]}

# --- دریافت قیمت ---
def fetch_gold_price():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(API_URL, headers=headers, proxies=PROXIES, timeout=15)
        logger.info(f"API وضعیت: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get('gold', []):
                if item.get('symbol') == 'IR_GOLD_MELTED':
                    price = int(item['price'])
                    logger.info(f"قیمت واقعی: {price:,} تومان")
                    return price
        else:
            logger.warning(f"API خطا: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"پروکسی/API خطا: {e}")
    # Fallback
    logger.warning("استفاده از قیمت پیش‌فرض")
    return 45545000

# --- ارسال پیام با دکمه ---
def send_price_with_button(chat_id):
    price = fetch_gold_price()
    message = f"💰 **قیمت طلای آب‌شده**\n`{price:,} تومان`\n\nکلیک برای بروزرسانی 👇"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=payload, proxies=PROXIES, timeout=10).json()
        if resp.get('ok'):
            logger.info(f"پیام ارسال شد به {chat_id}")
    except Exception as e:
        logger.error(f"ارسال تلگرام شکست: {e}")

# --- ویرایش پیام ---
def edit_price_message(chat_id, message_id):
    price = fetch_gold_price()
    new_text = f"💰 **قیمت طلای آب‌شده**\n`{price:,} تومان`\n\nکلیک برای بروزرسانی 👇"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': new_text,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText", data=payload, proxies=PROXIES, timeout=10)
    except Exception as e:
        logger.error(f"ویرایش شکست: {e}")

# --- polling تلگرام ---
def telegram_polling():
    global polling_running, last_update_id
    if polling_running: return
    polling_running = True
    logger.info("Polling شروع شد")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    while polling_running:
        try:
            params = {'offset': last_update_id + 1, 'timeout': 30}
            resp = requests.get(url, params=params, proxies=PROXIES, timeout=35).json()
            if not resp.get('ok'):
                logger.warning(f"getUpdates خطا: {resp}")
                time.sleep(10)
                continue
            for update in resp.get('result', []):
                last_update_id = update['update_id']
                if 'message' in update:
                    msg = update['message']
                    chat_id = msg['chat']['id']
                    text = msg.get('text', '').strip()
                    if text == '/start':
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                      data={'chat_id': chat_id, 'text': '✅ ربات فعال شد!'}, proxies=PROXIES)
                        send_price_with_button(chat_id)
                elif 'callback_query' in update:
                    cb = update['callback_query']
                    chat_id = cb['message']['chat']['id']
                    message_id = cb['message']['message_id']
                    if cb['data'] == 'get_price':
                        edit_price_message(chat_id, message_id)
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                                      data={'callback_query_id': cb['id']}, proxies=PROXIES)
        except Exception as e:
            logger.error(f"Polling کرش: {e}")
            time.sleep(10)

# --- استارت ---
threading.Thread(target=telegram_polling, daemon=True).start()

@app.route('/')
def home():
    return "ربات فعال!"

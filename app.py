from flask import Flask
import requests
import json
import logging
import threading
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
last_update_id = 0
polling_running = False
keyboard = {"inline_keyboard": [[{"text": "🔄 استعلام مجدد", "callback_data": "get_price"}]]}

# --- Nobitex API (بدون پروکسی) ---
def fetch_gold_price():
    try:
        resp = requests.get("https://api.nobitex.ir/v2/orderbook/XAUTUSDT", timeout=10).json()
        if resp.get('status') == 'ok':
            bids = float(resp['bids'][0][0]) if resp['bids'] else 0
            asks = float(resp['asks'][0][0]) if resp['asks'] else 0
            price_tether = (bids + asks) / 2
            # تبدیل تقریبی به گرم طلای آب‌شده (اونس → گرم → تومان)
            price_gram = price_tether * 600000 / 31.1035  # مثقال به گرم (تقریبی)
            price_irr = int(price_gram * 4.608)  # گرم آب‌شده
            logger.info(f"Nobitex قیمت: {price_irr:,} تومان")
            return price_irr
    except Exception as e:
        logger.error(f"Nobitex خطا: {e}")
    # Fallback به آخرین قیمت شما
    return 45545000

# --- ارسال با دکمه ---
def send_price_with_button(chat_id):
    price = fetch_gold_price()
    message = f"💰 **قیمت طلای آب‌شده (تقریبی از Nobitex)**\n`{price:,} تومان`\n\nکلیک برای بروزرسانی 👇"
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

# --- ویرایش پیام ---
def edit_price_message(chat_id, message_id):
    price = fetch_gold_price()
    new_text = f"💰 **قیمت طلای آب‌شده (تقریبی از Nobitex)**\n`{price:,} تومان`\n\nکلیک برای بروزرسانی 👇"
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

# --- polling بدون پروکسی ---
def telegram_polling():
    global polling_running, last_update_id
    if polling_running: return
    polling_running = True
    logger.info("Polling شروع شد (بدون پروکسی)")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    while polling_running:
        try:
            params = {'offset': last_update_id + 1, 'timeout': 30}
            resp = requests.get(url, params=params, timeout=35).json()
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
                        send_telegram(chat_id, "✅ ربات فعال شد!")
                        send_price_with_button(chat_id)
                elif 'callback_query' in update:
                    cb = update['callback_query']
                    chat_id = cb['message']['chat']['id']
                    message_id = cb['message']['message_id']
                    if cb['data'] == 'get_price':
                        edit_price_message(chat_id, message_id)
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                                      data={'callback_query_id': cb['id']})
        except Exception as e:
            logger.error(f"Polling کرش: {e}")
            time.sleep(10)

def send_telegram(chat_id, text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': text}, timeout=10)
    except Exception as e:
        logger.error(f"ارسال شکست: {e}")

# --- استارت ---
threading.Thread(target=telegram_polling, daemon=True).start()

@app.route('/')
def home():
    return "ربات فعال!"

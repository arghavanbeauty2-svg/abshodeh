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

# --- پروکسی زنده (برای Nobitex و تلگرام) ---
PROXIES = {"http": "http://185.105.236.10:80", "https": "http://185.105.236.10:80"}

# --- Nobitex API ---
def fetch_gold_price():
    try:
        resp = requests.get("https://api.nobitex.ir/v2/orderbook/XAUTUSDT", proxies=PROXIES, timeout=15).json()
        if resp.get('status') == 'ok':
            bids = float(resp['bids'][0][0]) if resp['bids'] else 0
            asks = float(resp['asks'][0][0]) if resp['asks'] else 0
            price_tether = (bids + asks) / 2
            price_gram = price_tether * 600000 / 31.1035
            price_irr = int(price_gram * 4.608)
            logger.info(f"Nobitex قیمت واقعی: {price_irr:,} تومان")
            return price_irr
    except Exception as e:
        logger.error(f"Nobitex خطا: {e}")
    # Fallback به brsapi.ir (اگر پروکسی کار کند)
    try:
        brs_resp = requests.get("https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly", proxies=PROXIES, timeout=15).json()
        for item in brs_resp.get('gold', []):
            if item.get('symbol') == 'IR_GOLD_MELTED':
                price = int(item['price'])
                logger.info(f"brsapi.ir fallback: {price:,} تومان")
                return price
    except Exception as e:
        logger.error(f"brsapi.ir خطا: {e}")
    # Final fallback
    logger.warning("استفاده از قیمت ثابت")
    return 45545000

# --- ارسال با دکمه ---
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
        logger.error(f"ارسال شکست: {e}")

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

# --- polling با پروکسی ---
def telegram_polling():
    global polling_running, last_update_id
    if polling_running: return
    polling_running = True
    logger.info("Polling شروع شد (با پروکسی)")
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
                        send_telegram(chat_id, "✅ ربات فعال شد!")
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

def send_telegram(chat_id, text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': text}, proxies=PROXIES, timeout=10)
    except Exception as e:
        logger.error(f"ارسال شکست: {e}")

# --- استارت ---
threading.Thread(target=telegram_polling, daemon=True).start()

@app.route('/')
def home():
    return "ربات فعال!"

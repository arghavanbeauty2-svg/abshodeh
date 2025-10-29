from flask import Flask
import requests
import pandas as pd
import pandas_ta as ta
import schedule
import time
import threading
import logging
from datetime import datetime
import json

# تنظیم لاگ‌گیری (به کنسول Render)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# تنظیمات
API_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
price_history = []
last_update_id = 0
active_chats = set()

# --- تست API تلگرام در استارت ---
def test_telegram_api():
    try:
        resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe", timeout=10).json()
        if resp.get('ok'):
            logger.info(f"ربات تلگرام فعال: @{resp['result']['username']}")
        else:
            logger.error(f"خطا در getMe: {resp}")
    except Exception as e:
        logger.error(f"خطا در تست API تلگرام: {e}")

# --- دریافت قیمت ---
def fetch_gold_price():
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        for item in data.get('gold', []):
            if item['symbol'] == 'IR_GOLD_MELTED':
                price = float(item['price'])
                logger.info(f"قیمت دریافت شد: {price:,.0f}")
                return price
    except Exception as e:
        logger.warning(f"دریافت قیمت شکست: {e}")
    return None

# --- ارسال پیام با دکمه ---
def send_price_with_button(chat_id):
    price = fetch_gold_price()
    if not price:
        send_telegram(chat_id, "⚠️ خطا در دریافت قیمت.")
        return
    message = f"💰 **قیمت لحظه‌ای طلای آب‌شده**\n`{price:,.0f} تومان`\n\nکلیک برای بروزرسانی 👇"
    keyboard = {"inline_keyboard": [[{"text": "🔄 استعلام مجدد", "callback_data": "get_price"}]]}
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=payload, timeout=10).json()
        if resp.get('ok'):
            logger.info(f"دکمه ارسال شد به {chat_id}")
    except Exception as e:
        logger.error(f"ارسال دکمه شکست: {e}")

# --- ویرایش پیام ---
def edit_price_message(chat_id, message_id):
    price = fetch_gold_price()
    if not price: return
    new_text = f"💰 **قیمت لحظه‌ای طلای آب‌شده**\n`{price:,.0f} تومان`\n\nکلیک برای بروزرسانی 👇"
    keyboard = {"inline_keyboard": [[{"text": "🔄 استعلام مجدد", "callback_data": "get_price"}]]}
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': new_text,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText", data=payload, timeout=10)
        logger.info(f"قیمت بروز شد برای {chat_id}")
    except Exception as e:
        logger.error(f"ویرایش شکست: {e}")

# --- ارسال پیام ساده ---
def send_telegram(chat_id, text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': text}, timeout=10)
    except Exception as e:
        logger.error(f"ارسال پیام شکست: {e}")

# --- polling با try/except قوی ---
def telegram_polling():
    global last_update_id
    logger.info("Polling تلگرام شروع شد")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    while True:
        try:
            params = {'offset': last_update_id + 1, 'timeout': 30}
            response = requests.get(url, params=params, timeout=35).json()
            if not response.get('ok'):
                logger.warning(f"getUpdates خطا: {response}")
                time.sleep(10)
                continue
            for update in response.get('result', []):
                last_update_id = update['update_id']
                logger.info(f"آپدیت {last_update_id} دریافت شد")
                
                if 'message' in update:
                    msg = update['message']
                    chat_id = msg['chat']['id']
                    text = msg.get('text', '').strip()
                    active_chats.add(chat_id)
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
            logger.error(f"Polling کرش کرد: {e}")
            time.sleep(10)

# --- تحلیل سیگنال (ساده‌شده برای تست) ---
def analyze_and_signal():
    if not active_chats:
        return
    price = fetch_gold_price()
    if price:
        for chat_id in active_chats:
            send_telegram(chat_id, f"تست سیگنال: قیمت فعلی {price:,.0f}")

# --- scheduler ---
def scheduler_thread():
    schedule.every(2).minutes.do(analyze_and_signal)
    logger.info("Scheduler شروع شد")
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- صفحه اصلی ---
@app.route('/')
def home():
    return "ربات فعال! لاگ‌ها را چک کنید."

# --- اجرا با try/except ---
if __name__ == '__main__':
    try:
        test_telegram_api()
        threading.Thread(target=scheduler_thread, daemon=True).start()
        threading.Thread(target=telegram_polling, daemon=True).start()
        logger.info("Threadها استارت شدند")
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        logger.critical(f"خطای استارت: {e}")

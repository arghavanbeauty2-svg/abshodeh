from flask import Flask
import requests
import json
import logging
import threading
import time
import schedule

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

API_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
last_update_id = 0
active_chats = set()
polling_running = False

# --- تست API در استارت ---
def test_gold_api():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    try:
        resp = requests.get(API_URL, headers=headers, timeout=15)
        logger.info(f"API وضعیت: {resp.status_code}")
        if resp.status_code != 200:
            logger.error(f"API خطا: {resp.status_code} - {resp.text[:200]}")
            return None
        data = resp.json()
        logger.info(f"API پاسخ: {json.dumps(data, ensure_ascii=False)[:500]}")
        
        for item in data.get('gold', []):
            if item.get('symbol') == 'IR_GOLD_MELTED':
                price = float(item['price'])
                logger.info(f"قیمت پیدا شد: {price:,.0f}")
                return price
        logger.warning("طلای آب‌شده پیدا نشد در JSON")
        return None
    except Exception as e:
        logger.error(f"خطا در تست API: {e}")
        return None

# تست فوری
price_test = test_gold_api()

# --- دریافت قیمت (با fallback) ---
def fetch_gold_price():
    price = test_gold_api()
    if price:
        return price
    # Fallback: قیمت موقت (برای تست)
    logger.warning("استفاده از قیمت پیش‌فرض (تست)")
    return 12345678  # فقط برای تست — بعداً حذف کنید

# --- ارسال با دکمه ---
def send_price_with_button(chat_id):
    price = fetch_gold_price()
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
            logger.info(f"پیام ارسال شد به {chat_id}")
    except Exception as e:
        logger.error(f"ارسال شکست: {e}")

# --- polling ---
def telegram_polling():
    global polling_running, last_update_id
    if polling_running: return
    polling_running = True
    logger.info("Polling شروع شد")
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
                    active_chats.add(chat_id)
                    if text == '/start':
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                      data={'chat_id': chat_id, 'text': '✅ ربات فعال شد!'})
                        send_price_with_button(chat_id)
                elif 'callback_query' in update:
                    cb = update['callback_query']
                    chat_id = cb['message']['chat']['id']
                    message_id = cb['message']['message_id']
                    if cb['data'] == 'get_price':
                        # ویرایش پیام
                        price = fetch_gold_price()
                        new_text = f"💰 **قیمت لحظه‌ای طلای آب‌شده**\n`{price:,.0f} تومان`\n\nکلیک برای بروزرسانی 👇"
                        payload = {
                            'chat_id': chat_id,
                            'message_id': message_id,
                            'text': new_text,
                            'parse_mode': 'Markdown',
                            'reply_markup': json.dumps(keyboard)
                        }
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText", data=payload)
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                                      data={'callback_query_id': cb['id']})
        except Exception as e:
            logger.error(f"Polling کرش: {e}")
            time.sleep(10)

# --- scheduler ---
def scheduler_thread():
    schedule.every(2).minutes.do(lambda: logger.info("تیک ۲ دقیقه"))
    logger.info("Scheduler شروع شد")
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- استارت ---
logger.info("استارت threadها...")
threading.Thread(target=telegram_polling, daemon=True).start()
threading.Thread(target=scheduler_thread, daemon=True).start()

@app.route('/')
def home():
    return "ربات فعال!"

# --- حذف webhook ---
requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true")

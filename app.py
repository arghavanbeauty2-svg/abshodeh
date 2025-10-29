from flask import Flask, request, abort
import requests
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
WEBHOOK_URL = "https://abshodeh.onrender.com/webhook"  # Render URL شما
keyboard = {"inline_keyboard": [[{"text": "🔄 استعلام مجدد", "callback_data": "get_price"}]]}

# --- Nobitex API (بدون پروکسی، با DNS عمومی) ---
def fetch_gold_price():
    try:
        # استفاده از DNS عمومی Google برای resolve .ir
        resp = requests.get("https://8.8.8.8/resolve?name=api.nobitex.ir", timeout=5).json()
        if 'Answer' in resp:
            ip = resp['Answer'][0]['data']
            url = f"https://{ip}/v2/orderbook/XAUTUSDT"
            resp = requests.get(url, timeout=10).json()
            if resp.get('status') == 'ok':
                bids = float(resp['bids'][0][0]) if resp['bids'] else 0
                asks = float(resp['asks'][0][0]) if resp['asks'] else 0
                price_tether = (bids + asks) / 2
                price_gram = price_tether * 600000 / 31.1035
                price_irr = int(price_gram * 4.608)
                logger.info(f"Nobitex قیمت: {price_irr:,} تومان")
                return price_irr
    except Exception as e:
        logger.error(f"Nobitex خطا: {e}")
    # Fallback به brsapi.ir با IP مستقیم (از DNS عمومی)
    try:
        brs_ip = requests.get("https://8.8.8.8/resolve?name=brsapi.ir", timeout=5).json()['Answer'][0]['data']
        url = f"https://{brs_ip}/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
        resp = requests.get(url, timeout=10).json()
        for item in resp.get('gold', []):
            if item.get('symbol') == 'IR_GOLD_MELTED':
                price = int(item['price'])
                logger.info(f"brsapi.ir قیمت: {price:,} تومان")
                return price
    except Exception as e:
        logger.error(f"brsapi.ir خطا: {e}")
    return 45545000

# --- ارسال قیمت ---
def send_price(chat_id):
    price = fetch_gold_price()
    message = f"💰 **قیمت طلای آب‌شده**\n`{price:,} تومان`\n\nکلیک برای بروزرسانی 👇"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=payload, timeout=10)

# --- ویرایش ---
def edit_price(chat_id, message_id):
    price = fetch_gold_price()
    new_text = f"💰 **قیمت طلای آب‌شده**\n`{price:,} تومان`\n\nکلیک برای بروزرسانی 👇"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': new_text,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText", data=payload, timeout=10)

# --- Webhook handler ---
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = request.get_json()
        if 'message' in update:
            msg = update['message']
            chat_id = msg['chat']['id']
            text = msg.get('text', '').strip()
            if text == '/start':
                send_price(chat_id)
        elif 'callback_query' in update:
            cb = update['callback_query']
            chat_id = cb['message']['chat']['id']
            message_id = cb['message']['message_id']
            if cb['data'] == 'get_price':
                edit_price(chat_id, message_id)
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                              data={'callback_query_id': cb['id']})
        return '', 200
    abort(403)

# --- setWebhook در استارت ---
@app.before_first_request
def setup_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    payload = {'url': WEBHOOK_URL}
    requests.post(url, data=payload)

@app.route('/')
def home():
    return "ربات فعال با Webhook!"

if __name__ == '__main__':
    app.run()

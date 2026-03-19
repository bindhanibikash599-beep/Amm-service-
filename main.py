import os
import telebot
import requests
import psycopg2
from flask import Flask, request
from threading import Thread
from telebot import types

# --- Configuration (Render Environment Variables) ---
BOT_TOKEN = os.environ.get('bot_token')
SMM_API_URL = os.environ.get('SMM_API_URL') # https://luvsmm.com/api/v2
SMM_API_KEY = os.environ.get('SMM_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')
UPI_GATEWAY_KEY = os.environ.get('UPI_GATEWAY_KEY') # 72e6e8c8-938b-4b4d-bad2-8e3234571d82
CHANNEL_ID = os.environ.get('CHANNEL_ID') # e.g., @YourChannel
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
PROFIT_PERCENT = float(os.environ.get('PROFIT_PERCENTAGE', 10))

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- Database Setup ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id BIGINT PRIMARY KEY, balance FLOAT DEFAULT 0.0, referrals INT DEFAULT 0)''')
    conn.commit()
    cur.close()
    conn.close()

def update_balance(user_id, amount):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = users.balance + %s", (user_id, amount, amount))
    conn.commit()
    cur.close()
    conn.close()

def get_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance, referrals FROM users WHERE user_id = %s", (user_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res if res else (0.0, 0)

# --- Force Join Check ---
def is_subscribed(user_id):
    if not CHANNEL_ID: return True
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return True

# --- Flask Server ---
@app.route('/webhook', methods=['POST'])
def upi_webhook():
    data = request.form
    if data.get('status') == 'COMPLETED':
        user_id = int(data.get('client_id'))
        amount = float(data.get('amount', 0))
        update_balance(user_id, amount)
        bot.send_message(user_id, f"✅ ₹{amount} added to wallet!\n⚠️ *Reminder: Deposits are non-refundable.*", parse_mode="Markdown")
    return "OK", 200

@app.route('/')
def home(): return "Bot is Active"

# --- Bot Handlers ---

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if not is_subscribed(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_ID.replace('@','')}"))
        markup.add(types.InlineKeyboardButton("🔄 Joined - Refresh", callback_data="check_joined"))
        bot.send_message(message.chat.id, f"❌ You must join our channel to use this bot!\nJoin {CHANNEL_ID} and click refresh.", reply_markup=markup)
        return

    update_balance(user_id, 0)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📂 Services", "🛒 New Order")
    markup.add("💳 Add Funds", "💰 My Wallet")
    markup.add("👥 Referral", "🔗 Follow Me", "📊 Status")
    
    welcome = (
        "🔥 **Welcome to Arshux SMM Bot** 🔥\n\n"
        "🚀 Best & Fastest SMM Services.\n"
        "💰 Minimum Deposit: ₹1\n\n"
        "⚠️ **WARNING:**\n"
        "1. Strictly **NO REFUNDS** after adding funds.\n"
        "2. Once an order is placed, it cannot be cancelled or refunded."
    )
    bot.send_message(message.chat.id, welcome, reply_markup=markup, parse_mode="Markdown")

# Social Media
@bot.message_handler(func=lambda message: message.text == "🔗 Follow Me")
def social_links(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📸 Instagram (Arshux)", url="https://www.instagram.com/arshux._"))
    markup.add(types.InlineKeyboardButton("📺 YouTube (Silk Road)", url="https://www.youtube.com/@silk_road402"))
    bot.send_message(message.chat.id, "Follow and Subscribe to stay updated! ❤️", reply_markup=markup)

# Add Funds
@bot.message_handler(func=lambda message: message.text == "💳 Add Funds")
def add_funds(message):
    warn_text = (
        "💳 **Add Funds (Automatic)**\n\n"
        "⚠️ **REFUND POLICY:**\n"
        "Money once added cannot be withdrawn or refunded to your bank account. It can only be used for SMM services.\n\n"
        "Enter amount (₹) [Min ₹1]:"
    )
    msg = bot.send_message(message.chat.id, warn_text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_pay)

def process_pay(message):
    try:
        amount = float(message.text)
        if amount < 1:
            bot.reply_to(message, "❌ Min deposit ₹1.")
            return
        
        payload = {
            'key': UPI_GATEWAY_KEY,
            'client_id': message.from_user.id,
            'amount': amount,
            'p_info': 'Wallet Deposit',
            'customer_name': message.from_user.first_name,
            'customer_email': 'user@bot.com',
            'customer_mobile': '9876543210',
            'redirect_url': 'https://t.me/ArshuxSmmBot'
        }
        res = requests.post("https://api.merchant.upigateway.com/v1/create_order", data=payload).json()
        if res.get('status'):
            bot.send_message(message.chat.id, f"🔗 [Pay ₹{amount} now]({res['data']['payment_url']})\n\n*(Note: No refunds once paid)*", parse_mode="Markdown")
    except:
        bot.reply_to(message, "Invalid amount.")

# New Order
@bot.message_handler(func=lambda message: message.text == "🛒 New Order")
def order_1(message):
    order_warn = (
        "🛒 **New Order**\n\n"
        "⚠️ **IMPORTANT:**\n"
        "Check the Link and Service ID twice. Wrong links will not be refunded.\n\n"
        "Enter Service ID (e.g. 709):"
    )
    bot.send_message(message.chat.id, order_warn, parse_mode="Markdown")
    bot.register_next_step_handler(message, order_2)

def order_2(message):
    sid = message.text
    bot.send_message(message.chat.id, "Enter Quantity:")
    bot.register_next_step_handler(message, order_3, sid)

def order_3(message, sid):
    qty = message.text
    bot.send_message(message.chat.id, "Enter Target Link:")
    bot.register_next_step_handler(message, process_order, sid, qty)

def process_order(message, sid, qty):
    link = message.text
    uid = message.from_user.id
    services = requests.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}).json()
    s = next((i for i in services if str(i['service']) == sid), None)
    
    if s:
        cost = (float(s['rate']) * (1 + (PROFIT_PERCENT/100)) / 1000) * int(qty)
        bal, refs = get_user(uid)
        
        if bal >= cost:
            update_balance(uid, -cost)
            res = requests.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'add', 'service': sid, 'link': link, 'quantity': qty}).json()
            if 'order' in res:
                bot.send_message(uid, f"✅ **Order Placed!**\n🆔 ID: {res['order']}\n💰 Cost: ₹{round(cost, 2)}\n\n*No refunds for wrong links.*", parse_mode="Markdown")
            else:
                update_balance(uid, cost)
                bot.send_message(uid, f"❌ Error: {res.get('error')}")
        else:
            bot.send_message(uid, f"❌ Insufficient balance! Need ₹{round(cost, 2)}")
    else:
        bot.send_message(uid, "❌ Service ID invalid.")

# Wallet & Status & Referral
@bot.message_handler(func=lambda message: message.text == "💰 My Wallet")
def my_wallet(message):
    bal, refs = get_user(message.from_user.id)
    bot.send_message(message.chat.id, f"💳 **Wallet Balance: ₹{round(bal, 2)}**")

@bot.message_handler(func=lambda message: message.text == "📊 Status")
def check_status(message):
    msg = bot.send_message(message.chat.id, "Enter Order ID:")
    bot.register_next_step_handler(msg, get_status)

def get_status(message):
    res = requests.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'status', 'order': message.text}).json()
    bot.reply_to(message, f"📊 Status: {res.get('status')}\n📉 Remains: {res.get('remains')}")

# Services
@bot.message_handler(func=lambda message: message.text == "📂 Services")
def show_cats(message):
    services = requests.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}).json()
    cats = sorted(list(set([s['category'] for s in services])))
    markup = types.InlineKeyboardMarkup()
    for c in cats[:15]:
        markup.add(types.InlineKeyboardButton(text=c, callback_data=f"c_{c[:25]}"))
    bot.send_message(message.chat.id, "📁 Select Category:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("c_"))
def show_servs(call):
    cat = call.data[2:]
    services = requests.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}).json()
    text = f"🌟 **Category: {cat}**\n\n"
    for s in services:
        if s['category'].startswith(cat):
            price = round(float(s['rate']) * (1 + (PROFIT_PERCENT/100)), 2)
            text += f"🆔 `{s['service']}` - {s['name']}\n💰 ₹{price} per 1k\n\n"
            if len(text) > 3500: break
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

# Admin Broadcast
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.from_user.id == ADMIN_ID:
        msg = bot.send_message(message.chat.id, "Enter broadcast message:")
        bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    cur.close(); conn.close()
    for u in users:
        try: bot.send_message(u[0], f"📢 **Update:**\n\n{message.text}", parse_mode="Markdown")
        except: continue
    bot.send_message(ADMIN_ID, "✅ Sent!")

if __name__ == "__main__":
    init_db()
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()

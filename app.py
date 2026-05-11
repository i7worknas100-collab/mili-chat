import json
import time
import threading
import sqlite3
import urllib.request
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

# ========== تنظیمات اصلی ==========
TOKEN = "400404882:JYKnasyJGd6y_4rEFeRyHGGZAvE72FlHWIg"
ADMIN_USERNAME = "whysay"

MAX_WAITING = 30
waiting_list = deque(maxlen=MAX_WAITING)
pairs = {}
BROADCAST_MODE = {}

# ========== راه‌اندازی وب سرور (برای Render) ==========
PORT = int(os.environ.get("PORT", 8080))

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"MILI CHAT Bot is Running!")
    
    def log_message(self, format, *args):
        # خاموش کردن لاگ‌های اضافی
        pass

def run_web_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    server.serve_forever()

# اجرای وب سرور در یک ترد جداگانه (برای اینکه رندر خاموشش نکنه)
threading.Thread(target=run_web_server, daemon=True).start()
# ==================================================

# ========== دیتابیس ==========
def db_execute(query, params=(), fetch_one=False, fetch_all=False):
    conn = sqlite3.connect('bot_data.db', timeout=10)
    c = conn.cursor()
    c.execute(query, params)
    if fetch_one:
        result = c.fetchone()
    elif fetch_all:
        result = c.fetchall()
    else:
        result = None
    conn.commit()
    conn.close()
    return result

def init_db():
    db_execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            last_seen INTEGER,
            username TEXT
        )
    ''')
init_db()

# ========== API بله ==========
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

def api_call(method, data=None):
    try:
        url = f"{BASE_URL}/{method}"
        if data:
            req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode())
    except Exception as e:
        print(f"API Error: {e}")
        return None

def send_msg(chat_id, text, kb=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if kb:
        data["reply_markup"] = kb
    return api_call("sendMessage", data)

def edit_msg(chat_id, msg_id, text):
    return api_call("editMessageText", {"chat_id": chat_id, "message_id": msg_id, "text": text})

def answer_cb(cb_id):
    api_call("answerCallbackQuery", {"callback_query_id": cb_id})

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates?timeout=25"
    if offset:
        url += f"&offset={offset}"
    try:
        with urllib.request.urlopen(url, timeout=30) as res:
            data = json.loads(res.read().decode())
            return data if data.get("ok") else {"result": []}
    except Exception as e:
        print(f"GetUpdates Error: {e}")
        return {"result": []}

def is_admin(username):
    return username == ADMIN_USERNAME

# ========== کیبوردها ==========
KB_START = {"inline_keyboard": [[{"text": "🔎 شروع چت", "callback_data": "next"}]]}
KB_CHAT = {"inline_keyboard": [[{"text": "⏭️ پارتنر بعدی", "callback_data": "next"}], [{"text": "🛑 پایان چت", "callback_data": "stop"}]]}
KB_END = {"inline_keyboard": [[{"text": "🔎 شروع دوباره", "callback_data": "next"}], [{"text": "⚠️ گزارش کاربر", "callback_data": "report"}]]}
KB_ADMIN = {"inline_keyboard": [
    [{"text": "📊 آمار", "callback_data": "admin_stats"}],
    [{"text": "📢 پیام همگانی", "callback_data": "admin_broadcast"}],
    [{"text": "🗑️ پاکسازی", "callback_data": "admin_clean"}],
    [{"text": "🔙 بستن", "callback_data": "admin_close"}]
]}
KB_BACK = {"inline_keyboard": [[{"text": "🔙 برگشت", "callback_data": "admin_back"}]]}

# ========== متن‌ها ==========
TXT = {
    "welcome": "🔰 MILI CHAT\n\n🔎 پیدا کردن پارتنر تصادفی\n\nبرای شروع کلیک کنید 👇",
    "search": "🔎 در حال جستجو...",
    "connect": "⚡️ متصل شد!\n🛡️ پارتنر پیدا شد\n\n━━━━━━━━━━━━━━━━━━━━\n💡 توجه:\n• از اطلاعات شخصی خود محافظت کنید\n• به افراد ناشناس زود اعتماد نکنید\n• مکالمه سیاسی ممنوع\n━━━━━━━━━━━━━━━━━━━━",
    "end": "🛑 چت پایان یافت.\n\nبرای شروع مجدد کلیک کنید.",
    "left": "❌ پارتنر شما چت را ترک کرد.\nبرای پیدا کردن پارتنر جدید کلیک کنید.",
    "report": "✅ گزارش شما ثبت شد.",
    "nochat": "🔍 شما در چت نیستید.\nروی Start کلیک کنید.",
    "admin_panel": "🔰 پنل مدیریت MILI CHAT\n\nخوش آمدی ادمین!",
    "stats": "📊 آمار:\n\n👥 کاربران: {}\n🔄 جفت فعال: {}\n⏳ در صف: {}",
    "cleaned": "✅ پاکسازی انجام شد.",
    "broadcast_prompt": "📢 متن پیام رو بفرست:",
    "broadcast_cancel": "❌ لغو شد.",
    "broadcast_done": "✅ پیام همگانی به {} کاربر ارسال شد.",
    "not_admin": "⛔ دسترسی غیرمجاز!",
}

# ========== پیام همگانی ==========
def broadcast_message(admin_id, text):
    users = db_execute("SELECT user_id FROM users", fetch_all=True)
    if not users:
        send_msg(admin_id, "❌ هیچ کاربری وجود ندارد!")
        return 0
    
    send_msg(admin_id, f"📢 در حال ارسال به {len(users)} کاربر...")
    
    success = 0
    fail = 0
    for user in users:
        try:
            send_msg(user[0], f"📢 **پیام همگانی:**\n\n{text}")
            success += 1
            time.sleep(0.2)
        except:
            fail += 1
    
    send_msg(admin_id, TXT["broadcast_done"].format(success))
    return success

# ========== پاکسازی خودکار ==========
def auto_cleaner():
    while True:
        time.sleep(6 * 3600)  # هر 6 ساعت
        old = int(time.time()) - (3 * 86400)  # 3 روز
        conn = sqlite3.connect('bot_data.db')
        deleted = conn.execute("DELETE FROM users WHERE last_seen < ?", (old,)).rowcount
        conn.execute("VACUUM")
        conn.close()
        print(f"🧹 پاکسازی: {deleted} کاربر حذف شد")

# ========== توابع اصلی ==========
def match():
    if len(waiting_list) >= 2:
        a = waiting_list.popleft()
        b = waiting_list.popleft()
        pairs[a] = b
        pairs[b] = a
        send_msg(a, TXT["connect"], KB_CHAT)
        send_msg(b, TXT["connect"], KB_CHAT)
        print(f"✅ جفت شد: {a} <-> {b}")

def get_stats():
    total = db_execute("SELECT COUNT(*) FROM users", fetch_one=True)[0]
    return total, len(pairs), len(waiting_list)

def clean_old():
    old = int(time.time()) - (3 * 86400)
    db_execute("DELETE FROM users WHERE last_seen < ?", (old,))
    conn = sqlite3.connect('bot_data.db')
    conn.execute("VACUUM")
    conn.close()

def handle(chat_id, text, msg_id, cb_id=None, username=""):
    # ذخیره کاربر
    db_execute("INSERT OR REPLACE INTO users (user_id, last_seen, username) VALUES (?, ?, ?)", 
               (chat_id, int(time.time()), username))
    
    # حالت پیام همگانی
    if chat_id in BROADCAST_MODE:
        if text == "/cancel":
            del BROADCAST_MODE[chat_id]
            send_msg(chat_id, TXT["broadcast_cancel"], KB_ADMIN)
        else:
            del BROADCAST_MODE[chat_id]
            broadcast_message(chat_id, text)
        return
    
    # دستور start
    if text == "/start":
        send_msg(chat_id, TXT["welcome"], KB_START)
        return
    
    # پنل ادمین
    if text == "/admin":
        if is_admin(username):
            send_msg(chat_id, TXT["admin_panel"], KB_ADMIN)
        else:
            send_msg(chat_id, TXT["not_admin"])
        return
    
    # پردازش دکمه‌ها
    if cb_id:
        answer_cb(cb_id)
        
        if text == "admin_stats" and is_admin(username):
            total, pairs_count, waiting_count = get_stats()
            send_msg(chat_id, TXT["stats"].format(total, pairs_count, waiting_count), KB_BACK)
            return
        
        if text == "admin_broadcast" and is_admin(username):
            send_msg(chat_id, TXT["broadcast_prompt"])
            BROADCAST_MODE[chat_id] = True
            return
        
        if text == "admin_clean" and is_admin(username):
            clean_old()
            send_msg(chat_id, TXT["cleaned"], KB_ADMIN)
            return
        
        if text == "admin_back" and is_admin(username):
            send_msg(chat_id, TXT["admin_panel"], KB_ADMIN)
            return
        
        if text == "admin_close":
            send_msg(chat_id, "🔰 پنل بسته شد.", KB_START)
            return
        
        if text == "next":
            # قطع ارتباط قبلی
            p = pairs.pop(chat_id, None)
            if p:
                pairs.pop(p, None)
                send_msg(p, TXT["left"], KB_START)
            if chat_id in waiting_list:
                waiting_list.remove(chat_id)
            edit_msg(chat_id, msg_id, TXT["search"])
            if chat_id not in waiting_list and chat_id not in pairs:
                waiting_list.append(chat_id)
            match()
            return
        
        if text == "stop":
            p = pairs.pop(chat_id, None)
            if p:
                pairs.pop(p, None)
                send_msg(p, TXT["left"], KB_START)
            if chat_id in waiting_list:
                waiting_list.remove(chat_id)
            send_msg(chat_id, TXT["end"], KB_START)
            return
        
        if text == "report":
            p = pairs.get(chat_id)
            if p:
                send_msg(chat_id, TXT["report"], KB_START)
                pairs.pop(chat_id, None)
                pairs.pop(p, None)
            else:
                send_msg(chat_id, "⚠️ هیچ پارتنری نیست", KB_START)
            return
    
    # پیام معمولی در چت
    if chat_id in pairs:
        send_msg(pairs[chat_id], f"📝 {text}")
    else:
        if chat_id not in waiting_list:
            send_msg(chat_id, TXT["nochat"], KB_START)

# ========== حلقه اصلی ==========
def main():
    print("=" * 50)
    print("🤖 MILI CHAT Bot Started Successfully!")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print(f"🔌 Web server running on port {PORT}")
    print("=" * 50)
    
    last_id = 0
    
    # ترد جفت‌سازی
    def matching_loop():
        while True:
            time.sleep(2)
            match()
    
    # ترد پاکسازی خودکار
    def cleaner_loop():
        while True:
            time.sleep(6 * 3600)
            auto_cleaner()
    
    threading.Thread(target=matching_loop, daemon=True).start()
    threading.Thread(target=cleaner_loop, daemon=True).start()
    
    # حلقه دریافت آپدیت
    while True:
        try:
            updates = get_updates(last_id + 1)
            if updates and updates.get("result"):
                for update in updates["result"]:
                    last_id = update["update_id"]
                    
                    if "message" in update:
                        m = update["message"]
                        chat_id = str(m["chat"]["id"])
                        text = m.get("text", "")
                        msg_id = m["message_id"]
                        username = m.get("from", {}).get("username", "")
                        handle(chat_id, text, msg_id, username=username)
                    
                    elif "callback_query" in update:
                        c = update["callback_query"]
                        chat_id = str(c["from"]["id"])
                        data = c.get("data", "")
                        msg_id = c["message"]["message_id"]
                        cb_id = c["id"]
                        username = c.get("from", {}).get("username", "")
                        handle(chat_id, data, msg_id, cb_id, username)
        
        except Exception as e:
            print(f"Main loop error: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()

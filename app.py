import json
import os
import random
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify
import requests
from apscheduler.schedulers.background import BackgroundScheduler

# ========== KONFIGURASI ==========
TOKEN = "6546544:AAHTR0awcVGQROy0iX3lmdtPGbxo8HCaW5U"
ADMIN_ID = 515154848
# =================================

app = Flask(__name__)

# File untuk menyimpan data
CONTACTS_FILE = "contacts.json"
DATA_FILE = "users.json"
PROMO_FILE = "promo.json"
CONFIG_FILE = "config.json"

# Variabel global
last_broadcast_log = []

# ============ FUNGSI LOAD DATA ============
def load_users():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return set(data) if data else set()
    except:
        return set()

def save_users(users):
    with open(DATA_FILE, "w") as f:
        json.dump(list(users), f)

def load_promos():
    try:
        with open(PROMO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("promos", []), data.get("settings", {"broadcast_interval_minutes": 20, "send_image": True})
    except Exception as e:
        print(f"Error loading promos: {e}")
        return [], {"broadcast_interval_minutes": 20, "send_image": True}

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"welcome_message": "🌟 SELAMAT DATANG DI KAJIAN4D OFFICIAL 🌟", "website_url": "https://siteq.link/kajian4d"}

# Load data
users = load_users()
promos, promo_settings = load_promos()
config = load_config()

print(f"✅ Loaded {len(promos)} promos")
print(f"✅ Broadcast interval: {promo_settings.get('broadcast_interval_minutes', 20)} minutes")
print(f"✅ Send image: {promo_settings.get('send_image', True)}")

# ============ FUNGSI KONTAK ============
def save_contact(user_id, username, first_name, last_name, phone_number):
    try:
        contacts = []
        if os.path.exists(CONTACTS_FILE):
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                contacts = json.load(f)
        
        existing = False
        for i, c in enumerate(contacts):
            if c.get("user_id") == user_id:
                contacts[i] = {
                    "user_id": user_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name or "",
                    "full_name": f"{first_name} {last_name or ''}".strip(),
                    "phone_number": phone_number,
                    "shared_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                existing = True
                break
        
        if not existing:
            contacts.append({
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name or "",
                "full_name": f"{first_name} {last_name or ''}".strip(),
                "phone_number": phone_number,
                "shared_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        
        with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(contacts, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving contact: {e}")
        return False

def get_all_contacts():
    try:
        if os.path.exists(CONTACTS_FILE):
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return []

def get_contact_count():
    return len(get_all_contacts())

# ============ FUNGSI TELEGRAM ============
def send_telegram_photo(chat_id, photo_url, caption, reply_markup=None):
    """Kirim pesan dengan gambar"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except Exception as e:
        print(f"Error send photo: {e}")
        return None

def send_telegram_message(chat_id, text, reply_markup=None):
    """Kirim pesan teks biasa"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except Exception as e:
        print(f"Error send message: {e}")
        return None

def send_promo_with_image(chat_id, promo):
    """Kirim promo lengkap dengan gambar"""
    send_image = promo_settings.get("send_image", True)
    image_url = promo.get("image_url", "")
    
    keyboard = {
        "inline_keyboard": [
            [{"text": promo.get("button_text", "🔥 Klaim Bonus"), "url": promo.get("button_url", config.get("website_url"))}]
        ]
    }
    
    if send_image and image_url and image_url.strip():
        result = send_telegram_photo(chat_id, image_url, promo.get("message", ""), keyboard)
        if result and result.get("ok"):
            return True
        else:
            return send_telegram_message(chat_id, promo.get("message", ""), keyboard)
    else:
        return send_telegram_message(chat_id, promo.get("message", ""), keyboard)

def send_main_menu(chat_id):
    welcome_msg = config.get("welcome_message", "🌟 SELAMAT DATANG DI KAJIAN4D OFFICIAL 🌟")
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "📞 Share Kontak Saya", "callback_data": "share_contact"}],
            [{"text": "🌐 Kunjungi Website", "url": config.get("website_url")}],
            [{"text": "🎰 Lihat Semua Promo", "callback_data": "list_promos"}],
            [{"text": "ℹ️ Bantuan", "callback_data": "help"}]
        ]
    }
    send_telegram_message(chat_id, welcome_msg, reply_markup=keyboard)

def send_promo_list(chat_id):
    if not promos:
        send_telegram_message(chat_id, "Belum ada promo tersedia.")
        return
    
    keyboard = {"inline_keyboard": []}
    row = []
    for promo in promos:
        row.append({"text": promo['title'][:25], "callback_data": f"promo_{promo['id']}"})
        if len(row) == 2:
            keyboard["inline_keyboard"].append(row)
            row = []
    if row:
        keyboard["inline_keyboard"].append(row)
    
    keyboard["inline_keyboard"].append([{"text": "🔙 Kembali ke Menu", "callback_data": "back_to_menu"}])
    send_telegram_message(chat_id, "*📋 DAFTAR PROMO KAJIAN4D*\n\nKlik promo yang ingin kamu lihat:", reply_markup=keyboard)

def send_contact_request(chat_id):
    contact_keyboard = {
        "keyboard": [[{"text": "📱 Share Nomor Saya", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    
    msg = """📞 *SHARE KONTAK ANDA*

Dengan membagikan nomor telepon, Anda akan mendapatkan update promo terbaru dan bonus special!

🔒 *Data Anda aman dan terjaga kerahasiaannya*

👇 Tekan tombol di bawah untuk share kontak👇"""
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(contact_keyboard)
    }
    
    try:
        requests.post(url, json=payload, timeout=30)
    except Exception as e:
        print(f"Error send contact request: {e}")

# ============ BROADCAST OTOMATIS (DIJAMIN JALAN) ============
broadcast_count = 0
broadcast_history = []

def do_broadcast():
    """Fungsi broadcast yang akan dijalankan setiap interval"""
    global broadcast_count, broadcast_history
    
    print("=" * 60)
    print(f"📢 [BROADCAST] Dimulai pada {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if not promos:
        print("❌ Tidak ada promo untuk broadcast")
        return
    
    # Pilih promo acak
    promo = random.choice(promos)
    users_list = list(load_users())
    
    if len(users_list) == 0:
        print("⚠️ Belum ada user yang terdaftar. Broadcast skipped.")
        return
    
    print(f"📢 Judul: {promo['title']}")
    print(f"👥 Target: {len(users_list)} user")
    print(f"🖼️ Gambar: {'YA' if promo.get('image_url') else 'TIDAK'}")
    
    success = 0
    fail = 0
    
    for user_id in users_list:
        result = send_promo_with_image(user_id, promo)
        if result:
            success += 1
        else:
            fail += 1
        time.sleep(0.1)  # Jeda 0.1 detik antar kirim
    
    broadcast_count += 1
    
    # Simpan history
    broadcast_history.insert(0, {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": promo['title'],
        "success": success,
        "fail": fail,
        "total": len(users_list)
    })
    
    # Keep hanya 10 history terakhir
    while len(broadcast_history) > 10:
        broadcast_history.pop()
    
    print(f"✅ Broadcast selesai!")
    print(f"✅ Berhasil: {success} user")
    print(f"❌ Gagal: {fail} user")
    print(f"📊 Total broadcast ke-{broadcast_count}")
    print("=" * 60)

def start_scheduler():
    """Memulai scheduler untuk broadcast otomatis"""
    interval_minutes = promo_settings.get("broadcast_interval_minutes", 20)
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=do_broadcast,
        trigger="interval",
        minutes=interval_minutes,
        id="broadcast_job",
        next_run_time=datetime.now()  # Langsung jalan pertama kali
    )
    scheduler.start()
    
    print(f"⏰ Scheduler dimulai!")
    print(f"📅 Broadcast pertama: SEKARANG (dalam beberapa detik)")
    print(f"🔄 Interval: setiap {interval_minutes} menit")
    
    return scheduler

# ============ WEBHOOK UTAMA ============
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "ok"})
        
        # Proses message
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            username = message["chat"].get("username", "unknown")
            first_name = message["chat"].get("first_name", "")
            
            # Simpan user baru
            current_users = load_users()
            if chat_id not in current_users:
                current_users.add(chat_id)
                save_users(current_users)
                print(f"📝 User baru: {first_name} (@{username}) - Total: {len(current_users)}")
            
            # Cek kontak yang dishare
            contact = message.get("contact")
            if contact:
                phone_number = contact.get("phone_number")
                first_name = contact.get("first_name", "")
                last_name = contact.get("last_name", "")
                user_id = contact.get("user_id", chat_id)
                
                save_contact(user_id, username, first_name, last_name, phone_number)
                
                confirm_msg = f"""✅ *TERIMA KASIH TELAH SHARE KONTAK!*

Halo *{first_name}*, nomor Anda *{phone_number}* telah tersimpan.

🎁 *BONUS UNTUK ANDA:*
Member yang sudah share kontak berhak mendapatkan bonus special!

🏠 Ketik /start untuk kembali ke menu utama"""
                send_telegram_message(chat_id, confirm_msg)
                
                admin_msg = f"""📞 *KONTAK BARU!*

👤 Nama: {first_name} {last_name}
📱 Nomor: {phone_number}
📊 Total Kontak: {get_contact_count()}"""
                send_telegram_message(ADMIN_ID, admin_msg)
                
                remove_keyboard = {"remove_keyboard": True}
                url_remove = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                requests.post(url_remove, json={
                    "chat_id": chat_id,
                    "text": "✅ Terima kasih! Ketik /start untuk kembali",
                    "reply_markup": json.dumps(remove_keyboard)
                })
            
            # Handle perintah
            elif text == "/start":
                send_main_menu(chat_id)
            
            elif text == "/share":
                send_contact_request(chat_id)
            
            elif text == "/promos":
                send_promo_list(chat_id)
            
            elif text == "/help":
                help_msg = """📖 *Panduan Bot KAJIAN4D*

/start - Menu utama
/help - Panduan ini
/promos - Lihat daftar promo
/share - Share kontak Anda

*Fitur:*
✅ Share kontak untuk dapat bonus
✅ Broadcast otomatis setiap 20 menit
✅ Gambar promo tampil otomatis"""
                send_telegram_message(chat_id, help_msg)
            
            elif text == "/status" and str(chat_id) == str(ADMIN_ID):
                next_broadcast = "Sedang berjalan..."
                status_msg = f"""📊 *STATUS BOT*

🔄 Status: ✅ AKTIF
👥 Total user: {len(load_users())}
📞 Total kontak: {get_contact_count()}
🎁 Total promo: {len(promos)}
⏱️ Interval: {promo_settings.get('broadcast_interval_minutes', 20)} MENIT
📢 Total broadcast: {broadcast_count} kali

📅 Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📋 *History Broadcast:*
"""
                for i, h in enumerate(broadcast_history[:5], 1):
                    status_msg += f"\n{i}. {h['time']}\n   {h['title'][:30]}... (✅{h['success']} user)"
                
                send_telegram_message(chat_id, status_msg)
            
            elif text == "/test_broadcast" and str(chat_id) == str(ADMIN_ID):
                send_telegram_message(chat_id, "⏳ Menjalankan broadcast test...")
                do_broadcast()
                send_telegram_message(chat_id, "✅ Broadcast test selesai! Cek log.")
            
            elif text == "/contacts" and str(chat_id) == str(ADMIN_ID):
                contacts = get_all_contacts()
                if contacts:
                    msg = "*📞 DAFTAR KONTAK*\n\n"
                    for i, c in enumerate(contacts[-10:], 1):
                        msg += f"{i}. {c.get('full_name', '-')} - {c.get('phone_number', '-')}\n"
                    msg += f"\n📊 Total: {len(contacts)} kontak"
                    send_telegram_message(chat_id, msg)
                else:
                    send_telegram_message(chat_id, "Belum ada kontak.")
            
            else:
                send_main_menu(chat_id)
        
        # Proses callback query
        elif "callback_query" in data:
            callback = data["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data_callback = callback.get("data", "")
            
            if data_callback == "share_contact":
                send_contact_request(chat_id)
            elif data_callback == "list_promos":
                send_promo_list(chat_id)
            elif data_callback == "back_to_menu":
                send_main_menu(chat_id)
            elif data_callback == "help":
                help_msg = "📖 *Bantuan*\n\n/start - Menu utama\n/promos - Lihat promo\n/share - Share kontak"
                send_telegram_message(chat_id, help_msg)
            elif data_callback.startswith("promo_"):
                try:
                    promo_id = int(data_callback.split("_")[1])
                    promo = next((p for p in promos if p.get('id') == promo_id), None)
                    if promo:
                        send_promo_with_image(chat_id, promo)
                    else:
                        send_telegram_message(chat_id, "Promo tidak ditemukan.")
                except Exception as e:
                    print(f"Error: {e}")
            
            # Answer callback
            url_answer = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
            requests.post(url_answer, json={"callback_query_id": callback["id"]})
        
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

# ============ FLASK ROUTES ============
@app.route('/')
def home():
    return """
    <html>
    <head><title>KAJIAN4D Bot</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>🤖 KAJIAN4D BOT TELEGRAM</h1>
        <p style="color: green; font-size: 20px;">✅ BOT AKTIF!</p>
        <p>🔄 Broadcast: <strong>AKTIF setiap 20 menit</strong></p>
        <p>🖼️ Gambar: <strong>AKTIF</strong></p>
        <p>📞 Share Kontak: <strong>AKTIF</strong></p>
        <hr>
        <p>📱 Kirim <code>/start</code> ke bot di Telegram</p>
        <p>🔧 <a href="/set_webhook">Set Webhook</a></p>
        <p>📊 <a href="/api/stats">Statistik</a></p>
    </body>
    </html>
    """

@app.route('/set_webhook')
def set_webhook():
    render_url = os.environ.get('RENDER_EXTERNAL_URL', request.host_url)
    if render_url.endswith('/'):
        render_url = render_url[:-1]
    webhook_url = f"{render_url}/webhook"
    
    requests.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    response = requests.post(url, json={"url": webhook_url})
    result = response.json()
    
    if result.get("ok"):
        return f"✅ Webhook berhasil! URL: {webhook_url}<br>🔄 Broadcast akan berjalan otomatis!"
    else:
        return f"❌ Gagal: {result}"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/api/stats')
def api_stats():
    return jsonify({
        'users': len(load_users()),
        'contacts': get_contact_count(),
        'promos': len(promos),
        'broadcast_count': broadcast_count,
        'interval': promo_settings.get('broadcast_interval_minutes', 20),
        'status': 'active',
        'last_broadcasts': broadcast_history[:5]
    })

@app.route('/api/contacts')
def api_contacts():
    return jsonify({
        'total': get_contact_count(),
        'contacts': get_all_contacts()
    })

@app.route('/api/trigger_broadcast', methods=['POST'])
def trigger_broadcast():
    """Manual trigger broadcast via API"""
    do_broadcast()
    return jsonify({'status': 'broadcast_triggered', 'time': datetime.now().isoformat()})

# ============ MAIN ============
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 KAJIAN4D BOT TELEGRAM - DENGAN BROADCAST OTOMATIS")
    print("=" * 60)
    
    # Cek koneksi
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        if response.ok:
            bot_info = response.json().get("result")
            print(f"✅ Bot terhubung: @{bot_info.get('username')}")
        else:
            print("❌ Token tidak valid!")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print(f"✅ Total promo: {len(promos)}")
    print(f"👥 Total user: {len(load_users())}")
    print(f"📞 Total kontak: {get_contact_count()}")
    print("=" * 60)
    
    # START SCHEDULER (PASTI JALAN)
    scheduler = start_scheduler()
    
    print("\n📱 Buka URL /set_webhook untuk mengaktifkan webhook")
    print("📱 Kirim /start ke bot di Telegram")
    print("📢 Broadcast akan berjalan OTOMATIS setiap 20 menit!")
    print("=" * 60)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
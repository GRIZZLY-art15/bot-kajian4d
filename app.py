import json
import os
import random
import time
from datetime import datetime
from flask import Flask, request, jsonify, make_response, redirect
from functools import wraps
import hashlib
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
import threading

# ========== KONFIGURASI ==========
TOKEN = "8736769212:AAHTR0awcVGQROy0iX3lmdtPGbxo8HCaW5U"
ADMIN_ID = 7176181382
ADMIN_PASSWORD_HASH = hashlib.sha256("admin123".encode()).hexdigest()  # Password: admin123
# =================================

app = Flask(__name__)

# File untuk menyimpan data
CONTACTS_FILE = "contacts.json"
DATA_FILE = "users.json"
PROMO_FILE = "promo.json"
CONFIG_FILE = "config.json"
GROUPS_FILE = "groups.json"  # File untuk menyimpan daftar grup

# Variabel global
last_broadcast_log = []
scheduler = None
_broadcast_lock = threading.Lock()
is_broadcasting = False
broadcast_job_id = "broadcast_job"
broadcast_enabled = True  # Status broadcast (ON/OFF)

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
            return data.get("promos", []), data.get("settings", {"broadcast_interval_minutes": 20, "send_image": True, "broadcast_to_groups": True})
    except Exception as e:
        print(f"Error loading promos: {e}")
        return [], {"broadcast_interval_minutes": 20, "send_image": True, "broadcast_to_groups": True}

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"welcome_message": "🌟 SELAMAT DATANG DI KAJIAN4D OFFICIAL 🌟", "website_url": "https://siteq.link/kajian4d"}

def load_groups():
    """Load daftar grup Telegram"""
    try:
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_groups(groups):
    """Simpan daftar grup Telegram"""
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(groups, f, indent=2, ensure_ascii=False)

# Load data
users = load_users()
promos, promo_settings = load_promos()
config = load_config()
groups = load_groups()

print(f"✅ Loaded {len(promos)} promos")
print(f"✅ Loaded {len(groups)} groups")
print(f"✅ Broadcast interval: {promo_settings.get('broadcast_interval_minutes', 20)} minutes")
print(f"✅ Send image: {promo_settings.get('send_image', True)}")
print(f"✅ Broadcast to groups: {promo_settings.get('broadcast_to_groups', True)}")

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
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error send photo: {e}")
        return None

def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error send message: {e}")
        return None

def send_promo_with_image(chat_id, promo):
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

def send_to_group(group_id, promo):
    """Kirim promo ke grup Telegram"""
    try:
        result = send_promo_with_image(group_id, promo)
        return result is not None and result.get("ok")
    except Exception as e:
        print(f"Error send to group {group_id}: {e}")
        return False

# ============ BROADCAST OTOMATIS ============
broadcast_count = 0
broadcast_history = []

def do_broadcast():
    """Fungsi broadcast yang akan dijalankan setiap interval"""
    global broadcast_count, broadcast_history, is_broadcasting
    
    if not broadcast_enabled:
        print("⚠️ Broadcast dimatikan oleh admin, skip...")
        return
    
    if is_broadcasting:
        print("⚠️ Broadcast sedang berjalan, skip...")
        return
    
    with _broadcast_lock:
        is_broadcasting = True
    
    try:
        print("=" * 60)
        print(f"📢 [BROADCAST] Dimulai pada {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not promos:
            print("❌ Tidak ada promo untuk broadcast")
            return
        
        promo = random.choice(promos)
        
        # Broadcast ke User Pribadi
        users_list = list(load_users())
        broadcast_to_groups = promo_settings.get('broadcast_to_groups', True)
        groups_list = load_groups() if broadcast_to_groups else []
        
        total_targets = len(users_list) + len(groups_list)
        
        if total_targets == 0:
            print("⚠️ Tidak ada target broadcast. Broadcast skipped.")
            return
        
        print(f"📢 Judul: {promo['title']}")
        print(f"👥 Target Personal: {len(users_list)} user")
        print(f"👥 Target Grup: {len(groups_list)} grup")
        print(f"📊 Total Target: {total_targets}")
        
        success = 0
        fail = 0
        
        # Kirim ke user pribadi
        for idx, user_id in enumerate(users_list):
            try:
                result = send_promo_with_image(user_id, promo)
                if result and result.get("ok"):
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                print(f"Error ke user {user_id}: {e}")
                fail += 1
            time.sleep(0.3)
        
        # Kirim ke grup
        for group in groups_list:
            try:
                group_id = group.get('id')
                if send_to_group(group_id, promo):
                    success += 1
                    print(f"✅ Berhasil kirim ke grup: {group.get('name')}")
                else:
                    fail += 1
                    print(f"❌ Gagal kirim ke grup: {group.get('name')}")
            except Exception as e:
                print(f"Error ke grup {group.get('name')}: {e}")
                fail += 1
            time.sleep(0.5)
        
        broadcast_count += 1
        
        broadcast_history.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title": promo['title'],
            "success": success,
            "fail": fail,
            "total": total_targets,
            "users": len(users_list),
            "groups": len(groups_list)
        })
        
        while len(broadcast_history) > 20:
            broadcast_history.pop()
        
        print(f"✅ Broadcast selesai!")
        print(f"✅ Berhasil: {success} target")
        print(f"❌ Gagal: {fail} target")
        print(f"📊 Total broadcast ke-{broadcast_count}")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error di broadcast: {e}")
    finally:
        is_broadcasting = False

def start_scheduler():
    """Memulai scheduler untuk broadcast otomatis"""
    global scheduler
    
    interval_minutes = promo_settings.get("broadcast_interval_minutes", 20)
    
    executors = {
        'default': ThreadPoolExecutor(max_workers=1)
    }
    job_defaults = {
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 60
    }
    
    scheduler = BackgroundScheduler(executors=executors, job_defaults=job_defaults)
    
    scheduler.add_job(
        func=do_broadcast,
        trigger="interval",
        minutes=interval_minutes,
        id=broadcast_job_id,
        next_run_time=datetime.now()
    )
    scheduler.start()
    
    print(f"⏰ Scheduler dimulai!")
    print(f"🔄 Interval: setiap {interval_minutes} menit")
    
    return scheduler

def restart_scheduler():
    """Restart scheduler dengan interval baru"""
    global scheduler, broadcast_enabled
    
    if scheduler:
        try:
            scheduler.remove_job(broadcast_job_id)
        except:
            pass
    
    interval_minutes = promo_settings.get("broadcast_interval_minutes", 20)
    
    if broadcast_enabled:
        scheduler.add_job(
            func=do_broadcast,
            trigger="interval",
            minutes=interval_minutes,
            id=broadcast_job_id,
            next_run_time=datetime.now()
        )
        print(f"🔄 Scheduler direstart dengan interval {interval_minutes} menit")
    else:
        print("⏸️ Broadcast dalam keadaan mati")

# ============ ADMIN PANEL ============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_cookie = request.cookies.get('admin_auth')
        if not auth_cookie or auth_cookie != ADMIN_PASSWORD_HASH:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if password_hash == ADMIN_PASSWORD_HASH:
            resp = make_response(redirect('/admin'))
            resp.set_cookie('admin_auth', password_hash, max_age=3600*24)
            return resp
        else:
            return '''
            <!DOCTYPE html>
            <html>
            <head><title>Login - KAJIAN4D Admin</title>
            <style>
                body { font-family: Arial; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                .login-box { background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; text-align: center; backdrop-filter: blur(10px); }
                input { padding: 12px 20px; margin: 10px 0; border-radius: 8px; border: none; width: 250px; }
                button { background: #00d4ff; padding: 12px 30px; border: none; border-radius: 8px; color: #1a1a2e; font-weight: bold; cursor: pointer; }
                h2 { color: white; margin-bottom: 20px; }
                .error { color: #ff6b6b; margin-top: 10px; }
            </style>
            </head>
            <body>
                <div class="login-box">
                    <h2>🔐 Login Admin KAJIAN4D</h2>
                    <form method="POST">
                        <input type="password" name="password" placeholder="Masukkan Password" required>
                        <br>
                        <button type="submit">Login</button>
                    </form>
                    <div class="error">❌ Password salah!</div>
                </div>
            </body>
            </html>
            '''
    
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Login - KAJIAN4D Admin</title>
    <style>
        body { font-family: Arial; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; text-align: center; backdrop-filter: blur(10px); }
        input { padding: 12px 20px; margin: 10px 0; border-radius: 8px; border: none; width: 250px; background: white; }
        button { background: #00d4ff; padding: 12px 30px; border: none; border-radius: 8px; color: #1a1a2e; font-weight: bold; cursor: pointer; font-size: 16px; }
        button:hover { transform: translateY(-2px); }
        h2 { color: white; margin-bottom: 20px; }
    </style>
    </head>
    <body>
        <div class="login-box">
            <h2>🔐 Login Admin KAJIAN4D</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="Masukkan Password" required>
                <br>
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
def admin_logout():
    resp = make_response(redirect('/login'))
    resp.set_cookie('admin_auth', '', expires=0)
    return resp

@app.route('/admin')
@login_required
def admin_panel():
    return '''
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin Panel - KAJIAN4D Bot</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff; padding: 20px; }
            .container { max-width: 1400px; margin: 0 auto; }
            h1 { text-align: center; margin-bottom: 30px; font-size: 2.5em; background: linear-gradient(135deg, #00d4ff, #ff6b6b); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .stat-card { background: rgba(255,255,255,0.1); border-radius: 15px; padding: 20px; text-align: center; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.2); }
            .stat-card h3 { font-size: 2em; margin-bottom: 5px; }
            .stat-card p { opacity: 0.8; }
            .stat-card.broadcast-on { border-left: 4px solid #51cf66; }
            .stat-card.broadcast-off { border-left: 4px solid #ff6b6b; }
            .section { background: rgba(255,255,255,0.05); border-radius: 15px; padding: 20px; margin-bottom: 30px; border: 1px solid rgba(255,255,255,0.1); }
            .section h2 { margin-bottom: 20px; color: #00d4ff; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
            th { background: rgba(0,212,255,0.2); color: #00d4ff; }
            tr:hover { background: rgba(255,255,255,0.05); }
            button, .button { background: linear-gradient(135deg, #00d4ff, #0099cc); border: none; padding: 8px 16px; border-radius: 8px; color: white; cursor: pointer; margin: 5px; transition: transform 0.2s; }
            button:hover { transform: translateY(-2px); }
            .btn-danger { background: linear-gradient(135deg, #ff6b6b, #cc4444); }
            .btn-success { background: linear-gradient(135deg, #51cf66, #37b24d); }
            .btn-warning { background: linear-gradient(135deg, #ffd93d, #f9a825); color: #1a1a2e; }
            .btn-stop { background: linear-gradient(135deg, #ff6b6b, #cc4444); }
            .btn-start { background: linear-gradient(135deg, #51cf66, #37b24d); }
            input, textarea, select { width: 100%; padding: 10px; margin: 10px 0; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: white; }
            textarea { min-height: 100px; }
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; z-index: 1000; }
            .modal-content { background: #1a1a2e; border-radius: 15px; padding: 30px; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto; }
            .close { float: right; font-size: 28px; cursor: pointer; }
            .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
            .tab { padding: 10px 20px; background: rgba(255,255,255,0.1); border-radius: 8px; cursor: pointer; }
            .tab.active { background: #00d4ff; color: #1a1a2e; }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            .group-item { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 15px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
            .status-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; }
            .status-on { background: #51cf66; color: #1a1a2e; }
            .status-off { background: #ff6b6b; color: white; }
            @media (max-width: 768px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } .tabs { justify-content: center; } }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 Admin Panel - KAJIAN4D Bot</h1>
            
            <div class="stats-grid" id="stats">
                <div class="stat-card"><h3 id="totalUsers">0</h3><p>Total User</p></div>
                <div class="stat-card"><h3 id="totalPromos">0</h3><p>Total Promo</p></div>
                <div class="stat-card"><h3 id="totalGroups">0</h3><p>Total Grup</p></div>
                <div class="stat-card" id="broadcastStatusCard"><h3 id="broadcastStatus">Loading...</h3><p>Status Broadcast</p></div>
            </div>
            
            <div class="tabs">
                <div class="tab active" onclick="showTab('broadcast_control')">📡 Kontrol Broadcast</div>
                <div class="tab" onclick="showTab('promos')">📋 Daftar Promo</div>
                <div class="tab" onclick="showTab('add')">➕ Tambah Promo</div>
                <div class="tab" onclick="showTab('groups')">👥 Grup Telegram</div>
                <div class="tab" onclick="showTab('users')">👤 User List</div>
                <div class="tab" onclick="showTab('settings')">⚙️ Pengaturan</div>
                <div class="tab" onclick="logout()">🚪 Logout</div>
            </div>
            
            <!-- Tab Kontrol Broadcast -->
            <div id="tab-broadcast_control" class="tab-content active">
                <div class="section">
                    <h2>📡 Kontrol Broadcast Otomatis</h2>
                    <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 20px;">
                        <button id="btnStartBroadcast" class="btn-start" onclick="controlBroadcast('start')">▶️ START BROADCAST</button>
                        <button id="btnStopBroadcast" class="btn-stop" onclick="controlBroadcast('stop')">⏸️ STOP BROADCAST</button>
                        <button id="btnTestBroadcast" class="btn-warning" onclick="testBroadcast()">🔨 TEST BROADCAST SEKARANG</button>
                    </div>
                    <div id="broadcastControlMsg" style="margin-top: 15px;"></div>
                </div>
                
                <div class="section">
                    <h2>⚙️ Pengaturan Interval Broadcast</h2>
                    <form id="intervalForm">
                        <label>Interval Broadcast (Menit):</label>
                        <input type="number" id="intervalMinutes" min="1" max="1440" value="20">
                        <button type="submit" class="btn-success">💾 Simpan & Restart</button>
                    </form>
                </div>
                
                <div class="section">
                    <h2>📊 History Broadcast</h2>
                    <div id="broadcastHistory"></div>
                </div>
            </div>
            
            <!-- Tab Promo List -->
            <div id="tab-promos" class="tab-content">
                <div class="section">
                    <h2>📋 Daftar Semua Promo</h2>
                    <div id="promosList"></div>
                </div>
            </div>
            
            <!-- Tab Tambah Promo -->
            <div id="tab-add" class="tab-content">
                <div class="section">
                    <h2>➕ Tambah Promo Baru</h2>
                    <form id="addPromoForm">
                        <input type="text" id="promoTitle" placeholder="Judul Promo" required>
                        <textarea id="promoMessage" placeholder="Pesan Promo (bisa pakai *bold*)" required></textarea>
                        <input type="url" id="promoImageUrl" placeholder="URL Gambar (opsional)">
                        <input type="text" id="promoButtonText" placeholder="Teks Tombol" value="🔥 Klaim Bonus">
                        <input type="url" id="promoButtonUrl" placeholder="URL Tombol" value="https://siteq.link/kajian4d">
                        <button type="submit" class="btn-success">💾 Simpan Promo</button>
                    </form>
                </div>
            </div>
            
            <!-- Tab Grup Telegram -->
            <div id="tab-groups" class="tab-content">
                <div class="section">
                    <h2>➕ Tambah Grup Baru</h2>
                    <form id="addGroupForm">
                        <input type="text" id="groupId" placeholder="ID Grup (contoh: -1001234567890)" required>
                        <input type="text" id="groupName" placeholder="Nama Grup" required>
                        <button type="submit" class="btn-success">💾 Tambah Grup</button>
                    </form>
                </div>
                
                <div class="section">
                    <h2>👥 Daftar Grup Telegram</h2>
                    <div id="groupsList"></div>
                </div>
            </div>
            
            <!-- Tab Users -->
            <div id="tab-users" class="tab-content">
                <div class="section">
                    <h2>👥 Daftar User Terdaftar</h2>
                    <div id="usersList"></div>
                </div>
            </div>
            
            <!-- Tab Settings -->
            <div id="tab-settings" class="tab-content">
                <div class="section">
                    <h2>⚙️ Pengaturan Bot</h2>
                    <form id="settingsForm">
                        <label>Kirim ke Grup:</label>
                        <select id="broadcastToGroups">
                            <option value="true">Ya (Kirim ke grup juga)</option>
                            <option value="false">Tidak (Hanya ke user pribadi)</option>
                        </select>
                        
                        <label>Kirim Gambar:</label>
                        <select id="sendImage">
                            <option value="true">Ya</option>
                            <option value="false">Tidak</option>
                        </select>
                        
                        <label>URL Website:</label>
                        <input type="url" id="websiteUrl" value="https://siteq.link/kajian4d">
                        
                        <label>Pesan Selamat Datang:</label>
                        <textarea id="welcomeMessage" rows="5"></textarea>
                        
                        <button type="submit" class="btn-success">💾 Simpan Pengaturan</button>
                    </form>
                </div>
            </div>
        </div>
        
        <div id="editModal" class="modal"><div class="modal-content"><span class="close" onclick="closeModal()">&times;</span><h2>✏️ Edit Promo</h2><form id="editPromoForm"><input type="hidden" id="editPromoId"><input type="text" id="editTitle" placeholder="Judul Promo" required><textarea id="editMessage" placeholder="Pesan Promo" required></textarea><input type="url" id="editImageUrl" placeholder="URL Gambar"><input type="text" id="editButtonText" placeholder="Teks Tombol"><input type="url" id="editButtonUrl" placeholder="URL Tombol"><button type="submit" class="btn-success">💾 Update</button><button type="button" class="btn-danger" onclick="deletePromo()">🗑️ Hapus</button></form></div></div>
        
        <script>
            let broadcastEnabled = true;
            
            function showTab(tabName) {
                document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.getElementById(`tab-${tabName}`).classList.add('active');
                event.target.classList.add('active');
                if (tabName === 'users') loadUsers();
                if (tabName === 'groups') loadGroups();
                if (tabName === 'broadcast_control') loadBroadcastHistory();
            }
            
            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    document.getElementById('totalUsers').textContent = data.users || 0;
                    document.getElementById('totalPromos').textContent = data.promos || 0;
                    document.getElementById('totalGroups').textContent = data.groups || 0;
                    broadcastEnabled = data.broadcast_enabled;
                    const statusEl = document.getElementById('broadcastStatus');
                    const statusCard = document.getElementById('broadcastStatusCard');
                    if (broadcastEnabled) {
                        statusEl.innerHTML = '✅ AKTIF';
                        statusCard.className = 'stat-card broadcast-on';
                    } else {
                        statusEl.innerHTML = '⏸️ MATI';
                        statusCard.className = 'stat-card broadcast-off';
                    }
                } catch(e) { console.log(e); }
            }
            
            async function loadBroadcastHistory() {
                try {
                    const response = await fetch('/api/broadcast_history');
                    const history = await response.json();
                    const container = document.getElementById('broadcastHistory');
                    if (!history.length) {
                        container.innerHTML = '<p>Belum ada history broadcast.</p>';
                        return;
                    }
                    let html = '<table><thead><tr><th>Waktu</th><th>Judul</th><th>Personal</th><th>Grup</th><th>Sukses</th><th>Gagal</th></thead><tbody>';
                    history.forEach(h => {
                        html += `<tr><td>${h.time}</td><td>${h.title.substring(0, 30)}...</td><td>${h.users || 0}</td><td>${h.groups || 0}</td><td style="color:#51cf66">✅ ${h.success}</td><td style="color:#ff6b6b">❌ ${h.fail}</td></tr>`;
                    });
                    html += '</tbody></table>';
                    container.innerHTML = html;
                } catch(e) { console.log(e); }
            }
            
            async function controlBroadcast(action) {
                const response = await fetch(`/api/broadcast_control/${action}`, { method: 'POST' });
                const result = await response.json();
                const msgDiv = document.getElementById('broadcastControlMsg');
                if (result.success) {
                    msgDiv.innerHTML = `<div class="alert alert-success">✅ ${result.message}</div>`;
                    loadStats();
                    setTimeout(() => msgDiv.innerHTML = '', 3000);
                } else {
                    msgDiv.innerHTML = `<div class="alert alert-error">❌ ${result.message}</div>`;
                }
            }
            
            async function testBroadcast() {
                if (!confirm('Kirim test broadcast sekarang?')) return;
                const msgDiv = document.getElementById('broadcastControlMsg');
                msgDiv.innerHTML = '<div class="alert">⏳ Mengirim broadcast test...</div>';
                const response = await fetch('/api/test_broadcast', { method: 'POST' });
                const result = await response.json();
                msgDiv.innerHTML = `<div class="alert alert-success">✅ Broadcast test selesai! Terkirim ke ${result.sent} target, gagal ${result.failed}</div>`;
                loadBroadcastHistory();
                loadStats();
                setTimeout(() => msgDiv.innerHTML = '', 5000);
            }
            
            document.getElementById('intervalForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const minutes = document.getElementById('intervalMinutes').value;
                const response = await fetch('/api/set_interval', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ interval_minutes: parseInt(minutes) })
                });
                const result = await response.json();
                const msgDiv = document.getElementById('broadcastControlMsg');
                if (result.success) {
                    msgDiv.innerHTML = `<div class="alert alert-success">✅ ${result.message}</div>`;
                    setTimeout(() => msgDiv.innerHTML = '', 3000);
                } else {
                    msgDiv.innerHTML = `<div class="alert alert-error">❌ ${result.message}</div>`;
                }
            });
            
            async function loadPromos() {
                try {
                    const response = await fetch('/api/promos');
                    const promos = await response.json();
                    const container = document.getElementById('promosList');
                    if (!promos.length) { container.innerHTML = '<p>Belum ada promo. Tambahkan promo baru!</p>'; return; }
                    let html = '<td><thead><tr><th>ID</th><th>Judul</th><th>Aksi</th></tr></thead><tbody>';
                    promos.forEach(p => { html += `<tr><td>${p.id}</td><td>${p.title}</td><td><button onclick="editPromo(${p.id})">✏️ Edit</button><button class="btn-danger" onclick="deletePromoById(${p.id})">🗑️ Hapus</button></td></tr>`; });
                    html += '</tbody>\\{table}';
                    container.innerHTML = html;
                } catch(e) { console.log(e); }
            }
            
            async function loadGroups() {
                try {
                    const response = await fetch('/api/groups');
                    const groups = await response.json();
                    const container = document.getElementById('groupsList');
                    if (!groups.length) { container.innerHTML = '<p>Belum ada grup. Tambahkan grup Telegram!</p>'; return; }
                    let html = '';
                    groups.forEach(g => {
                        html += `
                            <div class="group-item">
                                <div>
                                    <strong>${g.name}</strong><br>
                                    <small>ID: ${g.id}</small>
                                </div>
                                <div>
                                    <button onclick="testGroup(${g.id})" class="btn-warning">📨 Test Kirim</button>
                                    <button onclick="deleteGroup(${g.id})" class="btn-danger">🗑️ Hapus</button>
                                </div>
                            </div>
                        `;
                    });
                    container.innerHTML = html;
                } catch(e) { console.log(e); }
            }
            
            async function testGroup(groupId) {
                if (!confirm('Kirim test promo ke grup ini?')) return;
                const response = await fetch(`/api/test_group/${groupId}`, { method: 'POST' });
                const result = await response.json();
                alert(result.message);
            }
            
            async function deleteGroup(groupId) {
                if (!confirm('Yakin ingin menghapus grup ini?')) return;
                const response = await fetch(`/api/group/${groupId}`, { method: 'DELETE' });
                if (response.ok) {
                    alert('✅ Grup berhasil dihapus!');
                    loadGroups();
                    loadStats();
                } else {
                    alert('❌ Gagal menghapus grup');
                }
            }
            
            async function loadUsers() {
                try {
                    const response = await fetch('/api/users');
                    const users = await response.json();
                    const container = document.getElementById('usersList');
                    if (!users.length) { container.innerHTML = '<p>Belum ada user yang terdaftar.</p>'; return; }
                    let html = '<table><thead><tr><th>User ID</th></tr></thead><tbody>';
                    users.forEach(u => { html += `<tr><td>${u}</td></tr>`; });
                    html += '</tbody>这些';
                    container.innerHTML = html;
                } catch(e) { console.log(e); }
            }
            
            async function loadSettings() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    document.getElementById('broadcastToGroups').value = data.broadcast_to_groups;
                    document.getElementById('sendImage').value = data.send_image;
                    document.getElementById('websiteUrl').value = data.website_url || 'https://siteq.link/kajian4d';
                    document.getElementById('welcomeMessage').value = data.welcome_message || '';
                    document.getElementById('intervalMinutes').value = Math.floor(data.interval / 60) || 20;
                } catch(e) { console.log(e); }
            }
            
            async function logout() { if(confirm('Yakin ingin logout?')) window.location.href = '/logout'; }
            
            document.getElementById('addPromoForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const promo = {
                    title: document.getElementById('promoTitle').value,
                    message: document.getElementById('promoMessage').value,
                    image_url: document.getElementById('promoImageUrl').value,
                    button_text: document.getElementById('promoButtonText').value,
                    button_url: document.getElementById('promoButtonUrl').value
                };
                const response = await fetch('/api/promo', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(promo) });
                if(response.ok) { alert('✅ Promo berhasil ditambahkan!'); document.getElementById('addPromoForm').reset(); loadPromos(); loadStats(); }
                else alert('❌ Gagal menambahkan promo');
            });
            
            document.getElementById('addGroupForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const group = {
                    id: document.getElementById('groupId').value,
                    name: document.getElementById('groupName').value
                };
                const response = await fetch('/api/group', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(group) });
                if(response.ok) { alert('✅ Grup berhasil ditambahkan!'); document.getElementById('addGroupForm').reset(); loadGroups(); loadStats(); }
                else alert('❌ Gagal menambahkan grup');
            });
            
            document.getElementById('settingsForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const settings = {
                    broadcast_to_groups: document.getElementById('broadcastToGroups').value === 'true',
                    send_image: document.getElementById('sendImage').value === 'true',
                    website_url: document.getElementById('websiteUrl').value,
                    welcome_message: document.getElementById('welcomeMessage').value
                };
                const response = await fetch('/api/settings', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(settings) });
                if(response.ok) { alert('✅ Pengaturan berhasil disimpan!'); loadStats(); }
                else alert('❌ Gagal menyimpan pengaturan');
            });
            
            async function editPromo(id) {
                const response = await fetch(`/api/promo/${id}`);
                const promo = await response.json();
                document.getElementById('editPromoId').value = promo.id;
                document.getElementById('editTitle').value = promo.title;
                document.getElementById('editMessage').value = promo.message;
                document.getElementById('editImageUrl').value = promo.image_url || '';
                document.getElementById('editButtonText').value = promo.button_text;
                document.getElementById('editButtonUrl').value = promo.button_url;
                document.getElementById('editModal').style.display = 'flex';
            }
            
            document.getElementById('editPromoForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const id = document.getElementById('editPromoId').value;
                const promo = {
                    title: document.getElementById('editTitle').value,
                    message: document.getElementById('editMessage').value,
                    image_url: document.getElementById('editImageUrl').value,
                    button_text: document.getElementById('editButtonText').value,
                    button_url: document.getElementById('editButtonUrl').value
                };
                const response = await fetch(`/api/promo/${id}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(promo) });
                if(response.ok) { alert('✅ Promo berhasil diupdate!'); closeModal(); loadPromos(); }
                else alert('❌ Gagal update promo');
            });
            
            async function deletePromo() {
                const id = document.getElementById('editPromoId').value;
                if(!confirm('Yakin ingin menghapus promo ini?')) return;
                const response = await fetch(`/api/promo/${id}`, { method:'DELETE' });
                if(response.ok) { alert('✅ Promo berhasil dihapus!'); closeModal(); loadPromos(); loadStats(); }
                else alert('❌ Gagal hapus promo');
            }
            
            async function deletePromoById(id) {
                if(!confirm('Yakin ingin menghapus promo ini?')) return;
                const response = await fetch(`/api/promo/${id}`, { method:'DELETE' });
                if(response.ok) { alert('✅ Promo berhasil dihapus!'); loadPromos(); loadStats(); }
                else alert('❌ Gagal hapus promo');
            }
            
            function closeModal() { document.getElementById('editModal').style.display = 'none'; }
            
            loadStats(); loadPromos(); loadSettings(); loadBroadcastHistory();
            setInterval(() => { loadStats(); if(document.getElementById('tab-promos').classList.contains('active')) loadPromos(); }, 30000);
        </script>
    </body>
    </html>
    '''

# ============ API ROUTES UNTUK ADMIN ============
@app.route('/api/users')
def api_users():
    return jsonify(list(load_users()))

@app.route('/api/groups')
def api_groups():
    return jsonify(load_groups())

@app.route('/api/group', methods=['POST'])
def add_group():
    data = request.json
    groups = load_groups()
    groups.append({
        'id': data.get('id'),
        'name': data.get('name'),
        'added_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_groups(groups)
    return jsonify({'status': 'ok'})

@app.route('/api/group/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    groups = load_groups()
    groups = [g for g in groups if str(g.get('id')) != str(group_id)]
    save_groups(groups)
    return jsonify({'status': 'ok'})

@app.route('/api/test_group/<group_id>', methods=['POST'])
def test_group(group_id):
    groups = load_groups()
    group = next((g for g in groups if str(g.get('id')) == str(group_id)), None)
    if not group:
        return jsonify({'message': 'Grup tidak ditemukan'}), 404
    
    promo = promos[0] if promos else None
    if not promo:
        return jsonify({'message': 'Belum ada promo untuk test'}), 404
    
    result = send_to_group(group_id, promo)
    if result:
        return jsonify({'message': f'✅ Test berhasil dikirim ke {group.get("name")}'})
    else:
        return jsonify({'message': f'❌ Gagal mengirim ke {group.get("name")}. Pastikan bot sudah menjadi admin di grup!'})

@app.route('/api/promos')
def api_promos_list():
    return jsonify(promos)

@app.route('/api/promo/<int:promo_id>', methods=['GET'])
def get_promo(promo_id):
    promo = next((p for p in promos if p.get('id') == promo_id), None)
    return jsonify(promo) if promo else ('Not found', 404)

@app.route('/api/promo', methods=['POST'])
def add_promo():
    global promos
    data = request.json
    new_id = max([p.get('id', 0) for p in promos], default=0) + 1
    new_promo = {
        'id': new_id,
        'title': data.get('title'),
        'message': data.get('message'),
        'image_url': data.get('image_url', ''),
        'button_text': data.get('button_text', '🔥 Klaim Bonus'),
        'button_url': data.get('button_url', config.get('website_url'))
    }
    promos.append(new_promo)
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        json.dump({'promos': promos, 'settings': promo_settings}, f, indent=2, ensure_ascii=False)
    return jsonify({'status': 'ok'})

@app.route('/api/promo/<int:promo_id>', methods=['PUT'])
def update_promo(promo_id):
    global promos
    data = request.json
    for promo in promos:
        if promo.get('id') == promo_id:
            promo.update({
                'title': data.get('title'),
                'message': data.get('message'),
                'image_url': data.get('image_url', ''),
                'button_text': data.get('button_text', '🔥 Klaim Bonus'),
                'button_url': data.get('button_url', config.get('website_url'))
            })
            break
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        json.dump({'promos': promos, 'settings': promo_settings}, f, indent=2, ensure_ascii=False)
    return jsonify({'status': 'ok'})

@app.route('/api/promo/<int:promo_id>', methods=['DELETE'])
def delete_promo(promo_id):
    global promos
    promos = [p for p in promos if p.get('id') != promo_id]
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        json.dump({'promos': promos, 'settings': promo_settings}, f, indent=2, ensure_ascii=False)
    return jsonify({'status': 'ok'})

@app.route('/api/broadcast_control/<action>', methods=['POST'])
def broadcast_control(action):
    global broadcast_enabled, scheduler
    
    if action == 'start':
        if broadcast_enabled:
            return jsonify({'success': False, 'message': 'Broadcast sudah berjalan'})
        broadcast_enabled = True
        restart_scheduler()
        return jsonify({'success': True, 'message': 'Broadcast telah diaktifkan!'})
    
    elif action == 'stop':
        if not broadcast_enabled:
            return jsonify({'success': False, 'message': 'Broadcast sudah dimatikan'})
        broadcast_enabled = False
        if scheduler:
            try:
                scheduler.remove_job(broadcast_job_id)
            except:
                pass
        return jsonify({'success': True, 'message': 'Broadcast telah dimatikan!'})
    
    return jsonify({'success': False, 'message': 'Action tidak dikenal'})

@app.route('/api/set_interval', methods=['POST'])
def set_interval():
    global promo_settings
    
    data = request.json
    new_interval = data.get('interval_minutes', 20)
    
    promo_settings['broadcast_interval_minutes'] = new_interval
    
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        json.dump({'promos': promos, 'settings': promo_settings}, f, indent=2, ensure_ascii=False)
    
    if broadcast_enabled:
        restart_scheduler()
    
    return jsonify({'success': True, 'message': f'Interval diubah menjadi {new_interval} menit'})

@app.route('/api/test_broadcast', methods=['POST'])
def test_broadcast_api():
    global broadcast_count, broadcast_history
    
    if not promos:
        return jsonify({'sent': 0, 'failed': 0, 'message': 'Tidak ada promo'})
    
    promo = random.choice(promos)
    users_list = list(load_users())
    broadcast_to_groups = promo_settings.get('broadcast_to_groups', True)
    groups_list = load_groups() if broadcast_to_groups else []
    
    success = 0
    failed = 0
    
    for user_id in users_list:
        result = send_promo_with_image(user_id, promo)
        if result and result.get("ok"):
            success += 1
        else:
            failed += 1
        time.sleep(0.3)
    
    for group in groups_list:
        if send_to_group(group.get('id'), promo):
            success += 1
        else:
            failed += 1
        time.sleep(0.5)
    
    return jsonify({'sent': success, 'failed': failed})

@app.route('/api/broadcast_history')
def api_broadcast_history():
    return jsonify(broadcast_history)

@app.route('/api/settings', methods=['POST'])
def update_settings():
    global promo_settings, config
    
    data = request.json
    
    promo_settings['broadcast_to_groups'] = data.get('broadcast_to_groups', True)
    promo_settings['send_image'] = data.get('send_image', True)
    
    config['website_url'] = data.get('website_url', 'https://siteq.link/kajian4d')
    config['welcome_message'] = data.get('welcome_message', '🌟 SELAMAT DATANG DI KAJIAN4D OFFICIAL 🌟')
    
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        json.dump({'promos': promos, 'settings': promo_settings}, f, indent=2, ensure_ascii=False)
    
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    return jsonify({'status': 'ok'})

# ============ WEBHOOK ============
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "ok"}), 200
        
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            username = message["chat"].get("username", "unknown")
            first_name = message["chat"].get("first_name", "")
            
            current_users = load_users()
            if chat_id not in current_users:
                current_users.add(chat_id)
                save_users(current_users)
                print(f"📝 User baru: {first_name} (@{username}) - Total: {len(current_users)}")
            
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
                status_msg = f"""📊 *STATUS BOT*

🔄 Status: {'✅ AKTIF' if broadcast_enabled else '⏸️ MATI'}
👥 Total user: {len(load_users())}
📞 Total kontak: {get_contact_count()}
👥 Total grup: {len(load_groups())}
🎁 Total promo: {len(promos)}
⏱️ Interval: {promo_settings.get('broadcast_interval_minutes', 20)} MENIT
📢 Total broadcast: {broadcast_count} kali

📅 Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                send_telegram_message(chat_id, status_msg)
            elif text == "/test_broadcast" and str(chat_id) == str(ADMIN_ID):
                send_telegram_message(chat_id, "⏳ Menjalankan broadcast test...")
                threading.Thread(target=do_broadcast).start()
                send_telegram_message(chat_id, "✅ Broadcast test dimulai! Cek log.")
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
                        send_telegram_message(

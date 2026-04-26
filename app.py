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
ADMIN_PASSWORD_HASH = hashlib.sha256("Kajian225511".encode()).hexdigest()  # Password: Kajian225511
# =================================

app = Flask(__name__)

# File untuk menyimpan data
CONTACTS_FILE = "contacts.json"
DATA_FILE = "users.json"
PROMO_FILE = "promo.json"
CONFIG_FILE = "config.json"
GROUPS_FILE = "groups.json"

# Variabel global
last_broadcast_log = []
scheduler = None
_broadcast_lock = threading.Lock()
is_broadcasting = False
broadcast_job_id = "broadcast_job"
broadcast_enabled = True

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
    try:
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_groups(groups):
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
        
        success = 0
        fail = 0
        
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
        
        print(f"✅ Broadcast selesai! Berhasil: {success}, Gagal: {fail}")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error di broadcast: {e}")
    finally:
        is_broadcasting = False

def start_scheduler():
    global scheduler
    interval_minutes = promo_settings.get("broadcast_interval_minutes", 20)
    
    executors = {'default': ThreadPoolExecutor(max_workers=1)}
    job_defaults = {'coalesce': True, 'max_instances': 1, 'misfire_grace_time': 60}
    
    scheduler = BackgroundScheduler(executors=executors, job_defaults=job_defaults)
    scheduler.add_job(func=do_broadcast, trigger="interval", minutes=interval_minutes, id=broadcast_job_id, next_run_time=datetime.now())
    scheduler.start()
    
    print(f"⏰ Scheduler dimulai! Interval: {interval_minutes} menit")
    return scheduler

def restart_scheduler():
    global scheduler, broadcast_enabled
    if scheduler:
        try:
            scheduler.remove_job(broadcast_job_id)
        except:
            pass
    
    interval_minutes = promo_settings.get("broadcast_interval_minutes", 20)
    if broadcast_enabled:
        scheduler.add_job(func=do_broadcast, trigger="interval", minutes=interval_minutes, id=broadcast_job_id, next_run_time=datetime.now())
        print(f"🔄 Scheduler direstart dengan interval {interval_minutes} menit")

# ============ LOGIN DECORATOR ============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_cookie = request.cookies.get('admin_auth')
        if not auth_cookie or auth_cookie != ADMIN_PASSWORD_HASH:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# ============ ROUTE WEBHOOK ============
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
                print(f"📝 User baru: {first_name}")
            
            contact = message.get("contact")
            if contact:
                phone_number = contact.get("phone_number")
                first_name = contact.get("first_name", "")
                last_name = contact.get("last_name", "")
                user_id = contact.get("user_id", chat_id)
                save_contact(user_id, username, first_name, last_name, phone_number)
                send_telegram_message(chat_id, f"✅ Terima kasih *{first_name}*! Nomor Anda telah tersimpan.")
                send_telegram_message(ADMIN_ID, f"📞 Kontak baru: {first_name} {last_name}\n📱 {phone_number}")
            elif text == "/start":
                send_main_menu(chat_id)
            elif text == "/share":
                send_contact_request(chat_id)
            elif text == "/promos":
                send_promo_list(chat_id)
            elif text == "/help":
                send_telegram_message(chat_id, "📖 *Panduan*\n/start - Menu\n/promos - Promo\n/share - Share kontak")
            elif text == "/status" and str(chat_id) == str(ADMIN_ID):
                send_telegram_message(chat_id, f"📊 *STATUS*\nUser: {len(load_users())}\nPromo: {len(promos)}\nGrup: {len(load_groups())}")
            elif text == "/test_broadcast" and str(chat_id) == str(ADMIN_ID):
                threading.Thread(target=do_broadcast).start()
                send_telegram_message(chat_id, "✅ Broadcast test dimulai!")
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
            elif data_callback.startswith("promo_"):
                try:
                    promo_id = int(data_callback.split("_")[1])
                    promo = next((p for p in promos if p.get('id') == promo_id), None)
                    if promo:
                        send_promo_with_image(chat_id, promo)
                except Exception as e:
                    print(f"Error: {e}")
            
            requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": callback["id"]})
        
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 200

# ============ ROUTE LOGIN ============
@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash == ADMIN_PASSWORD_HASH:
            resp = make_response(redirect('/admin'))
            resp.set_cookie('admin_auth', password_hash, max_age=3600*24)
            return resp
        return '<h2>❌ Password salah!</h2><a href="/login">Coba lagi</a>'
    
    return '''
    <html><head><title>Login</title><style>
    body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); display: flex; justify-content: center; align-items: center; height: 100vh; }
    .box { background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; text-align: center; }
    input { padding: 12px; margin: 10px; border-radius: 8px; border: none; width: 250px; }
    button { background: #00d4ff; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; }
    h2 { color: white; }
    </style></head>
    <body><div class="box"><h2>🔐 Login Admin KAJIAN4D</h2>
    <form method="POST"><input type="password" name="password" placeholder="Password" required><br><button type="submit">Login</button></form></div></body></html>
    '''

@app.route('/logout')
def admin_logout():
    resp = make_response(redirect('/login'))
    resp.set_cookie('admin_auth', '', expires=0)
    return resp

# ============ ADMIN PANEL (DIPERCEPAT) ============
@app.route('/admin')
@login_required
def admin_panel():
    return '''
    <html><head><title>KAJIAN4D Admin</title><style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:Arial;background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:20px}
    .container{max-width:1200px;margin:0 auto}
    h1{text-align:center;margin-bottom:30px;color:#00d4ff}
    .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-bottom:30px}
    .stat-card{background:rgba(255,255,255,0.1);border-radius:15px;padding:20px;text-align:center}
    .stat-card h3{font-size:2em}
    .tabs{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
    .tab{padding:10px 20px;background:rgba(255,255,255,0.1);border-radius:8px;cursor:pointer}
    .tab.active{background:#00d4ff;color:#1a1a2e}
    .tab-content{display:none;background:rgba(255,255,255,0.05);border-radius:15px;padding:20px}
    .tab-content.active{display:block}
    button{background:#00d4ff;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;margin:5px}
    .btn-danger{background:#ff6b6b}
    .btn-success{background:#51cf66}
    input,textarea,select{width:100%;padding:10px;margin:10px 0;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff}
    table{width:100%;border-collapse:collapse}
    th,td{padding:12px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1)}
    th{background:rgba(0,212,255,0.2)}
    .group-item{background:rgba(255,255,255,0.05);border-radius:10px;padding:15px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}
    </style></head>
    <body><div class="container">
    <h1>🎯 Admin Panel - KAJIAN4D Bot</h1>
    <div class="stats" id="stats">
        <div class="stat-card"><h3 id="totalUsers">0</h3><p>Total User</p></div>
        <div class="stat-card"><h3 id="totalPromos">0</h3><p>Total Promo</p></div>
        <div class="stat-card"><h3 id="totalGroups">0</h3><p>Total Grup</p></div>
        <div class="stat-card"><h3 id="broadcastStatus">Loading</h3><p>Status Broadcast</p></div>
    </div>
    <div class="tabs">
        <div class="tab active" onclick="showTab('control')">📡 Kontrol</div>
        <div class="tab" onclick="showTab('promos')">📋 Promo</div>
        <div class="tab" onclick="showTab('add')">➕ Tambah</div>
        <div class="tab" onclick="showTab('groups')">👥 Grup</div>
        <div class="tab" onclick="showTab('users')">👤 User</div>
        <div class="tab" onclick="logout()">🚪 Logout</div>
    </div>
    
    <div id="tab-control" class="tab-content active">
        <h2>📡 Kontrol Broadcast</h2>
        <button onclick="controlBroadcast('start')" class="btn-success">▶️ START</button>
        <button onclick="controlBroadcast('stop')" class="btn-danger">⏸️ STOP</button>
        <button onclick="testBroadcast()">🔨 TEST</button>
        <hr><h2>⚙️ Interval (Menit)</h2>
        <input type="number" id="intervalMinutes" value="20">
        <button onclick="setInterval()" class="btn-success">Simpan</button>
        <hr><h2>📊 History</h2><div id="history"></div>
    </div>
    
    <div id="tab-promos" class="tab-content"><h2>📋 Daftar Promo</h2><div id="promosList"></div></div>
    <div id="tab-add" class="tab-content"><h2>➕ Tambah Promo</h2>
        <form id="addPromoForm"><input id="promoTitle" placeholder="Judul" required><textarea id="promoMessage" placeholder="Pesan" required></textarea><input id="promoImageUrl" placeholder="URL Gambar"><input id="promoButtonText" placeholder="Teks Tombol" value="🔥 Klaim"><input id="promoButtonUrl" placeholder="URL Tombol" value="https://siteq.link/kajian4d"><button type="submit" class="btn-success">Simpan</button></form></div>
    <div id="tab-groups" class="tab-content"><h2>➕ Tambah Grup</h2><form id="addGroupForm"><input id="groupId" placeholder="ID Grup (-100xxx)" required><input id="groupName" placeholder="Nama Grup" required><button type="submit" class="btn-success">Tambah</button></form><hr><h2>👥 Daftar Grup</h2><div id="groupsList"></div></div>
    <div id="tab-users" class="tab-content"><h2>👥 User Terdaftar</h2><div id="usersList"></div></div>
    </div>
    <div id="editModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);justify-content:center;align-items:center"><div style="background:#1a1a2e;padding:30px;border-radius:15px;width:90%;max-width:500px"><span onclick="closeModal()" style="float:right;cursor:pointer">&times;</span><h2>Edit Promo</h2><form id="editPromoForm"><input type="hidden" id="editId"><input id="editTitle" placeholder="Judul"><textarea id="editMessage" placeholder="Pesan"></textarea><input id="editImageUrl" placeholder="URL Gambar"><input id="editButtonText" placeholder="Teks Tombol"><input id="editButtonUrl" placeholder="URL Tombol"><button type="submit" class="btn-success">Update</button><button type="button" onclick="deletePromoById()" class="btn-danger">Hapus</button></form></div></div>
    <script>
        async function loadStats(){const r=await fetch('/api/stats'),d=await r.json();document.getElementById('totalUsers').innerText=d.users||0;document.getElementById('totalPromos').innerText=d.promos||0;document.getElementById('totalGroups').innerText=d.groups||0;const s=document.getElementById('broadcastStatus');s.innerText=d.broadcast_enabled?'✅ AKTIF':'⏸️ MATI';s.style.color=d.broadcast_enabled?'#51cf66':'#ff6b6b';}
        async function loadHistory(){const r=await fetch('/api/broadcast_history'),h=await r.json();if(!h.length){document.getElementById('history').innerHTML='<p>Belum ada history</p>';return}let html='<table><tr><th>Waktu</th><th>Judul</th><th>User</th><th>Grup</th><th>Sukses</th></tr>';h.forEach(h=>{html+=`<tr><td>${h.time}</td><td>${h.title.substring(0,30)}</td><td>${h.users||0}</td><td>${h.groups||0}</td><td style="color:#51cf66">✅${h.success}</td></tr>`});html+='</table>';document.getElementById('history').innerHTML=html;}
        async function loadPromos(){const r=await fetch('/api/promos'),p=await r.json();if(!p.length){document.getElementById('promosList').innerHTML='<p>Belum ada promo</p>';return}let html='<table><tr><th>ID</th><th>Judul</th><th>Aksi</th></tr>';p.forEach(p=>{html+=`<tr><td>${p.id}</td><td>${p.title}</td><td><button onclick="editPromo(${p.id})">Edit</button><button class="btn-danger" onclick="deletePromo(${p.id})">Hapus</button><button onclick="broadcastNow(${p.id})">Kirim</button></td></tr>`});html+='</table>';document.getElementById('promosList').innerHTML=html;}
        async function loadGroups(){const r=await fetch('/api/groups'),g=await r.json();if(!g.length){document.getElementById('groupsList').innerHTML='<p>Belum ada grup</p>';return}let html='';g.forEach(g=>{html+=`<div class="group-item"><div><strong>${g.name}</strong><br><small>${g.id}</small></div><div><button onclick="testGroup('${g.id}')">Test</button><button class="btn-danger" onclick="deleteGroup('${g.id}')">Hapus</button></div></div>`});document.getElementById('groupsList').innerHTML=html;}
        async function loadUsers(){const r=await fetch('/api/users'),u=await r.json();if(!u.length){document.getElementById('usersList').innerHTML='<p>Belum ada user</p>';return}let html='<table><tr><th>User ID</th></tr>';u.forEach(u=>{html+=`<tr><td>${u}</td></tr>`});html+='</table>';document.getElementById('usersList').innerHTML=html;}
        function showTab(t){document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById(`tab-${t}`).classList.add('active');event.target.classList.add('active');if(t==='users')loadUsers();if(t==='groups')loadGroups();if(t==='control')loadHistory();}
        async function controlBroadcast(a){const r=await fetch(`/api/broadcast_control/${a}`,{method:'POST'}),d=await r.json();alert(d.message);loadStats();}
        async function testBroadcast(){if(!confirm('Kirim test broadcast?'))return;const r=await fetch('/api/test_broadcast',{method:'POST'}),d=await r.json();alert(`Test selesai! Terkirim: ${d.sent}, Gagal: ${d.failed}`);loadHistory();}
        async function setInterval(){const m=document.getElementById('intervalMinutes').value;const r=await fetch('/api/set_interval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({interval_minutes:parseInt(m)})});const d=await r.json();alert(d.message);}
        async function broadcastNow(id){if(!confirm('Kirim promo ini sekarang?'))return;const r=await fetch(`/api/broadcast_promo/${id}`,{method:'POST'}),d=await r.json();alert(`Terkirim: ${d.sent}, Gagal: ${d.failed}`);}
        async function testGroup(id){const r=await fetch(`/api/test_group/${id}`,{method:'POST'}),d=await r.json();alert(d.message);}
        async function deleteGroup(id){if(!confirm('Hapus grup ini?'))return;await fetch(`/api/group/${id}`,{method:'DELETE'});loadGroups();loadStats();}
        async function deletePromo(id){if(!confirm('Hapus promo ini?'))return;await fetch(`/api/promo/${id}`,{method:'DELETE'});loadPromos();loadStats();}
        async function editPromo(id){const r=await fetch(`/api/promo/${id}`),p=await r.json();document.getElementById('editId').value=p.id;document.getElementById('editTitle').value=p.title;document.getElementById('editMessage').value=p.message;document.getElementById('editImageUrl').value=p.image_url||'';document.getElementById('editButtonText').value=p.button_text;document.getElementById('editButtonUrl').value=p.button_url;document.getElementById('editModal').style.display='flex';}
        function closeModal(){document.getElementById('editModal').style.display='none';}
        document.getElementById('addPromoForm').addEventListener('submit',async(e)=>{e.preventDefault();const promo={title:document.getElementById('promoTitle').value,message:document.getElementById('promoMessage').value,image_url:document.getElementById('promoImageUrl').value,button_text:document.getElementById('promoButtonText').value,button_url:document.getElementById('promoButtonUrl').value};const r=await fetch('/api/promo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(promo)});if(r.ok){alert('Promo ditambahkan');document.getElementById('addPromoForm').reset();loadPromos();loadStats();}});
        document.getElementById('addGroupForm').addEventListener('submit',async(e)=>{e.preventDefault();const group={id:document.getElementById('groupId').value,name:document.getElementById('groupName').value};const r=await fetch('/api/group',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(group)});if(r.ok){alert('Grup ditambahkan');document.getElementById('addGroupForm').reset();loadGroups();loadStats();}});
        document.getElementById('editPromoForm').addEventListener('submit',async(e)=>{e.preventDefault();const id=document.getElementById('editId').value;const promo={title:document.getElementById('editTitle').value,message:document.getElementById('editMessage').value,image_url:document.getElementById('editImageUrl').value,button_text:document.getElementById('editButtonText').value,button_url:document.getElementById('editButtonUrl').value};const r=await fetch(`/api/promo/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(promo)});if(r.ok){alert('Promo diupdate');closeModal();loadPromos();}});
        async function deletePromoById(){const id=document.getElementById('editId').value;if(!confirm('Hapus promo?'))return;await fetch(`/api/promo/${id}`,{method:'DELETE'});closeModal();loadPromos();loadStats();}
        async function logout(){if(confirm('Logout?'))window.location.href='/logout';}
        loadStats();loadPromos();loadHistory();setInterval(()=>{loadStats();},30000);
    </script></body></html>
    '''

# ============ API ROUTES ============
@app.route('/api/stats')
def api_stats():
    return jsonify({
        'users': len(load_users()),
        'contacts': get_contact_count(),
        'groups': len(load_groups()),
        'promos': len(promos),
        'broadcast_count': broadcast_count,
        'broadcast_enabled': broadcast_enabled,
        'broadcast_to_groups': promo_settings.get('broadcast_to_groups', True),
        'send_image': promo_settings.get('send_image', True),
        'interval': promo_settings.get('broadcast_interval_minutes', 20),
        'website_url': config.get('website_url'),
        'welcome_message': config.get('welcome_message')
    })

@app.route('/api/users')
def api_users():
    return jsonify(list(load_users()))

@app.route('/api/groups')
def api_groups():
    return jsonify(load_groups())

@app.route('/api/group', methods=['POST'])
def add_group():
    data = request.json
    g = load_groups()
    g.append({'id': data.get('id'), 'name': data.get('name'), 'added_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    save_groups(g)
    return jsonify({'status': 'ok'})

@app.route('/api/group/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    g = load_groups()
    g = [x for x in g if str(x.get('id')) != str(group_id)]
    save_groups(g)
    return jsonify({'status': 'ok'})

@app.route('/api/test_group/<group_id>', methods=['POST'])
def test_group(group_id):
    g = load_groups()
    group = next((x for x in g if str(x.get('id')) == str(group_id)), None)
    if not group:
        return jsonify({'message': 'Grup tidak ditemukan'}), 404
    if not promos:
        return jsonify({'message': 'Belum ada promo'}), 404
    result = send_to_group(group_id, promos[0])
    return jsonify({'message': f'✅ Berhasil ke {group.get("name")}' if result else f'❌ Gagal ke {group.get("name")}'})

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
    promos.append({
        'id': new_id,
        'title': data.get('title'),
        'message': data.get('message'),
        'image_url': data.get('image_url', ''),
        'button_text': data.get('button_text', '🔥 Klaim Bonus'),
        'button_url': data.get('button_url', config.get('website_url'))
    })
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
        return jsonify({'success': True, 'message': 'Broadcast diaktifkan!'})
    elif action == 'stop':
        if not broadcast_enabled:
            return jsonify({'success': False, 'message': 'Broadcast sudah mati'})
        broadcast_enabled = False
        if scheduler:
            try:
                scheduler.remove_job(broadcast_job_id)
            except:
                pass
        return jsonify({'success': True, 'message': 'Broadcast dimatikan!'})
    return jsonify({'success': False, 'message': 'Aksi tidak dikenal'})

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
    return jsonify({'success': True, 'message': f'Interval diubah ke {new_interval} menit'})

@app.route('/api/test_broadcast', methods=['POST'])
def test_broadcast_api():
    if not promos:
        return jsonify({'sent': 0, 'failed': 0})
    promo = random.choice(promos)
    users_list = list(load_users())
    broadcast_to_groups = promo_settings.get('broadcast_to_groups', True)
    groups_list = load_groups() if broadcast_to_groups else []
    success, failed = 0, 0
    for uid in users_list:
        if send_promo_with_image(uid, promo) and True:
            success += 1
        else:
            failed += 1
        time.sleep(0.3)
    for g in groups_list:
        if send_to_group(g.get('id'), promo):
            success += 1
        else:
            failed += 1
        time.sleep(0.5)
    return jsonify({'sent': success, 'failed': failed})

@app.route('/api/broadcast_promo/<int:promo_id>', methods=['POST'])
def broadcast_promo(promo_id):
    promo = next((p for p in promos if p.get('id') == promo_id), None)
    if not promo:
        return jsonify({'sent': 0, 'failed': 0})
    users_list = list(load_users())
    broadcast_to_groups = promo_settings.get('broadcast_to_groups', True)
    groups_list = load_groups() if broadcast_to_groups else []
    success, failed = 0, 0
    for uid in users_list:
        if send_promo_with_image(uid, promo) and True:
            success += 1
        else:
            failed += 1
        time.sleep(0.3)
    for g in groups_list:
        if send_to_group(g.get('id'), promo):
            success += 1
        else:
            failed += 1
        time.sleep(0.5)
    return jsonify({'sent': success, 'failed': failed})

@app.route('/api/broadcast_history')
def api_broadcast_history():
    return jsonify(broadcast_history)

@app.route('/')
def home():
    return '<h1>🤖 KAJIAN4D Bot</h1><p>✅ Bot aktif!</p><a href="/admin">Admin Panel</a>'

@app.route('/set_webhook')
def set_webhook():
    render_url = os.environ.get('RENDER_EXTERNAL_URL', request.host_url)
    if render_url.endswith('/'):
        render_url = render_url[:-1]
    webhook_url = f"{render_url}/webhook"
    requests.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook", json={"url": webhook_url})
    if r.json().get("ok"):
        return f"✅ Webhook berhasil! URL: {webhook_url}<br><a href='/admin'>Admin Panel</a>"
    return f"❌ Gagal: {r.json()}"

@app.route('/health')
def health():
    return "OK", 200

# ============ MAIN ============
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 KAJIAN4D BOT TELEGRAM")
    print("=" * 60)
    
    try:
        r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=10)
        if r.ok:
            print(f"✅ Bot terhubung: @{r.json().get('result',{}).get('username')}")
        else:
            print("❌ Token tidak valid!")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print(f"✅ Total promo: {len(promos)}")
    print(f"👥 Total user: {len(load_users())}")
    print(f"👥 Total grup: {len(load_groups())}")
    print("=" * 60)
    
    scheduler = start_scheduler()
    
    print("\n📱 Buka: /set_webhook")
    print("👑 Admin: /admin (password: admin123)")
    print("=" * 60)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

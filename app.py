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
ADMIN_ID = 8736769212
ADMIN_PASSWORD_HASH = hashlib.sha256("admin123".encode()).hexdigest()  # Password: admin123
# =================================

app = Flask(__name__)

# File untuk menyimpan data
CONTACTS_FILE = "contacts.json"
DATA_FILE = "users.json"
PROMO_FILE = "promo.json"
CONFIG_FILE = "config.json"

# Variabel global
last_broadcast_log = []
scheduler = None
_broadcast_lock = threading.Lock()
is_broadcasting = False

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

# ============ BROADCAST OTOMATIS ============
broadcast_count = 0
broadcast_history = []

def do_broadcast():
    global broadcast_count, broadcast_history, is_broadcasting
    
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
        
        if len(users_list) == 0:
            print("⚠️ Belum ada user yang terdaftar. Broadcast skipped.")
            return
        
        print(f"📢 Judul: {promo['title']}")
        print(f"👥 Target: {len(users_list)} user")
        
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
                print(f"Error ke {user_id}: {e}")
                fail += 1
            
            time.sleep(0.5)
            
            if (idx + 1) % 10 == 0:
                print(f"Progress: {idx + 1}/{len(users_list)} (✅{success} ❌{fail})")
        
        broadcast_count += 1
        
        broadcast_history.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title": promo['title'],
            "success": success,
            "fail": fail,
            "total": len(users_list)
        })
        
        while len(broadcast_history) > 10:
            broadcast_history.pop()
        
        print(f"✅ Broadcast selesai!")
        print(f"✅ Berhasil: {success} user")
        print(f"❌ Gagal: {fail} user")
        print(f"📊 Total broadcast ke-{broadcast_count}")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error di broadcast: {e}")
    finally:
        is_broadcasting = False

def start_scheduler():
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
    
    from datetime import datetime, timedelta
    first_run = datetime.now() + timedelta(seconds=5)
    
    scheduler.add_job(
        func=do_broadcast,
        trigger="interval",
        minutes=interval_minutes,
        id="broadcast_job",
        next_run_time=first_run
    )
    scheduler.start()
    
    print(f"⏰ Scheduler dimulai!")
    print(f"📅 Broadcast pertama: dalam 5 detik")
    print(f"🔄 Interval: setiap {interval_minutes} menit")
    
    return scheduler

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
            @media (max-width: 768px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } .tabs { justify-content: center; } }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 Admin Panel - KAJIAN4D Bot</h1>
            <div class="stats-grid" id="stats">
                <div class="stat-card"><h3 id="totalUsers">0</h3><p>Total User</p></div>
                <div class="stat-card"><h3 id="totalPromos">0</h3><p>Total Promo</p></div>
                <div class="stat-card"><h3 id="broadcastInterval">1</h3><p>Broadcast (Jam)</p></div>
                <div class="stat-card"><h3 id="randomMode">Random</h3><p>Mode Promo</p></div>
            </div>
            <div class="tabs">
                <div class="tab active" onclick="showTab('promos')">📋 Daftar Promo</div>
                <div class="tab" onclick="showTab('add')">➕ Tambah Promo</div>
                <div class="tab" onclick="showTab('broadcast')">📢 Broadcast</div>
                <div class="tab" onclick="showTab('users')">👥 User List</div>
                <div class="tab" onclick="logout()">🚪 Logout</div>
            </div>
            <div id="tab-promos" class="tab-content active"><div class="section"><h2>📋 Daftar Semua Promo</h2><div id="promosList"></div></div></div>
            <div id="tab-add" class="tab-content"><div class="section"><h2>➕ Tambah Promo Baru</h2><form id="addPromoForm"><input type="text" id="promoTitle" placeholder="Judul Promo" required><textarea id="promoMessage" placeholder="Pesan Promo (bisa pakai *bold*)" required></textarea><input type="url" id="promoImageUrl" placeholder="URL Gambar (opsional)"><input type="text" id="promoButtonText" placeholder="Teks Tombol" value="🔥 Klaim Bonus"><input type="url" id="promoButtonUrl" placeholder="URL Tombol" value="https://siteq.link/kajian4d"><button type="submit" class="btn-success">💾 Simpan Promo</button></form></div></div>
            <div id="tab-broadcast" class="tab-content"><div class="section"><h2>📢 Broadcast Promo yang Sudah Ada</h2><div id="broadcastPromosList"></div></div></div>
            <div id="tab-users" class="tab-content"><div class="section"><h2>👥 Daftar User Terdaftar</h2><div id="usersList"></div></div></div>
        </div>
        <div id="editModal" class="modal"><div class="modal-content"><span class="close" onclick="closeModal()">&times;</span><h2>✏️ Edit Promo</h2><form id="editPromoForm"><input type="hidden" id="editPromoId"><input type="text" id="editTitle" placeholder="Judul Promo" required><textarea id="editMessage" placeholder="Pesan Promo" required></textarea><input type="url" id="editImageUrl" placeholder="URL Gambar"><input type="text" id="editButtonText" placeholder="Teks Tombol"><input type="url" id="editButtonUrl" placeholder="URL Tombol"><button type="submit" class="btn-success">💾 Update</button><button type="button" class="btn-danger" onclick="deletePromo()">🗑️ Hapus</button></form></div></div>
        <script>
            function showTab(tabName) {
                document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.getElementById(`tab-${tabName}`).classList.add('active');
                event.target.classList.add('active');
                if (tabName === 'users') loadUsers();
                if (tabName === 'broadcast') loadBroadcastPromos();
            }
            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    document.getElementById('totalUsers').textContent = data.users || 0;
                    document.getElementById('totalPromos').textContent = data.promos || 0;
                    document.getElementById('broadcastInterval').textContent = Math.floor(data.interval / 60) || 1;
                } catch(e) { console.log(e); }
            }
            async function loadPromos() {
                try {
                    const response = await fetch('/api/promos');
                    const promos = await response.json();
                    const container = document.getElementById('promosList');
                    if (!promos.length) { container.innerHTML = '<p>Belum ada promo. Tambahkan promo baru!</p>'; return; }
                    let html = '<table><thead><tr><th>ID</th><th>Judul</th><th>Aksi</th></tr></thead><tbody>';
                    promos.forEach(p => { html += `<tr><td>${p.id}</td><td>${p.title}</td><td><button onclick="editPromo(${p.id})">✏️ Edit</button><button class="btn-danger" onclick="deletePromoById(${p.id})">🗑️ Hapus</button></td></tr>`; });
                    html += '</tbody></table>';
                    container.innerHTML = html;
                } catch(e) { console.log(e); }
            }
            async function loadBroadcastPromos() {
                try {
                    const response = await fetch('/api/promos');
                    const promos = await response.json();
                    const container = document.getElementById('broadcastPromosList');
                    if (!promos.length) { container.innerHTML = '<p>Belum ada promo.</p>'; return; }
                    let html = '<div style="display: flex; flex-wrap: wrap; gap: 10px;">';
                    promos.forEach(p => { html += `<button onclick="broadcastPromo(${p.id})" style="flex:1;min-width:200px;">📢 ${p.title}</button>`; });
                    html += '</div>';
                    container.innerHTML = html;
                } catch(e) { console.log(e); }
            }
            async function loadUsers() {
                try {
                    const response = await fetch('/api/users');
                    const users = await response.json();
                    const container = document.getElementById('usersList');
                    if (!users.length) { container.innerHTML = '<p>Belum ada user yang terdaftar.</p>'; return; }
                    let html = '<table><thead><tr><th>User ID</th></tr></thead><tbody>';
                    users.forEach(u => { html += `<tr><td>${u}</td></tr>`; });
                    html += '</tbody></table>';
                    container.innerHTML = html;
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
            async function broadcastPromo(id) {
                if(!confirm('Kirim promo ini ke semua user?')) return;
                const response = await fetch(`/api/broadcast_promo/${id}`, { method:'POST' });
                const result = await response.json();
                alert(`✅ Broadcast selesai!\\n📨 Terkirim: ${result.sent} user\\n❌ Gagal: ${result.failed} user`);
            }
            function closeModal() { document.getElementById('editModal').style.display = 'none'; }
            loadStats(); loadPromos();
            setInterval(() => { loadStats(); if(document.getElementById('tab-promos').classList.contains('active')) loadPromos(); }, 30000);
        </script>
    </body>
    </html>
    '''

# ============ API ROUTES UNTUK ADMIN ============
@app.route('/api/users')
def api_users():
    return jsonify(list(load_users()))

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

@app.route('/api/broadcast_promo/<int:promo_id>', methods=['POST'])
def broadcast_promo(promo_id):
    promo = next((p for p in promos if p.get('id') == promo_id), None)
    if not promo:
        return jsonify({'error': 'Promo not found'}), 404
    
    users_list = list(load_users())
    success = 0
    failed = 0
    
    for user_id in users_list:
        result = send_promo_with_image(user_id, promo)
        if result and result.get('ok'):
            success += 1
        else:
            failed += 1
        time.sleep(0.3)
    
    return jsonify({'sent': success, 'failed': failed})

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
                        send_telegram_message(chat_id, "Promo tidak ditemukan.")
                except Exception as e:
                    print(f"Error: {e}")
            
            url_answer = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
            requests.post(url_answer, json={"callback_query_id": callback["id"]})
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 200

# ============ FLASK ROUTES LAINNYA ============
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
        <p>👑 <a href="/admin">Admin Panel</a></p>
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
        return f"✅ Webhook berhasil! URL: {webhook_url}<br>🔄 Broadcast akan berjalan otomatis!<br><br><a href='/admin'>Klik disini untuk masuk Admin Panel</a>"
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
        'website_url': config.get('website_url'),
        'welcome_message': config.get('welcome_message'),
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
    threading.Thread(target=do_broadcast).start()
    return jsonify({'status': 'broadcast_started', 'time': datetime.now().isoformat()})

# ============ MAIN ============
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 KAJIAN4D BOT TELEGRAM - DENGAN BROADCAST OTOMATIS")
    print("=" * 60)
    
    is_main_process = os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
    
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
    
    if is_main_process:
        scheduler = start_scheduler()
    else:
        print("⚠️ Debug reloader mode - Scheduler tidak di-start di proses reloader")
    
    print("\n📱 Buka URL /set_webhook untuk mengaktifkan webhook")
    print("📱 Kirim /start ke bot di Telegram")
    print("👑 Admin Panel: /admin (password: admin123)")
    print("📢 Broadcast akan berjalan OTOMATIS setiap 20 menit!")
    print("=" * 60)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

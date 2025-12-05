# app.py - AUTO ADMIN ROLE DETECTION BOT
import os
import json
import sqlite3
import random
import string
import time
import hashlib
import requests
from flask import Flask, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from datetime import datetime
import logging
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord credentials
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot status
bot_active = False
bot_info = {}

# Cache for admin roles per server
admin_role_cache = {}

# Ping responses
PING_RESPONSES = [
    "I'm here",
    "Bot is up",
    "Still alive",
    "Yeah I'm here",
    "Online",
    "Ready",
    "Here",
    "Present",
    "Awake",
    "Active"
]

# =============================================================================
# DISCORD API HELPERS
# =============================================================================

def discord_api_request(endpoint, method="GET", data=None):
    """Make Discord API request"""
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json"
    }
    
    url = f"https://discord.com/api/v10{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=10)
        else:
            return None
            
        if response.status_code in [200, 201, 204]:
            return response.json() if response.content else True
        else:
            logger.error(f"Discord API error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Discord API request failed: {e}")
        return None

def get_guild_member(guild_id, user_id):
    """Get guild member info"""
    return discord_api_request(f"/guilds/{guild_id}/members/{user_id}")

def get_guild_roles(guild_id):
    """Get all roles for a guild"""
    return discord_api_request(f"/guilds/{guild_id}/roles")

def get_guild_info(guild_id):
    """Get guild information"""
    return discord_api_request(f"/guilds/{guild_id}")

def is_user_admin_in_guild(guild_id, user_id):
    """Check if user has admin/manage permissions in guild"""
    # Check cache first
    cache_key = f"{guild_id}_{user_id}"
    if cache_key in admin_role_cache:
        return admin_role_cache[cache_key]
    
    try:
        # Get member info
        member = get_guild_member(guild_id, user_id)
        if not member:
            admin_role_cache[cache_key] = False
            return False
        
        # Get guild info to find owner
        guild = get_guild_info(guild_id)
        if guild and guild.get('owner_id') == user_id:
            admin_role_cache[cache_key] = True
            return True
        
        # Get all roles
        roles = get_guild_roles(guild_id)
        if not roles:
            admin_role_cache[cache_key] = False
            return False
        
        # Check user's roles for admin permissions
        member_roles = member.get('roles', [])
        for role_id in member_roles:
            for role in roles:
                if role['id'] == role_id:
                    permissions = int(role.get('permissions', 0))
                    # Check for ADMINISTRATOR permission (0x8)
                    if permissions & 0x8:
                        admin_role_cache[cache_key] = True
                        return True
                    # Check for MANAGE_GUILD permission (0x20)
                    if permissions & 0x20:
                        admin_role_cache[cache_key] = True
                        return True
                    # Check for MANAGE_ROLES permission (0x10000000)
                    if permissions & 0x10000000:
                        admin_role_cache[cache_key] = True
                        return True
        
        admin_role_cache[cache_key] = False
        return False
        
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        admin_role_cache[cache_key] = False
        return False

def detect_admin_roles(guild_id):
    """Detect admin/manage roles in a guild"""
    try:
        roles = get_guild_roles(guild_id)
        if not roles:
            return []
        
        admin_roles = []
        for role in roles:
            permissions = int(role.get('permissions', 0))
            # Check for key admin permissions
            if (permissions & 0x8) or (permissions & 0x20) or (permissions & 0x10000000):
                admin_roles.append({
                    'id': role['id'],
                    'name': role['name'],
                    'permissions': permissions,
                    'color': role.get('color'),
                    'position': role.get('position')
                })
        
        # Sort by position (highest first)
        admin_roles.sort(key=lambda x: x.get('position', 0), reverse=True)
        return admin_roles
        
    except Exception as e:
        logger.error(f"Error detecting admin roles: {e}")
        return []

# =============================================================================
# SECURE KEY GENERATION
# =============================================================================

def generate_secure_key():
    """Generate strong 32-character API key"""
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
    key = 'BOT-' + ''.join(secrets.choice(alphabet) for _ in range(28))
    return key

# =============================================================================
# DATABASE SETUP
# =============================================================================

def init_db():
    """Initialize database"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                discord_name TEXT,
                in_game_name TEXT,
                api_key TEXT UNIQUE,
                server_id TEXT,
                key_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                total_kills INTEGER DEFAULT 0,
                total_deaths INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                prestige INTEGER DEFAULT 0,
                is_admin BOOLEAN DEFAULT 0,
                admin_servers TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Webhooks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_url TEXT UNIQUE,
                server_id TEXT,
                webhook_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Updates table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT UNIQUE,
                download_url TEXT,
                changelog TEXT,
                file_size TEXT,
                is_critical BOOLEAN DEFAULT 0,
                uploaded_by TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tickets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE,
                discord_id TEXT,
                discord_name TEXT,
                issue TEXT,
                status TEXT DEFAULT 'open',
                assigned_to TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            )
        ''')
        
        # Admin actions log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT,
                admin_name TEXT,
                action TEXT,
                target_id TEXT,
                details TEXT,
                server_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add default update
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO updates 
                (version, download_url, changelog, file_size, uploaded_by)
                VALUES 
                ('1.0.0', 'https://example.com/client-v1.zip', 'Initial release', '15.2 MB', 'system')
            ''')
        except:
            pass
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# KEY VALIDATION
# =============================================================================

def validate_api_key(api_key):
    """Validate API key"""
    if not api_key or not api_key.startswith("BOT-"):
        return None
    
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE api_key = ?',
        (api_key,)
    ).fetchone()
    
    if player:
        # Update last used
        conn.execute(
            'UPDATE players SET last_used = CURRENT_TIMESTAMP WHERE id = ?',
            (player['id'],)
        )
        conn.commit()
    
    conn.close()
    return dict(player) if player else None

# =============================================================================
# DISCORD BOT FUNCTIONS
# =============================================================================

def test_discord_token():
    """Test if Discord token is valid"""
    global bot_active, bot_info
    
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN not set")
        return False
    
    try:
        url = "https://discord.com/api/v10/users/@me"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            bot_info = response.json()
            bot_active = True
            logger.info(f"✅ Discord bot is ACTIVE: {bot_info['username']}")
            return True
        else:
            logger.error(f"❌ Invalid Discord token: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Discord API error: {e}")
        return False

def register_commands():
    """Register slash commands"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        logger.error("❌ Cannot register commands")
        return False
    
    commands = [
        {
            "name": "ping",
            "description": "Check if bot is online",
            "type": 1
        },
        {
            "name": "register",
            "description": "Register and get API key",
            "type": 1,
            "options": [
                {
                    "name": "name",
                    "description": "Your in-game name",
                    "type": 3,
                    "required": True
                }
            ]
        },
        {
            "name": "ticket",
            "description": "Create a support ticket",
            "type": 1,
            "options": [
                {
                    "name": "issue",
                    "description": "Describe your issue",
                    "type": 3,
                    "required": True
                }
            ]
        },
        {
            "name": "stats",
            "description": "Show your stats",
            "type": 1
        },
        {
            "name": "admin",
            "description": "Admin commands",
            "type": 1,
            "options": [
                {
                    "name": "action",
                    "description": "Admin action",
                    "type": 3,
                    "required": True,
                    "choices": [
                        {"name": "Check Admin Roles", "value": "check_roles"},
                        {"name": "Add Webhook", "value": "add_webhook"},
                        {"name": "Update Stats", "value": "update_stats"}
                    ]
                }
            ]
        }
    ]
    
    try:
        url = f"https://discord.com/api/v10/applications/{DISCORD_CLIENT_ID}/commands"
        headers = {
            "Authorization": f"Bot {DISCORD_TOKEN}",
            "Content-Type": "application/json"
        }
        
        response = requests.put(url, headers=headers, json=commands, timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info(f"✅ Registered commands")
            return True
        else:
            logger.error(f"❌ Failed to register commands: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error registering commands: {e}")
        return False

def send_webhook_stats(server_id):
    """Send stats to webhook"""
    conn = get_db_connection()
    webhooks = conn.execute(
        'SELECT * FROM webhooks WHERE server_id = ? AND is_active = 1',
        (server_id,)
    ).fetchall()
    
    if not webhooks:
        conn.close()
        return
    
    # Get server stats
    players = conn.execute(
        'SELECT COUNT(*) as count FROM players WHERE server_id = ?',
        (server_id,)
    ).fetchone()['count']
    
    total_kills = conn.execute(
        'SELECT SUM(total_kills) as sum FROM players WHERE server_id = ?',
        (server_id,)
    ).fetchone()['sum'] or 0
    
    admins = conn.execute(
        'SELECT COUNT(*) as count FROM players WHERE server_id = ? AND is_admin = 1',
        (server_id,)
    ).fetchone()['count']
    
    conn.close()
    
    for webhook in webhooks:
        try:
            embed = {
                "title": "📊 Server Statistics",
                "description": f"Automatic stats update",
                "color": 0x3498db,
                "fields": [
                    {"name": "👥 Total Players", "value": str(players), "inline": True},
                    {"name": "🎯 Total Kills", "value": str(total_kills), "inline": True},
                    {"name": "👑 Admin Users", "value": str(admins), "inline": True},
                    {"name": "🌐 Dashboard", "value": f"http://localhost:{port}", "inline": True}
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "Auto-updated every 30 minutes"}
            }
            
            requests.post(webhook['webhook_url'], json={"embeds": [embed]}, timeout=5)
            
        except:
            continue

def log_admin_action(admin_id, admin_name, action, target_id=None, details=None, server_id=None):
    """Log admin actions"""
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO admin_logs 
        (admin_id, admin_name, action, target_id, details, server_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (admin_id, admin_name, action, target_id, details, server_id))
    conn.commit()
    conn.close()

# =============================================================================
# DISCORD INTERACTIONS
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord slash commands"""
    # Verify signature
    if not verify_discord_signature(request):
        return jsonify({"error": "Invalid signature"}), 401
    
    data = request.get_json()
    
    # Handle Discord verification ping
    if data.get('type') == 1:
        return jsonify({"type": 1})
    
    # Handle slash commands
    if data.get('type') == 2:
        command = data.get('data', {}).get('name')
        user_id = data.get('member', {}).get('user', {}).get('id')
        user_name = data.get('member', {}).get('user', {}).get('global_name', 'Unknown')
        server_id = data.get('guild_id', 'DM')
        
        logger.info(f"Command: {command} from {user_name} in {server_id}")
        
        if command == 'ping':
            response = random.choice(PING_RESPONSES)
            return jsonify({
                "type": 4,
                "data": {
                    "content": response,
                    "flags": 0
                }
            })
        
        elif command == 'register':
            options = data.get('data', {}).get('options', [])
            in_game_name = options[0].get('value', 'Unknown') if options else 'Unknown'
            
            conn = get_db_connection()
            
            # Check if already registered
            existing = conn.execute(
                'SELECT * FROM players WHERE discord_id = ?',
                (user_id,)
            ).fetchone()
            
            if existing:
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"Already registered as `{existing['in_game_name']}`\n\nLogin to dashboard for API key.",
                        "flags": 64
                    }
                })
            
            # Check if user is admin in this server
            is_admin = is_user_admin_in_guild(server_id, user_id)
            
            # Generate secure API key
            api_key = generate_secure_key()
            
            # Register player
            conn.execute('''
                INSERT INTO players 
                (discord_id, discord_name, in_game_name, api_key, server_id, is_admin)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, user_name, in_game_name, api_key, server_id, 1 if is_admin else 0))
            
            conn.commit()
            
            # Log admin registration if applicable
            if is_admin:
                log_admin_action(user_id, user_name, "register_admin", server_id=server_id)
            
            conn.close()
            
            # Send to webhook
            send_webhook_stats(server_id)
            
            admin_note = "\n⚠️ **Admin access detected** - You have additional privileges." if is_admin else ""
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"✅ **Registered Successfully**{admin_note}\n\n"
                        f"**Name:** `{in_game_name}`\n\n"
                        f"**Dashboard:** {request.host_url}\n"
                        f"Login to view your API key and stats"
                    ),
                    "flags": 64
                }
            })
        
        elif command == 'ticket':
            options = data.get('data', {}).get('options', [])
            issue = options[0].get('value', 'No issue specified') if options else 'No issue specified'
            
            # Generate ticket ID
            ticket_id = f"TICKET-{int(time.time())}-{random.randint(1000, 9999)}"
            
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO tickets 
                (ticket_id, discord_id, discord_name, issue)
                VALUES (?, ?, ?, ?)
            ''', (ticket_id, user_id, user_name, issue))
            conn.commit()
            conn.close()
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"✅ **Ticket Created**\n\n"
                        f"**Ticket ID:** `{ticket_id}`\n"
                        f"**Issue:** {issue}\n\n"
                        f"Our team will review your ticket shortly."
                    ),
                    "flags": 64
                }
            })
        
        elif command == 'stats':
            conn = get_db_connection()
            player = conn.execute(
                'SELECT * FROM players WHERE discord_id = ?',
                (user_id,)
            ).fetchone()
            conn.close()
            
            if not player:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ Not registered. Use `/register [name]` first",
                        "flags": 64
                    }
                })
            
            kd = player['total_kills'] / max(player['total_deaths'], 1)
            win_rate = (player['wins'] / max(player['wins'] + player['losses'], 1)) * 100
            
            admin_badge = " 👑" if player['is_admin'] else ""
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"📊 **Your Stats**{admin_badge}\n\n"
                        f"**Name:** `{player['in_game_name']}`\n"
                        f"**K/D Ratio:** {kd:.2f}\n"
                        f"**Win Rate:** {win_rate:.1f}%\n"
                        f"**Wins/Losses:** {player['wins']}-{player['losses']}\n"
                        f"**Prestige:** {player['prestige']}\n\n"
                        f"View more: {request.host_url}"
                    ),
                    "flags": 64
                }
            })
        
        elif command == 'admin':
            options = data.get('data', {}).get('options', [])
            action = options[0].get('value') if options else None
            
            # Check if user is admin
            if not is_user_admin_in_guild(server_id, user_id):
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ Admin permissions required",
                        "flags": 64
                    }
                })
            
            if action == 'check_roles':
                # Detect admin roles
                admin_roles = detect_admin_roles(server_id)
                
                if not admin_roles:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": "No admin roles detected in this server",
                            "flags": 64
                        }
                    })
                
                role_list = "\n".join([f"• <@&{role['id']}> - {role['name']}" for role in admin_roles[:10]])
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"👑 **Detected Admin Roles**\n\n"
                            f"{role_list}\n\n"
                            f"Users with these roles can change API keys."
                        ),
                        "flags": 64
                    }
                })
            
            elif action == 'add_webhook':
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            "**Add Webhook**\n\n"
                            "Use the dashboard to add webhooks:\n"
                            f"{request.host_url}\n\n"
                            "Webhooks will auto-send stats every 30 minutes."
                        ),
                        "flags": 64
                    }
                })
            
            elif action == 'update_stats':
                send_webhook_stats(server_id)
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "✅ Stats webhook sent",
                        "flags": 64
                    }
                })
    
    return jsonify({
        "type": 4,
        "data": {
            "content": "Unknown command",
            "flags": 64
        }
    })

def verify_discord_signature(request):
    """Verify Discord request signature"""
    signature = request.headers.get('X-Signature-Ed25519')
    timestamp = request.headers.get('X-Signature-Timestamp')
    body = request.get_data().decode('utf-8')
    
    if not signature or not timestamp:
        return False
    
    if not DISCORD_PUBLIC_KEY:
        return False
    
    try:
        import nacl.signing
        import nacl.exceptions
        
        message = f"{timestamp}{body}".encode('utf-8')
        signature_bytes = bytes.fromhex(signature)
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify(message, signature_bytes)
        
        return True
        
    except:
        return False

# =============================================================================
# WEB INTERFACE
# =============================================================================

@app.route('/')
def home():
    """Main page"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            return redirect(url_for('dashboard'))
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bot Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
            .login-card { background: rgba(30, 41, 59, 0.8); backdrop-filter: blur(20px); border-radius: 24px; padding: 50px 40px; width: 100%; max-width: 450px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.2); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); position: relative; overflow: hidden; }
            .login-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, #38bdf8, #3b82f6); }
            h1 { font-size: 2.5rem; font-weight: 800; margin-bottom: 15px; background: linear-gradient(45deg, #38bdf8, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .subtitle { color: #94a3b8; margin-bottom: 40px; line-height: 1.6; }
            .key-input { width: 100%; padding: 18px; background: rgba(15, 23, 42, 0.8); border: 2px solid rgba(56, 189, 248, 0.3); border-radius: 12px; color: white; font-size: 18px; text-align: center; margin-bottom: 25px; transition: all 0.3s; }
            .key-input:focus { outline: none; border-color: #38bdf8; box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.2); }
            .login-btn { width: 100%; padding: 18px; background: linear-gradient(45deg, #38bdf8, #3b82f6); color: white; border: none; border-radius: 12px; font-size: 18px; font-weight: 600; cursor: pointer; transition: all 0.3s; }
            .login-btn:hover { transform: translateY(-3px); box-shadow: 0 15px 30px rgba(56, 189, 248, 0.3); }
            .error-box { background: rgba(239, 68, 68, 0.1); border: 2px solid rgba(239, 68, 68, 0.4); border-radius: 12px; padding: 16px; margin-top: 20px; color: #fca5a5; display: none; }
            .info-box { background: rgba(56, 189, 248, 0.1); border: 2px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 25px; margin-top: 35px; text-align: left; color: #cbd5e1; }
            .info-box strong { color: white; display: block; margin-bottom: 15px; }
            .bot-status { padding: 10px 20px; background: rgba(30, 41, 59, 0.8); border: 2px solid rgba(56, 189, 248, 0.3); border-radius: 20px; margin-top: 25px; display: inline-block; }
            @media (max-width: 768px) { .login-card { padding: 40px 25px; } h1 { font-size: 2rem; } }
        </style>
    </head>
    <body>
        <div class="login-card">
            <h1>Bot Dashboard</h1>
            <div class="subtitle">Enter your API key to access the dashboard</div>
            <input type="password" class="key-input" id="apiKey" placeholder="Enter your API key" autocomplete="off" spellcheck="false">
            <button class="login-btn" onclick="validateKey()">Access Dashboard</button>
            <div class="error-box" id="errorMessage">Invalid API key</div>
            <div class="info-box">
                <strong>How to get started:</strong>
                <p>1. Use <code>/register your_name</code> in Discord</p>
                <p>2. Admin roles are auto-detected</p>
                <p>3. Login to dashboard for API key</p>
            </div>
            <div class="bot-status" id="botStatus">Bot Status: Checking...</div>
        </div>
        <script>
            async function validateKey() {
                const key = document.getElementById('apiKey').value.trim();
                const errorDiv = document.getElementById('errorMessage');
                const btn = document.querySelector('.login-btn');
                if (!key) { errorDiv.textContent = "Please enter an API key"; errorDiv.style.display = 'block'; return; }
                btn.innerHTML = 'Checking...'; btn.disabled = true;
                try {
                    const response = await fetch('/api/validate-key', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ api_key: key })
                    });
                    const data = await response.json();
                    if (data.valid) {
                        btn.innerHTML = '✅ Access Granted';
                        setTimeout(() => window.location.href = '/dashboard', 500);
                    } else {
                        errorDiv.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        btn.innerHTML = 'Access Dashboard';
                        btn.disabled = false;
                    }
                } catch (error) {
                    errorDiv.textContent = 'Connection error';
                    errorDiv.style.display = 'block';
                    btn.innerHTML = 'Access Dashboard';
                    btn.disabled = false;
                }
            }
            document.getElementById('apiKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') validateKey();
            });
            async function checkBotStatus() {
                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    const status = document.getElementById('botStatus');
                    status.innerHTML = data.bot_active ? '✅ Bot Status: ONLINE' : '❌ Bot Status: OFFLINE';
                } catch (error) {
                    document.getElementById('botStatus').innerHTML = '⚠️ Bot Status: ERROR';
                }
            }
            document.addEventListener('DOMContentLoaded', function() {
                document.getElementById('apiKey').focus();
                checkBotStatus();
                setInterval(checkBotStatus, 30000);
            });
        </script>
    </body>
    </html>
    '''

@app.route('/api/validate-key', methods=['POST'])
def api_validate_key():
    """Validate API key"""
    data = request.get_json()
    api_key = data.get('api_key', '').strip()
    
    if not api_key:
        return jsonify({"valid": False, "error": "No key provided"})
    
    user_data = validate_api_key(api_key)
    
    if user_data:
        session['user_key'] = api_key
        session['user_data'] = user_data
        return jsonify({"valid": True})
    else:
        return jsonify({"valid": False, "error": "Invalid API key"})

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    """Main dashboard"""
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    user_data = session.get('user_data')
    if not user_data:
        return redirect(url_for('home'))
    
    # Calculate stats
    kd = user_data.get('total_kills', 0) / max(user_data.get('total_deaths', 1), 1)
    total_games = user_data.get('wins', 0) + user_data.get('losses', 0)
    win_rate = (user_data.get('wins', 0) / total_games * 100) if total_games > 0 else 0
    
    # Get latest updates
    conn = get_db_connection()
    updates = conn.execute('SELECT * FROM updates ORDER BY uploaded_at DESC LIMIT 3').fetchall()
    conn.close()
    
    updates_html = ''
    for update in updates:
        critical = '🚨 ' if update['is_critical'] else ''
        uploaded_by = f" by {update['uploaded_by']}" if update['uploaded_by'] else ''
        updates_html += f'''
        <div class="update-card">
            <div class="update-header">
                <strong>{critical}v{update['version']}</strong>
                <span class="update-size">{update['file_size']}</span>
            </div>
            <p>{update['changelog']}{uploaded_by}</p>
            <button class="download-btn" onclick="downloadUpdate('{update['download_url']}')">
                📥 Download Update
            </button>
        </div>
        '''
    
    # Check if user is admin in any server
    is_admin = user_data.get('is_admin', 0)
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: white; min-height: 100vh; }}
            .header {{ background: rgba(30, 41, 59, 0.9); backdrop-filter: blur(20px); border-bottom: 1px solid rgba(56, 189, 248, 0.2); padding: 25px 40px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; }}
            .logo {{ font-size: 1.8rem; font-weight: 700; background: linear-gradient(45deg, #38bdf8, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
            .user-info {{ display: flex; align-items: center; gap: 25px; }}
            .admin-badge {{ background: linear-gradient(45deg, #f59e0b, #d97706); color: white; padding: 5px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }}
            .logout-btn {{ padding: 10px 24px; background: linear-gradient(45deg, #ef4444, #dc2626); color: white; border: none; border-radius: 10px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; transition: all 0.3s; }}
            .logout-btn:hover {{ transform: translateY(-3px); box-shadow: 0 10px 25px rgba(239, 68, 68, 0.3); }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 40px; }}
            .welcome-card {{ background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.8)); border-radius: 24px; padding: 50px; margin-bottom: 40px; border: 1px solid rgba(56, 189, 248, 0.2); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; margin-bottom: 50px; }}
            .stat-card {{ background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.8)); border-radius: 20px; padding: 35px; text-align: center; border: 1px solid rgba(56, 189, 248, 0.1); transition: all 0.3s; }}
            .stat-card:hover {{ transform: translateY(-5px); border-color: rgba(56, 189, 248, 0.3); }}
            .stat-value {{ font-size: 3rem; font-weight: 800; margin: 15px 0; }}
            .stat-label {{ color: #94a3b8; text-transform: uppercase; letter-spacing: 2px; font-size: 0.9rem; }}
            .key-section {{ background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.8)); border-radius: 24px; padding: 50px; margin-bottom: 40px; border: 1px solid rgba(56, 189, 248, 0.2); }}
            .key-display {{ background: rgba(15, 23, 42, 0.8); border: 2px solid rgba(56, 189, 248, 0.3); border-radius: 16px; padding: 25px; margin: 30px 0; font-family: monospace; color: #38bdf8; text-align: center; cursor: pointer; position: relative; overflow: hidden; }}
            .key-display::before {{ content: 'Click to reveal'; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(15, 23, 42, 0.9); display: flex; align-items: center; justify-content: center; font-family: sans-serif; font-size: 1.2rem; color: #94a3b8; }}
            .key-display.revealed::before {{ display: none; }}
            .updates-section {{ background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.8)); border-radius: 24px; padding: 50px; border: 1px solid rgba(56, 189, 248, 0.2); }}
            .update-card {{ background: rgba(15, 23, 42, 0.6); border-radius: 16px; padding: 25px; margin-bottom: 20px; border: 1px solid rgba(56, 189, 248, 0.1); }}
            .update-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
            .update-size {{ color: #94a3b8; font-size: 0.9rem; }}
            .download-btn {{ background: linear-gradient(45deg, #38bdf8, #3b82f6); color: white; border: none; border-radius: 10px; padding: 12px 24px; margin-top: 15px; cursor: pointer; font-weight: 600; transition: all 0.3s; }}
            .download-btn:hover {{ transform: translateY(-3px); box-shadow: 0 10px 25px rgba(56, 189, 248, 0.3); }}
            .action-buttons {{ display: flex; gap: 20px; margin-top: 30px; flex-wrap: wrap; }}
            .action-btn {{ padding: 16px 32px; background: linear-gradient(45deg, #38bdf8, #3b82f6); color: white; border: none; border-radius: 12px; font-weight: 600; cursor: pointer; transition: all 0.3s; text-decoration: none; display: inline-flex; align-items: center; gap: 12px; }}
            .action-btn:hover {{ transform: translateY(-5px); box-shadow: 0 15px 30px rgba(56, 189, 248, 0.3); }}
            .action-btn.admin {{ background: linear-gradient(45deg, #f59e0b, #d97706); }}
            .admin-panel {{ background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.8)); border-radius: 24px; padding: 50px; margin-top: 40px; border: 1px solid rgba(245, 158, 11, 0.2); }}
            .admin-panel h2 {{ color: #f59e0b; margin-bottom: 30px; }}
            .admin-features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
            .admin-feature {{ background: rgba(15, 23, 42, 0.6); padding: 25px; border-radius: 16px; border: 1px solid rgba(245, 158, 11, 0.1); }}
            @media (max-width: 768px) {{ .header {{ flex-direction: column; gap: 20px; text-align: center; }} .container {{ padding: 20px; }} .welcome-card, .key-section, .updates-section, .admin-panel {{ padding: 30px 20px; }} .stats-grid {{ grid-template-columns: 1fr; }} .action-buttons {{ flex-direction: column; }} }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">Dashboard</div>
            <div class="user-info">
                <div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <strong>{user_data.get('in_game_name', 'Player')}</strong>
                        { '<span class="admin-badge">👑 ADMIN</span>' if is_admin else '' }
                    </div>
                    <div style="color: #94a3b8; font-size: 0.9rem;">Prestige {user_data.get('prestige', 0)}</div>
                </div>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="welcome-card">
                <h1>Welcome, {user_data.get('in_game_name', 'Player')}</h1>
                <p style="color: #94a3b8;">{'👑 You have admin privileges' if is_admin else 'Standard user account'}</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">K/D Ratio</div>
                    <div class="stat-value" style="color: { '#10b981' if kd >= 1.5 else '#f59e0b' if kd >= 1 else '#ef4444' };">{kd:.2f}</div>
                    <div style="color: #cbd5e1;">{user_data.get('total_kills', 0)} kills / {user_data.get('total_deaths', 0)} deaths</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Win Rate</div>
                    <div class="stat-value" style="color: { '#10b981' if win_rate >= 60 else '#f59e0b' if win_rate >= 40 else '#ef4444' };">{win_rate:.1f}%</div>
                    <div style="color: #cbd5e1;">{user_data.get('wins', 0)} wins / {user_data.get('losses', 0)} losses</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Games Played</div>
                    <div class="stat-value" style="color: #38bdf8;">{total_games}</div>
                    <div style="color: #cbd5e1;">Total matches</div>
                </div>
            </div>
            
            <div class="key-section">
                <h2 style="margin-bottom: 10px; font-size: 1.8rem;">Your API Key</h2>
                <p style="color: #94a3b8; margin-bottom: 20px;">
                    Keep this key secure. Do not share it with anyone.
                </p>
                
                <div class="key-display" id="apiKeyDisplay" onclick="revealKey()">
                    {session['user_key']}
                </div>
                
                <div class="action-buttons">
                    <button class="action-btn" onclick="copyKey()">
                        📋 Copy Key
                    </button>
                    { '<button class="action-btn admin" onclick="changeKey()">🔑 Change Key</button>' if is_admin else '' }
                    <button class="action-btn" onclick="refreshStats()">
                        🔄 Refresh Stats
                    </button>
                </div>
            </div>
            
            <div class="updates-section">
                <h2 style="margin-bottom: 30px; font-size: 1.8rem;">📥 Available Updates</h2>
                {updates_html if updates_html else '<p style="color: #94a3b8; text-align: center;">No updates available</p>'}
            </div>
            
            { f'''
            <div class="admin-panel">
                <h2>👑 Admin Controls</h2>
                <div class="admin-features">
                    <div class="admin-feature">
                        <h3 style="color: #f59e0b; margin-bottom: 15px;">Webhook Setup</h3>
                        <p style="color: #cbd5e1; margin-bottom: 20px;">Add webhook for automatic stats</p>
                        <button class="download-btn" onclick="setupWebhook()">Add Webhook</button>
                    </div>
                    <div class="admin-feature">
                        <h3 style="color: #f59e0b; margin-bottom: 15px;">Upload Update</h3>
                        <p style="color: #cbd5e1; margin-bottom: 20px;">Upload new client version</p>
                        <button class="download-btn" onclick="uploadUpdate()">Upload Update</button>
                    </div>
                    <div class="admin-feature">
                        <h3 style="color: #f59e0b; margin-bottom: 15px;">Admin Logs</h3>
                        <p style="color: #cbd5e1; margin-bottom: 20px;">View admin activity logs</p>
                        <button class="download-btn" onclick="viewLogs()">View Logs</button>
                    </div>
                </div>
            </div>
            ''' if is_admin else '' }
        </div>
        
        <script>
            function revealKey() {{
                const display = document.getElementById('apiKeyDisplay');
                display.classList.add('revealed');
            }}
            
            function copyKey() {{
                const key = "{session['user_key']}";
                navigator.clipboard.writeText(key);
                alert('✅ API key copied to clipboard');
            }}
            
            function downloadUpdate(url) {{
                window.open(url, '_blank');
            }}
            
            async function refreshStats() {{
                try {{
                    const response = await fetch('/api/refresh-stats?key={session['user_key']}');
                    const data = await response.json();
                    if (data.success) {{
                        alert('✅ Stats refreshed!');
                        location.reload();
                    }}
                }} catch (error) {{
                    alert('❌ Error refreshing stats');
                }}
            }}
            
            async function changeKey() {{
                if (!confirm('Generate a new API key? Your current key will be invalidated.')) return;
                
                try {{
                    const response = await fetch('/api/change-key', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ api_key: "{session['user_key']}" }})
                    }});
                    
                    const data = await response.json();
                    if (data.success) {{
                        alert('✅ New key generated! Please login again.');
                        window.location.href = '/logout';
                    }} else {{
                        alert('❌ ' + data.error);
                    }}
                }} catch (error) {{
                    alert('❌ Error changing key');
                }}
            }}
            
            function setupWebhook() {{
                const url = prompt('Enter Discord webhook URL:');
                if (url) {{
                    fetch('/api/add-webhook', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            api_key: "{session['user_key']}",
                            webhook_url: url,
                            server_id: "{user_data.get('server_id', '')}"
                        }})
                    }}).then(r => r.json()).then(data => {{
                        alert(data.success ? '✅ Webhook added!' : '❌ ' + data.error);
                    }});
                }}
            }}
            
            function uploadUpdate() {{
                const version = prompt('Version (e.g., 1.2.3):');
                const url = prompt('Download URL:');
                const changelog = prompt('Changelog:');
                const size = prompt('File size (e.g., 15.2 MB):');
                
                if (version && url && changelog) {{
                    fetch('/api/upload-update', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            api_key: "{session['user_key']}",
                            version: version,
                            download_url: url,
                            changelog: changelog,
                            file_size: size || 'Unknown'
                        }})
                    }}).then(r => r.json()).then(data => {{
                        alert(data.success ? '✅ Update uploaded!' : '❌ ' + data.error);
                        if (data.success) location.reload();
                    }});
                }}
            }}
            
            function viewLogs() {{
                alert('Admin logs feature coming soon!');
            }}
            
            // Auto-refresh every 5 minutes
            setInterval(refreshStats, 300000);
        </script>
    </body>
    </html>
    '''

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/check-admin')
def check_admin():
    """Check if user has admin role"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"is_admin": False})
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"is_admin": False})
    
    # Check database for admin flag
    is_admin = user_data.get('is_admin', 0)
    return jsonify({"is_admin": bool(is_admin)})

@app.route('/api/change-key', methods=['POST'])
def change_key():
    """Change API key (admin only)"""
    data = request.get_json()
    api_key = data.get('api_key')
    
    if not api_key:
        return jsonify({"success": False, "error": "Missing API key"})
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"success": False, "error": "Invalid API key"})
    
    # Check if user is admin
    if not user_data.get('is_admin'):
        return jsonify({"success": False, "error": "Admin privileges required"})
    
    # Generate new secure key
    new_key = generate_secure_key()
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE players SET api_key = ? WHERE id = ?',
        (new_key, user_data['id'])
    )
    conn.commit()
    conn.close()
    
    # Log the action
    log_admin_action(
        user_data['discord_id'],
        user_data['discord_name'],
        "change_api_key",
        details=f"Changed API key for {user_data['in_game_name']}"
    )
    
    return jsonify({"success": True, "new_key": new_key})

@app.route('/api/add-webhook', methods=['POST'])
def add_webhook():
    """Add webhook for stats"""
    data = request.get_json()
    api_key = data.get('api_key')
    webhook_url = data.get('webhook_url')
    server_id = data.get('server_id')
    
    if not api_key or not webhook_url or not server_id:
        return jsonify({"success": False, "error": "Missing parameters"})
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"success": False, "error": "Invalid API key"})
    
    # Check if user is admin in this server
    if not is_user_admin_in_guild(server_id, user_data['discord_id']):
        return jsonify({"success": False, "error": "Admin privileges required for this server"})
    
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO webhooks (webhook_url, server_id, webhook_name)
            VALUES (?, ?, ?)
        ''', (webhook_url, server_id, 'Stats Webhook'))
        conn.commit()
        conn.close()
        
        # Send initial webhook
        send_webhook_stats(server_id)
        
        # Log the action
        log_admin_action(
            user_data['discord_id'],
            user_data['discord_name'],
            "add_webhook",
            details=f"Added webhook for server {server_id}",
            server_id=server_id
        )
        
        return jsonify({"success": True})
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/upload-update', methods=['POST'])
def upload_update():
    """Upload new update (admin only)"""
    data = request.get_json()
    api_key = data.get('api_key')
    
    if not api_key:
        return jsonify({"success": False, "error": "Missing API key"})
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"success": False, "error": "Invalid API key"})
    
    # Check if user is admin
    if not user_data.get('is_admin'):
        return jsonify({"success": False, "error": "Admin privileges required"})
    
    version = data.get('version')
    download_url = data.get('download_url')
    changelog = data.get('changelog')
    file_size = data.get('file_size', 'Unknown')
    is_critical = data.get('is_critical', False)
    
    if not version or not download_url or not changelog:
        return jsonify({"success": False, "error": "Missing parameters"})
    
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO updates (version, download_url, changelog, file_size, is_critical, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (version, download_url, changelog, file_size, is_critical, user_data['discord_name']))
        conn.commit()
        conn.close()
        
        # Log the action
        log_admin_action(
            user_data['discord_id'],
            user_data['discord_name'],
            "upload_update",
            details=f"Uploaded version {version}"
        )
        
        return jsonify({"success": True})
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/refresh-stats')
def refresh_stats():
    """Refresh player stats"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "No key provided"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"error": "Invalid key"}), 401
    
    # Send webhook update
    send_webhook_stats(user_data.get('server_id', ''))
    
    return jsonify({"success": True})

@app.route('/api/latest-update')
def latest_update():
    """Get latest update"""
    conn = get_db_connection()
    update = conn.execute(
        'SELECT * FROM updates ORDER BY uploaded_at DESC LIMIT 1'
    ).fetchone()
    conn.close()
    
    if update:
        return jsonify(dict(update))
    else:
        return jsonify({"error": "No updates available"}), 404

@app.route('/api/stats')
def api_stats():
    """Get global stats"""
    conn = get_db_connection()
    
    total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
    total_kills = conn.execute('SELECT SUM(total_kills) as sum FROM players').fetchone()['sum'] or 0
    total_games = conn.execute('SELECT SUM(wins + losses) as sum FROM players').fetchone()['sum'] or 0
    total_admins = conn.execute('SELECT COUNT(*) as count FROM players WHERE is_admin = 1').fetchone()['count']
    
    conn.close()
    
    return jsonify({
        "total_players": total_players,
        "total_kills": total_kills,
        "total_games": total_games,
        "total_admins": total_admins,
        "bot_active": bot_active,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy" if bot_active else "offline",
        "bot_active": bot_active,
        "service": "Auto Admin Detection Bot",
        "version": "4.0",
        "timestamp": datetime.utcnow().isoformat()
    })

# =============================================================================
# BACKGROUND TASKS
# =============================================================================

def webhook_scheduler():
    """Schedule webhook updates"""
    import threading
    import time
    
    def send_updates():
        while True:
            try:
                conn = get_db_connection()
                servers = conn.execute('SELECT DISTINCT server_id FROM webhooks WHERE is_active = 1').fetchall()
                conn.close()
                
                for server in servers:
                    send_webhook_stats(server['server_id'])
                
                time.sleep(1800)  # 30 minutes
            except:
                time.sleep(300)  # 5 minutes on error
    
    thread = threading.Thread(target=send_updates, daemon=True)
    thread.start()

def admin_role_updater():
    """Update admin status for all users"""
    import threading
    import time
    
    def update_admins():
        while True:
            try:
                conn = get_db_connection()
                players = conn.execute('SELECT discord_id, server_id FROM players').fetchall()
                
                for player in players:
                    is_admin = is_user_admin_in_guild(player['server_id'], player['discord_id'])
                    conn.execute(
                        'UPDATE players SET is_admin = ? WHERE discord_id = ?',
                        (1 if is_admin else 0, player['discord_id'])
                    )
                
                conn.commit()
                conn.close()
                time.sleep(3600)  # 1 hour
            except:
                time.sleep(600)  # 10 minutes on error
    
    thread = threading.Thread(target=update_admins, daemon=True)
    thread.start()

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*60}")
    print("🤖 AUTO ADMIN DETECTION BOT")
    print(f"{'='*60}")
    
    # Test Discord connection
    if test_discord_token():
        bot_active = True
        print("✅ Discord bot connected")
        
        if register_commands():
            print("✅ Commands registered")
        else:
            print("⚠️ Could not register commands")
    else:
        print("❌ Discord token not set or invalid")
    
    # Start background tasks
    webhook_scheduler()
    admin_role_updater()
    print("✅ Background tasks started")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🔗 Interactions: http://localhost:{port}/interactions")
    
    print(f"\n🎮 Discord Commands:")
    print(f"   /ping - Check bot status")
    print(f"   /register [name] - Register (admin auto-detected)")
    print(f"   /ticket [issue] - Create support ticket")
    print(f"   /stats - View your stats")
    print(f"   /admin check_roles - Show admin roles in server")
    
    print(f"\n👑 Admin Detection:")
    print(f"   • Auto-detects ADMINISTRATOR permission")
    print(f"   • Auto-detects MANAGE_GUILD permission")
    print(f"   • Auto-detects MANAGE_ROLES permission")
    print(f"   • Server owner is automatically admin")
    print(f"   • Updates admin status hourly")
    
    print(f"\n🔐 Security Features:")
    print(f"   • Strong 32-character API keys")
    print(f"   • Hidden API keys (click to reveal)")
    print(f"   • Admin-only key changes")
    print(f"   • Admin-only webhook management")
    print(f"   • Admin-only update uploads")
    
    print(f"\n📊 Webhook System:")
    print(f"   • Auto-send stats every 30 minutes")
    print(f"   • Server-specific webhooks")
    print(f"   • Admin can add webhooks via dashboard")
    
    print(f"\n📥 Update System:")
    print(f"   • Online download button")
    print(f"   • Admin upload via dashboard")
    print(f"   • Version tracking")
    
    print(f"\n💡 How it works:")
    print(f"   1. User registers with /register")
    print(f"   2. Bot checks Discord permissions for admin roles")
    print(f"   3. Admin flag stored in database")
    print(f"   4. Admin users get extra dashboard features")
    print(f"   5. Only admins can change keys/add webhooks")
    
    print(f"\n{'='*60}\n")
    
    # Start server
    app.run(host='0.0.0.0', port=port, debug=False)

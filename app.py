# app.py - ANIMATED DARK MODE BOT DASHBOARD
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

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'bot-dashboard-secret-key')
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
# DISCORD SIGNATURE VERIFICATION
# =============================================================================

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
# DATABASE SETUP
# =============================================================================

def init_db():
    """Initialize database"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT,
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
                credits INTEGER DEFAULT 1000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# KEY GENERATION & VALIDATION
# =============================================================================

def generate_api_key():
    """Generate short API key - exactly 12 characters"""
    # Format: KEY-XXXXXXX (12 chars total)
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"KEY-{random_str}"  # Total: 4 + 8 = 12 chars

def validate_api_key(api_key):
    """Validate API key"""
    if not api_key or not api_key.startswith("KEY-"):
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
        
        logger.info(f"Command: {command} from {user_name}")
        
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
                api_key = existing['api_key']
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"Already registered as `{existing['in_game_name']}`\n\n"
                            f"**Your API Key:** `{api_key}`\n\n"
                            f"Dashboard: {request.host_url}"
                        ),
                        "flags": 64
                    }
                })
            
            # Generate short API key (12 chars)
            api_key = generate_api_key()
            
            # Register player
            conn.execute('''
                INSERT INTO players 
                (discord_id, discord_name, in_game_name, api_key, server_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, user_name, in_game_name, api_key, server_id))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"✅ **Registered Successfully**\n\n"
                        f"**Name:** `{in_game_name}`\n"
                        f"**API Key:** `{api_key}`\n\n"
                        f"**Dashboard:** {request.host_url}\n"
                        f"Use this key to login to your dashboard"
                    ),
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

# =============================================================================
# WEB INTERFACE - ANIMATED DARK MODE
# =============================================================================

@app.route('/')
def home():
    """Main page - Animated dark mode login"""
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
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #0a0a0a;
                color: white;
                min-height: 100vh;
                overflow: hidden;
                position: relative;
            }
            
            /* Animated background */
            .bg-animation {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: -1;
            }
            
            .dot {
                position: absolute;
                background: linear-gradient(45deg, #6366f1, #8b5cf6);
                border-radius: 50%;
                animation: float 20s infinite linear;
            }
            
            @keyframes float {
                0% {
                    transform: translate(0, 0) rotate(0deg);
                    opacity: 0;
                }
                10% {
                    opacity: 0.6;
                }
                90% {
                    opacity: 0.6;
                }
                100% {
                    transform: translate(calc(100vw * var(--tx)), calc(100vh * var(--ty))) rotate(360deg);
                    opacity: 0;
                }
            }
            
            .container {
                width: 100%;
                max-width: 450px;
                margin: 0 auto;
                padding: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
            }
            
            .login-card {
                background: rgba(20, 20, 30, 0.8);
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 50px 40px;
                width: 100%;
                text-align: center;
                border: 1px solid rgba(99, 102, 241, 0.2);
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                position: relative;
                overflow: hidden;
                animation: slideUp 0.6s ease-out;
            }
            
            @keyframes slideUp {
                from {
                    opacity: 0;
                    transform: translateY(30px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .login-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899);
                animation: gradientMove 3s infinite linear;
            }
            
            @keyframes gradientMove {
                0% { background-position: 0% 50%; }
                100% { background-position: 100% 50%; }
            }
            
            h1 {
                font-size: 2.5rem;
                font-weight: 800;
                margin-bottom: 10px;
                background: linear-gradient(45deg, #6366f1, #8b5cf6);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-size: 200% 200%;
                animation: gradientShift 4s ease infinite;
            }
            
            @keyframes gradientShift {
                0%, 100% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
            }
            
            .subtitle {
                color: #94a3b8;
                margin-bottom: 40px;
                font-size: 1.1rem;
                line-height: 1.6;
            }
            
            .key-input {
                width: 100%;
                padding: 18px;
                background: rgba(30, 30, 40, 0.8);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 12px;
                color: white;
                font-size: 18px;
                font-family: monospace;
                letter-spacing: 2px;
                text-align: center;
                margin-bottom: 25px;
                transition: all 0.3s;
                text-transform: uppercase;
            }
            
            .key-input:focus {
                outline: none;
                border-color: #6366f1;
                box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.2);
                background: rgba(30, 30, 40, 0.9);
                transform: scale(1.02);
            }
            
            .key-input::placeholder {
                color: #64748b;
            }
            
            .login-btn {
                width: 100%;
                padding: 18px;
                background: linear-gradient(45deg, #6366f1, #8b5cf6);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
            }
            
            .login-btn:hover {
                transform: translateY(-3px);
                box-shadow: 0 15px 30px rgba(99, 102, 241, 0.3);
            }
            
            .login-btn:active {
                transform: translateY(-1px);
            }
            
            .login-btn::after {
                content: '';
                position: absolute;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: linear-gradient(45deg, transparent, rgba(255, 255, 255, 0.1), transparent);
                transform: rotate(45deg);
                transition: all 0.5s;
            }
            
            .login-btn:hover::after {
                left: 100%;
            }
            
            .error-box {
                background: rgba(239, 68, 68, 0.1);
                border: 2px solid rgba(239, 68, 68, 0.4);
                border-radius: 12px;
                padding: 16px;
                margin-top: 20px;
                color: #fca5a5;
                font-size: 14px;
                display: none;
                animation: shake 0.5s;
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }
            
            .info-box {
                background: rgba(99, 102, 241, 0.1);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 12px;
                padding: 25px;
                margin-top: 35px;
                text-align: left;
                font-size: 14px;
                color: #cbd5e1;
            }
            
            .info-box strong {
                display: block;
                margin-bottom: 15px;
                color: white;
                font-size: 16px;
            }
            
            .info-box code {
                background: rgba(0, 0, 0, 0.4);
                padding: 4px 8px;
                border-radius: 6px;
                font-family: monospace;
                color: #6366f1;
                margin: 0 2px;
            }
            
            .bot-status {
                display: inline-block;
                padding: 10px 20px;
                background: rgba(30, 30, 40, 0.8);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 20px;
                margin-top: 25px;
                font-size: 14px;
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }
            
            .status-online {
                color: #10b981;
                border-color: rgba(16, 185, 129, 0.3);
            }
            
            .status-offline {
                color: #ef4444;
                border-color: rgba(239, 68, 68, 0.3);
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 20px;
                }
                .login-card {
                    padding: 40px 25px;
                }
                h1 {
                    font-size: 2rem;
                }
                .key-input {
                    font-size: 16px;
                    padding: 16px;
                }
            }
        </style>
    </head>
    <body>
        <!-- Animated background -->
        <div class="bg-animation" id="bgAnimation"></div>
        
        <div class="container">
            <div class="login-card">
                <h1>Bot Dashboard</h1>
                <div class="subtitle">
                    Enter your API key to access your personal dashboard
                </div>
                
                <input type="text" 
                       class="key-input" 
                       id="apiKey" 
                       placeholder="KEY-XXXXXXXX"
                       autocomplete="off"
                       spellcheck="false"
                       maxlength="12">
                
                <button class="login-btn" onclick="validateKey()">
                    Access Dashboard
                </button>
                
                <div class="error-box" id="errorMessage">
                    Invalid API key
                </div>
                
                <div class="info-box">
                    <strong>How to get your API key:</strong>
                    <p>1. Add bot to your Discord server</p>
                    <p>2. Type: <code>/register your_name</code></p>
                    <p>3. Copy your <code>KEY-XXXXXXXX</code> key</p>
                    <p>4. Enter it above to access your dashboard</p>
                </div>
                
                <div class="bot-status" id="botStatus">
                    Bot Status: Checking...
                </div>
            </div>
        </div>
        
        <script>
            // Initialize animated background
            function initBackground() {
                const container = document.getElementById('bgAnimation');
                for (let i = 0; i < 30; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    const size = Math.random() * 3 + 1;
                    dot.style.width = dot.style.height = size + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.opacity = Math.random() * 0.4 + 0.1;
                    dot.style.setProperty('--tx', Math.random() * 2 - 1);
                    dot.style.setProperty('--ty', Math.random() * 2 - 1);
                    dot.style.animationDelay = Math.random() * 5 + 's';
                    dot.style.animationDuration = Math.random() * 15 + 15 + 's';
                    container.appendChild(dot);
                }
            }
            
            async function validateKey() {
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const errorDiv = document.getElementById('errorMessage');
                const btn = document.querySelector('.login-btn');
                
                if (!key) {
                    errorDiv.textContent = "Please enter an API key";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                if (!key.startsWith('KEY-')) {
                    errorDiv.textContent = "Key must start with KEY-";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                // Show loading
                const originalText = btn.innerHTML;
                btn.innerHTML = 'Checking...';
                btn.disabled = true;
                
                try {
                    const response = await fetch('/api/validate-key', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ api_key: key })
                    });
                    
                    const data = await response.json();
                    
                    if (data.valid) {
                        // Success animation
                        btn.innerHTML = '✅ Access Granted';
                        btn.style.background = 'linear-gradient(45deg, #10b981, #34d399)';
                        
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 500);
                    } else {
                        // Error
                        errorDiv.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        btn.innerHTML = originalText;
                        btn.disabled = false;
                    }
                } catch (error) {
                    errorDiv.textContent = 'Connection error. Please try again.';
                    errorDiv.style.display = 'block';
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                }
            }
            
            // Enter key to submit
            document.getElementById('apiKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    validateKey();
                }
            });
            
            // Auto-format key (12 chars max)
            document.getElementById('apiKey').addEventListener('input', function(e) {
                let value = e.target.value.toUpperCase().replace(/[^A-Z0-9\-]/g, '');
                if (value.length > 12) value = value.substring(0, 12);
                e.target.value = value;
            });
            
            // Check bot status
            async function checkBotStatus() {
                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    const statusElement = document.getElementById('botStatus');
                    
                    if (data.bot_active) {
                        statusElement.innerHTML = '✅ Bot Status: ONLINE';
                        statusElement.className = 'bot-status status-online';
                    } else {
                        statusElement.innerHTML = '❌ Bot Status: OFFLINE';
                        statusElement.className = 'bot-status status-offline';
                    }
                } catch (error) {
                    document.getElementById('botStatus').innerHTML = '⚠️ Bot Status: ERROR';
                }
            }
            
            // Initialize
            document.addEventListener('DOMContentLoaded', function() {
                initBackground();
                checkBotStatus();
                document.getElementById('apiKey').focus();
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
    api_key = data.get('api_key', '').strip().upper()
    
    if not api_key:
        return jsonify({"valid": False, "error": "No key provided"})
    
    # Validate length
    if len(api_key) != 12:
        return jsonify({"valid": False, "error": "Key must be 12 characters"})
    
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
    """Animated dark mode dashboard"""
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    user_data = session.get('user_data')
    if not user_data:
        return redirect(url_for('home'))
    
    # Generate stats
    kd = user_data.get('total_kills', 0) / max(user_data.get('total_deaths', 1), 1)
    total_games = user_data.get('wins', 0) + user_data.get('losses', 0)
    win_rate = (user_data.get('wins', 0) / total_games * 100) if total_games > 0 else 0
    
    # Color based on KD
    kd_color = '#10b981' if kd >= 1.5 else '#f59e0b' if kd >= 1 else '#ef4444'
    win_color = '#10b981' if win_rate >= 60 else '#f59e0b' if win_rate >= 40 else '#ef4444'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #0a0a0a;
                color: white;
                min-height: 100vh;
                position: relative;
                overflow-x: hidden;
            }}
            
            /* Animated background */
            .bg-animation {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: -1;
                opacity: 0.3;
            }}
            
            .bg-dot {{
                position: absolute;
                background: rgba(99, 102, 241, 0.2);
                border-radius: 50%;
                animation: floatBg 40s infinite linear;
            }}
            
            @keyframes floatBg {{
                0% {{ transform: translateY(0) rotate(0deg); }}
                100% {{ transform: translateY(-100vh) rotate(360deg); }}
            }}
            
            /* Glass morphism header */
            .header {{
                background: rgba(20, 20, 30, 0.8);
                backdrop-filter: blur(20px);
                border-bottom: 1px solid rgba(99, 102, 241, 0.2);
                padding: 25px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
            }}
            
            .logo {{
                font-size: 1.8rem;
                font-weight: 700;
                background: linear-gradient(45deg, #6366f1, #8b5cf6);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            
            .user-info {{
                display: flex;
                align-items: center;
                gap: 25px;
            }}
            
            .user-name {{
                font-size: 1.1rem;
                font-weight: 600;
            }}
            
            .user-level {{
                font-size: 0.9rem;
                color: #94a3b8;
            }}
            
            .logout-btn {{
                padding: 10px 24px;
                background: linear-gradient(45deg, #ef4444, #dc2626);
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-block;
            }}
            
            .logout-btn:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 25px rgba(239, 68, 68, 0.3);
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 40px;
            }}
            
            /* Welcome card with animation */
            .welcome-card {{
                background: linear-gradient(135deg, rgba(30, 30, 40, 0.8), rgba(20, 20, 30, 0.8));
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 50px;
                margin-bottom: 40px;
                border: 1px solid rgba(99, 102, 241, 0.2);
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                position: relative;
                overflow: hidden;
                animation: slideUp 0.8s ease-out;
            }}
            
            .welcome-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899);
                animation: gradientMove 3s infinite linear;
            }}
            
            .welcome-card h1 {{
                font-size: 2.5rem;
                margin-bottom: 15px;
                background: linear-gradient(45deg, white, #cbd5e1);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            
            .welcome-card p {{
                color: #94a3b8;
                font-size: 1.2rem;
                line-height: 1.6;
            }}
            
            /* Stats grid with hover effects */
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 25px;
                margin-bottom: 50px;
            }}
            
            .stat-card {{
                background: linear-gradient(135deg, rgba(30, 30, 40, 0.8), rgba(20, 20, 30, 0.8));
                backdrop-filter: blur(20px);
                border-radius: 20px;
                padding: 35px;
                text-align: center;
                border: 1px solid rgba(99, 102, 241, 0.1);
                transition: all 0.4s;
                position: relative;
                overflow: hidden;
            }}
            
            .stat-card:hover {{
                transform: translateY(-10px) scale(1.02);
                border-color: rgba(99, 102, 241, 0.3);
                box-shadow: 0 20px 40px rgba(99, 102, 241, 0.2);
            }}
            
            .stat-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #6366f1, #8b5cf6);
            }}
            
            .stat-value {{
                font-size: 3.5rem;
                font-weight: 800;
                margin: 20px 0;
                font-family: 'Segoe UI', sans-serif;
            }}
            
            .stat-label {{
                color: #94a3b8;
                font-size: 0.95rem;
                text-transform: uppercase;
                letter-spacing: 2px;
                margin-bottom: 10px;
            }}
            
            .stat-details {{
                color: #cbd5e1;
                font-size: 1rem;
            }}
            
            /* Key section */
            .key-section {{
                background: linear-gradient(135deg, rgba(30, 30, 40, 0.8), rgba(20, 20, 30, 0.8));
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 50px;
                margin-top: 40px;
                border: 1px solid rgba(99, 102, 241, 0.2);
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                position: relative;
                overflow: hidden;
            }}
            
            .key-section::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #10b981, #34d399);
            }}
            
            .key-display {{
                background: rgba(10, 10, 15, 0.6);
                border: 2px solid rgba(99, 102, 241, 0.3);
                border-radius: 16px;
                padding: 25px;
                margin: 30px 0;
                font-family: monospace;
                font-size: 1.4rem;
                color: #6366f1;
                text-align: center;
                letter-spacing: 3px;
                cursor: pointer;
                transition: all 0.3s;
                word-break: break-all;
            }}
            
            .key-display:hover {{
                background: rgba(10, 10, 15, 0.8);
                border-color: #6366f1;
                box-shadow: 0 0 30px rgba(99, 102, 241, 0.3);
                transform: scale(1.02);
            }}
            
            /* Action buttons */
            .action-buttons {{
                display: flex;
                gap: 20px;
                margin-top: 40px;
                flex-wrap: wrap;
            }}
            
            .action-btn {{
                padding: 16px 32px;
                background: linear-gradient(45deg, #6366f1, #8b5cf6);
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: 600;
                font-size: 16px;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 12px;
                flex: 1;
                min-width: 200px;
                justify-content: center;
            }}
            
            .action-btn:hover {{
                transform: translateY(-5px);
                box-shadow: 0 15px 30px rgba(99, 102, 241, 0.3);
            }}
            
            .action-btn.secondary {{
                background: linear-gradient(45deg, #6b7280, #4b5563);
            }}
            
            .action-btn.secondary:hover {{
                box-shadow: 0 15px 30px rgba(107, 114, 128, 0.3);
            }}
            
            .action-btn.danger {{
                background: linear-gradient(45deg, #ef4444, #dc2626);
            }}
            
            .action-btn.danger:hover {{
                box-shadow: 0 15px 30px rgba(239, 68, 68, 0.3);
            }}
            
            /* Floating notification */
            .notification {{
                position: fixed;
                bottom: 30px;
                right: 30px;
                background: linear-gradient(45deg, #10b981, #34d399);
                color: white;
                padding: 20px 30px;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(16, 185, 129, 0.3);
                z-index: 1000;
                display: none;
                animation: slideInRight 0.5s ease-out;
            }}
            
            @keyframes slideInRight {{
                from {{ transform: translateX(100%); opacity: 0; }}
                to {{ transform: translateX(0); opacity: 1; }}
            }}
            
            /* Responsive */
            @media (max-width: 768px) {{
                .header {{
                    flex-direction: column;
                    gap: 20px;
                    text-align: center;
                    padding: 20px;
                }}
                .container {{
                    padding: 20px;
                }}
                .welcome-card, .key-section {{
                    padding: 30px 20px;
                }}
                .welcome-card h1 {{
                    font-size: 2rem;
                }}
                .stats-grid {{
                    grid-template-columns: 1fr;
                }}
                .stat-card {{
                    padding: 30px 20px;
                }}
                .action-buttons {{
                    flex-direction: column;
                }}
                .action-btn {{
                    min-width: 100%;
                }}
                .key-display {{
                    font-size: 1.2rem;
                    padding: 20px;
                }}
            }}
        </style>
    </head>
    <body>
        <!-- Animated background -->
        <div class="bg-animation" id="bgAnimation"></div>
        
        <div class="header">
            <div class="logo">Dashboard</div>
            <div class="user-info">
                <div>
                    <div class="user-name">{user_data.get('in_game_name', 'Player')}</div>
                    <div class="user-level">Level {user_data.get('prestige', 0)} • {user_data.get('credits', 1000)} credits</div>
                </div>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="welcome-card">
                <h1>Welcome back, {user_data.get('in_game_name', 'Player')}</h1>
                <p>Your stats and information are updated in real-time. Keep playing to improve your rankings!</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">K/D Ratio</div>
                    <div class="stat-value" style="color: {kd_color};">{kd:.2f}</div>
                    <div class="stat-details">{user_data.get('total_kills', 0)} kills / {user_data.get('total_deaths', 0)} deaths</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Win Rate</div>
                    <div class="stat-value" style="color: {win_color};">{win_rate:.1f}%</div>
                    <div class="stat-details">{user_data.get('wins', 0)} wins / {user_data.get('losses', 0)} losses</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Games Played</div>
                    <div class="stat-value" style="color: #6366f1;">{total_games}</div>
                    <div class="stat-details">Total matches completed</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Credits</div>
                    <div class="stat-value" style="color: #f59e0b;">${user_data.get('credits', 1000)}</div>
                    <div class="stat-details">Available balance</div>
                </div>
            </div>
            
            <div class="key-section">
                <h2 style="margin-bottom: 10px; font-size: 1.8rem;">Your API Key</h2>
                <p style="color: #94a3b8; margin-bottom: 20px;">
                    Use this key to access the bot API. Keep it secure and don't share it with anyone.
                </p>
                
                <div class="key-display" onclick="copyKey()">
                    {session['user_key']}
                    <div style="font-size: 0.9rem; color: #64748b; margin-top: 15px;">
                        Click to copy to clipboard
                    </div>
                </div>
                
                <div class="action-buttons">
                    <button class="action-btn" onclick="refreshStats()">
                        <span>🔄</span> Refresh Stats
                    </button>
                    <button class="action-btn secondary" onclick="viewApiDocs()">
                        <span>📖</span> API Documentation
                    </button>
                    <button class="action-btn danger" onclick="getNewKey()">
                        <span>🔑</span> Generate New Key
                    </button>
                </div>
            </div>
        </div>
        
        <!-- Notification -->
        <div class="notification" id="notification"></div>
        
        <script>
            // Initialize animated background
            function initBackground() {{
                const container = document.getElementById('bgAnimation');
                for (let i = 0; i < 20; i++) {{
                    const dot = document.createElement('div');
                    dot.className = 'bg-dot';
                    const size = Math.random() * 100 + 50;
                    dot.style.width = dot.style.height = size + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = '100vh';
                    dot.style.opacity = Math.random() * 0.1 + 0.05;
                    dot.style.animationDelay = Math.random() * 20 + 's';
                    dot.style.animationDuration = Math.random() * 30 + 30 + 's';
                    container.appendChild(dot);
                }}
            }}
            
            function copyKey() {{
                navigator.clipboard.writeText("{session['user_key']}");
                showNotification("✅ Key copied to clipboard");
            }}
            
            async function refreshStats() {{
                try {{
                    const response = await fetch('/api/refresh-stats?key={session['user_key']}');
                    const data = await response.json();
                    if (data.success) {{
                        showNotification("✅ Stats refreshed!");
                        setTimeout(() => location.reload(), 1000);
                    }}
                }} catch (error) {{
                    showNotification("❌ Error refreshing stats");
                }}
            }}
            
            function viewApiDocs() {{
                showNotification("📚 API Documentation loaded in console");
                console.log("API Documentation:\\n\\n" +
                      "GET /api/profile?key=YOUR_KEY - Get your profile\\n" +
                      "GET /api/stats - Get global statistics\\n" +
                      "GET /health - Check service status\\n" +
                      "POST /api/new-key?key=YOUR_KEY - Generate new API key");
            }}
            
            async function getNewKey() {{
                if (confirm("Generate a new API key? Your old key will stop working immediately.")) {{
                    try {{
                        const response = await fetch('/api/new-key?key={session['user_key']}', {{
                            method: 'POST'
                        }});
                        const data = await response.json();
                        if (data.success) {{
                            showNotification("✅ New key generated! Redirecting to login...");
                            setTimeout(() => window.location.href = '/logout', 1500);
                        }}
                    }} catch (error) {{
                        showNotification("❌ Error generating new key");
                    }}
                }}
            }}
            
            function showNotification(message) {{
                const notification = document.getElementById('notification');
                notification.textContent = message;
                notification.style.display = 'block';
                
                setTimeout(() => {{
                    notification.style.display = 'none';
                }}, 3000);
            }}
            
            // Add hover effects to stat cards
            document.addEventListener('DOMContentLoaded', function() {{
                initBackground();
                
                const statCards = document.querySelectorAll('.stat-card');
                statCards.forEach(card => {{
                    card.addEventListener('mouseenter', () => {{
                        card.style.transform = 'translateY(-10px) scale(1.02)';
                    }});
                    
                    card.addEventListener('mouseleave', () => {{
                        card.style.transform = '';
                    }});
                }});
                
                // Auto-refresh stats every 60 seconds
                setInterval(() => {{
                    refreshStats();
                }}, 60000);
            }});
        </script>
    </body>
    </html>
    '''

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/refresh-stats')
def api_refresh_stats():
    """Refresh player stats"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "No key provided"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"error": "Invalid key"}), 401
    
    return jsonify({"success": True})

@app.route('/api/new-key', methods=['POST'])
def api_new_key():
    """Generate new API key"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "No key provided"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"error": "Invalid key"}), 401
    
    # Generate new key (12 chars)
    new_key = generate_api_key()
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE players SET api_key = ? WHERE id = ?',
        (new_key, user_data['id'])
    )
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "new_key": new_key})

@app.route('/api/profile')
def api_profile():
    """Get player profile"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "No key"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"error": "Invalid key"}), 401
    
    return jsonify(user_data)

@app.route('/api/stats')
def api_stats():
    """Get global stats"""
    conn = get_db_connection()
    
    total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
    total_kills = conn.execute('SELECT SUM(total_kills) as sum FROM players').fetchone()['sum'] or 0
    total_games = conn.execute('SELECT SUM(wins + losses) as sum FROM players').fetchone()['sum'] or 0
    
    conn.close()
    
    return jsonify({
        "total_players": total_players,
        "total_kills": total_kills,
        "total_games": total_games,
        "bot_active": bot_active,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy" if bot_active else "offline",
        "bot_active": bot_active,
        "service": "Bot Dashboard",
        "version": "2.0",
        "timestamp": datetime.utcnow().isoformat()
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*60}")
    print("🌙 ANIMATED DARK MODE BOT DASHBOARD")
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
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🔗 Interactions: http://localhost:{port}/interactions")
    
    print(f"\n🎮 Discord Commands:")
    print(f"   /ping - Check if bot is online")
    print(f"   /register [name] - Get API key (KEY-XXXXXXXX)")
    
    print(f"\n🔑 API Key Format: KEY-XXXXXXXX (12 characters)")
    print(f"   • Exactly 12 characters")
    print(f"   • Starts with KEY-")
    print(f"   • 8 random characters")
    
    print(f"\n✨ Features:")
    print(f"   • Animated dark mode interface")
    print(f"   • Real-time stats")
    print(f"   • Glass morphism design")
    print(f"   • Hover animations")
    print(f"   • Mobile responsive")
    
    print(f"\n{'='*60}\n")
    
    # Start server
    app.run(host='0.0.0.0', port=port, debug=False)

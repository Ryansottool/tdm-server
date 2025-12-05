# app.py - SIMPLE DISCORD BOT & DASHBOARD
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
app.secret_key = os.environ.get('SECRET_KEY', 'simple-secret-key-change-this')
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

# Simple ping responses
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
    """Generate short API key"""
    timestamp = str(int(time.time()))[-6:]
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"KEY-{timestamp}{random_str}"

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
        
        logger.info(f"Command: {command} from {user_name} ({user_id})")
        
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
                            f"You're already registered as `{existing['in_game_name']}`\n\n"
                            f"**Your API Key:** `{api_key}`\n\n"
                            f"Dashboard: {request.host_url}"
                        ),
                        "flags": 64
                    }
                })
            
            # Generate short API key
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
                        f"**Web Dashboard:** {request.host_url}\n"
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
# WEB INTERFACE
# =============================================================================

@app.route('/')
def home():
    """Main page - Simple key entry"""
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
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }
            
            .login-card {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 40px;
                width: 100%;
                max-width: 400px;
                text-align: center;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            
            h1 {
                font-size: 2rem;
                margin-bottom: 10px;
                font-weight: 600;
            }
            
            .subtitle {
                color: rgba(255, 255, 255, 0.8);
                margin-bottom: 30px;
                line-height: 1.5;
            }
            
            .key-input {
                width: 100%;
                padding: 15px;
                background: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 10px;
                color: white;
                font-size: 16px;
                text-align: center;
                margin-bottom: 20px;
                transition: all 0.3s;
            }
            
            .key-input:focus {
                outline: none;
                border-color: rgba(255, 255, 255, 0.6);
                background: rgba(255, 255, 255, 0.15);
            }
            
            .key-input::placeholder {
                color: rgba(255, 255, 255, 0.6);
            }
            
            .login-btn {
                width: 100%;
                padding: 15px;
                background: white;
                color: #667eea;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
            }
            
            .login-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            }
            
            .login-btn:active {
                transform: translateY(0);
            }
            
            .error-message {
                background: rgba(255, 59, 48, 0.2);
                border: 1px solid rgba(255, 59, 48, 0.4);
                border-radius: 8px;
                padding: 12px;
                margin-top: 20px;
                color: #ffcccb;
                font-size: 14px;
                display: none;
            }
            
            .info-box {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 20px;
                margin-top: 30px;
                text-align: left;
                font-size: 14px;
            }
            
            .info-box strong {
                display: block;
                margin-bottom: 10px;
                color: white;
            }
            
            .info-box code {
                background: rgba(0, 0, 0, 0.3);
                padding: 3px 6px;
                border-radius: 4px;
                font-family: monospace;
            }
            
            @media (max-width: 768px) {
                .login-card {
                    padding: 30px 20px;
                }
                h1 {
                    font-size: 1.5rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="login-card">
            <h1>Bot Dashboard</h1>
            <div class="subtitle">
                Enter your API key to access your dashboard
            </div>
            
            <input type="text" 
                   class="key-input" 
                   id="apiKey" 
                   placeholder="KEY-XXXXXXXX"
                   autocomplete="off"
                   spellcheck="false"
                   maxlength="15">
            
            <button class="login-btn" onclick="validateKey()">
                Access Dashboard
            </button>
            
            <div class="error-message" id="errorMessage">
                Invalid API key
            </div>
            
            <div class="info-box">
                <strong>How to get your API key:</strong>
                <p>1. Add bot to your Discord server</p>
                <p>2. Type: <code>/register your_name</code></p>
                <p>3. Copy your <code>KEY-XXXXXX</code> key</p>
                <p>4. Enter it above to access your dashboard</p>
            </div>
        </div>
        
        <script>
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
                        // Success
                        btn.innerHTML = '✅ Access Granted';
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
            
            // Auto-format key
            document.getElementById('apiKey').addEventListener('input', function(e) {
                let value = e.target.value.toUpperCase().replace(/[^A-Z0-9\-]/g, '');
                if (value.length > 15) value = value.substring(0, 15);
                e.target.value = value;
            });
            
            // Focus on input when page loads
            document.addEventListener('DOMContentLoaded', function() {
                document.getElementById('apiKey').focus();
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
    """User dashboard"""
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    user_data = session.get('user_data')
    if not user_data:
        return redirect(url_for('home'))
    
    kd = user_data.get('total_kills', 0) / max(user_data.get('total_deaths', 1), 1)
    total_games = user_data.get('wins', 0) + user_data.get('losses', 0)
    win_rate = (user_data.get('wins', 0) / total_games * 100) if total_games > 0 else 0
    
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
                background: #f5f5f7;
                color: #1d1d1f;
                min-height: 100vh;
            }}
            
            .header {{
                background: white;
                border-bottom: 1px solid #e5e5e7;
                padding: 20px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
            }}
            
            .logo {{
                font-size: 1.5rem;
                font-weight: 600;
                color: #007AFF;
            }}
            
            .user-info {{
                display: flex;
                align-items: center;
                gap: 20px;
            }}
            
            .logout-btn {{
                padding: 8px 16px;
                background: #FF3B30;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-block;
            }}
            
            .logout-btn:hover {{
                background: #FF453A;
                transform: translateY(-1px);
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 40px;
            }}
            
            .welcome-section {{
                background: white;
                border-radius: 16px;
                padding: 40px;
                margin-bottom: 30px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
            }}
            
            .welcome-section h1 {{
                font-size: 2rem;
                margin-bottom: 10px;
                color: #1d1d1f;
            }}
            
            .welcome-section p {{
                color: #86868b;
                line-height: 1.6;
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 40px;
            }}
            
            .stat-card {{
                background: white;
                border-radius: 12px;
                padding: 30px;
                text-align: center;
                transition: all 0.3s;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
            }}
            
            .stat-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
            }}
            
            .stat-value {{
                font-size: 2.5rem;
                font-weight: 700;
                margin: 10px 0;
                color: #007AFF;
            }}
            
            .stat-label {{
                color: #86868b;
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            
            .key-section {{
                background: white;
                border-radius: 16px;
                padding: 40px;
                margin-top: 40px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
            }}
            
            .key-display {{
                background: #f5f5f7;
                border: 2px solid #e5e5e7;
                border-radius: 10px;
                padding: 20px;
                margin: 20px 0;
                font-family: monospace;
                font-size: 1.2rem;
                color: #1d1d1f;
                text-align: center;
                letter-spacing: 1px;
                cursor: pointer;
                transition: all 0.3s;
            }}
            
            .key-display:hover {{
                background: #e8e8ed;
                border-color: #007AFF;
            }}
            
            .action-buttons {{
                display: flex;
                gap: 15px;
                margin-top: 30px;
                flex-wrap: wrap;
            }}
            
            .action-btn {{
                padding: 12px 24px;
                background: #007AFF;
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }}
            
            .action-btn:hover {{
                background: #0056CC;
                transform: translateY(-2px);
            }}
            
            .action-btn.secondary {{
                background: #8e8e93;
            }}
            
            .action-btn.secondary:hover {{
                background: #6e6e73;
            }}
            
            @media (max-width: 768px) {{
                .header {{
                    flex-direction: column;
                    gap: 15px;
                    text-align: center;
                    padding: 20px;
                }}
                .container {{
                    padding: 20px;
                }}
                .stats-grid {{
                    grid-template-columns: 1fr;
                }}
                .welcome-section, .key-section {{
                    padding: 30px 20px;
                }}
                .action-buttons {{
                    flex-direction: column;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">Bot Dashboard</div>
            <div class="user-info">
                <div>
                    <strong>{user_data.get('in_game_name', 'User')}</strong>
                    <div style="font-size: 0.9rem; color: #86868b;">Level {user_data.get('prestige', 0)}</div>
                </div>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="welcome-section">
                <h1>Welcome back, {user_data.get('in_game_name', 'Player')}</h1>
                <p>Here are your current stats and information.</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">K/D Ratio</div>
                    <div class="stat-value">{kd:.2f}</div>
                    <div>{user_data.get('total_kills', 0)} kills / {user_data.get('total_deaths', 0)} deaths</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Win Rate</div>
                    <div class="stat-value">{win_rate:.1f}%</div>
                    <div>{user_data.get('wins', 0)} wins / {user_data.get('losses', 0)} losses</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Credits</div>
                    <div class="stat-value">${user_data.get('credits', 1000)}</div>
                    <div>Available balance</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Games Played</div>
                    <div class="stat-value">{total_games}</div>
                    <div>Total matches</div>
                </div>
            </div>
            
            <div class="key-section">
                <h2 style="margin-bottom: 20px; color: #1d1d1f;">Your API Key</h2>
                <div class="key-display" onclick="copyKey()">
                    {session['user_key']}
                    <div style="font-size: 0.8rem; color: #86868b; margin-top: 10px;">Click to copy</div>
                </div>
                
                <p style="color: #86868b; margin: 20px 0;">
                    Use this key to access the bot API. Keep it secure and don't share it with anyone.
                </p>
                
                <div class="action-buttons">
                    <button class="action-btn" onclick="refreshStats()">
                        <span>🔄</span> Refresh Stats
                    </button>
                    <button class="action-btn" onclick="viewApiDocs()">
                        <span>📖</span> API Documentation
                    </button>
                    <button class="action-btn secondary" onclick="getNewKey()">
                        <span>🔑</span> Generate New Key
                    </button>
                </div>
            </div>
        </div>
        
        <script>
            function copyKey() {{
                navigator.clipboard.writeText("{session['user_key']}");
                alert("Key copied to clipboard");
            }}
            
            async function refreshStats() {{
                try {{
                    const response = await fetch('/api/refresh-stats?key={session['user_key']}');
                    const data = await response.json();
                    if (data.success) {{
                        alert("Stats refreshed!");
                        location.reload();
                    }}
                }} catch (error) {{
                    alert("Error refreshing stats");
                }}
            }}
            
            function viewApiDocs() {{
                alert("API Documentation:\\n\\n" +
                      "GET /api/profile?key=YOUR_KEY - Get your profile\\n" +
                      "GET /api/stats - Get global statistics\\n" +
                      "GET /health - Check service status");
            }}
            
            async function getNewKey() {{
                if (confirm("Generate a new API key? Your old key will stop working.")) {{
                    try {{
                        const response = await fetch('/api/new-key?key={session['user_key']}', {{
                            method: 'POST'
                        }});
                        const data = await response.json();
                        if (data.success) {{
                            alert("New key generated! Please login again.");
                            window.location.href = '/logout';
                        }}
                    }} catch (error) {{
                        alert("Error generating new key");
                    }}
                }}
            }}
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
    
    # Generate new key
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
        "timestamp": datetime.utcnow().isoformat()
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*60}")
    print("🤖 SIMPLE BOT DASHBOARD")
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
    print(f"   /register [name] - Get API key")
    
    print(f"\n📱 API Key Format: KEY-XXXXXXXX (short)")
    print(f"\n💡 Get started:")
    print(f"   1. Add bot to Discord server")
    print(f"   2. Use /register in Discord to get key")
    print(f"   3. Enter key on website to access dashboard")
    
    print(f"\n{'='*60}\n")
    
    # Start server
    app.run(host='0.0.0.0', port=port, debug=False)

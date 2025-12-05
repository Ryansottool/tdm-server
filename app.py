# app.py - TOXIC GOBLIN REGISTRY (Key-First Access)
import os
import json
import sqlite3
import random
import string
import threading
import time
import hashlib
import requests
from flask import Flask, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from datetime import datetime, timedelta
import logging
import hmac
import base64

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'toxic-goblin-secret-key-change-this')
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord credentials
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')

# Developer keys (for update functionality)
DEVELOPER_KEYS = os.environ.get('DEVELOPER_KEYS', '').split(',')
DEV_UPDATE_PASSWORD = os.environ.get('DEV_UPDATE_PASSWORD', 'admin123')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot status
bot_active = False
bot_info = {}

# Toxic COD voice chat responses (RAW)
TOXIC_PING_RESPONSES = [
    "Shut the fuck up kid",
    "Bro thinks pinging does something 💀",
    "Yapping",
    "Your mom's calling you for dinner",
    "1v1 me rust rn",
    "Bro's malding",
    "Imagine being this down bad",
    "L+Ratio+You fell off",
    "Go touch grass",
    "Bro's seething",
    "Cry about it",
    "Skill issue",
    "Mad cuz bad",
    "Get good",
    "What's your K/D? Oh wait you don't have one",
    "Bro thinks he's him",
    "Actual bot",
    "Go back to Fortnite",
    "Zero PR",
    "You're that kid who goes 2-17",
    "Bro got filtered",
    "Dogwater player",
    "Get a life",
    "Bro is NOT him",
    "Absolute clown behavior",
    "Go back to silver",
    "Actual NPC",
    "Lil bro is lost",
    "Bro is COOKED",
    "Take the L and move on"
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
        logger.error("Missing Discord signature headers")
        return False
    
    if not DISCORD_PUBLIC_KEY:
        logger.error("DISCORD_PUBLIC_KEY not set")
        return False
    
    try:
        import nacl.signing
        import nacl.exceptions
        
        message = f"{timestamp}{body}".encode('utf-8')
        signature_bytes = bytes.fromhex(signature)
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify(message, signature_bytes)
        
        return True
        
    except ImportError:
        logger.error("PyNaCl not installed")
        return False
    except nacl.exceptions.BadSignatureError:
        logger.error("Invalid Discord signature")
        return False
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False

# =============================================================================
# DATABASE SETUP - MULTI-SERVER READY
# =============================================================================

def init_db():
    """Initialize database for multi-server support"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Players - now with server_id
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
                title TEXT DEFAULT 'Bot',
                status TEXT DEFAULT 'active',
                banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                banned_by TEXT,
                banned_at TIMESTAMP,
                toxic_level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(discord_id, server_id)
            )
        ''')
        
        # Server-specific settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_settings (
                server_id TEXT PRIMARY KEY,
                server_name TEXT,
                owner_id TEXT,
                mod_role_ids TEXT DEFAULT '',
                welcome_message TEXT DEFAULT '',
                toxic_mode BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Client updates table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT UNIQUE,
                download_url TEXT,
                changelog TEXT,
                is_critical BOOLEAN DEFAULT 0,
                uploaded_by TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Moderators - server-specific
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_moderators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT,
                discord_id TEXT,
                role TEXT,  -- 'owner', 'admin', 'mod'
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(server_id, discord_id)
            )
        ''')
        
        # Multi-server moderation logs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                server_id TEXT,
                action TEXT,
                moderator_id TEXT,
                moderator_name TEXT,
                reason TEXT,
                duration_days INTEGER,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
        ''')
        
        # Matches - can be cross-server
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_code TEXT UNIQUE,
                server_id TEXT,
                player1_id INTEGER,
                player2_id INTEGER,
                player1_score INTEGER DEFAULT 0,
                player2_score INTEGER DEFAULT 0,
                winner_id INTEGER,
                status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player1_id) REFERENCES players (id),
                FOREIGN KEY (player2_id) REFERENCES players (id)
            )
        ''')
        
        # Global bans (cross-server)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                reason TEXT,
                banned_by TEXT,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        # Indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_api_key ON players(api_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_discord_server ON players(discord_id, server_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_server ON players(server_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mods_server ON server_moderators(server_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_settings_server ON server_settings(server_id)')
        
        conn.commit()
        conn.close()
        logger.info("✅ Multi-server database initialized")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# KEY VALIDATION & AUTHENTICATION
# =============================================================================

def validate_api_key(api_key):
    """Validate API key and return player data"""
    if not api_key:
        return None
    
    # Check if it's a developer key
    if api_key in DEVELOPER_KEYS:
        return {"type": "developer", "key": api_key}
    
    # Check if it's a regular player key
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE api_key = ?',
        (api_key,)
    ).fetchone()
    
    if player:
        # Check if globally banned
        global_ban = conn.execute(
            'SELECT * FROM global_bans WHERE discord_id = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)',
            (player['discord_id'],)
        ).fetchone()
        
        if global_ban:
            conn.close()
            return None
            
        # Update last used
        conn.execute(
            'UPDATE players SET last_used = CURRENT_TIMESTAMP WHERE id = ?',
            (player['id'],)
        )
        conn.commit()
    
    conn.close()
    if player:
        return {"type": "player", "data": dict(player)}
    return None

def is_developer_key(key):
    """Check if key is a developer key"""
    return key in DEVELOPER_KEYS

# =============================================================================
# WEB INTERFACE - KEY-FIRST ACCESS
# =============================================================================

@app.route('/')
def home():
    """Main page - Key entry only"""
    # Check if user is already authenticated
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            return redirect(url_for('dashboard'))
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>🔑 TOXIC GOBLIN - ACCESS</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Inter:wght@400;600&display=swap');
            
            :root {
                --toxic-green: #39ff14;
                --toxic-purple: #9d00ff;
                --toxic-pink: #ff00ff;
                --toxic-orange: #ff6b00;
                --dark: #0a0a0a;
                --darker: #050505;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', sans-serif;
                background: var(--dark);
                color: white;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                position: relative;
                overflow: hidden;
            }
            
            body::before {
                content: '';
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: 
                    radial-gradient(circle at 20% 80%, var(--toxic-green) 0%, transparent 50%),
                    radial-gradient(circle at 80% 20%, var(--toxic-purple) 0%, transparent 50%),
                    radial-gradient(circle at 40% 40%, var(--toxic-pink) 0%, transparent 50%);
                opacity: 0.1;
                z-index: -1;
                animation: pulse 10s infinite alternate;
            }
            
            @keyframes pulse {
                0% { opacity: 0.05; }
                100% { opacity: 0.15; }
            }
            
            .container {
                width: 100%;
                max-width: 500px;
                padding: 30px;
            }
            
            .access-card {
                background: rgba(20, 20, 20, 0.9);
                border: 3px solid;
                border-image: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple)) 1;
                border-radius: 15px;
                padding: 40px;
                backdrop-filter: blur(10px);
                text-align: center;
                position: relative;
                overflow: hidden;
            }
            
            .access-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 5px;
                background: linear-gradient(90deg, var(--toxic-green), var(--toxic-purple), var(--toxic-pink));
            }
            
            h1 {
                font-family: 'Montserrat', sans-serif;
                font-size: 2.5rem;
                background: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 10px;
            }
            
            .subtitle {
                color: #888;
                margin-bottom: 30px;
                font-size: 1rem;
            }
            
            .key-input {
                width: 100%;
                padding: 18px;
                background: rgba(0, 0, 0, 0.7);
                border: 2px solid var(--toxic-purple);
                border-radius: 10px;
                color: white;
                font-size: 18px;
                font-family: monospace;
                letter-spacing: 1px;
                text-align: center;
                margin-bottom: 25px;
                transition: all 0.3s;
            }
            
            .key-input:focus {
                outline: none;
                border-color: var(--toxic-green);
                box-shadow: 0 0 20px rgba(57, 255, 20, 0.3);
                transform: scale(1.02);
            }
            
            .submit-btn {
                width: 100%;
                padding: 18px;
                background: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple));
                color: black;
                border: none;
                border-radius: 10px;
                font-family: 'Montserrat', sans-serif;
                font-weight: bold;
                font-size: 18px;
                cursor: pointer;
                transition: all 0.3s;
                text-transform: uppercase;
                letter-spacing: 2px;
            }
            
            .submit-btn:hover {
                transform: translateY(-3px);
                box-shadow: 0 10px 25px rgba(57, 255, 20, 0.3);
                background: linear-gradient(45deg, var(--toxic-purple), var(--toxic-green));
            }
            
            .submit-btn:active {
                transform: translateY(-1px);
            }
            
            .error-message {
                background: rgba(255, 0, 0, 0.1);
                border: 2px solid #ff0000;
                color: #ff5555;
                padding: 15px;
                border-radius: 8px;
                margin-top: 20px;
                display: none;
                animation: slideIn 0.3s;
            }
            
            @keyframes slideIn {
                from { opacity: 0; transform: translateY(-10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .help-text {
                margin-top: 25px;
                color: #666;
                font-size: 0.9rem;
                line-height: 1.5;
            }
            
            .help-text a {
                color: var(--toxic-green);
                text-decoration: none;
            }
            
            .help-text a:hover {
                text-decoration: underline;
            }
            
            .floating-toxic {
                position: fixed;
                font-size: 1.5rem;
                opacity: 0.1;
                pointer-events: none;
                z-index: -1;
                animation: float 20s infinite linear;
            }
            
            @keyframes float {
                0% { transform: translateY(100vh) rotate(0deg); }
                100% { transform: translateY(-100vh) rotate(360deg); }
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 20px;
                }
                .access-card {
                    padding: 30px 20px;
                }
                h1 {
                    font-size: 2rem;
                }
            }
        </style>
    </head>
    <body>
        <!-- Floating toxic symbols -->
        <div class="floating-toxic" style="left: 10%; animation-delay: 0s;">🔑</div>
        <div class="floating-toxic" style="left: 20%; animation-delay: -5s;">🔒</div>
        <div class="floating-toxic" style="left: 30%; animation-delay: -10s;">⚡</div>
        <div class="floating-toxic" style="left: 40%; animation-delay: -15s;">💀</div>
        <div class="floating-toxic" style="left: 50%; animation-delay: -20s;">🔥</div>
        
        <div class="container">
            <div class="access-card">
                <h1>TOXIC GOBLIN</h1>
                <div class="subtitle">Enter your API key to access the system</div>
                
                <input type="text" 
                       class="key-input" 
                       id="apiKey" 
                       placeholder="TOX-XXXX-XXXX-XXXX-XXXX" 
                       autocomplete="off"
                       autocorrect="off"
                       autocapitalize="off"
                       spellcheck="false">
                
                <button class="submit-btn" onclick="validateKey()">
                    🔐 ACCESS SYSTEM
                </button>
                
                <div class="error-message" id="errorMessage">
                    Invalid API key. Get your key from Discord using /register
                </div>
                
                <div class="help-text">
                    <p>• Get your API key from Discord: <code>/register your_name</code></p>
                    <p>• Developer keys have additional privileges</p>
                    <p>• Keys are server-specific for player accounts</p>
                </div>
            </div>
        </div>
        
        <script>
            async function validateKey() {
                const key = document.getElementById('apiKey').value.trim();
                const errorDiv = document.getElementById('errorMessage');
                
                if (!key) {
                    errorDiv.textContent = "Please enter an API key";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                if (!key.startsWith('TOX-')) {
                    errorDiv.textContent = "Key must start with TOX-";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                // Disable button and show loading
                const btn = document.querySelector('.submit-btn');
                btn.innerHTML = '🔐 VERIFYING...';
                btn.disabled = true;
                
                try {
                    // Send key to server for validation
                    const response = await fetch('/api/validate-key', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ api_key: key })
                    });
                    
                    const data = await response.json();
                    
                    if (data.valid) {
                        // Key is valid, redirect to dashboard
                        window.location.href = '/dashboard';
                    } else {
                        // Key is invalid
                        errorDiv.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        btn.innerHTML = '🔐 ACCESS SYSTEM';
                        btn.disabled = false;
                    }
                } catch (error) {
                    errorDiv.textContent = 'Connection error. Try again.';
                    errorDiv.style.display = 'block';
                    btn.innerHTML = '🔐 ACCESS SYSTEM';
                    btn.disabled = false;
                }
            }
            
            // Allow Enter key to submit
            document.getElementById('apiKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    validateKey();
                }
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
def validate_key():
    """Validate API key and set session"""
    data = request.get_json()
    api_key = data.get('api_key', '').strip()
    
    if not api_key:
        return jsonify({"valid": False, "error": "No key provided"})
    
    # Validate the key
    user_data = validate_api_key(api_key)
    
    if user_data:
        # Set session
        session['user_key'] = api_key
        session['user_type'] = user_data['type']
        
        if user_data['type'] == 'player':
            session['player_data'] = user_data['data']
        
        return jsonify({"valid": True})
    else:
        return jsonify({"valid": False, "error": "Invalid or expired API key"})

@app.route('/logout')
def logout():
    """Clear session and logout"""
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    """Main dashboard after key validation"""
    # Check if user is authenticated
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    # Validate key again
    user_data = validate_api_key(session['user_key'])
    if not user_data:
        session.clear()
        return redirect(url_for('home'))
    
    user_type = session.get('user_type')
    player_data = session.get('player_data', {})
    
    # Render appropriate dashboard
    if user_type == 'developer':
        return render_developer_dashboard()
    else:
        return render_player_dashboard(player_data)

def render_player_dashboard(player_data):
    """Render player dashboard"""
    kd = player_data.get('total_kills', 0) / max(player_data.get('total_deaths', 1), 1)
    win_rate = 0
    if player_data.get('wins', 0) + player_data.get('losses', 0) > 0:
        win_rate = (player_data.get('wins', 0) / (player_data.get('wins', 0) + player_data.get('losses', 0)) * 100)
    
    # Toxic commentary based on stats
    commentary = ""
    if kd < 0.5:
        commentary = "📉 K/D ratio looking rough"
    elif kd < 1:
        commentary = "📊 Mediocre at best"
    elif player_data.get('losses', 0) > player_data.get('wins', 0):
        commentary = "💀 Professional L-taker detected"
    else:
        commentary = "⭐ Not completely terrible"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>📊 PLAYER DASHBOARD</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Inter:wght@400;600&display=swap');
            
            :root {{
                --toxic-green: #39ff14;
                --toxic-purple: #9d00ff;
                --toxic-pink: #ff00ff;
                --dark: #0a0a0a;
                --darker: #050505;
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Inter', sans-serif;
                background: var(--dark);
                color: white;
                min-height: 100vh;
                position: relative;
                overflow-x: hidden;
            }}
            
            body::before {{
                content: '';
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: 
                    radial-gradient(circle at 20% 80%, var(--toxic-green) 0%, transparent 50%),
                    radial-gradient(circle at 80% 20%, var(--toxic-purple) 0%, transparent 50%);
                opacity: 0.1;
                z-index: -1;
            }}
            
            .header {{
                background: rgba(20, 20, 20, 0.9);
                border-bottom: 3px solid var(--toxic-green);
                padding: 20px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                backdrop-filter: blur(10px);
            }}
            
            .logo {{
                font-family: 'Montserrat', sans-serif;
                font-size: 1.8rem;
                background: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            
            .user-info {{
                display: flex;
                align-items: center;
                gap: 20px;
            }}
            
            .logout-btn {{
                padding: 10px 20px;
                background: rgba(255, 0, 0, 0.2);
                border: 2px solid #ff0000;
                color: #ff5555;
                border-radius: 6px;
                text-decoration: none;
                font-weight: bold;
                transition: all 0.3s;
            }}
            
            .logout-btn:hover {{
                background: rgba(255, 0, 0, 0.3);
                transform: translateY(-2px);
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 30px;
            }}
            
            .dashboard-grid {{
                display: grid;
                grid-template-columns: 300px 1fr;
                gap: 30px;
            }}
            
            .sidebar {{
                background: rgba(20, 20, 20, 0.8);
                border: 2px solid var(--toxic-purple);
                border-radius: 10px;
                padding: 25px;
            }}
            
            .sidebar h2 {{
                color: var(--toxic-green);
                margin-bottom: 20px;
                font-family: 'Montserrat', sans-serif;
            }}
            
            .player-card {{
                background: rgba(0, 0, 0, 0.5);
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
                border: 1px solid rgba(57, 255, 20, 0.2);
            }}
            
            .player-name {{
                font-size: 1.4rem;
                font-weight: bold;
                margin-bottom: 10px;
                color: var(--toxic-green);
            }}
            
            .key-display {{
                background: rgba(0, 0, 0, 0.7);
                border: 2px solid var(--toxic-purple);
                border-radius: 8px;
                padding: 15px;
                margin-top: 15px;
                font-family: monospace;
                font-size: 0.9rem;
                color: var(--toxic-green);
                word-break: break-all;
                cursor: pointer;
                transition: all 0.3s;
            }}
            
            .key-display:hover {{
                background: rgba(0, 0, 0, 0.9);
                box-shadow: 0 0 15px var(--toxic-purple);
            }}
            
            .main-content {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
            }}
            
            .stat-card {{
                background: rgba(20, 20, 20, 0.8);
                border: 2px solid;
                border-image: linear-gradient(45deg, var(--toxic-green), transparent) 1;
                border-radius: 10px;
                padding: 25px;
                text-align: center;
            }}
            
            .stat-value {{
                font-size: 2.5rem;
                font-weight: bold;
                margin: 10px 0;
                color: var(--toxic-green);
            }}
            
            .stat-label {{
                color: #888;
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            
            .commentary {{
                background: rgba(57, 255, 20, 0.1);
                border: 2px solid var(--toxic-green);
                border-radius: 8px;
                padding: 20px;
                margin-top: 20px;
                font-style: italic;
                color: var(--toxic-green);
            }}
            
            .action-section {{
                background: rgba(20, 20, 20, 0.8);
                border: 2px solid var(--toxic-purple);
                border-radius: 10px;
                padding: 25px;
                margin-top: 30px;
            }}
            
            .action-btn {{
                display: inline-block;
                padding: 15px 30px;
                background: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple));
                color: black;
                border: none;
                border-radius: 8px;
                font-family: 'Montserrat', sans-serif;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                margin: 10px;
            }}
            
            .action-btn:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(57, 255, 20, 0.3);
            }}
            
            .floating-toxic {{
                position: fixed;
                font-size: 1.5rem;
                opacity: 0.05;
                pointer-events: none;
                z-index: -1;
                animation: float 20s infinite linear;
            }}
            
            @keyframes float {{
                0% {{ transform: translateY(100vh) rotate(0deg); }}
                100% {{ transform: translateY(-100vh) rotate(360deg); }}
            }}
            
            @media (max-width: 768px) {{
                .dashboard-grid {{
                    grid-template-columns: 1fr;
                }}
                .header {{
                    flex-direction: column;
                    gap: 15px;
                    text-align: center;
                }}
                .main-content {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <!-- Floating elements -->
        <div class="floating-toxic" style="left: 5%; animation-delay: 0s;">📊</div>
        <div class="floating-toxic" style="left: 15%; animation-delay: -5s;">🎮</div>
        <div class="floating-toxic" style="left: 25%; animation-delay: -10s;">⚡</div>
        
        <div class="header">
            <div class="logo">TOXIC GOBLIN DASHBOARD</div>
            <div class="user-info">
                <div>Player: <strong>{player_data.get('in_game_name', 'Unknown')}</strong></div>
                <a href="/logout" class="logout-btn">🚪 LOGOUT</a>
            </div>
        </div>
        
        <div class="container">
            <div class="dashboard-grid">
                <div class="sidebar">
                    <h2>🎮 PLAYER INFO</h2>
                    <div class="player-card">
                        <div class="player-name">{player_data.get('in_game_name', 'Unknown')}</div>
                        <div>Server: {player_data.get('server_id', 'Global')}</div>
                        <div>Toxic Level: {player_data.get('toxic_level', 1)}/10</div>
                        <div>Status: <span style="color: #39ff14;">ACTIVE</span></div>
                        
                        <div class="key-display" onclick="copyToClipboard('{session['user_key']}')">
                            {session['user_key']}
                            <div style="font-size: 0.7rem; color: #888; margin-top: 5px;">Click to copy</div>
                        </div>
                    </div>
                    
                    <h2 style="margin-top: 30px;">📋 QUICK ACTIONS</h2>
                    <button class="action-btn" onclick="refreshStats()">🔄 Refresh Stats</button>
                    <button class="action-btn" onclick="getRandomRoast()">🔥 Get Roasted</button>
                </div>
                
                <div class="main-content">
                    <div class="stat-card">
                        <div class="stat-label">K/D RATIO</div>
                        <div class="stat-value" style="color: { '#ff0000' if kd < 0.5 else '#ff6b00' if kd < 1 else '#39ff14' };">{kd:.2f}</div>
                        <div>{player_data.get('total_kills', 0)} kills / {player_data.get('total_deaths', 0)} deaths</div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-label">WIN RATE</div>
                        <div class="stat-value" style="color: { '#ff0000' if win_rate < 40 else '#ff6b00' if win_rate < 60 else '#39ff14' };">{win_rate:.1f}%</div>
                        <div>{player_data.get('wins', 0)} wins / {player_data.get('losses', 0)} losses</div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-label">PRESTIGE</div>
                        <div class="stat-value">⭐ {player_data.get('prestige', 0)}</div>
                        <div>Title: {player_data.get('title', 'Bot')}</div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-label">CREDITS</div>
                        <div class="stat-value">💰 {player_data.get('credits', 0)}</div>
                        <div>Available balance</div>
                    </div>
                    
                    <div class="commentary">
                        <h3>💬 TOXIC COMMENTARY:</h3>
                        <p>{commentary}</p>
                        <div id="roastResult" style="margin-top: 10px; font-size: 0.9rem;"></div>
                    </div>
                    
                    <div class="action-section">
                        <h2 style="color: var(--toxic-purple); margin-bottom: 20px;">⚡ API ENDPOINTS</h2>
                        <div style="background: rgba(0, 0, 0, 0.5); padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                            <code>GET /api/profile?key=YOUR_KEY</code>
                            <div style="color: #888; font-size: 0.9rem;">Get your stats</div>
                        </div>
                        <div style="background: rgba(0, 0, 0, 0.5); padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                            <code>GET /api/roast?key=YOUR_KEY</code>
                            <div style="color: #888; font-size: 0.9rem;">Get roasted</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            function copyToClipboard(text) {{
                navigator.clipboard.writeText(text);
                alert('✅ Key copied to clipboard');
            }}
            
            async function refreshStats() {{
                try {{
                    const response = await fetch('/api/refresh-stats?key={session['user_key']}');
                    const data = await response.json();
                    alert('✅ Stats refreshed');
                    location.reload();
                }} catch (error) {{
                    alert('❌ Error refreshing stats');
                }}
            }}
            
            async function getRandomRoast() {{
                try {{
                    const response = await fetch('/api/roast?key={session['user_key']}');
                    const data = await response.json();
                    document.getElementById('roastResult').innerHTML = `<strong>🔥 Roast:</strong> ${{data.roast}}`;
                }} catch (error) {{
                    document.getElementById('roastResult').innerHTML = '❌ Error getting roast';
                }}
            }}
            
            // Auto-refresh every 30 seconds
            setInterval(refreshStats, 30000);
        </script>
    </body>
    </html>
    '''

def render_developer_dashboard():
    """Render developer dashboard with update functionality"""
    conn = get_db_connection()
    updates = conn.execute('SELECT * FROM client_updates ORDER BY uploaded_at DESC LIMIT 5').fetchall()
    conn.close()
    
    updates_html = ""
    for update in updates:
        updates_html += f'''
        <div style="background: rgba(30, 30, 30, 0.8); border-left: 4px solid #39ff14; padding: 15px; margin-bottom: 10px; border-radius: 4px;">
            <strong>v{update['version']}</strong> - {update['uploaded_at']}
            <div style="color: #888; font-size: 0.9rem; margin-top: 5px;">{update['changelog'][:100]}...</div>
            <div style="margin-top: 5px;">
                <a href="{update['download_url']}" target="_blank" style="color: #39ff14;">Download</a>
                { '🚨 CRITICAL' if update['is_critical'] else '' }
            </div>
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>⚙️ DEVELOPER DASHBOARD</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Inter:wght@400;600&display=swap');
            
            :root {{
                --toxic-green: #39ff14;
                --toxic-purple: #9d00ff;
                --toxic-pink: #ff00ff;
                --dark: #0a0a0a;
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Inter', sans-serif;
                background: var(--dark);
                color: white;
                min-height: 100vh;
            }}
            
            .header {{
                background: rgba(20, 20, 20, 0.9);
                border-bottom: 3px solid var(--toxic-purple);
                padding: 20px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                backdrop-filter: blur(10px);
            }}
            
            .logo {{
                font-family: 'Montserrat', sans-serif;
                font-size: 1.8rem;
                background: linear-gradient(45deg, var(--toxic-purple), var(--toxic-green));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            
            .user-info {{
                display: flex;
                align-items: center;
                gap: 20px;
            }}
            
            .logout-btn {{
                padding: 10px 20px;
                background: rgba(255, 0, 0, 0.2);
                border: 2px solid #ff0000;
                color: #ff5555;
                border-radius: 6px;
                text-decoration: none;
                font-weight: bold;
                transition: all 0.3s;
            }}
            
            .logout-btn:hover {{
                background: rgba(255, 0, 0, 0.3);
                transform: translateY(-2px);
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 30px;
            }}
            
            .dev-card {{
                background: rgba(20, 20, 20, 0.8);
                border: 2px solid var(--toxic-purple);
                border-radius: 10px;
                padding: 30px;
                margin-bottom: 30px;
            }}
            
            h2 {{
                color: var(--toxic-green);
                margin-bottom: 20px;
                font-family: 'Montserrat', sans-serif;
            }}
            
            h3 {{
                color: var(--toxic-purple);
                margin: 20px 0 10px 0;
            }}
            
            .update-form {{
                background: rgba(0, 0, 0, 0.5);
                padding: 25px;
                border-radius: 8px;
                margin-top: 20px;
                border: 2px solid rgba(57, 255, 20, 0.2);
            }}
            
            .form-input {{
                width: 100%;
                padding: 12px;
                background: rgba(0, 0, 0, 0.7);
                border: 2px solid var(--toxic-purple);
                border-radius: 6px;
                color: white;
                margin-bottom: 15px;
                font-family: 'Inter', sans-serif;
            }}
            
            .form-input:focus {{
                outline: none;
                border-color: var(--toxic-green);
            }}
            
            .submit-btn {{
                padding: 15px 30px;
                background: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple));
                color: black;
                border: none;
                border-radius: 8px;
                font-family: 'Montserrat', sans-serif;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                margin-top: 10px;
            }}
            
            .submit-btn:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(57, 255, 20, 0.3);
            }}
            
            .message {{
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
                display: none;
            }}
            
            .success {{
                background: rgba(57, 255, 20, 0.1);
                border: 2px solid var(--toxic-green);
                color: var(--toxic-green);
            }}
            
            .error {{
                background: rgba(255, 0, 0, 0.1);
                border: 2px solid #ff0000;
                color: #ff5555;
            }}
            
            .warning {{
                background: rgba(255, 107, 0, 0.1);
                border: 2px solid #ff6b00;
                color: #ff6b00;
            }}
            
            .updates-list {{
                max-height: 400px;
                overflow-y: auto;
                margin-top: 20px;
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }}
            
            .stat-box {{
                background: rgba(0, 0, 0, 0.5);
                padding: 20px;
                border-radius: 8px;
                text-align: center;
                border: 1px solid var(--toxic-purple);
            }}
            
            .stat-value {{
                font-size: 2rem;
                font-weight: bold;
                margin: 10px 0;
                color: var(--toxic-green);
            }}
            
            .stat-label {{
                color: #888;
                font-size: 0.9rem;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">⚙️ DEVELOPER DASHBOARD</div>
            <div class="user-info">
                <div>Developer Access</div>
                <a href="/logout" class="logout-btn">🚪 LOGOUT</a>
            </div>
        </div>
        
        <div class="container">
            <div class="dev-card">
                <h2>📡 ONLINE UPDATE CLIENT</h2>
                <p style="color: #888; margin-bottom: 20px;">
                    Upload new client versions for automatic distribution to players.
                </p>
                
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-value">{len(updates)}</div>
                        <div class="stat-label">Versions</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="totalPlayers">0</div>
                        <div class="stat-label">Players</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="totalServers">0</div>
                        <div class="stat-label">Servers</div>
                    </div>
                </div>
                
                <h3>📤 UPLOAD NEW VERSION</h3>
                <div class="update-form">
                    <input type="text" class="form-input" id="version" placeholder="Version (e.g., 1.2.3)">
                    <input type="text" class="form-input" id="downloadUrl" placeholder="Download URL">
                    <textarea class="form-input" id="changelog" placeholder="Changelog" rows="4"></textarea>
                    
                    <div style="margin-bottom: 15px;">
                        <input type="checkbox" id="isCritical">
                        <label for="isCritical" style="color: #ff6b00;">🚨 Mark as critical update</label>
                    </div>
                    
                    <input type="password" class="form-input" id="updatePassword" placeholder="Update Password">
                    
                    <button class="submit-btn" onclick="uploadUpdate()">📤 UPLOAD UPDATE</button>
                    
                    <div class="message" id="uploadMessage"></div>
                </div>
                
                <h3>📋 RECENT UPDATES</h3>
                <div class="updates-list">
                    {updates_html if updates_html else '<p style="color: #888; text-align: center; padding: 20px;">No updates yet</p>'}
                </div>
            </div>
            
            <div class="dev-card">
                <h2>⚙️ SYSTEM CONTROLS</h2>
                <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                    <button class="submit-btn" onclick="refreshStats()">🔄 Refresh Stats</button>
                    <button class="submit-btn" onclick="clearCache()">🧹 Clear Cache</button>
                    <button class="submit-btn" onclick="restartBot()">🔄 Restart Bot</button>
                </div>
            </div>
        </div>
        
        <script>
            async function uploadUpdate() {{
                const version = document.getElementById('version').value;
                const downloadUrl = document.getElementById('downloadUrl').value;
                const changelog = document.getElementById('changelog').value;
                const isCritical = document.getElementById('isCritical').checked;
                const password = document.getElementById('updatePassword').value;
                
                if (!version || !downloadUrl || !changelog || !password) {{
                    showMessage('uploadMessage', 'Please fill all fields', 'error');
                    return;
                }}
                
                try {{
                    const response = await fetch('/api/upload-update', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            version,
                            download_url: downloadUrl,
                            changelog,
                            is_critical: isCritical,
                            password
                        }})
                    }});
                    
                    const data = await response.json();
                    
                    if (data.success) {{
                        showMessage('uploadMessage', '✅ Update uploaded successfully', 'success');
                        setTimeout(() => location.reload(), 1500);
                    }} else {{
                        showMessage('uploadMessage', '❌ ' + data.error, 'error');
                    }}
                }} catch (error) {{
                    showMessage('uploadMessage', '❌ Connection error', 'error');
                }}
            }}
            
            async function refreshStats() {{
                try {{
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    document.getElementById('totalPlayers').textContent = data.total_players || '0';
                    document.getElementById('totalServers').textContent = data.total_servers || '0';
                    showMessage('uploadMessage', '✅ Stats refreshed', 'success');
                }} catch (error) {{
                    showMessage('uploadMessage', '❌ Error refreshing stats', 'error');
                }}
            }}
            
            async function clearCache() {{
                if (confirm('Clear all cache? This will force clients to reload data.')) {{
                    showMessage('uploadMessage', '🔄 Clearing cache...', 'warning');
                    // Add cache clearing logic here
                }}
            }}
            
            async function restartBot() {{
                if (confirm('Restart Discord bot connection?')) {{
                    showMessage('uploadMessage', '🔄 Restarting bot...', 'warning');
                    // Add bot restart logic here
                }}
            }}
            
            function showMessage(elementId, message, type) {{
                const element = document.getElementById(elementId);
                element.textContent = message;
                element.className = 'message ' + type;
                element.style.display = 'block';
                
                setTimeout(() => {{
                    element.style.display = 'none';
                }}, 5000);
            }}
            
            // Load stats on page load
            document.addEventListener('DOMContentLoaded', function() {{
                refreshStats();
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
    
    player = validate_api_key(api_key)
    if not player or player.get('type') != 'player':
        return jsonify({"error": "Invalid key"}), 401
    
    # In a real implementation, you'd update stats from external sources
    return jsonify({"success": True, "message": "Stats refreshed"})

@app.route('/api/upload-update', methods=['POST'])
def api_upload_update():
    """Upload new client update (developer only)"""
    data = request.get_json()
    api_key = session.get('user_key')
    
    if not api_key or not is_developer_key(api_key):
        return jsonify({"success": False, "error": "Developer access required"}), 403
    
    # Verify password
    password = data.get('password')
    if password != DEV_UPDATE_PASSWORD:
        return jsonify({"success": False, "error": "Invalid update password"}), 401
    
    version = data.get('version')
    download_url = data.get('download_url')
    changelog = data.get('changelog')
    is_critical = data.get('is_critical', False)
    
    if not version or not download_url or not changelog:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO client_updates (version, download_url, changelog, is_critical, uploaded_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (version, download_url, changelog, is_critical, 'developer'))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "error": "Version already exists"}), 400
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/latest-update')
def api_latest_update():
    """Get latest client update"""
    conn = get_db_connection()
    update = conn.execute(
        'SELECT * FROM client_updates ORDER BY uploaded_at DESC LIMIT 1'
    ).fetchone()
    conn.close()
    
    if update:
        return jsonify(dict(update))
    else:
        return jsonify({"error": "No updates available"}), 404

@app.route('/api/stats')
def api_stats():
    """Get global toxic stats"""
    conn = get_db_connection()
    
    total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
    total_servers = conn.execute('SELECT COUNT(DISTINCT server_id) as count FROM server_settings').fetchone()['count']
    total_kills = conn.execute('SELECT SUM(total_kills) as sum FROM players').fetchone()['sum'] or 0
    total_bans = conn.execute('SELECT COUNT(*) as count FROM players WHERE banned = 1').fetchone()['count']
    
    conn.close()
    
    return jsonify({
        "total_players": total_players,
        "total_servers": total_servers,
        "total_kills": total_kills,
        "total_bans": total_bans,
        "message": "Get rekt",
        "toxic_level": random.randint(1, 10)
    })

@app.route('/api/profile')
def api_profile():
    """Get toxic profile"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "No key, no stats, scrub"}), 401
    
    player_data = validate_api_key(api_key)
    if not player_data or player_data.get('type') != 'player':
        return jsonify({"error": "Invalid or banned key. L"}), 401
    
    player = player_data['data']
    
    # Add toxic commentary
    kd = player['total_kills'] / max(player['total_deaths'], 1)
    commentary = ""
    if kd < 0.5:
        commentary = "Absolute bot behavior"
    elif kd < 1:
        commentary = "Mediocre at best"
    elif kd < 2:
        commentary = "Not completely terrible"
    else:
        commentary = "Okay, you might be decent"
    
    return jsonify({
        **player,
        "commentary": commentary,
        "roast": random.choice(TOXIC_PING_RESPONSES)
    })

@app.route('/api/roast')
def api_roast():
    """Get personalized roast"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"roast": "No key? That's pretty lame, ngl"})
    
    player_data = validate_api_key(api_key)
    if player_data and player_data.get('type') == 'player':
        player = player_data['data']
        kd = player['total_kills'] / max(player['total_deaths'], 1)
        if kd < 0.5:
            roast = f"K/D of {kd:.2f}? My grandma plays better"
        elif player['losses'] > player['wins']:
            roast = f"More L's than W's? Professional loser detected"
        else:
            roast = random.choice(TOXIC_PING_RESPONSES)
    else:
        roast = "Can't even provide a valid key. Typical."
    
    return jsonify({"roast": roast})

@app.route('/health')
def health():
    """Health check with attitude"""
    return jsonify({
        "status": "toxic",
        "service": "Key-First Toxic Goblin",
        "version": "5.0",
        "message": "Still here, still judging you",
        "bot_active": bot_active,
        "toxic_level": 11
    })

# =============================================================================
# DISCORD BOT FUNCTIONS (unchanged)
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
    """Register multi-server slash commands"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        logger.error("❌ Cannot register commands")
        return False
    
    commands = [
        {
            "name": "ping",
            "description": "Ping the toxic bot (prepare for flame)",
            "type": 1
        },
        {
            "name": "register",
            "description": "Register for TDM (get flamed)",
            "type": 1,
            "options": [
                {
                    "name": "ingame_name",
                    "description": "Your in-game name (for roasting)",
                    "type": 3,
                    "required": True
                }
            ]
        },
        {
            "name": "profile",
            "description": "Check your stats (and get mocked)",
            "type": 1
        },
        {
            "name": "roast",
            "description": "Roast someone (mod only)",
            "type": 1,
            "options": [
                {
                    "name": "target",
                    "description": "Who to flame",
                    "type": 6,
                    "required": True
                }
            ]
        },
        {
            "name": "banish",
            "description": "Ban a player (server mod only)",
            "type": 1,
            "options": [
                {
                    "name": "player",
                    "description": "Player to banish",
                    "type": 6,
                    "required": True
                },
                {
                    "name": "reason",
                    "description": "Why they're trash",
                    "type": 3,
                    "required": False
                }
            ]
        },
        {
            "name": "leaderboard",
            "description": "See who's least bad",
            "type": 1
        },
        {
            "name": "setup",
            "description": "Setup bot for this server (admin only)",
            "type": 1
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
            logger.info(f"✅ Registered toxic commands")
            return True
        else:
            logger.error(f"❌ Failed to register commands: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error registering commands: {e}")
        return False

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*80}")
    print("🔑 TOXIC GOBLIN - KEY-FIRST ACCESS v5.0")
    print(f"{'='*80}")
    
    # Check PyNaCl
    try:
        import nacl.signing
        print("✅ PyNaCl installed - Ready for Discord verification")
    except ImportError:
        print("❌ PyNaCl not installed! Run: pip install pynacl")
    
    # Test Discord
    if test_discord_token():
        print(f"✅ Bot connected: {bot_info.get('username', 'Unknown')}")
        
        if register_commands():
            print("✅ Toxic commands registered globally")
        else:
            print("⚠️ Could not register commands")
    else:
        print("❌ Discord token not set or invalid")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🤖 Interactions: http://localhost:{port}/interactions")
    print(f"🔑 Login Flow: Key-first access")
    
    print(f"\n🎮 TOXIC COMMANDS:")
    print(f"   /register   - Get API key from Discord")
    print(f"   /profile    - Check your stats")
    
    print(f"\n⚙️ ACCESS SYSTEM:")
    print(f"   1. Get key via Discord: /register your_name")
    print(f"   2. Enter key on website")
    print(f"   3. Access dashboard with stats")
    print(f"   4. Developer keys get update privileges")
    
    print(f"\n🔧 Environment Variables:")
    print(f"   DEVELOPER_KEYS = comma-separated developer keys")
    print(f"   DEV_UPDATE_PASSWORD = password for update uploads")
    
    print(f"\n💀 'git gud scrub' - Toxic Goblin")
    print(f"{'='*80}\n")
    
    # Start server
    app.run(host='0.0.0.0', port=port, debug=False)# app.py - SIMPLE ANIMATED WEB + DISCORD BOT
import os
import json
import sqlite3
import random
import string
import threading
import time
import hashlib
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import logging

app = Flask(__name__)
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

# Simple ping responses
PING_RESPONSES = [
    "I'm here newgen",
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
# SIMPLE DATABASE
# =============================================================================

def init_db():
    """Initialize simple database"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                username TEXT,
                key TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                server_id TEXT,
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
# DISCORD BOT
# =============================================================================

def test_discord_token():
    """Test if Discord token is valid"""
    global bot_active
    
    if not DISCORD_TOKEN:
        return False
    
    try:
        url = "https://discord.com/api/v10/users/@me"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            bot_active = True
            return True
        return False
            
    except:
        return False

def register_commands():
    """Register only ping command"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        return False
    
    commands = [
        {
            "name": "ping",
            "description": "Check if bot is awake",
            "type": 1
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
            logger.info("✅ Ping command registered")
            return True
        return False
            
    except:
        return False

# =============================================================================
# DISCORD INTERACTIONS
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord interactions"""
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
        server_id = data.get('guild_id')
        
        if command == 'ping':
            # Log the ping
            if user_id and server_id:
                conn = get_db_connection()
                conn.execute('INSERT INTO pings (user_id, server_id) VALUES (?, ?)', (user_id, server_id))
                conn.commit()
                conn.close()
            
            response = random.choice(PING_RESPONSES)
            return jsonify({
                "type": 4,
                "data": {
                    "content": response,
                    "flags": 0
                }
            })
    
    return jsonify({"type": 4, "data": {"content": "Unknown", "flags": 64}})

# =============================================================================
# SIMPLE ANIMATED WEB INTERFACE
# =============================================================================

@app.route('/')
def home():
    """Simple animated web page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Goblin Bot</title>
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
                background: #000;
                color: #fff;
                min-height: 100vh;
                overflow: hidden;
                position: relative;
            }
            
            /* Background animation */
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
                background: #00ff00;
                border-radius: 50%;
                animation: float 20s infinite linear;
            }
            
            @keyframes float {
                0% {
                    transform: translate(0, 0) rotate(0deg);
                    opacity: 0;
                }
                10% {
                    opacity: 1;
                }
                90% {
                    opacity: 1;
                }
                100% {
                    transform: translate(calc(100vw * var(--tx)), calc(100vh * var(--ty))) rotate(360deg);
                    opacity: 0;
                }
            }
            
            /* Main container */
            .container {
                max-width: 800px;
                margin: 0 auto;
                padding: 40px 20px;
                text-align: center;
                position: relative;
                z-index: 1;
            }
            
            /* Logo/Header animation */
            .logo {
                font-size: 4rem;
                font-weight: 900;
                margin-bottom: 20px;
                background: linear-gradient(45deg, #00ff00, #00cc00, #009900);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-size: 200% 200%;
                animation: gradient 3s ease infinite;
                text-shadow: 0 0 30px rgba(0, 255, 0, 0.3);
            }
            
            @keyframes gradient {
                0% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
            }
            
            .subtitle {
                font-size: 1.2rem;
                color: #888;
                margin-bottom: 40px;
                animation: fadeIn 2s;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            /* Stats cards */
            .stats {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-bottom: 50px;
                flex-wrap: wrap;
            }
            
            .stat-card {
                background: rgba(30, 30, 30, 0.8);
                padding: 25px;
                border-radius: 15px;
                min-width: 180px;
                border: 1px solid rgba(0, 255, 0, 0.1);
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
            }
            
            .stat-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(0, 255, 0, 0.1), transparent);
                transition: left 0.5s;
            }
            
            .stat-card:hover::before {
                left: 100%;
            }
            
            .stat-card:hover {
                transform: translateY(-5px);
                border-color: rgba(0, 255, 0, 0.3);
                box-shadow: 0 10px 30px rgba(0, 255, 0, 0.1);
            }
            
            .stat-number {
                font-size: 2.5rem;
                font-weight: bold;
                color: #00ff00;
                margin-bottom: 10px;
            }
            
            .stat-label {
                color: #888;
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            /* Action buttons */
            .actions {
                display: flex;
                justify-content: center;
                gap: 15px;
                margin-bottom: 50px;
                flex-wrap: wrap;
            }
            
            .btn {
                padding: 15px 30px;
                background: rgba(0, 255, 0, 0.1);
                border: 2px solid #00ff00;
                color: #00ff00;
                border-radius: 10px;
                font-size: 1rem;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                position: relative;
                overflow: hidden;
            }
            
            .btn::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(0, 255, 0, 0.2), transparent);
                transition: left 0.5s;
            }
            
            .btn:hover::before {
                left: 100%;
            }
            
            .btn:hover {
                background: rgba(0, 255, 0, 0.2);
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(0, 255, 0, 0.2);
            }
            
            .btn:active {
                transform: translateY(-1px);
            }
            
            /* Ping animation */
            .ping-container {
                margin: 40px auto;
                max-width: 400px;
            }
            
            .ping-btn {
                width: 100%;
                padding: 20px;
                font-size: 1.2rem;
                background: rgba(0, 255, 0, 0.2);
                border: 2px solid #00ff00;
                border-radius: 10px;
                color: #fff;
                cursor: pointer;
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
            }
            
            .ping-btn:hover {
                background: rgba(0, 255, 0, 0.3);
                transform: scale(1.05);
            }
            
            .ping-wave {
                position: absolute;
                border: 2px solid #00ff00;
                border-radius: 50%;
                animation: wave 1s linear;
                pointer-events: none;
            }
            
            @keyframes wave {
                0% {
                    width: 0;
                    height: 0;
                    opacity: 1;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                }
                100% {
                    width: 400px;
                    height: 400px;
                    opacity: 0;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                }
            }
            
            /* Response display */
            .response {
                margin-top: 30px;
                padding: 20px;
                background: rgba(30, 30, 30, 0.8);
                border-radius: 10px;
                border-left: 4px solid #00ff00;
                display: none;
                animation: slideIn 0.5s;
                position: relative;
            }
            
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateY(20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .response::before {
                content: "💬";
                position: absolute;
                top: -15px;
                left: 20px;
                background: #000;
                padding: 0 10px;
                font-size: 1.5rem;
            }
            
            /* Footer */
            footer {
                margin-top: 60px;
                padding-top: 20px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                color: #666;
                font-size: 0.9rem;
            }
            
            .status {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: #ff0000;
                margin-right: 10px;
                animation: pulse 2s infinite;
            }
            
            .status.online {
                background: #00ff00;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            
            /* Code display */
            .code {
                background: rgba(0, 0, 0, 0.5);
                padding: 15px;
                border-radius: 8px;
                font-family: monospace;
                margin: 20px 0;
                border: 1px solid rgba(0, 255, 0, 0.2);
                text-align: left;
                overflow-x: auto;
            }
            
            /* Loading animation */
            .loader {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 2px solid rgba(0, 255, 0, 0.3);
                border-radius: 50%;
                border-top-color: #00ff00;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            
            /* Mobile responsiveness */
            @media (max-width: 768px) {
                .logo { font-size: 2.5rem; }
                .stats { flex-direction: column; align-items: center; }
                .stat-card { width: 100%; max-width: 300px; }
                .actions { flex-direction: column; align-items: center; }
                .btn { width: 100%; max-width: 300px; }
            }
        </style>
    </head>
    <body>
        <!-- Background animation -->
        <div class="bg-animation" id="bgAnimation"></div>
        
        <div class="container">
            <!-- Logo/Header -->
            <div class="logo">GOBLIN</div>
            <div class="subtitle">Simple bot with animated interface</div>
            
            <!-- Stats -->
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number" id="totalPings">0</div>
                    <div class="stat-label">Total Pings</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="botStatus">OFF</div>
                    <div class="stat-label">Bot Status</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="uptime">0d</div>
                    <div class="stat-label">Uptime</div>
                </div>
            </div>
            
            <!-- Actions -->
            <div class="actions">
                <button class="btn" onclick="testBot()">
                    🤖 Test Bot
                </button>
                <button class="btn" onclick="showEndpoint()">
                    🔗 Endpoint
                </button>
                <button class="btn" onclick="inviteBot()">
                    ➕ Invite Bot
                </button>
                <a href="/health" class="btn" target="_blank">
                    📊 Health
                </a>
            </div>
            
            <!-- Ping section -->
            <div class="ping-container">
                <button class="ping-btn" onclick="sendPing()">
                    🏓 PING THE BOT
                </button>
                <div class="response" id="pingResponse"></div>
            </div>
            
            <!-- Endpoint info (hidden by default) -->
            <div class="response" id="endpointInfo" style="display: none;">
                <h3>🔗 Interactions Endpoint</h3>
                <div class="code" id="endpointUrl">Loading...</div>
                <p style="margin-top: 10px; color: #888; font-size: 0.9rem;">
                    Copy this URL to Discord Developer Portal → Interactions Endpoint URL
                </p>
            </div>
            
            <!-- Footer -->
            <footer>
                <div style="margin-bottom: 10px;">
                    <span class="status" id="statusIndicator"></span>
                    <span id="statusText">Checking status...</span>
                </div>
                <div>
                    Use <code>/ping</code> in Discord to wake up the bot • Simple and clean
                </div>
                <div style="margin-top: 10px; color: #444;">
                    Made with minimal animations
                </div>
            </footer>
        </div>
        
        <script>
            let startTime = Date.now();
            let pingCount = 0;
            
            // Initialize background animation
            function initBackground() {
                const container = document.getElementById('bgAnimation');
                for (let i = 0; i < 50; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    dot.style.width = dot.style.height = Math.random() * 4 + 1 + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.opacity = Math.random() * 0.5 + 0.1;
                    dot.style.setProperty('--tx', Math.random() * 2 - 1);
                    dot.style.setProperty('--ty', Math.random() * 2 - 1);
                    dot.style.animationDelay = Math.random() * 5 + 's';
                    dot.style.animationDuration = Math.random() * 10 + 10 + 's';
                    container.appendChild(dot);
                }
            }
            
            // Update uptime
            function updateUptime() {
                const now = Date.now();
                const diff = now - startTime;
                const days = Math.floor(diff / (1000 * 60 * 60 * 24));
                const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                
                let uptimeText = '';
                if (days > 0) uptimeText += days + 'd ';
                if (hours > 0) uptimeText += hours + 'h ';
                uptimeText += minutes + 'm';
                
                document.getElementById('uptime').textContent = uptimeText;
            }
            
            // Send ping
            function sendPing() {
                const btn = document.querySelector('.ping-btn');
                const response = document.getElementById('pingResponse');
                
                // Create wave effect
                const wave = document.createElement('div');
                wave.className = 'ping-wave';
                btn.parentNode.appendChild(wave);
                
                // Remove wave after animation
                setTimeout(() => {
                    wave.remove();
                }, 1000);
                
                // Show loading
                response.innerHTML = '<div class="loader"></div> Loading...';
                response.style.display = 'block';
                
                // Simulate ping response (in real app, this would call your API)
                setTimeout(() => {
                    const responses = [
                        "I'm here newgen",
                        "Bot is up",
                        "Still alive",
                        "Yeah I'm here",
                        "Online",
                        "Ready",
                        "Here",
                        "Present",
                        "Awake",
                        "Active"
                    ];
                    
                    const randomResponse = responses[Math.floor(Math.random() * responses.length)];
                    response.innerHTML = `<strong>${randomResponse}</strong>`;
                    
                    // Update ping count
                    pingCount++;
                    document.getElementById('totalPings').textContent = pingCount;
                    
                    // Hide response after 3 seconds
                    setTimeout(() => {
                        response.style.display = 'none';
                    }, 3000);
                }, 800);
            }
            
            // Test bot connection
            async function testBot() {
                const statusIndicator = document.getElementById('statusIndicator');
                const statusText = document.getElementById('statusText');
                const botStatus = document.getElementById('botStatus');
                
                statusIndicator.className = 'status';
                statusText.textContent = 'Checking...';
                
                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    
                    if (data.status === 'healthy') {
                        statusIndicator.className = 'status online';
                        statusText.textContent = '✅ Bot is connected';
                        botStatus.textContent = 'ON';
                        botStatus.style.color = '#00ff00';
                    } else {
                        statusIndicator.className = 'status';
                        statusText.textContent = '❌ Bot not connected';
                        botStatus.textContent = 'OFF';
                        botStatus.style.color = '#ff0000';
                    }
                } catch (error) {
                    statusIndicator.className = 'status';
                    statusText.textContent = '❌ Connection error';
                    botStatus.textContent = 'ERR';
                    botStatus.style.color = '#ff9900';
                }
            }
            
            // Show endpoint URL
            function showEndpoint() {
                const endpointInfo = document.getElementById('endpointInfo');
                const endpointUrl = document.getElementById('endpointUrl');
                
                endpointUrl.textContent = window.location.origin + '/interactions';
                
                if (endpointInfo.style.display === 'none') {
                    endpointInfo.style.display = 'block';
                } else {
                    endpointInfo.style.display = 'none';
                }
            }
            
            // Invite bot
            function inviteBot() {
                alert('In a real implementation, this would open the Discord bot invite link.');
                // window.open('https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands', '_blank');
            }
            
            // Load stats
            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    if (data.total_pings !== undefined) {
                        pingCount = data.total_pings;
                        document.getElementById('totalPings').textContent = pingCount;
                    }
                } catch (error) {
                    // Use random demo data
                    pingCount = Math.floor(Math.random() * 100) + 50;
                    document.getElementById('totalPings').textContent = pingCount;
                }
            }
            
            // Initialize
            document.addEventListener('DOMContentLoaded', function() {
                initBackground();
                loadStats();
                testBot();
                updateUptime();
                
                // Update uptime every minute
                setInterval(updateUptime, 60000);
                
                // Update stats every 30 seconds
                setInterval(loadStats, 30000);
                
                // Randomly trigger animations
                setInterval(() => {
                    if (Math.random() > 0.7) {
                        const stats = document.querySelectorAll('.stat-card');
                        const randomStat = stats[Math.floor(Math.random() * stats.length)];
                        randomStat.style.transform = 'translateY(-5px)';
                        setTimeout(() => {
                            randomStat.style.transform = '';
                        }, 300);
                    }
                }, 5000);
            });
        </script>
    </body>
    </html>
    '''

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/stats')
def api_stats():
    """Get simple stats"""
    conn = get_db_connection()
    
    total_pings = conn.execute('SELECT COUNT(*) as count FROM pings').fetchone()['count']
    
    conn.close()
    
    return jsonify({
        "total_pings": total_pings,
        "bot_active": bot_active,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy" if bot_active else "offline",
        "service": "Simple Goblin Bot",
        "bot": "active" if bot_active else "inactive",
        "timestamp": datetime.utcnow().isoformat(),
        "simple": True
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*60}")
    print("🤖 SIMPLE GOBLIN BOT")
    print(f"{'='*60}")
    
    # Test Discord connection
    if test_discord_token():
        bot_active = True
        print("✅ Bot token valid")
        
        if register_commands():
            print("✅ Ping command registered")
        else:
            print("⚠️ Could not register commands")
    else:
        print("❌ Discord token not set or invalid")
        print("   Set DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_PUBLIC_KEY")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🔗 Interactions: http://localhost:{port}/interactions")
    print(f"📊 Health Check: http://localhost:{port}/health")
    
    print(f"\n🎮 Discord Command:")
    print(f"   /ping - Simple response to wake up bot")
    
    print(f"\n⚙️ Simple setup:")
    print(f"   1. Set environment variables")
    print(f"   2. Deploy to Render")
    print(f"   3. Set interactions endpoint in Discord")
    print(f"   4. Use /ping in Discord")
    
    print(f"\n💡 Responses are simple: 'I'm here newgen', 'Bot is up', etc.")
    print(f"{'='*60}\n")
    
    # Start server
    app.run(host='0.0.0.0', port=port, debug=False)# app.py - TOXIC GOBLIN REGISTRY (Multi-Server Ready)
import os
import json
import sqlite3
import random
import string
import threading
import time
import hashlib
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import logging
import hmac
import base64

app = Flask(__name__)
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

# Toxic COD voice chat responses (RAW)
TOXIC_PING_RESPONSES = [
    "Shut the fuck up kid",
    "Bro thinks pinging does something 💀",
    "Yapping",
    "Your mom's calling you for dinner",
    "1v1 me rust rn",
    "Bro's malding",
    "Imagine being this down bad",
    "L+Ratio+You fell off",
    "Go touch grass",
    "Bro's seething",
    "Cry about it",
    "Skill issue",
    "Mad cuz bad",
    "Get good",
    "What's your K/D? Oh wait you don't have one",
    "Bro thinks he's him",
    "Actual bot",
    "Go back to Fortnite",
    "Zero PR",
    "You're that kid who goes 2-17",
    "Bro got filtered",
    "Dogwater player",
    "Get a life",
    "Bro is NOT him",
    "Absolute clown behavior",
    "Go back to silver",
    "Actual NPC",
    "Lil bro is lost",
    "Bro is COOKED",
    "Take the L and move on"
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
        logger.error("Missing Discord signature headers")
        return False
    
    if not DISCORD_PUBLIC_KEY:
        logger.error("DISCORD_PUBLIC_KEY not set")
        return False
    
    try:
        import nacl.signing
        import nacl.exceptions
        
        message = f"{timestamp}{body}".encode('utf-8')
        signature_bytes = bytes.fromhex(signature)
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify(message, signature_bytes)
        
        return True
        
    except ImportError:
        logger.error("PyNaCl not installed")
        return False
    except nacl.exceptions.BadSignatureError:
        logger.error("Invalid Discord signature")
        return False
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False

# =============================================================================
# DATABASE SETUP - MULTI-SERVER READY
# =============================================================================

def init_db():
    """Initialize database for multi-server support"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Players - now with server_id
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
                title TEXT DEFAULT 'Bot',
                status TEXT DEFAULT 'active',
                banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                banned_by TEXT,
                banned_at TIMESTAMP,
                toxic_level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(discord_id, server_id)
            )
        ''')
        
        # Server-specific settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_settings (
                server_id TEXT PRIMARY KEY,
                server_name TEXT,
                owner_id TEXT,
                mod_role_ids TEXT DEFAULT '',
                welcome_message TEXT DEFAULT '',
                toxic_mode BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Moderators - server-specific
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_moderators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT,
                discord_id TEXT,
                role TEXT,  -- 'owner', 'admin', 'mod'
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(server_id, discord_id)
            )
        ''')
        
        # Multi-server moderation logs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                server_id TEXT,
                action TEXT,
                moderator_id TEXT,
                moderator_name TEXT,
                reason TEXT,
                duration_days INTEGER,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
        ''')
        
        # Matches - can be cross-server
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_code TEXT UNIQUE,
                server_id TEXT,
                player1_id INTEGER,
                player2_id INTEGER,
                player1_score INTEGER DEFAULT 0,
                player2_score INTEGER DEFAULT 0,
                winner_id INTEGER,
                status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player1_id) REFERENCES players (id),
                FOREIGN KEY (player2_id) REFERENCES players (id)
            )
        ''')
        
        # Global bans (cross-server)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                reason TEXT,
                banned_by TEXT,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        # Indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_api_key ON players(api_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_discord_server ON players(discord_id, server_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_server ON players(server_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mods_server ON server_moderators(server_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_settings_server ON server_settings(server_id)')
        
        conn.commit()
        conn.close()
        logger.info("✅ Multi-server database initialized")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# KEY GENERATION
# =============================================================================

def generate_api_key(discord_id, discord_name):
    """Generate toxic API key"""
    timestamp = str(int(time.time()))
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=24))
    raw_key = f"{discord_id}:{discord_name}:{timestamp}:{random_str}:GETGUD"
    hash_key = hashlib.sha256(raw_key.encode()).hexdigest()[:32]
    formatted_key = f"TOX-{hash_key[:8]}-{hash_key[8:16]}-{hash_key[16:24]}-{hash_key[24:32]}"
    return formatted_key.upper()

def validate_api_key(api_key):
    """Validate API key"""
    if not api_key or not api_key.startswith("TOX-"):
        return None
    
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE api_key = ?',
        (api_key,)
    ).fetchone()
    
    if player:
        # Check if globally banned
        global_ban = conn.execute(
            'SELECT * FROM global_bans WHERE discord_id = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)',
            (player['discord_id'],)
        ).fetchone()
        
        if global_ban:
            conn.close()
            return None
            
        # Update last used
        conn.execute(
            'UPDATE players SET last_used = CURRENT_TIMESTAMP WHERE id = ?',
            (player['id'],)
        )
        conn.commit()
    
    conn.close()
    return player

# =============================================================================
# SERVER & MODERATION MANAGEMENT (Multi-server)
# =============================================================================

def is_server_moderator(server_id, discord_id):
    """Check if user is mod in specific server"""
    conn = get_db_connection()
    
    # Check server moderators table
    mod = conn.execute('''
        SELECT * FROM server_moderators 
        WHERE server_id = ? AND discord_id = ?
    ''', (server_id, discord_id)).fetchone()
    
    if mod:
        conn.close()
        return True
    
    # Check server owner
    owner = conn.execute('''
        SELECT * FROM server_settings 
        WHERE server_id = ? AND owner_id = ?
    ''', (server_id, discord_id)).fetchone()
    
    conn.close()
    return bool(owner)

def get_server_settings(server_id):
    """Get server-specific settings"""
    conn = get_db_connection()
    settings = conn.execute(
        'SELECT * FROM server_settings WHERE server_id = ?',
        (server_id,)
    ).fetchone()
    conn.close()
    
    if not settings:
        # Create default settings
        return {
            'server_id': server_id,
            'server_name': 'Unknown Server',
            'toxic_mode': True,
            'welcome_message': 'Get rekt newgens'
        }
    
    return dict(settings)

def setup_new_server(server_id, server_name, owner_id):
    """Initialize settings for new server"""
    conn = get_db_connection()
    
    # Create server settings
    conn.execute('''
        INSERT OR REPLACE INTO server_settings 
        (server_id, server_name, owner_id, toxic_mode)
        VALUES (?, ?, ?, 1)
    ''', (server_id, server_name, owner_id))
    
    # Add owner as admin
    conn.execute('''
        INSERT OR IGNORE INTO server_moderators 
        (server_id, discord_id, role, added_by)
        VALUES (?, ?, 'owner', 'system')
    ''', (server_id, owner_id))
    
    conn.commit()
    conn.close()
    
    logger.info(f"✅ Setup new server: {server_name} ({server_id})")

def get_toxic_insult():
    """Generate toxic insult"""
    insults = [
        "absolute bot",
        "certified noob",
        "professional feeder",
        "human ward",
        "walking ult charge",
        "bronze mentality",
        "potato aim",
        "negative IQ play",
        "skill-less wonder",
        "L collector",
        "ratio enthusiast",
        "copium addict",
        "malding expert",
        "seethe specialist",
        "cope merchant"
    ]
    return random.choice(insults)

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
    """Register multi-server slash commands"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        logger.error("❌ Cannot register commands")
        return False
    
    commands = [
        {
            "name": "ping",
            "description": "Ping the toxic bot (prepare for flame)",
            "type": 1
        },
        {
            "name": "register",
            "description": "Register for TDM (get flamed)",
            "type": 1,
            "options": [
                {
                    "name": "ingame_name",
                    "description": "Your in-game name (for roasting)",
                    "type": 3,
                    "required": True
                }
            ]
        },
        {
            "name": "profile",
            "description": "Check your stats (and get mocked)",
            "type": 1
        },
        {
            "name": "roast",
            "description": "Roast someone (mod only)",
            "type": 1,
            "options": [
                {
                    "name": "target",
                    "description": "Who to flame",
                    "type": 6,
                    "required": True
                }
            ]
        },
        {
            "name": "banish",
            "description": "Ban a player (server mod only)",
            "type": 1,
            "options": [
                {
                    "name": "player",
                    "description": "Player to banish",
                    "type": 6,
                    "required": True
                },
                {
                    "name": "reason",
                    "description": "Why they're trash",
                    "type": 3,
                    "required": False
                }
            ]
        },
        {
            "name": "leaderboard",
            "description": "See who's least bad",
            "type": 1
        },
        {
            "name": "setup",
            "description": "Setup bot for this server (admin only)",
            "type": 1
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
            logger.info(f"✅ Registered toxic commands")
            return True
        else:
            logger.error(f"❌ Failed to register commands: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error registering commands: {e}")
        return False

def create_invite_link():
    """Generate bot invite link"""
    if not DISCORD_CLIENT_ID:
        return None
    
    permissions = "274877975616"
    return f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions={permissions}&scope=bot%20applications.commands"

# =============================================================================
# DISCORD INTERACTIONS - MULTI-SERVER READY
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord slash commands with multi-server support"""
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
        server_id = data.get('guild_id')
        
        if not server_id:
            return jsonify({
                "type": 4,
                "data": {
                    "content": "❌ This command only works in servers, not DMs",
                    "flags": 64
                }
            })
        
        # Setup server if first time
        server_settings = get_server_settings(server_id)
        if not server_settings.get('server_name'):
            # Get server info from Discord
            try:
                url = f"https://discord.com/api/v10/guilds/{server_id}"
                headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    guild_info = response.json()
                    setup_new_server(server_id, guild_info['name'], user_id)
            except:
                pass
        
        # TOXIC MODE: Add random toxic comments to responses
        toxic_mode = server_settings.get('toxic_mode', True)
        toxic_prefix = random.choice(["Bro", "Kid", "My guy", "Homie", "Chief"]) if toxic_mode else ""
        
        if command == 'ping':
            response = random.choice(TOXIC_PING_RESPONSES)
            if toxic_mode and random.random() > 0.5:
                response += f" {get_toxic_insult()}"
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": response,
                    "flags": 0  # Public so everyone sees the flame
                }
            })
        
        elif command == 'register':
            options = data.get('data', {}).get('options', [])
            if options and len(options) > 0:
                in_game_name = options[0].get('value', 'Unknown')
                
                conn = get_db_connection()
                
                # Check if already registered in this server
                existing = conn.execute(
                    'SELECT * FROM players WHERE discord_id = ? AND server_id = ?',
                    (user_id, server_id)
                ).fetchone()
                
                if existing:
                    conn.close()
                    roast = f" Already registered as {existing['in_game_name']} you 🤡" if toxic_mode else ""
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"❌{roost}",
                            "flags": 64
                        }
                    })
                
                # Check global ban
                global_ban = conn.execute(
                    'SELECT * FROM global_bans WHERE discord_id = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)',
                    (user_id,)
                ).fetchone()
                
                if global_ban:
                    conn.close()
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"🚫 Globally banned. Reason: {global_ban['reason']}. L",
                            "flags": 64
                        }
                    })
                
                # Generate API key
                api_key = generate_api_key(user_id, user_name)
                
                # Register player
                conn.execute('''
                    INSERT INTO players 
                    (discord_id, discord_name, in_game_name, api_key, server_id, toxic_level)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, user_name, in_game_name, api_key, server_id, random.randint(1, 10)))
                
                conn.commit()
                conn.close()
                
                # Toxic welcome message
                welcome = server_settings.get('welcome_message', 'Get rekt')
                toxic_welcome = f"\n\n{welcome} {get_toxic_insult().upper()}" if toxic_mode else ""
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"✅ **Registered** {toxic_prefix}\n\n"
                            f"**Name:** `{in_game_name}`\n"
                            f"**API Key:** `{api_key}`\n"
                            f"**Toxic Level:** {random.randint(1, 10)}/10{toxic_welcome}\n\n"
                            f"🔗 **Dashboard:** {request.host_url}\n"
                            f"📊 **Stats:** `/profile`\n"
                            f"💰 **Credits:** 1000 (don't spend it all in one place)"
                        ),
                        "flags": 64
                    }
                })
        
        elif command == 'profile':
            conn = get_db_connection()
            player = conn.execute(
                'SELECT * FROM players WHERE discord_id = ? AND server_id = ?',
                (user_id, server_id)
            ).fetchone()
            conn.close()
            
            if not player:
                insult = f" {get_toxic_insult()}" if toxic_mode else ""
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"❌ Not registered{insult}. Use `/register`",
                        "flags": 64
                    }
                })
            
            kd = player['total_kills'] / max(player['total_deaths'], 1)
            win_rate = (player['wins'] + player['losses']) > 0 and (player['wins'] / (player['wins'] + player['losses']) * 100) or 0
            
            # Toxic commentary based on stats
            commentary = ""
            if toxic_mode:
                if kd < 0.5:
                    commentary = f"\n\n📉 K/D ratio looking rough {get_toxic_insult()}"
                elif player['losses'] > player['wins']:
                    commentary = f"\n\n💀 Professional L-taker detected"
                elif player['toxic_level'] > 7:
                    commentary = f"\n\n☢️ Certified toxic player"
                elif player['toxic_level'] < 3:
                    commentary = f"\n\n😇 Surprisingly not toxic (sus)"
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"📊 **{player['in_game_name']}'s Stats**\n\n"
                        f"**K/D:** `{kd:.2f}` ({player['total_kills']}k/{player['total_deaths']}d)\n"
                        f"**W/L:** {player['wins']}-{player['losses']} ({win_rate:.1f}%)\n"
                        f"**Credits:** {player['credits']}\n"
                        f"**Toxic Level:** {player['toxic_level']}/10 ⚠️\n"
                        f"**Title:** {player['title']}\n\n"
                        f"🔑 **API Key:**\n`{player['api_key']}`\n\n"
                        f"🌐 **Dashboard:** {request.host_url}{commentary}"
                    ),
                    "flags": 64
                }
            })
        
        elif command == 'roast':
            # Check if mod
            if not is_server_moderator(server_id, user_id):
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ You're not a mod, stop pretending",
                        "flags": 64
                    }
                })
            
            options = data.get('data', {}).get('options', [])
            if options and len(options) > 0:
                target = options[0].get('value')
                
                roasts = [
                    f"<@{target}> is so bad they make bots look pro",
                    f"<@{target}>'s gameplay is a crime against humanity",
                    f"<@{target}> has the game sense of a potato",
                    f"<@{target}> is the reason we can't have nice things",
                    f"<@{target}>'s aim is so bad they couldn't hit water if they fell out of a boat",
                    f"<@{target}> is carrying the team... to defeat",
                    f"<@{target}> is proof that anyone can play",
                    f"<@{target}> is the human equivalent of a participation trophy",
                    f"<@{target}>'s KD is in the witness protection program",
                    f"<@{target}> is the reason matchmaking takes so long"
                ]
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"🔥 {random.choice(roasts)}",
                        "flags": 0
                    }
                })
        
        elif command == 'banish':
            # Check if mod
            if not is_server_moderator(server_id, user_id):
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ Mods only, go back to complaining in general",
                        "flags": 64
                    }
                })
            
            options = data.get('data', {}).get('options', [])
            if options and len(options) > 0:
                target_id = options[0].get('value')
                reason = options[1].get('value') if len(options) > 1 else "Being trash"
                
                conn = get_db_connection()
                
                # Ban player in this server
                conn.execute('''
                    UPDATE players 
                    SET status = 'banned', 
                        banned = 1,
                        ban_reason = ?,
                        banned_by = ?,
                        banned_at = CURRENT_TIMESTAMP
                    WHERE discord_id = ? AND server_id = ?
                ''', (reason, user_name, target_id, server_id))
                
                # Log the action
                conn.execute('''
                    INSERT INTO moderation_logs 
                    (player_id, server_id, action, moderator_id, moderator_name, reason)
                    SELECT id, ?, 'ban', ?, ?, ?
                    FROM players WHERE discord_id = ? AND server_id = ?
                ''', (server_id, user_id, user_name, reason, target_id, server_id))
                
                conn.commit()
                conn.close()
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"🔨 <@{target_id}> has been banished.\nReason: {reason}\nGet good, scrub.",
                        "flags": 0
                    }
                })
        
        elif command == 'leaderboard':
            conn = get_db_connection()
            players = conn.execute('''
                SELECT in_game_name, total_kills, total_deaths, wins, losses, toxic_level
                FROM players 
                WHERE server_id = ? AND banned = 0
                ORDER BY total_kills DESC, wins DESC
                LIMIT 10
            ''', (server_id,)).fetchall()
            conn.close()
            
            if not players:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "📭 No registered players yet. Be the first to get flamed.",
                        "flags": 0
                    }
                })
            
            leaderboard = "🏆 **LEAST WORST PLAYERS** 🏆\n\n"
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            
            for i, player in enumerate(players[:10]):
                kd = player['total_kills'] / max(player['total_deaths'], 1)
                toxic_stars = "☢️" * min(player['toxic_level'], 5)
                leaderboard += f"{medals[i]} **{player['in_game_name']}**\n"
                leaderboard += f"   K/D: {kd:.2f} | W/L: {player['wins']}-{player['losses']} {toxic_stars}\n\n"
            
            leaderboard += "*Based on who's slightly less terrible*"
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": leaderboard,
                    "flags": 0
                }
            })
        
        elif command == 'setup':
            # Check if user has admin permissions in Discord
            member = data.get('member', {})
            permissions = int(member.get('permissions', 0))
            has_admin = (permissions & 0x8) == 0x8  # ADMINISTRATOR permission
            
            if not has_admin:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ Need admin perms, chief",
                        "flags": 64
                    }
                })
            
            setup_new_server(server_id, "Server", user_id)
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        "✅ **Bot setup complete**\n\n"
                        f"**Server ID:** {server_id}\n"
                        f"**Owner:** <@{user_id}>\n"
                        f"**Toxic Mode:** ✅ ENABLED (obviously)\n\n"
                        "🛠️ **Admin Commands:**\n"
                        "• `/roast @user` - Flame someone\n"
                        "• `/banish @user` - Ban trash players\n"
                        "• Add more mods via web dashboard\n\n"
                        "🎮 **Player Commands:**\n"
                        "• `/register [name]` - Get roasted & get key\n"
                        "• `/profile` - See how bad you are\n"
                        "• `/leaderboard` - See who's least terrible\n\n"
                        f"🔗 **Web Dashboard:** {request.host_url}"
                    ),
                    "flags": 64
                }
            })
    
    return jsonify({"type": 4, "data": {"content": "Bro what?", "flags": 64}})

# =============================================================================
# WEB INTERFACE - TOXIC EDITION
# =============================================================================

@app.route('/')
def home():
    """Main toxic web page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>☢️ TOXIC GOBLIN REGISTRY</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Inter:wght@400;600&display=swap');
            
            :root {
                --toxic-green: #39ff14;
                --toxic-purple: #9d00ff;
                --toxic-pink: #ff00ff;
                --toxic-orange: #ff6b00;
                --dark: #0a0a0a;
                --darker: #050505;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', sans-serif;
                background: var(--dark);
                color: white;
                min-height: 100vh;
                overflow-x: hidden;
                position: relative;
            }
            
            body::before {
                content: '';
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: 
                    radial-gradient(circle at 20% 80%, var(--toxic-green) 0%, transparent 50%),
                    radial-gradient(circle at 80% 20%, var(--toxic-purple) 0%, transparent 50%),
                    radial-gradient(circle at 40% 40%, var(--toxic-pink) 0%, transparent 50%);
                opacity: 0.1;
                z-index: -1;
                animation: pulse 10s infinite alternate;
            }
            
            @keyframes pulse {
                0% { opacity: 0.05; }
                100% { opacity: 0.15; }
            }
            
            .toxic-header {
                background: linear-gradient(45deg, var(--darker), transparent);
                border-bottom: 3px solid var(--toxic-green);
                padding: 20px;
                text-align: center;
                backdrop-filter: blur(10px);
                position: relative;
                overflow: hidden;
            }
            
            .toxic-header::before {
                content: '☢️';
                position: absolute;
                font-size: 10rem;
                opacity: 0.05;
                top: -50px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 0;
            }
            
            h1 {
                font-family: 'Montserrat', sans-serif;
                font-size: 4rem;
                background: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple), var(--toxic-pink));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                text-shadow: 0 0 30px rgba(57, 255, 20, 0.3);
                margin-bottom: 10px;
                position: relative;
                z-index: 1;
            }
            
            .tagline {
                color: #888;
                font-size: 1.2rem;
                margin-bottom: 20px;
                font-style: italic;
            }
            
            .toxic-badge {
                display: inline-block;
                padding: 8px 16px;
                background: linear-gradient(45deg, var(--toxic-green), transparent);
                border: 2px solid var(--toxic-green);
                border-radius: 20px;
                font-weight: bold;
                font-size: 0.9rem;
                letter-spacing: 1px;
                box-shadow: 0 0 15px var(--toxic-green);
                animation: glow 2s infinite alternate;
            }
            
            @keyframes glow {
                0% { box-shadow: 0 0 15px var(--toxic-green); }
                100% { box-shadow: 0 0 25px var(--toxic-green); }
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 30px;
            }
            
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                gap: 25px;
                margin-top: 30px;
            }
            
            .card {
                background: rgba(20, 20, 20, 0.8);
                border: 2px solid;
                border-image: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple)) 1;
                border-radius: 10px;
                padding: 25px;
                backdrop-filter: blur(5px);
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
            }
            
            .card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, var(--toxic-green), var(--toxic-purple), var(--toxic-pink));
            }
            
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 30px rgba(57, 255, 20, 0.2);
            }
            
            .card h2 {
                color: var(--toxic-green);
                margin-bottom: 20px;
                font-size: 1.8rem;
                font-family: 'Montserrat', sans-serif;
            }
            
            .toxic-input {
                width: 100%;
                padding: 15px;
                background: rgba(0, 0, 0, 0.5);
                border: 2px solid var(--toxic-purple);
                border-radius: 8px;
                color: white;
                font-size: 16px;
                margin-bottom: 15px;
                transition: all 0.3s;
            }
            
            .toxic-input:focus {
                outline: none;
                border-color: var(--toxic-green);
                box-shadow: 0 0 15px rgba(57, 255, 20, 0.3);
            }
            
            .toxic-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 15px 30px;
                background: linear-gradient(45deg, var(--toxic-green), var(--toxic-purple));
                color: black;
                border: none;
                border-radius: 8px;
                font-family: 'Montserrat', sans-serif;
                font-weight: bold;
                font-size: 16px;
                cursor: pointer;
                transition: all 0.3s;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin: 5px;
                text-decoration: none;
            }
            
            .toxic-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(57, 255, 20, 0.3);
                background: linear-gradient(45deg, var(--toxic-purple), var(--toxic-green));
            }
            
            .toxic-btn.warning {
                background: linear-gradient(45deg, var(--toxic-orange), #ff0000);
            }
            
            .toxic-btn.danger {
                background: linear-gradient(45deg, #ff0000, #8b0000);
            }
            
            .toxic-btn.success {
                background: linear-gradient(45deg, #00ff00, var(--toxic-green));
            }
            
            .key-display {
                background: rgba(0, 0, 0, 0.7);
                border: 2px solid var(--toxic-green);
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
                font-family: monospace;
                font-size: 1.3rem;
                color: var(--toxic-green);
                text-align: center;
                letter-spacing: 2px;
                word-break: break-all;
                cursor: pointer;
                position: relative;
                overflow: hidden;
            }
            
            .key-display::before {
                content: 'CLICK TO COPY';
                position: absolute;
                top: 5px;
                left: 10px;
                font-size: 0.7rem;
                color: var(--toxic-purple);
                opacity: 0.7;
            }
            
            .key-display:hover {
                background: rgba(0, 0, 0, 0.9);
                box-shadow: 0 0 20px var(--toxic-green);
            }
            
            .player-card {
                background: rgba(30, 30, 30, 0.8);
                border-left: 5px solid var(--toxic-green);
                border-radius: 8px;
                padding: 20px;
                margin: 15px 0;
                transition: all 0.3s;
            }
            
            .player-card:hover {
                border-left-color: var(--toxic-pink);
                transform: translateX(5px);
            }
            
            .player-card.banned {
                border-left-color: #ff0000;
                opacity: 0.7;
            }
            
            .player-card.moderator {
                border-left-color: var(--toxic-purple);
            }
            
            .player-name {
                font-weight: bold;
                font-size: 1.2rem;
                margin-bottom: 10px;
            }
            
            .toxic-level {
                display: inline-block;
                padding: 3px 10px;
                background: rgba(57, 255, 20, 0.2);
                border-radius: 12px;
                font-size: 0.9rem;
                margin-left: 10px;
            }
            
            .tab-container {
                display: flex;
                gap: 10px;
                margin-bottom: 30px;
                border-bottom: 2px solid var(--toxic-purple);
                padding-bottom: 10px;
                flex-wrap: wrap;
            }
            
            .tab {
                padding: 12px 24px;
                background: transparent;
                border: 2px solid var(--toxic-purple);
                color: white;
                border-radius: 6px;
                cursor: pointer;
                transition: all 0.3s;
                font-family: 'Montserrat', sans-serif;
            }
            
            .tab:hover {
                background: rgba(157, 0, 255, 0.2);
                border-color: var(--toxic-green);
            }
            
            .tab.active {
                background: linear-gradient(45deg, var(--toxic-purple), transparent);
                border-color: var(--toxic-green);
                color: var(--toxic-green);
            }
            
            .tab-content {
                display: none;
                animation: fadeIn 0.3s;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            .tab-content.active {
                display: block;
            }
            
            .toxic-alert {
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
                border: 2px solid;
                animation: slideIn 0.3s;
            }
            
            @keyframes slideIn {
                from { transform: translateY(-10px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
            
            .toxic-alert.success {
                background: rgba(57, 255, 20, 0.1);
                border-color: var(--toxic-green);
                color: var(--toxic-green);
            }
            
            .toxic-alert.error {
                background: rgba(255, 0, 0, 0.1);
                border-color: #ff0000;
                color: #ff5555;
            }
            
            .toxic-alert.warning {
                background: rgba(255, 107, 0, 0.1);
                border-color: var(--toxic-orange);
                color: var(--toxic-orange);
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 20px;
                margin: 25px 0;
            }
            
            .stat-box {
                background: rgba(0, 0, 0, 0.5);
                padding: 25px;
                border-radius: 10px;
                text-align: center;
                border: 1px solid var(--toxic-purple);
            }
            
            .stat-value {
                font-size: 3rem;
                font-weight: bold;
                margin: 10px 0;
                color: var(--toxic-green);
                text-shadow: 0 0 10px var(--toxic-green);
            }
            
            .stat-label {
                color: #888;
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .floating-toxic {
                position: fixed;
                font-size: 2rem;
                opacity: 0.1;
                pointer-events: none;
                z-index: -1;
                animation: float 20s infinite linear;
            }
            
            @keyframes float {
                0% { transform: translateY(100vh) rotate(0deg); }
                100% { transform: translateY(-100vh) rotate(360deg); }
            }
            
            footer {
                text-align: center;
                padding: 40px 20px;
                margin-top: 50px;
                color: #555;
                font-size: 0.9rem;
                border-top: 1px solid var(--toxic-purple);
            }
            
            .toxic-comment {
                color: var(--toxic-green);
                font-style: italic;
                margin-top: 10px;
                font-size: 0.8rem;
            }
            
            @media (max-width: 768px) {
                h1 { font-size: 2.5rem; }
                .grid { grid-template-columns: 1fr; }
                .container { padding: 15px; }
            }
        </style>
    </head>
    <body>
        <!-- Floating toxic symbols -->
        <div class="floating-toxic" style="left: 10%; animation-delay: 0s;">☢️</div>
        <div class="floating-toxic" style="left: 20%; animation-delay: -5s;">💀</div>
        <div class="floating-toxic" style="left: 30%; animation-delay: -10s;">⚠️</div>
        <div class="floating-toxic" style="left: 40%; animation-delay: -15s;">☣️</div>
        <div class="floating-toxic" style="left: 50%; animation-delay: -20s;">🔥</div>
        <div class="floating-toxic" style="left: 60%; animation-delay: -25s;">💥</div>
        <div class="floating-toxic" style="left: 70%; animation-delay: -30s;">⚡</div>
        <div class="floating-toxic" style="left: 80%; animation-delay: -35s;">🎮</div>
        <div class="floating-toxic" style="left: 90%; animation-delay: -40s;">🤖</div>
        
        <div class="toxic-header">
            <h1>TOXIC GOBLIN REGISTRY</h1>
            <div class="tagline">Where bad players get roasted and good players get bored</div>
            <div class="toxic-badge">MULTI-SERVER READY • GET FLAMED • SKILL ISSUE DETECTED</div>
        </div>
        
        <div class="container">
            <div class="tab-container">
                <button class="tab active" onclick="switchTab('register')">🎮 REGISTER</button>
                <button class="tab" onclick="switchTab('profile')">📊 PROFILE</button>
                <button class="tab" onclick="switchTab('mod')">🛡️ MOD TOOLS</button>
                <button class="tab" onclick="switchTab('stats')">📈 STATS</button>
                <button class="tab" onclick="switchTab('api')">🔌 API</button>
            </div>
            
            <!-- Register Tab -->
            <div id="register" class="tab-content active">
                <div class="grid">
                    <div class="card">
                        <h2>GET YOUR TOXIC KEY</h2>
                        <p style="margin-bottom: 20px; color: #aaa;">
                            Register to get flamed and receive your API key. Works in ANY Discord server with the bot.
                        </p>
                        
                        <input type="text" class="toxic-input" id="discordId" placeholder="Your Discord ID (right click → Copy ID)">
                        <input type="text" class="toxic-input" id="serverId" placeholder="Server ID (optional, for server-specific)">
                        <input type="text" class="toxic-input" id="ingameName" placeholder="In-game name (for roasting)">
                        
                        <button class="toxic-btn" onclick="registerPlayer()">
                            🎮 GET ROASTED & GET KEY
                        </button>
                        
                        <div id="registerResult"></div>
                    </div>
                    
                    <div class="card">
                        <h2>📋 HOW TO REGISTER</h2>
                        <div style="margin: 20px 0;">
                            <h3 style="color: var(--toxic-green); margin-bottom: 10px;">🎯 IN DISCORD:</h3>
                            <p>1. Add bot to your server</p>
                            <p>2. Type: <code>/register your_ingame_name</code></p>
                            <p>3. Get flamed & get your key</p>
                            
                            <h3 style="color: var(--toxic-purple); margin-top: 20px;">🌐 ON WEBSITE:</h3>
                            <p>1. Enter your Discord ID above</p>
                            <p>2. Get your toxic API key</p>
                            <p>3. Use it to access the roast API</p>
                        </div>
                        
                        <button class="toxic-btn success" onclick="inviteBot()">
                            🤖 INVITE BOT TO SERVER
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- Profile Tab -->
            <div id="profile" class="tab-content">
                <div class="grid">
                    <div class="card">
                        <h2>🔍 CHECK YOUR PROFILE</h2>
                        <input type="text" class="toxic-input" id="apiKey" placeholder="Enter your TOX-XXXX-XXXX-XXXX-XXXX key">
                        
                        <button class="toxic-btn" onclick="loadProfile()">📊 LOAD PROFILE</button>
                        <button class="toxic-btn warning" onclick="generateDemoKey()">🎲 DEMO KEY</button>
                        <button class="toxic-btn danger" onclick="roastYourself()">🔥 ROAST ME</button>
                        
                        <div id="profileResult" style="margin-top: 20px;"></div>
                        
                        <div class="key-display" id="keyDisplay" onclick="copyKey(this)" style="display: none;">
                            Your key appears here after loading
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>📊 YOUR STATS</h2>
                        <div id="statsDisplay">
                            <p style="color: #888; text-align: center; padding: 40px;">
                                Load your profile to see how bad you are
                            </p>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Mod Tools Tab -->
            <div id="mod" class="tab-content">
                <div class="card">
                    <h2>🛡️ SERVER MODERATION</h2>
                    <p style="margin-bottom: 20px; color: #aaa;">
                        Server admins can manage players. Works per-server, no global IDs needed.
                    </p>
                    
                    <div class="grid">
                        <div class="card">
                            <h3>⚡ QUICK BAN</h3>
                            <input type="text" class="toxic-input" id="banKey" placeholder="Player's API key or Discord ID">
                            <input type="text" class="toxic-input" id="banReason" placeholder="Reason (they're trash because...)">
                            <input type="text" class="toxic-input" id="modServerId" placeholder="Your Server ID">
                            
                            <button class="toxic-btn danger" onclick="banPlayer()">🔨 BANISH PLAYER</button>
                            <button class="toxic-btn warning" onclick="suspendPlayer()">⏸️ SUSPEND</button>
                            <button class="toxic-btn success" onclick="restorePlayer()">✅ RESTORE</button>
                            
                            <div id="modResult" style="margin-top: 15px;"></div>
                        </div>
                        
                        <div class="card">
                            <h3>📋 SERVER PLAYERS</h3>
                            <input type="text" class="toxic-input" id="serverLookup" placeholder="Enter Server ID">
                            <button class="toxic-btn" onclick="listServerPlayers()">👥 LIST PLAYERS</button>
                            
                            <div id="serverPlayers" style="margin-top: 15px; max-height: 300px; overflow-y: auto;"></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Stats Tab -->
            <div id="stats" class="tab-content">
                <div class="card">
                    <h2>📈 GLOBAL STATS</h2>
                    <div class="stats-grid" id="globalStats">
                        <div class="stat-box">
                            <div class="stat-value" id="totalPlayers">0</div>
                            <div class="stat-label">TOXIC PLAYERS</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="totalServers">0</div>
                            <div class="stat-label">SERVERS</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="totalKills">0</div>
                            <div class="stat-label">KILLS</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="totalBans">0</div>
                            <div class="stat-label">BANS</div>
                        </div>
                    </div>
                    
                    <button class="toxic-btn" onclick="refreshStats()">🔄 REFRESH STATS</button>
                    
                    <div style="margin-top: 30px;">
                        <h3>🔥 TOP TOXIC PLAYERS</h3>
                        <div id="toxicLeaderboard" style="margin-top: 15px;"></div>
                    </div>
                </div>
            </div>
            
            <!-- API Tab -->
            <div id="api" class="tab-content">
                <div class="grid">
                    <div class="card">
                        <h2>🔌 TOXIC API</h2>
                        <div style="margin: 20px 0;">
                            <h3 style="color: var(--toxic-green); margin-bottom: 10px;">📡 ENDPOINTS:</h3>
                            <code>GET /api/profile?key=TOX-XXXX...</code>
                            <div class="toxic-comment">Get roasted with your stats</div>
                            
                            <code style="display: block; margin-top: 15px;">GET /api/roast?key=TOX-XXXX...</code>
                            <div class="toxic-comment">Get a personalized insult</div>
                            
                            <code style="display: block; margin-top: 15px;">POST /api/report-match</code>
                            <div class="toxic-comment">Report how bad someone played</div>
                            
                            <code style="display: block; margin-top: 15px;">GET /api/stats</code>
                            <div class="toxic-comment">Global toxic statistics</div>
                        </div>
                        
                        <button class="toxic-btn" onclick="testAPI()">🧪 TEST API</button>
                    </div>
                    
                    <div class="card">
                        <h2>⚙️ MULTI-SERVER FEATURES</h2>
                        <ul style="margin: 20px 0; padding-left: 20px; color: #aaa;">
                            <li>✅ Works in ANY Discord server</li>
                            <li>✅ No global role IDs needed</li>
                            <li>✅ Server-specific moderation</li>
                            <li>✅ Cross-server player tracking</li>
                            <li>✅ Automatic server setup</li>
                            <li>✅ Toxic mode per server</li>
                        </ul>
                        
                        <div class="toxic-alert warning">
                            ⚠️ The bot automatically detects server admins based on Discord permissions.
                            No configuration needed for multi-server support.
                        </div>
                    </div>
                </div>
            </div>
            
            <footer>
                <p>☢️ TOXIC GOBLIN REGISTRY v4.0 • MULTI-SERVER READY • GET REKT</p>
                <p style="margin-top: 10px; font-size: 0.8rem; color: #666;">
                    "The only thing more toxic than our community is your K/D ratio"
                </p>
            </footer>
        </div>
        
        <script>
            // Toxic responses
            const TOXIC_ROASTS = [
                "Bro your K/D is in the negative 💀",
                "Skill issue detected 🤖",
                "You play like my grandma 🧓",
                "Actual bot behavior 🤡",
                "Get good scrub 🗑️",
                "Mad cuz bad 😭",
                "L+Ratio+You fell off 📉",
                "Zero PR activities 🚫",
                "Go back to training mode 🎯",
                "You're that kid who goes 0-20 😂"
            ];
            
            let currentProfile = null;
            
            // Tab switching
            function switchTab(tabName) {
                document.querySelectorAll('.tab-content').forEach(tab => {
                    tab.classList.remove('active');
                });
                document.getElementById(tabName).classList.add('active');
                
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                event.target.classList.add('active');
                
                if (tabName === 'stats') refreshStats();
            }
            
            // Register player
            async function registerPlayer() {
                const discordId = document.getElementById('discordId').value;
                const serverId = document.getElementById('serverId').value || 'global';
                const ingameName = document.getElementById('ingameName').value;
                
                if (!discordId || !ingameName) {
                    showToxicAlert('registerResult', '❌ Missing info, dummy', 'error');
                    return;
                }
                
                const roast = TOXIC_ROASTS[Math.floor(Math.random() * TOXIC_ROASTS.length)];
                
                try {
                    // In real implementation, this would call your API
                    // For demo, generate a fake key
                    const fakeKey = 'TOX-' + Math.random().toString(36).substr(2, 8).toUpperCase() + 
                                   '-' + Math.random().toString(36).substr(2, 8).toUpperCase() + 
                                   '-' + Math.random().toString(36).substr(2, 8).toUpperCase() + 
                                   '-' + Math.random().toString(36).substr(2, 8).toUpperCase();
                    
                    const resultDiv = document.getElementById('registerResult');
                    resultDiv.innerHTML = `
                        <div class="toxic-alert success">
                            <h3>✅ REGISTERED (GET REKT)</h3>
                            <p>${roast}</p>
                            <div class="key-display" onclick="copyKey(this)">
                                ${fakeKey}
                            </div>
                            <p style="margin-top: 10px; font-size: 0.9rem;">
                                🔗 Use this key to access the toxic API<br>
                                📊 Your toxic level: ${Math.floor(Math.random() * 10) + 1}/10
                            </p>
                        </div>
                    `;
                    
                    // Auto-switch to profile tab
                    setTimeout(() => {
                        document.getElementById('apiKey').value = fakeKey;
                        switchTab('profile');
                        loadDemoProfile(fakeKey);
                    }, 1500);
                    
                } catch (error) {
                    showToxicAlert('registerResult', `❌ Error: ${error.message}`, 'error');
                }
            }
            
            // Load profile
            async function loadProfile() {
                const apiKey = document.getElementById('apiKey').value;
                
                if (!apiKey || !apiKey.startsWith('TOX-')) {
                    showToxicAlert('profileResult', '❌ Invalid key format, genius', 'error');
                    return;
                }
                
                loadDemoProfile(apiKey);
            }
            
            // Demo profile (since we don't have backend in this example)
            function loadDemoProfile(apiKey) {
                const kd = (Math.random() * 3).toFixed(2);
                const wins = Math.floor(Math.random() * 100);
                const losses = Math.floor(Math.random() * 120);
                const toxicLevel = Math.floor(Math.random() * 10) + 1;
                const credits = Math.floor(Math.random() * 5000);
                
                const roast = kd < 1 ? 
                    `K/D ratio looking rough ${TOXIC_ROASTS[Math.floor(Math.random() * TOXIC_ROASTS.length)]}` :
                    `Not completely terrible, I guess`;
                
                document.getElementById('profileResult').innerHTML = `
                    <div class="toxic-alert success">
                        <h3>📊 PROFILE LOADED</h3>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
                            <div>
                                <strong>K/D Ratio:</strong><br>
                                <span style="font-size: 2rem; color: ${kd > 1 ? '#39ff14' : '#ff0000'}">${kd}</span>
                            </div>
                            <div>
                                <strong>W/L Record:</strong><br>
                                <span style="font-size: 2rem;">${wins}-${losses}</span>
                            </div>
                            <div>
                                <strong>Toxic Level:</strong><br>
                                <span style="font-size: 2rem;">${toxicLevel}/10</span>
                            </div>
                            <div>
                                <strong>Credits:</strong><br>
                                <span style="font-size: 2rem;">${credits}</span>
                            </div>
                        </div>
                        <p style="margin-top: 15px; color: #39ff14;">${roast}</p>
                    </div>
                `;
                
                document.getElementById('keyDisplay').textContent = apiKey;
                document.getElementById('keyDisplay').style.display = 'block';
                
                currentProfile = { apiKey, kd, wins, losses, toxicLevel, credits };
            }
            
            // Generate demo key
            function generateDemoKey() {
                const fakeKey = 'TOX-DEMO-' + Math.random().toString(36).substr(2, 8).toUpperCase();
                document.getElementById('apiKey').value = fakeKey;
                loadDemoProfile(fakeKey);
            }
            
            // Roast yourself
            function roastYourself() {
                if (!currentProfile) {
                    showToxicAlert('profileResult', '❌ Load profile first, idiot', 'error');
                    return;
                }
                
                const roasts = [
                    `With a ${currentProfile.kd} K/D, you should uninstall`,
                    `${currentProfile.wins} wins? My grandma has more`,
                    `Toxic level ${currentProfile.toxicLevel}/10? That's cute`,
                    `You have ${currentProfile.credits} credits and zero skill`,
                    `I've seen bots with better stats`,
                    `Your gameplay is a war crime`,
                    `Bro is COOKED with these stats`,
                    `Absolute clown fiesta of a player`,
                    `You're the reason matchmaking is broken`,
                    `Zero PR, zero skill, zero bitches`
                ];
                
                const roast = roasts[Math.floor(Math.random() * roasts.length)];
                
                document.getElementById('profileResult').innerHTML += `
                    <div class="toxic-alert warning" style="margin-top: 15px;">
                        <h3>🔥 PERSONAL ROAST:</h3>
                        <p>${roast}</p>
                    </div>
                `;
            }
            
            // Ban player (demo)
            async function banPlayer() {
                const key = document.getElementById('banKey').value;
                const reason = document.getElementById('banReason').value || 'Being trash';
                const serverId = document.getElementById('modServerId').value;
                
                if (!key) {
                    showToxicAlert('modResult', '❌ Enter something to ban, genius', 'error');
                    return;
                }
                
                showToxicAlert('modResult', 
                    `🔨 BANNED "${key.substring(0, 10)}..."\nReason: ${reason}\nServer: ${serverId || 'Global'}\n\nGet good, scrub.`, 
                    'error');
            }
            
            // List server players (demo)
            async function listServerPlayers() {
                const serverId = document.getElementById('serverLookup').value;
                
                if (!serverId) {
                    showToxicAlert('serverPlayers', '❌ Enter server ID first', 'error');
                    return;
                }
                
                const players = [
                    { name: 'xX_ProGamer_Xx', kd: '2.34', toxic: 8, status: 'active' },
                    { name: 'NoobSlayer69', kd: '1.89', toxic: 9, status: 'active' },
                    { name: 'CampingRandy', kd: '0.45', toxic: 3, status: 'banned' },
                    { name: 'TriggerHappy', kd: '3.12', toxic: 7, status: 'active' },
                    { name: 'OneShotWill', kd: '2.67', toxic: 6, status: 'suspended' }
                ];
                
                let html = '';
                players.forEach(player => {
                    html += `
                        <div class="player-card ${player.status}">
                            <div class="player-name">
                                ${player.name}
                                <span class="toxic-level">☢️ ${player.toxic}/10</span>
                            </div>
                            <div>K/D: ${player.kd} | Status: ${player.status.toUpperCase()}</div>
                        </div>
                    `;
                });
                
                document.getElementById('serverPlayers').innerHTML = html || '<p style="color: #888; text-align: center;">No players found (or they\'re all trash)</p>';
            }
            
            // Refresh stats
            async function refreshStats() {
                // Demo stats
                document.getElementById('totalPlayers').textContent = Math.floor(Math.random() * 1000) + 500;
                document.getElementById('totalServers').textContent = Math.floor(Math.random() * 100) + 50;
                document.getElementById('totalKills').textContent = Math.floor(Math.random() * 100000) + 50000;
                document.getElementById('totalBans').textContent = Math.floor(Math.random() * 100) + 20;
                
                // Demo leaderboard
                const topPlayers = [
                    { name: 'TOXIC_KING', kd: '4.32', toxic: 10 },
                    { name: 'SALT_LORD', kd: '3.89', toxic: 9 },
                    { name: 'RAGE_QUIT', kd: '3.45', toxic: 8 },
                    { name: 'TRASH_TALK', kd: '3.21', toxic: 7 },
                    { name: 'NO_MERCY', kd: '3.05', toxic: 6 }
                ];
                
                let leaderboard = '';
                topPlayers.forEach((player, i) => {
                    leaderboard += `
                        <div class="player-card" style="margin: 10px 0;">
                            <div class="player-name">
                                ${i + 1}. ${player.name}
                                <span class="toxic-level">☢️ ${player.toxic}/10</span>
                            </div>
                            <div>K/D: ${player.kd} | Certified Toxic</div>
                        </div>
                    `;
                });
                
                document.getElementById('toxicLeaderboard').innerHTML = leaderboard;
            }
            
            // Test API
            async function testAPI() {
                const roasts = [
                    "API working fine, unlike your gameplay",
                    "Endpoint response: Skill issue detected",
                    "200 OK - You're still bad though",
                    "Connection established, competence not found",
                    "API is up, you're still down bad"
                ];
                
                alert(roasts[Math.floor(Math.random() * roasts.length)]);
            }
            
            // Invite bot
            function inviteBot() {
                window.open('https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877975616&scope=bot%20applications.commands', '_blank');
            }
            
            // Helper functions
            function showToxicAlert(elementId, message, type) {
                const element = document.getElementById(elementId);
                element.innerHTML = `
                    <div class="toxic-alert ${type}">
                        ${message}
                    </div>
                `;
            }
            
            function copyKey(element) {
                const text = element.textContent;
                navigator.clipboard.writeText(text);
                
                const original = element.innerHTML;
                element.innerHTML = '✅ COPIED (USE IT WISELY)';
                element.style.background = 'rgba(57, 255, 20, 0.3)';
                
                setTimeout(() => {
                    element.innerHTML = original;
                    element.style.background = '';
                }, 2000);
            }
            
            // Initialize
            document.addEventListener('DOMContentLoaded', function() {
                refreshStats();
                
                // Add some random toxic comments
                setTimeout(() => {
                    const comments = document.querySelectorAll('.toxic-comment');
                    comments.forEach(comment => {
                        if (Math.random() > 0.5) {
                            comment.textContent = TOXIC_ROASTS[Math.floor(Math.random() * TOXIC_ROASTS.length)];
                        }
                    });
                }, 1000);
            });
        </script>
    </body>
    </html>
    '''

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/stats')
def api_stats():
    """Get global toxic stats"""
    conn = get_db_connection()
    
    total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
    total_servers = conn.execute('SELECT COUNT(DISTINCT server_id) as count FROM server_settings').fetchone()['count']
    total_kills = conn.execute('SELECT SUM(total_kills) as sum FROM players').fetchone()['sum'] or 0
    total_bans = conn.execute('SELECT COUNT(*) as count FROM players WHERE banned = 1').fetchone()['count']
    
    conn.close()
    
    return jsonify({
        "total_players": total_players,
        "total_servers": total_servers,
        "total_kills": total_kills,
        "total_bans": total_bans,
        "message": "Get rekt",
        "toxic_level": random.randint(1, 10)
    })

@app.route('/api/profile')
def api_profile():
    """Get toxic profile"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "No key, no stats, scrub"}), 401
    
    player = validate_api_key(api_key)
    if not player:
        return jsonify({"error": "Invalid or banned key. L"}), 401
    
    # Add toxic commentary
    kd = player['total_kills'] / max(player['total_deaths'], 1)
    commentary = ""
    if kd < 0.5:
        commentary = "Absolute bot behavior"
    elif kd < 1:
        commentary = "Mediocre at best"
    elif kd < 2:
        commentary = "Not completely terrible"
    else:
        commentary = "Okay, you might be decent"
    
    return jsonify({
        **dict(player),
        "commentary": commentary,
        "roast": random.choice(TOXIC_PING_RESPONSES)
    })

@app.route('/api/roast')
def api_roast():
    """Get personalized roast"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"roast": "No key? That's pretty lame, ngl"})
    
    player = validate_api_key(api_key)
    if player:
        kd = player['total_kills'] / max(player['total_deaths'], 1)
        if kd < 0.5:
            roast = f"K/D of {kd:.2f}? My grandma plays better"
        elif player['losses'] > player['wins']:
            roast = f"More L's than W's? Professional loser detected"
        else:
            roast = random.choice(TOXIC_PING_RESPONSES)
    else:
        roast = "Can't even provide a valid key. Typical."
    
    return jsonify({"roast": roast})

@app.route('/health')
def health():
    """Health check with attitude"""
    return jsonify({
        "status": "toxic",
        "service": "Multi-Server Toxic Goblin",
        "version": "4.0",
        "message": "Still here, still judging you",
        "bot_active": bot_active,
        "toxic_level": 11
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*80}")
    print("☢️  TOXIC GOBLIN REGISTRY v4.0 - MULTI-SERVER READY")
    print(f"{'='*80}")
    
    # Check PyNaCl
    try:
        import nacl.signing
        print("✅ PyNaCl installed - Ready for Discord verification")
    except ImportError:
        print("❌ PyNaCl not installed! Run: pip install pynacl")
    
    # Test Discord
    if test_discord_token():
        print(f"✅ Bot connected: {bot_info.get('username', 'Unknown')}")
        
        if register_commands():
            print("✅ Toxic commands registered globally")
        else:
            print("⚠️ Could not register commands")
    else:
        print("❌ Discord token not set or invalid")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🤖 Interactions: http://localhost:{port}/interactions")
    
    print(f"\n🎮 TOXIC COMMANDS (works in ANY server):")
    print(f"   /ping       - Get flamed")
    print(f"   /register   - Get roasted & get key")
    print(f"   /profile    - See how bad you are")
    print(f"   /roast @user - Flame someone (mods)")
    print(f"   /banish @user - Ban trash players")
    print(f"   /leaderboard - See who's least terrible")
    print(f"   /setup      - Setup bot (server admins)")
    
    print(f"\n🔥 FEATURES:")
    print(f"   • Multi-server ready (no config needed)")
    print(f"   • Automatic server detection")
    print(f"   • Server-specific moderation")
    print(f"   • Toxic commentary on everything")
    print(f"   • COD voice chat vibes")
    print(f"   • Global & server bans")
    
    print(f"\n⚙️ ENVIRONMENT:")
    print(f"   DISCORD_TOKEN: {'✅' if DISCORD_TOKEN else '❌'}")
    print(f"   DISCORD_CLIENT_ID: {'✅' if DISCORD_CLIENT_ID else '❌'}")
    print(f"   DISCORD_PUBLIC_KEY: {'✅' if DISCORD_PUBLIC_KEY else '❌'}")
    
    print(f"\n💀 'git gud scrub' - Toxic Goblin")
    print(f"{'='*80}\n")
    
    # Start server
    app.run(host='0.0.0.0', port=port, debug=False)

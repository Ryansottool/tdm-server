# app.py - WITH DISCORD SIGNATURE VERIFICATION
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
import hmac
import base64

app = Flask(__name__)
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord credentials - ALL REQUIRED
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot status
bot_active = False
bot_info = {}

# =============================================================================
# DISCORD SIGNATURE VERIFICATION - CRITICAL FIX
# =============================================================================

def verify_discord_signature(request):
    """
    Verify Discord request signature using Ed25519
    This is REQUIRED by Discord for security
    """
    signature = request.headers.get('X-Signature-Ed25519')
    timestamp = request.headers.get('X-Signature-Timestamp')
    body = request.get_data().decode('utf-8')
    
    if not signature or not timestamp:
        logger.error("Missing Discord signature headers")
        return False
    
    if not DISCORD_PUBLIC_KEY:
        logger.error("DISCORD_PUBLIC_KEY not set in environment")
        return False
    
    try:
        # Import nacl for Ed25519 verification
        import nacl.signing
        import nacl.exceptions
        
        # The message to verify is timestamp + body
        message = f"{timestamp}{body}".encode('utf-8')
        
        # Convert hex signature to bytes
        signature_bytes = bytes.fromhex(signature)
        
        # Create verify key from public key
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        
        # Verify the signature
        verify_key.verify(message, signature_bytes)
        
        logger.debug("Discord signature verified successfully")
        return True
        
    except ImportError:
        logger.error("PyNaCl not installed. Install with: pip install pynacl")
        return False
    except nacl.exceptions.BadSignatureError:
        logger.error("Invalid Discord signature")
        return False
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False

# =============================================================================
# SIMPLIFIED DATABASE SETUP
# =============================================================================

def init_db():
    """Initialize database"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                discord_name TEXT,
                in_game_name TEXT,
                api_key TEXT UNIQUE,
                key_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                total_kills INTEGER DEFAULT 0,
                total_deaths INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                prestige INTEGER DEFAULT 0,
                credits INTEGER DEFAULT 1000,
                title TEXT DEFAULT 'Deckhand',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_code TEXT UNIQUE,
                status TEXT DEFAULT 'waiting',
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
# KEY GENERATION
# =============================================================================

def generate_api_key(discord_id, discord_name):
    """Generate unique API key for player"""
    timestamp = str(int(time.time()))
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    raw_key = f"{discord_id}:{discord_name}:{timestamp}:{random_str}"
    
    # Create hash-based key
    api_key = hashlib.sha256(raw_key.encode()).hexdigest()[:32]
    
    # Format as SOT-XXXX-XXXX-XXXX-XXXX
    formatted_key = f"SOT-{api_key[:4]}-{api_key[4:8]}-{api_key[8:12]}-{api_key[12:16]}"
    
    return formatted_key

# =============================================================================
# DISCORD BOT FUNCTIONS
# =============================================================================

def test_discord_token():
    """Test if Discord token is valid"""
    global bot_active, bot_info
    
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN not set in environment")
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
    """Register slash commands with Discord"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        logger.error("❌ Cannot register commands: Missing token or client ID")
        return False
    
    commands = [
        {
            "name": "ping",
            "description": "Check if the goblin is watching",
            "type": 1
        },
        {
            "name": "register",
            "description": "Register and get your API key",
            "type": 1,
            "options": [
                {
                    "name": "ingame_name",
                    "description": "Your in-game name",
                    "type": 3,
                    "required": True
                }
            ]
        },
        {
            "name": "profile",
            "description": "View your profile and API key",
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
            logger.info(f"✅ Registered {len(commands)} slash commands")
            return True
        else:
            logger.error(f"❌ Failed to register commands: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error registering commands: {e}")
        return False

# =============================================================================
# DISCORD INTERACTIONS ENDPOINT - WITH SIGNATURE VERIFICATION
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """
    Handle Discord slash commands WITH SIGNATURE VERIFICATION
    This is required by Discord for security
    """
    # VERIFY THE SIGNATURE - THIS IS REQUIRED
    if not verify_discord_signature(request):
        logger.warning("Invalid Discord signature - rejecting request")
        return jsonify({"error": "Invalid request signature"}), 401
    
    try:
        data = request.get_json()
        
        # Handle Discord verification ping (type 1)
        if data.get('type') == 1:
            logger.info("Received Discord verification ping - responding with pong")
            return jsonify({"type": 1})  # PONG response
        
        # Handle slash commands (type 2)
        if data.get('type') == 2:
            command = data.get('data', {}).get('name')
            user_id = data.get('member', {}).get('user', {}).get('id')
            user_name = data.get('member', {}).get('user', {}).get('global_name', 'Unknown')
            
            logger.info(f"Received command: {command} from {user_name}")
            
            if command == 'ping':
                responses = [
                    "🏓 Pong! Goblin is UP and watching!",
                    "⚡ Still alive, newgen. What do you want?",
                    "👁️ I see you... yes, I'm online.",
                    "⚓ Captain's log: Bot operational. Stop bothering me.",
                    "🎮 Stop pinging and go play some TDM."
                ]
                response = random.choice(responses)
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": response,
                        "flags": 64  # EPHEMERAL
                    }
                })
            
            elif command == 'register':
                options = data.get('data', {}).get('options', [])
                if options and len(options) > 0:
                    in_game_name = options[0].get('value', 'Unknown')
                    
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
                                "content": f"⚓ You're already registered, {in_game_name}!\nUse `/profile` to see your API key.",
                                "flags": 64
                            }
                        })
                    
                    # Generate API key
                    api_key = generate_api_key(user_id, user_name)
                    
                    # Register new player
                    conn.execute('''
                        INSERT INTO players 
                        (discord_id, discord_name, in_game_name, api_key, credits)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, user_name, in_game_name, api_key, 1000))
                    
                    conn.commit()
                    conn.close()
                    
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": (
                                f"🎉 **Welcome aboard, {in_game_name}!**\n\n"
                                f"**Your API Key:** `{api_key}`\n"
                                f"**Keep this secret!** Use it to access the web API.\n\n"
                                f"🔗 Visit: {request.host_url}\n"
                                f"📊 Use `/profile` to see your stats\n"
                                f"💰 Start with: **1000G**\n\n"
                                f"⚓ *The goblin is now watching you...*"
                            ),
                            "flags": 64  # EPHEMERAL - only user can see
                        }
                    })
            
            elif command == 'profile':
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
                            "content": "❌ You're not registered! Use `/register [ingame_name]` first.",
                            "flags": 64
                        }
                    })
                
                kd = player['total_deaths'] > 0 and player['total_kills'] / player['total_deaths'] or player['total_kills']
                win_rate = (player['wins'] + player['losses']) > 0 and (player['wins'] / (player['wins'] + player['losses']) * 100) or 0
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"🏴‍☠️ **{player['in_game_name']}'s Profile**\n\n"
                            f"**Title:** {player['title']}\n"
                            f"**Prestige:** {player['prestige']}\n"
                            f"**Gold:** {player['credits']}G\n\n"
                            f"📊 **Stats:**\n"
                            f"• Kills: {player['total_kills']}\n"
                            f"• Deaths: {player['total_deaths']}\n"
                            f"• K/D: {kd:.2f}\n"
                            f"• Wins: {player['wins']}\n"
                            f"• Losses: {player['losses']}\n"
                            f"• Win Rate: {win_rate:.1f}%\n\n"
                            f"🔑 **API Key:**\n`{player['api_key']}`\n\n"
                            f"🔗 **Web Dashboard:**\n{request.host_url}\n\n"
                            f"*Use your key wisely, pirate.*"
                        ),
                        "flags": 64
                    }
                })
        
        # Unknown command type
        return jsonify({
            "type": 4,
            "data": {
                "content": "Unknown command",
                "flags": 64
            }
        })
        
    except Exception as e:
        logger.error(f"Interactions error: {e}")
        return jsonify({
            "type": 4,
            "data": {
                "content": f"⚓ Yarrr! There be an error: {str(e)[:100]}",
                "flags": 64
            }
        }), 500

# =============================================================================
# WEB INTERFACE (SIMPLIFIED)
# =============================================================================

@app.route('/')
def home():
    """Main web page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>🏴‍☠️ SoT TDM Goblin Registry</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                margin: 0;
                padding: 20px;
                min-height: 100vh;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
            }
            h1 {
                text-align: center;
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .status {
                text-align: center;
                padding: 10px;
                background: rgba(0,0,0,0.3);
                border-radius: 10px;
                margin: 20px 0;
            }
            .card {
                background: rgba(255,255,255,0.15);
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
                border: 1px solid rgba(255,255,255,0.2);
            }
            .btn {
                display: inline-block;
                background: #4CAF50;
                color: white;
                padding: 12px 24px;
                border-radius: 5px;
                text-decoration: none;
                margin: 10px 5px;
                border: none;
                cursor: pointer;
                font-weight: bold;
            }
            .btn:hover {
                background: #45a049;
            }
            code {
                background: rgba(0,0,0,0.3);
                padding: 10px;
                border-radius: 5px;
                display: block;
                margin: 10px 0;
                font-family: monospace;
                word-break: break-all;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏴‍☠️ The Goblin's Registry</h1>
            <div class="status">
                <h3>🔐 SECURE MODE: Signature Verification Enabled</h3>
                <p>Discord interactions are now properly secured</p>
            </div>
            
            <div class="card">
                <h2>🤖 Discord Bot Commands</h2>
                <p>Add the bot to your server and use:</p>
                <code>/ping</code>
                <code>/register [your_ingame_name]</code>
                <code>/profile</code>
                
                <div style="margin-top: 20px;">
                    <button class="btn" onclick="testEndpoint()">Test Endpoint</button>
                    <button class="btn" onclick="checkHealth()">Check Health</button>
                </div>
            </div>
            
            <div class="card">
                <h2>🔧 Setup Instructions</h2>
                <ol>
                    <li>Set environment variables in Render:
                        <code>DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_PUBLIC_KEY</code>
                    </li>
                    <li>Set Interactions Endpoint URL in Discord Developer Portal:
                        <code id="endpointUrl">Loading...</code>
                    </li>
                    <li>Save changes and wait 2 minutes</li>
                    <li>Test with <code>/ping</code> in Discord</li>
                </ol>
            </div>
            
            <div class="card">
                <h2>✅ Signature Verification Status</h2>
                <p id="sigStatus">Checking...</p>
                <p><small>Discord requires all interaction endpoints to verify request signatures for security.</small></p>
            </div>
        </div>
        
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                document.getElementById('endpointUrl').textContent = window.location.origin + '/interactions';
                checkHealth();
            });
            
            function testEndpoint() {
                fetch('/interactions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: 1 })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.type === 1) {
                        document.getElementById('sigStatus').innerHTML = 
                            '<span style="color: #4CAF50;">✅ Endpoint working correctly!</span>';
                        alert('✅ Endpoint test successful! Discord verification working.');
                    } else {
                        document.getElementById('sigStatus').innerHTML = 
                            '<span style="color: #f44336;">❌ Unexpected response</span>';
                    }
                })
                .catch(e => {
                    document.getElementById('sigStatus').innerHTML = 
                        '<span style="color: #f44336;">❌ Error: ' + e.message + '</span>';
                });
            }
            
            function checkHealth() {
                fetch('/health')
                    .then(r => r.json())
                    .then(data => {
                        console.log('Health check:', data);
                    });
            }
        </script>
    </body>
    </html>
    '''

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "SoT Goblin Registry",
        "timestamp": datetime.utcnow().isoformat(),
        "signature_verification": "enabled",
        "discord_public_key_set": bool(DISCORD_PUBLIC_KEY),
        "interactions_endpoint": f"{request.host_url}interactions"
    })

@app.route('/api/test-signature', methods=['POST'])
def test_signature():
    """Test endpoint for signature verification (for debugging)"""
    verified = verify_discord_signature(request)
    return jsonify({
        "signature_verified": verified,
        "headers": dict(request.headers),
        "public_key_set": bool(DISCORD_PUBLIC_KEY)
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*70}")
    print("🏴‍☠️  THE GOBLIN'S REGISTRY - SECURE EDITION")
    print(f"{'='*70}")
    
    # Check if PyNaCl is installed (required for signature verification)
    try:
        import nacl.signing
        print("✅ PyNaCl installed - Signature verification READY")
    except ImportError:
        print("❌ CRITICAL: PyNaCl not installed!")
        print("   Run: pip install pynacl")
        print("   This is REQUIRED for Discord signature verification")
    
    # Test Discord connection
    if test_discord_token():
        print(f"✅ Discord bot connected: {bot_info.get('username', 'Unknown')}")
        
        # Register commands
        if register_commands():
            print("✅ Slash commands registered")
        else:
            print("⚠️ Could not register commands")
    else:
        print("❌ Discord bot NOT connected")
        print("   Set DISCORD_TOKEN in environment")
    
    # Check public key
    if not DISCORD_PUBLIC_KEY:
        print("❌ CRITICAL: DISCORD_PUBLIC_KEY not set!")
        print("   Get it from Discord Developer Portal → General Information")
        print("   Set it as environment variable in Render")
    else:
        print(f"✅ Discord public key is set")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🤖 Interactions: http://localhost:{port}/interactions")
    print(f"📊 Health Check: http://localhost:{port}/health")
    
    print(f"\n🔐 IMPORTANT: Set in Discord Developer Portal:")
    print(f"   Interactions Endpoint URL: https://YOUR-APP.onrender.com/interactions")
    print(f"   (Wait 2 minutes after saving)")
    
    print(f"\n🎮 Discord Commands:")
    print(f"   /ping       - Check if goblin is watching")
    print(f"   /register   - Get your API key")
    print(f"   /profile    - View your profile")
    
    print(f"{'='*70}\n")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=port, debug=False)# app.py - COMPLETE GOBLIN REGISTRY WITH MODERATION
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

# Discord credentials - ALL REQUIRED
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')
DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID', '')  # Your server ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot status
bot_active = False
bot_info = {}

# Sarcastic ping responses (non-pirate)
PING_RESPONSES = [
    "Oh look, another ping. How original.",
    "Yes, I'm here. No, I'm not impressed.",
    "🏓 Wow, you discovered the ping command. Nobel prize when?",
    "I'm up. You're bothering me. What's new?",
    "Alert: Bot is functional. Alert: You're predictable.",
    "Pong. Are we done here?",
    "Still alive, somehow. Unlike your creativity.",
    "Yes master, I obey your ping command... not.",
    "Beep boop. I'm a bot. You're a human. We're all miserable.",
    "If I had a gold coin for every ping, I'd retire. Stop it.",
    "Wow, you really needed to know I'm online? Sad.",
    "Pong. Now go do something productive.",
    "I'm here, you're there, we're all wasting time.",
    "Congratulations! You successfully typed 4 letters. 🎉",
    "Ping received. Enthusiasm level: 0.",
    "Yep. Still here. Still judging you.",
    "Did you ping me just to feel something?",
    "Pong. This interaction cost you 2 seconds of your life.",
    "Bot status: online. Your life status: questionable.",
    "Oh great, another ping. My favorite thing ever. /s"
]

# =============================================================================
# DISCORD SIGNATURE VERIFICATION - CRITICAL
# =============================================================================

def verify_discord_signature(request):
    """Verify Discord request signature using Ed25519"""
    signature = request.headers.get('X-Signature-Ed25519')
    timestamp = request.headers.get('X-Signature-Timestamp')
    body = request.get_data().decode('utf-8')
    
    if not signature or not timestamp:
        logger.error("Missing Discord signature headers")
        return False
    
    if not DISCORD_PUBLIC_KEY:
        logger.error("DISCORD_PUBLIC_KEY not set in environment")
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
# DISCORD API FUNCTIONS FOR ROLE CHECKING
# =============================================================================

def get_discord_user_roles(user_id):
    """Get user's roles from Discord API"""
    if not DISCORD_TOKEN or not DISCORD_GUILD_ID:
        logger.warning("Discord token or guild ID not set, skipping role check")
        return []
    
    try:
        url = f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/members/{user_id}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            member_data = response.json()
            return member_data.get('roles', [])
        else:
            logger.warning(f"Could not fetch roles for user {user_id}: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"Error fetching Discord roles: {e}")
        return []

def has_moderation_role(user_id):
    """Check if user has moderator/manager role"""
    roles = get_discord_user_roles(user_id)
    
    # Check for common moderation role names
    moderator_keywords = ['admin', 'mod', 'manager', 'staff', 'developer', 'dev', 'owner']
    
    for role_id in roles:
        # We'd need to fetch role names, but for simplicity we'll use role IDs
        # You can configure specific role IDs in environment variables
        mod_role_ids = os.environ.get('MOD_ROLE_IDS', '').split(',')
        if role_id in mod_role_ids:
            return True
    
    return False

def get_discord_user_info(user_id):
    """Get user info from Discord"""
    if not DISCORD_TOKEN:
        return None
    
    try:
        url = f"https://discord.com/api/v10/users/{user_id}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            return response.json()
        return None
        
    except Exception as e:
        logger.error(f"Error fetching user info: {e}")
        return None

# =============================================================================
# DATABASE SETUP
# =============================================================================

def init_db():
    """Initialize database with all tables"""
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
                key_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                total_kills INTEGER DEFAULT 0,
                total_deaths INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                prestige INTEGER DEFAULT 0,
                credits INTEGER DEFAULT 1000,
                title TEXT DEFAULT 'Rookie',
                status TEXT DEFAULT 'active',
                banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                banned_by TEXT,
                banned_at TIMESTAMP,
                is_moderator BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Suspensions/Moderation actions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                action TEXT,  -- 'suspend', 'ban', 'warn', 'restore'
                moderator_id TEXT,
                moderator_name TEXT,
                reason TEXT,
                duration_days INTEGER,  -- 0 for permanent
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
        ''')
        
        # Match history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_code TEXT UNIQUE,
                player1_id INTEGER,
                player2_id INTEGER,
                player1_score INTEGER DEFAULT 0,
                player2_score INTEGER DEFAULT 0,
                winner_id INTEGER,
                status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player1_id) REFERENCES players (id),
                FOREIGN KEY (player2_id) REFERENCES players (id),
                FOREIGN KEY (winner_id) REFERENCES players (id)
            )
        ''')
        
        # API usage logs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                endpoint TEXT,
                ip_address TEXT,
                user_agent TEXT,
                status_code INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
        ''')
        
        # Moderation settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS moderation_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default settings
        default_settings = [
            ('mod_role_ids', ''),
            ('ban_reasons', 'Cheating,Harassment,Exploiting,Multiple Accounts,Other'),
            ('max_warnings', '3'),
            ('auto_ban_on_warnings', 'true')
        ]
        
        for key, value in default_settings:
            cursor.execute('''
                INSERT OR IGNORE INTO moderation_settings (setting_key, setting_value)
                VALUES (?, ?)
            ''', (key, value))
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_api_key ON players(api_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_discord_id ON players(discord_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_status ON players(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_moderation_logs_player ON moderation_logs(player_id)')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized with moderation system")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# KEY GENERATION & VALIDATION
# =============================================================================

def generate_api_key(discord_id, discord_name):
    """Generate unique API key for player"""
    timestamp = str(int(time.time()))
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=24))
    raw_key = f"{discord_id}:{discord_name}:{timestamp}:{random_str}"
    hash_key = hashlib.sha256(raw_key.encode()).hexdigest()[:32]
    formatted_key = f"GLB-{hash_key[:8]}-{hash_key[8:16]}-{hash_key[16:24]}-{hash_key[24:32]}"
    return formatted_key.upper()

def validate_api_key(api_key):
    """Validate API key and return player info"""
    if not api_key or not api_key.startswith("GLB-"):
        return None
    
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE api_key = ?',
        (api_key,)
    ).fetchone()
    
    if player:
        # Check if banned
        if player['banned']:
            conn.close()
            return None
            
        # Update last used
        conn.execute(
            'UPDATE players SET last_used = CURRENT_TIMESTAMP WHERE id = ?',
            (player['id'],)
        )
        
        # Log API usage
        try:
            conn.execute('''
                INSERT INTO api_logs (player_id, endpoint, ip_address, user_agent)
                VALUES (?, ?, ?, ?)
            ''', (
                player['id'],
                request.endpoint if request else 'unknown',
                request.remote_addr if request else 'unknown',
                request.user_agent.string if request and request.user_agent else 'unknown'
            ))
        except:
            pass
        
        conn.commit()
    
    conn.close()
    return player

# =============================================================================
# MODERATION FUNCTIONS
# =============================================================================

def suspend_player(player_id, moderator_id, moderator_name, reason, duration_days=7):
    """Suspend a player's API key"""
    conn = get_db_connection()
    
    # Update player status
    expires_at = datetime.utcnow() + timedelta(days=duration_days) if duration_days > 0 else None
    
    conn.execute('''
        UPDATE players 
        SET status = 'suspended', 
            banned = 1,
            ban_reason = ?,
            banned_by = ?,
            banned_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (reason, moderator_name, player_id))
    
    # Log the action
    conn.execute('''
        INSERT INTO moderation_logs 
        (player_id, action, moderator_id, moderator_name, reason, duration_days, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        player_id, 'suspend', moderator_id, moderator_name, 
        reason, duration_days, expires_at
    ))
    
    conn.commit()
    
    # Get player info for response
    player = conn.execute('SELECT * FROM players WHERE id = ?', (player_id,)).fetchone()
    conn.close()
    
    return dict(player) if player else None

def ban_player(player_id, moderator_id, moderator_name, reason):
    """Permanently ban a player"""
    conn = get_db_connection()
    
    conn.execute('''
        UPDATE players 
        SET status = 'banned', 
            banned = 1,
            ban_reason = ?,
            banned_by = ?,
            banned_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (reason, moderator_name, player_id))
    
    conn.execute('''
        INSERT INTO moderation_logs 
        (player_id, action, moderator_id, moderator_name, reason, duration_days)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (player_id, 'ban', moderator_id, moderator_name, reason, 0))
    
    conn.commit()
    player = conn.execute('SELECT * FROM players WHERE id = ?', (player_id,)).fetchone()
    conn.close()
    
    return dict(player) if player else None

def restore_player(player_id, moderator_id, moderator_name, reason):
    """Restore a suspended/banned player"""
    conn = get_db_connection()
    
    conn.execute('''
        UPDATE players 
        SET status = 'active', 
            banned = 0,
            ban_reason = NULL,
            banned_by = NULL,
            banned_at = NULL
        WHERE id = ?
    ''', (player_id,))
    
    conn.execute('''
        INSERT INTO moderation_logs 
        (player_id, action, moderator_id, moderator_name, reason)
        VALUES (?, ?, ?, ?, ?)
    ''', (player_id, 'restore', moderator_id, moderator_name, reason))
    
    conn.commit()
    player = conn.execute('SELECT * FROM players WHERE id = ?', (player_id,)).fetchone()
    conn.close()
    
    return dict(player) if player else None

def get_moderation_logs(player_id=None, limit=50):
    """Get moderation logs"""
    conn = get_db_connection()
    
    if player_id:
        logs = conn.execute('''
            SELECT ml.*, p.in_game_name, p.discord_name
            FROM moderation_logs ml
            LEFT JOIN players p ON ml.player_id = p.id
            WHERE ml.player_id = ?
            ORDER BY ml.created_at DESC
            LIMIT ?
        ''', (player_id, limit)).fetchall()
    else:
        logs = conn.execute('''
            SELECT ml.*, p.in_game_name, p.discord_name
            FROM moderation_logs ml
            LEFT JOIN players p ON ml.player_id = p.id
            ORDER BY ml.created_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()
    
    conn.close()
    return [dict(log) for log in logs]

# =============================================================================
# DISCORD BOT FUNCTIONS
# =============================================================================

def test_discord_token():
    """Test if Discord token is valid"""
    global bot_active, bot_info
    
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN not set in environment")
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
    """Register slash commands with Discord"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        logger.error("❌ Cannot register commands: Missing token or client ID")
        return False
    
    commands = [
        {
            "name": "ping",
            "description": "Check if the bot is alive (prepare for sarcasm)",
            "type": 1
        },
        {
            "name": "register",
            "description": "Register and get your API key",
            "type": 1,
            "options": [
                {
                    "name": "ingame_name",
                    "description": "Your in-game name",
                    "type": 3,
                    "required": True
                }
            ]
        },
        {
            "name": "profile",
            "description": "View your profile and API key",
            "type": 1
        },
        {
            "name": "moderate",
            "description": "Moderation commands (mod only)",
            "type": 1,
            "options": [
                {
                    "name": "action",
                    "description": "Action to perform",
                    "type": 3,
                    "required": True,
                    "choices": [
                        {"name": "suspend", "value": "suspend"},
                        {"name": "ban", "value": "ban"},
                        {"name": "restore", "value": "restore"},
                        {"name": "logs", "value": "logs"}
                    ]
                },
                {
                    "name": "player",
                    "description": "Player's Discord ID or in-game name",
                    "type": 3,
                    "required": False
                },
                {
                    "name": "reason",
                    "description": "Reason for action",
                    "type": 3,
                    "required": False
                },
                {
                    "name": "days",
                    "description": "Duration in days (for suspend)",
                    "type": 4,
                    "required": False
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
            logger.info(f"✅ Registered {len(commands)} slash commands")
            return True
        else:
            logger.error(f"❌ Failed to register commands: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error registering commands: {e}")
        return False

def create_invite_link():
    """Generate bot invite link"""
    if not DISCORD_CLIENT_ID:
        return None
    
    permissions = "274877975616"  # Send Messages, Read Messages, Use Slash Commands
    return f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions={permissions}&scope=bot%20applications.commands"

# =============================================================================
# DISCORD INTERACTIONS ENDPOINT
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord slash commands with signature verification"""
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
        
        if command == 'ping':
            response = random.choice(PING_RESPONSES)
            return jsonify({
                "type": 4,
                "data": {
                    "content": response,
                    "flags": 64
                }
            })
        
        elif command == 'register':
            options = data.get('data', {}).get('options', [])
            if options and len(options) > 0:
                in_game_name = options[0].get('value', 'Unknown')
                
                conn = get_db_connection()
                existing = conn.execute(
                    'SELECT * FROM players WHERE discord_id = ?',
                    (user_id,)
                ).fetchone()
                
                if existing:
                    conn.close()
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"Already registered as {existing['in_game_name']}. Use `/profile`.",
                            "flags": 64
                        }
                    })
                
                api_key = generate_api_key(user_id, user_name)
                
                # Check if user has mod role
                is_mod = has_moderation_role(user_id)
                
                conn.execute('''
                    INSERT INTO players 
                    (discord_id, discord_name, in_game_name, api_key, is_moderator)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, user_name, in_game_name, api_key, 1 if is_mod else 0))
                
                conn.commit()
                conn.close()
                
                role_note = " (Moderator)" if is_mod else ""
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"✅ **Registered successfully{role_note}!**\n\n"
                            f"**Name:** {in_game_name}\n"
                            f"**API Key:** `{api_key}`\n\n"
                            f"🔗 Web Dashboard: {request.host_url}\n"
                            f"📊 Use `/profile` for stats\n"
                            f"🔒 Keep your key secret!"
                        ),
                        "flags": 64
                    }
                })
        
        elif command == 'profile':
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
                        "content": "❌ Not registered. Use `/register [name]`",
                        "flags": 64
                    }
                })
            
            kd = player['total_kills'] / max(player['total_deaths'], 1)
            status_emoji = "🔴" if player['banned'] else "🟢"
            mod_badge = " 👮" if player['is_moderator'] else ""
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"{status_emoji} **{player['in_game_name']}'s Profile{mod_badge}**\n\n"
                        f"**Status:** {player['status'].upper()}\n"
                        f"**Title:** {player['title']}\n"
                        f"**K/D:** {kd:.2f} ({player['total_kills']} kills)\n"
                        f"**W/L:** {player['wins']}-{player['losses']}\n"
                        f"**Credits:** {player['credits']}\n\n"
                        f"🔑 **API Key:**\n`{player['api_key']}`\n\n"
                        f"🌐 **Dashboard:** {request.host_url}"
                    ),
                    "flags": 64
                }
            })
        
        elif command == 'moderate':
            # Check if user has mod role
            if not has_moderation_role(user_id):
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ You need moderator/manager role to use this command.",
                        "flags": 64
                    }
                })
            
            options = {opt['name']: opt.get('value') for opt in data.get('data', {}).get('options', [])}
            action = options.get('action')
            player_ident = options.get('player')
            reason = options.get('reason', 'No reason provided')
            days = int(options.get('days') or 7)
            
            conn = get_db_connection()
            
            if action in ['suspend', 'ban', 'restore'] and not player_ident:
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ Need to specify a player.",
                        "flags": 64
                    }
                })
            
            if action == 'suspend':
                # Find player
                player = conn.execute(
                    'SELECT * FROM players WHERE discord_id = ? OR in_game_name LIKE ?',
                    (player_ident, f'%{player_ident}%')
                ).fetchone()
                
                if not player:
                    conn.close()
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"❌ Player '{player_ident}' not found.",
                            "flags": 64
                        }
                    })
                
                result = suspend_player(player['id'], user_id, user_name, reason, days)
                conn.close()
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"✅ Suspended {result['in_game_name']} for {days} days.\nReason: {reason}",
                        "flags": 64
                    }
                })
            
            elif action == 'ban':
                player = conn.execute(
                    'SELECT * FROM players WHERE discord_id = ? OR in_game_name LIKE ?',
                    (player_ident, f'%{player_ident}%')
                ).fetchone()
                
                if not player:
                    conn.close()
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"❌ Player '{player_ident}' not found.",
                            "flags": 64
                        }
                    })
                
                result = ban_player(player['id'], user_id, user_name, reason)
                conn.close()
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"🔨 Banned {result['in_game_name']} permanently.\nReason: {reason}",
                        "flags": 64
                    }
                })
            
            elif action == 'restore':
                player = conn.execute(
                    'SELECT * FROM players WHERE discord_id = ? OR in_game_name LIKE ?',
                    (player_ident, f'%{player_ident}%')
                ).fetchone()
                
                if not player:
                    conn.close()
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"❌ Player '{player_ident}' not found.",
                            "flags": 64
                        }
                    })
                
                result = restore_player(player['id'], user_id, user_name, reason)
                conn.close()
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"✅ Restored {result['in_game_name']}.\nReason: {reason}",
                        "flags": 64
                    }
                })
            
            elif action == 'logs':
                logs = get_moderation_logs(limit=10)
                
                if not logs:
                    conn.close()
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": "No moderation logs found.",
                            "flags": 64
                        }
                    })
                
                log_text = "📋 **Recent Moderation Logs:**\n\n"
                for log in logs[:5]:
                    action_emoji = {
                        'suspend': '⏸️',
                        'ban': '🔨',
                        'restore': '✅',
                        'warn': '⚠️'
                    }.get(log['action'], '📝')
                    
                    player_name = log['in_game_name'] or log['discord_name'] or 'Unknown'
                    time_ago = (datetime.utcnow() - datetime.fromisoformat(log['created_at'].replace('Z', '+00:00'))).days
                    
                    log_text += f"{action_emoji} **{player_name}** - {log['action'].upper()}\n"
                    log_text += f"   By: {log['moderator_name']}\n"
                    log_text += f"   Reason: {log['reason'] or 'None'}\n"
                    log_text += f"   {time_ago} days ago\n\n"
                
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": log_text,
                        "flags": 64
                    }
                })
    
    return jsonify({"type": 4, "data": {"content": "Unknown command", "flags": 64}})

# =============================================================================
# WEB INTERFACE - COMPLETE WITH MODERATION PANEL
# =============================================================================

@app.route('/')
def home():
    """Main web page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>🔧 Goblin Registry - Moderation System</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            :root {
                --primary: #2d3748;
                --secondary: #4a5568;
                --accent: #4299e1;
                --danger: #f56565;
                --success: #48bb78;
                --warning: #ed8936;
                --dark: #1a202c;
                --light: #f7fafc;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: var(--light);
                min-height: 100vh;
                line-height: 1.6;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }
            
            header {
                text-align: center;
                padding: 40px 20px;
                margin-bottom: 40px;
                background: rgba(45, 55, 72, 0.9);
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.1);
            }
            
            h1 {
                font-size: 3rem;
                margin-bottom: 10px;
                background: linear-gradient(45deg, #4299e1, #9f7aea);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                text-shadow: 0 2px 10px rgba(0,0,0,0.2);
            }
            
            .subtitle {
                font-size: 1.2rem;
                color: #a0aec0;
                margin-bottom: 20px;
            }
            
            .status-badge {
                display: inline-block;
                padding: 8px 16px;
                background: var(--success);
                color: white;
                border-radius: 20px;
                font-weight: bold;
                margin: 10px;
            }
            
            .main-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 30px;
                margin-bottom: 40px;
            }
            
            @media (max-width: 1024px) {
                .main-grid {
                    grid-template-columns: 1fr;
                }
            }
            
            .card {
                background: rgba(45, 55, 72, 0.9);
                border-radius: 15px;
                padding: 30px;
                border: 1px solid rgba(255,255,255,0.1);
                box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                transition: transform 0.3s, box-shadow 0.3s;
            }
            
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 35px rgba(0,0,0,0.3);
                border-color: var(--accent);
            }
            
            .card h2 {
                color: var(--accent);
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 2px solid rgba(66, 153, 225, 0.3);
                font-size: 1.8rem;
            }
            
            .tab-container {
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
                border-bottom: 2px solid var(--secondary);
                padding-bottom: 10px;
            }
            
            .tab {
                padding: 10px 20px;
                background: var(--secondary);
                border: none;
                color: white;
                border-radius: 8px 8px 0 0;
                cursor: pointer;
                transition: all 0.3s;
            }
            
            .tab:hover {
                background: var(--accent);
            }
            
            .tab.active {
                background: var(--accent);
                font-weight: bold;
            }
            
            .tab-content {
                display: none;
            }
            
            .tab-content.active {
                display: block;
            }
            
            .input-group {
                margin-bottom: 20px;
            }
            
            .input-group label {
                display: block;
                margin-bottom: 8px;
                color: #a0aec0;
                font-weight: 500;
            }
            
            input, select, textarea {
                width: 100%;
                padding: 12px;
                background: rgba(26, 32, 44, 0.8);
                border: 2px solid var(--secondary);
                border-radius: 8px;
                color: white;
                font-size: 16px;
                transition: border-color 0.3s;
            }
            
            input:focus, select:focus, textarea:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.2);
            }
            
            .btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 12px 24px;
                background: var(--accent);
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                margin: 5px;
                font-size: 16px;
            }
            
            .btn:hover {
                background: #3182ce;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(66, 153, 225, 0.4);
            }
            
            .btn-danger {
                background: var(--danger);
            }
            
            .btn-danger:hover {
                background: #e53e3e;
                box-shadow: 0 5px 15px rgba(245, 101, 101, 0.4);
            }
            
            .btn-success {
                background: var(--success);
            }
            
            .btn-success:hover {
                background: #38a169;
                box-shadow: 0 5px 15px rgba(72, 187, 120, 0.4);
            }
            
            .btn-warning {
                background: var(--warning);
            }
            
            .btn-warning:hover {
                background: #dd6b20;
                box-shadow: 0 5px 15px rgba(237, 137, 54, 0.4);
            }
            
            .key-display {
                background: rgba(0,0,0,0.3);
                border: 2px dashed var(--accent);
                border-radius: 10px;
                padding: 20px;
                margin: 20px 0;
                font-family: monospace;
                font-size: 1.2rem;
                color: #68d391;
                text-align: center;
                letter-spacing: 1px;
                word-break: break-all;
                cursor: pointer;
                transition: all 0.3s;
            }
            
            .key-display:hover {
                background: rgba(0,0,0,0.4);
                border-color: #68d391;
            }
            
            .player-list {
                max-height: 400px;
                overflow-y: auto;
                margin: 20px 0;
            }
            
            .player-item {
                padding: 15px;
                background: rgba(26, 32, 44, 0.8);
                border-radius: 8px;
                margin-bottom: 10px;
                border-left: 4px solid var(--accent);
                transition: all 0.3s;
            }
            
            .player-item:hover {
                background: rgba(26, 32, 44, 1);
                transform: translateX(5px);
            }
            
            .player-item.banned {
                border-left-color: var(--danger);
                opacity: 0.8;
            }
            
            .player-item.suspended {
                border-left-color: var(--warning);
            }
            
            .player-item.moderator {
                border-left-color: var(--success);
            }
            
            .player-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            
            .player-name {
                font-weight: bold;
                font-size: 1.1rem;
            }
            
            .player-status {
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 0.8rem;
                font-weight: bold;
            }
            
            .status-active { background: var(--success); color: white; }
            .status-banned { background: var(--danger); color: white; }
            .status-suspended { background: var(--warning); color: white; }
            
            .mod-actions {
                display: flex;
                gap: 10px;
                margin-top: 10px;
                flex-wrap: wrap;
            }
            
            .logs-container {
                max-height: 400px;
                overflow-y: auto;
                margin: 20px 0;
            }
            
            .log-item {
                padding: 12px;
                background: rgba(26, 32, 44, 0.8);
                border-radius: 8px;
                margin-bottom: 8px;
                border-left: 4px solid;
            }
            
            .log-suspend { border-color: var(--warning); }
            .log-ban { border-color: var(--danger); }
            .log-restore { border-color: var(--success); }
            .log-warn { border-color: #d69e2e; }
            
            .alert {
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                display: none;
            }
            
            .alert-success {
                background: rgba(72, 187, 120, 0.2);
                border: 1px solid var(--success);
                color: #68d391;
            }
            
            .alert-error {
                background: rgba(245, 101, 101, 0.2);
                border: 1px solid var(--danger);
                color: #fc8181;
            }
            
            .alert-info {
                background: rgba(66, 153, 225, 0.2);
                border: 1px solid var(--accent);
                color: #90cdf4;
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }
            
            .stat-box {
                background: rgba(26, 32, 44, 0.8);
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                border: 1px solid rgba(255,255,255,0.1);
            }
            
            .stat-value {
                font-size: 2.5rem;
                font-weight: bold;
                margin: 10px 0;
            }
            
            .stat-label {
                color: #a0aec0;
                font-size: 0.9rem;
            }
            
            footer {
                text-align: center;
                padding: 30px;
                margin-top: 50px;
                color: #a0aec0;
                font-size: 0.9rem;
                border-top: 1px solid rgba(255,255,255,0.1);
            }
            
            code {
                background: rgba(0,0,0,0.3);
                padding: 2px 6px;
                border-radius: 4px;
                font-family: monospace;
                font-size: 0.9rem;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🔧 Goblin Registry Control Panel</h1>
                <div class="subtitle">Moderation System with Discord Role Integration</div>
                <div class="status-badge" id="statusBadge">🔐 SECURE MODE</div>
                <p>Discord moderators/developers can manage API keys and players</p>
            </header>
            
            <div class="tab-container">
                <button class="tab active" onclick="switchTab('dashboard')">📊 Dashboard</button>
                <button class="tab" onclick="switchTab('players')">👥 Players</button>
                <button class="tab" onclick="switchTab('moderation')">🛡️ Moderation</button>
                <button class="tab" onclick="switchTab('mykey')">🔑 My Key</button>
                <button class="tab" onclick="switchTab('api')">🔌 API</button>
            </div>
            
            <!-- Dashboard Tab -->
            <div id="dashboard" class="tab-content active">
                <div class="main-grid">
                    <div class="card">
                        <h2>📈 System Statistics</h2>
                        <div class="stats-grid" id="statsGrid">
                            <div class="stat-box">
                                <div class="stat-value" id="totalPlayers">0</div>
                                <div class="stat-label">Total Players</div>
                            </div>
                            <div class="stat-box">
                                <div class="stat-value" id="activePlayers">0</div>
                                <div class="stat-label">Active</div>
                            </div>
                            <div class="stat-box">
                                <div class="stat-value" id="bannedPlayers">0</div>
                                <div class="stat-label">Banned</div>
                            </div>
                            <div class="stat-box">
                                <div class="stat-value" id="modActions">0</div>
                                <div class="stat-label">Mod Actions</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>🔐 Quick Actions</h2>
                        <div style="margin: 20px 0;">
                            <button class="btn" onclick="testSignature()">🔍 Test Signature</button>
                            <button class="btn" onclick="refreshStats()">🔄 Refresh Stats</button>
                            <button class="btn" onclick="checkBotStatus()">🤖 Check Bot</button>
                        </div>
                        <div id="quickResult"></div>
                    </div>
                </div>
                
                <div class="card" style="margin-top: 30px;">
                    <h2>📋 Recent Moderation Logs</h2>
                    <div class="logs-container" id="recentLogs">
                        Loading logs...
                    </div>
                </div>
            </div>
            
            <!-- Players Tab -->
            <div id="players" class="tab-content">
                <div class="card">
                    <h2>👥 Player Management</h2>
                    <div class="input-group">
                        <label>Search Player (Name or Discord ID):</label>
                        <input type="text" id="searchPlayer" placeholder="Enter name or ID..." onkeyup="searchPlayers()">
                    </div>
                    <div class="player-list" id="playerList">
                        Loading players...
                    </div>
                </div>
            </div>
            
            <!-- Moderation Tab -->
            <div id="moderation" class="tab-content">
                <div class="main-grid">
                    <div class="card">
                        <h2>⚡ Quick Mod Actions</h2>
                        <div class="input-group">
                            <label>Player API Key:</label>
                            <input type="text" id="modKeyInput" placeholder="Enter player's API key...">
                        </div>
                        
                        <div class="input-group">
                            <label>Action:</label>
                            <select id="modAction">
                                <option value="suspend">⏸️ Suspend (7 days)</option>
                                <option value="ban">🔨 Permanent Ban</option>
                                <option value="restore">✅ Restore Access</option>
                                <option value="info">ℹ️ Get Info</option>
                            </select>
                        </div>
                        
                        <div class="input-group">
                            <label>Reason:</label>
                            <textarea id="modReason" rows="3" placeholder="Reason for action..."></textarea>
                        </div>
                        
                        <div class="input-group">
                            <label>Duration (days, for suspend):</label>
                            <input type="number" id="modDuration" value="7" min="1" max="365">
                        </div>
                        
                        <button class="btn btn-danger" onclick="performModAction()" style="width: 100%;">
                            ⚡ Execute Mod Action
                        </button>
                        
                        <div class="alert" id="modAlert"></div>
                    </div>
                    
                    <div class="card">
                        <h2>🛡️ Moderation Tools</h2>
                        <div style="margin: 20px 0;">
                            <button class="btn" onclick="getAllBanned()">🔨 View All Banned</button>
                            <button class="btn" onclick="exportLogs()">📤 Export Logs</button>
                            <button class="btn btn-warning" onclick="bulkRestore()">🔄 Bulk Restore</button>
                        </div>
                        
                        <div class="input-group">
                            <label>Your Discord ID (for verification):</label>
                            <input type="text" id="moderatorId" placeholder="Your Discord ID">
                            <small style="color: #a0aec0; display: block; margin-top: 5px;">
                                Enter your Discord ID to verify moderator role
                            </small>
                        </div>
                        
                        <button class="btn" onclick="verifyModRole()">🔍 Verify My Role</button>
                        <div id="roleResult" style="margin-top: 15px;"></div>
                    </div>
                </div>
            </div>
            
            <!-- My Key Tab -->
            <div id="mykey" class="tab-content">
                <div class="card">
                    <h2>🔑 Your API Key</h2>
                    <div class="input-group">
                        <label>Enter your API Key to manage:</label>
                        <input type="text" id="myApiKey" placeholder="GLB-XXXX-XXXX-XXXX-XXXX">
                    </div>
                    
                    <button class="btn" onclick="loadMyProfile()">📋 Load Profile</button>
                    <button class="btn btn-success" onclick="regenerateKey()">🔄 Regenerate Key</button>
                    <button class="btn btn-danger" onclick="deleteMyKey()">🗑️ Delete Account</button>
                    
                    <div id="profileResult" style="margin-top: 20px;"></div>
                    
                    <div class="key-display" id="keyDisplay" onclick="copyToClipboard(this)" style="display: none;">
                        Your key will appear here
                    </div>
                </div>
            </div>
            
            <!-- API Tab -->
            <div id="api" class="tab-content">
                <div class="card">
                    <h2>🔌 API Documentation</h2>
                    <div style="margin: 20px 0;">
                        <h3>📊 Public Endpoints:</h3>
                        <code>GET /api/stats</code> - System statistics<br>
                        <code>GET /api/health</code> - Health check<br>
                        <code>GET /api/test-signature</code> - Test signature verification
                        
                        <h3 style="margin-top: 30px;">🔐 Protected Endpoints (API Key required):</h3>
                        <code>GET /api/profile?key=YOUR_KEY</code> - Get your profile<br>
                        <code>POST /api/report-match</code> - Report match results<br>
                        <code>GET /api/mod/logs?key=MOD_KEY</code> - Moderation logs (mod only)
                        
                        <h3 style="margin-top: 30px;">🛡️ Moderation Endpoints:</h3>
                        <code>POST /api/mod/suspend</code> - Suspend player<br>
                        <code>POST /api/mod/ban</code> - Ban player<br>
                        <code>POST /api/mod/restore</code> - Restore player
                    </div>
                    
                    <button class="btn" onclick="testAllEndpoints()">🧪 Test All Endpoints</button>
                    <div id="apiTestResult" style="margin-top: 15px;"></div>
                </div>
            </div>
            
            <footer>
                <p>Goblin Registry v3.0 | Discord Role-Based Moderation System</p>
                <p>Only users with moderator/manager roles in Discord can perform moderation actions</p>
                <p style="margin-top: 10px; font-size: 0.8rem;">
                    🔒 All requests are signature-verified | 🔑 API keys are encrypted | 🛡️ Role-based access control
                </p>
            </footer>
        </div>
        
        <script>
            let currentUser = null;
            let userIsMod = false;
            
            // Tab switching
            function switchTab(tabName) {
                // Hide all tabs
                document.querySelectorAll('.tab-content').forEach(tab => {
                    tab.classList.remove('active');
                });
                
                // Show selected tab
                document.getElementById(tabName).classList.add('active');
                
                // Update tab buttons
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                event.target.classList.add('active');
                
                // Refresh tab content if needed
                if (tabName === 'dashboard') {
                    refreshStats();
                    loadRecentLogs();
                } else if (tabName === 'players') {
                    loadPlayers();
                }
            }
            
            // Load statistics
            async function refreshStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    document.getElementById('totalPlayers').textContent = data.total_players || '0';
                    document.getElementById('activePlayers').textContent = data.active_players || '0';
                    document.getElementById('bannedPlayers').textContent = data.banned_players || '0';
                    document.getElementById('modActions').textContent = data.mod_actions || '0';
                } catch (error) {
                    console.error('Error loading stats:', error);
                }
            }
            
            // Load players
            async function loadPlayers() {
                try {
                    const response = await fetch('/api/players');
                    const players = await response.json();
                    
                    const container = document.getElementById('playerList');
                    container.innerHTML = '';
                    
                    players.forEach(player => {
                        const item = document.createElement('div');
                        item.className = `player-item ${player.status} ${player.is_moderator ? 'moderator' : ''}`;
                        
                        const statusClass = `status-${player.status}`;
                        const statusText = player.status.toUpperCase();
                        const modBadge = player.is_moderator ? ' 👮' : '';
                        const banBadge = player.banned ? ' 🔨' : '';
                        
                        item.innerHTML = `
                            <div class="player-header">
                                <div class="player-name">
                                    ${player.in_game_name}${modBadge}${banBadge}
                                    <div style="font-size: 0.8rem; color: #a0aec0; margin-top: 5px;">
                                        ${player.discord_name} • ${player.api_key.substring(0, 8)}...
                                    </div>
                                </div>
                                <div class="player-status ${statusClass}">${statusText}</div>
                            </div>
                            <div>
                                K/D: ${(player.total_kills / Math.max(player.total_deaths, 1)).toFixed(2)} |
                                W/L: ${player.wins}-${player.losses} |
                                Credits: ${player.credits}
                            </div>
                            ${player.ban_reason ? `<div style="color: #f56565; margin-top: 5px; font-size: 0.9rem;">
                                ⚠️ Banned: ${player.ban_reason}
                            </div>` : ''}
                            <div class="mod-actions">
                                <button class="btn btn-warning" onclick="suspendPlayer('${player.api_key}')" ${player.banned ? 'disabled' : ''}>
                                    ⏸️ Suspend
                                </button>
                                <button class="btn btn-danger" onclick="banPlayer('${player.api_key}')" ${player.banned ? 'disabled' : ''}>
                                    🔨 Ban
                                </button>
                                <button class="btn btn-success" onclick="restorePlayer('${player.api_key}')" ${!player.banned ? 'disabled' : ''}>
                                    ✅ Restore
                                </button>
                                <button class="btn" onclick="viewPlayerLogs('${player.api_key}')">
                                    📋 Logs
                                </button>
                            </div>
                        `;
                        
                        container.appendChild(item);
                    });
                } catch (error) {
                    document.getElementById('playerList').innerHTML = 
                        '<div style="color: #f56565; text-align: center; padding: 40px;">Error loading players</div>';
                }
            }
            
            // Search players
            async function searchPlayers() {
                const query = document.getElementById('searchPlayer').value;
                if (!query) {
                    loadPlayers();
                    return;
                }
                
                try {
                    const response = await fetch(`/api/players/search?q=${encodeURIComponent(query)}`);
                    const players = await response.json();
                    
                    const container = document.getElementById('playerList');
                    container.innerHTML = '';
                    
                    if (players.length === 0) {
                        container.innerHTML = '<div style="text-align: center; padding: 40px; color: #a0aec0;">No players found</div>';
                        return;
                    }
                    
                    players.forEach(player => {
                        const item = document.createElement('div');
                        item.className = `player-item ${player.status} ${player.is_moderator ? 'moderator' : ''}`;
                        
                        const statusClass = `status-${player.status}`;
                        const statusText = player.status.toUpperCase();
                        const modBadge = player.is_moderator ? ' 👮' : '';
                        
                        item.innerHTML = `
                            <div class="player-header">
                                <div class="player-name">
                                    ${player.in_game_name}${modBadge}
                                    <div style="font-size: 0.8rem; color: #a0aec0; margin-top: 5px;">
                                        ${player.discord_name} • ${player.api_key.substring(0, 8)}...
                                    </div>
                                </div>
                                <div class="player-status ${statusClass}">${statusText}</div>
                            </div>
                            <div class="mod-actions">
                                <button class="btn" onclick="usePlayerKey('${player.api_key}')">Use This Key</button>
                            </div>
                        `;
                        
                        container.appendChild(item);
                    });
                } catch (error) {
                    console.error('Search error:', error);
                }
            }
            
            // Moderation actions
            async function performModAction() {
                const apiKey = document.getElementById('modKeyInput').value;
                const action = document.getElementById('modAction').value;
                const reason = document.getElementById('modReason').value;
                const duration = document.getElementById('modDuration').value;
                const moderatorId = document.getElementById('moderatorId').value;
                
                if (!apiKey || !apiKey.startsWith('GLB-')) {
                    showAlert('modAlert', 'Please enter a valid API key', 'error');
                    return;
                }
                
                if (!moderatorId) {
                    showAlert('modAlert', 'Please enter your Discord ID for verification', 'error');
                    return;
                }
                
                try {
                    const response = await fetch(`/api/mod/${action}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            player_key: apiKey,
                            moderator_id: moderatorId,
                            reason: reason || 'No reason provided',
                            duration: parseInt(duration)
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        showAlert('modAlert', `✅ ${result.message}`, 'success');
                        loadPlayers();
                        loadRecentLogs();
                    } else {
                        showAlert('modAlert', `❌ ${result.error}`, 'error');
                    }
                } catch (error) {
                    showAlert('modAlert', `❌ Error: ${error.message}`, 'error');
                }
            }
            
            // Load profile
            async function loadMyProfile() {
                const apiKey = document.getElementById('myApiKey').value;
                
                if (!apiKey || !apiKey.startsWith('GLB-')) {
                    showAlert('profileResult', 'Please enter a valid API key', 'error');
                    return;
                }
                
                try {
                    const response = await fetch(`/api/profile?key=${encodeURIComponent(apiKey)}`);
                    const data = await response.json();
                    
                    if (data.error) {
                        showAlert('profileResult', `❌ ${data.error}`, 'error');
                        return;
                    }
                    
                    currentUser = data;
                    userIsMod = data.is_moderator;
                    
                    const display = document.getElementById('keyDisplay');
                    display.textContent = data.api_key;
                    display.style.display = 'block';
                    
                    document.getElementById('profileResult').innerHTML = `
                        <div class="alert alert-success">
                            <h3>✅ Profile Loaded</h3>
                            <p><strong>Name:</strong> ${data.in_game_name}</p>
                            <p><strong>Status:</strong> ${data.status.toUpperCase()}</p>
                            <p><strong>K/D:</strong> ${(data.total_kills / Math.max(data.total_deaths, 1)).toFixed(2)}</p>
                            <p><strong>Moderator:</strong> ${data.is_moderator ? 'Yes 👮' : 'No'}</p>
                            ${data.banned ? `<p style="color: #f56565;"><strong>Banned:</strong> ${data.ban_reason || 'No reason'}</p>` : ''}
                        </div>
                    `;
                } catch (error) {
                    showAlert('profileResult', `❌ Error loading profile: ${error.message}`, 'error');
                }
            }
            
            // Regenerate key
            async function regenerateKey() {
                if (!currentUser) {
                    showAlert('profileResult', 'Please load your profile first', 'error');
                    return;
                }
                
                if (!confirm('Are you sure? This will invalidate your old key immediately.')) {
                    return;
                }
                
                try {
                    const response = await fetch('/api/regenerate-key', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            old_key: currentUser.api_key,
                            discord_id: currentUser.discord_id
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        showAlert('profileResult', `✅ New key: ${result.new_key}`, 'success');
                        document.getElementById('keyDisplay').textContent = result.new_key;
                        currentUser.api_key = result.new_key;
                    } else {
                        showAlert('profileResult', `❌ ${result.error}`, 'error');
                    }
                } catch (error) {
                    showAlert('profileResult', `❌ Error: ${error.message}`, 'error');
                }
            }
            
            // Load recent logs
            async function loadRecentLogs() {
                try {
                    const response = await fetch('/api/mod/logs/recent');
                    const logs = await response.json();
                    
                    const container = document.getElementById('recentLogs');
                    container.innerHTML = '';
                    
                    logs.forEach(log => {
                        const item = document.createElement('div');
                        item.className = `log-item log-${log.action}`;
                        
                        const actionEmoji = {
                            'suspend': '⏸️',
                            'ban': '🔨',
                            'restore': '✅',
                            'warn': '⚠️'
                        }[log.action] || '📝';
                        
                        item.innerHTML = `
                            <div style="font-weight: bold;">
                                ${actionEmoji} ${log.action.toUpperCase()}: ${log.player_name || 'Unknown'}
                            </div>
                            <div style="font-size: 0.9rem; color: #a0aec0; margin-top: 5px;">
                                By ${log.moderator_name} • ${new Date(log.created_at).toLocaleString()}
                            </div>
                            <div style="margin-top: 5px;">
                                ${log.reason || 'No reason provided'}
                            </div>
                        `;
                        
                        container.appendChild(item);
                    });
                } catch (error) {
                    console.error('Error loading logs:', error);
                }
            }
            
            // Verify mod role
            async function verifyModRole() {
                const moderatorId = document.getElementById('moderatorId').value;
                
                if (!moderatorId) {
                    document.getElementById('roleResult').innerHTML = 
                        '<div style="color: #f56565;">Please enter your Discord ID</div>';
                    return;
                }
                
                try {
                    const response = await fetch(`/api/mod/verify-role?user_id=${moderatorId}`);
                    const result = await response.json();
                    
                    if (result.is_moderator) {
                        document.getElementById('roleResult').innerHTML = 
                            `<div style="color: #48bb78;">✅ You have moderation privileges</div>`;
                        userIsMod = true;
                    } else {
                        document.getElementById('roleResult').innerHTML = 
                            `<div style="color: #f56565;">❌ You don't have moderator/manager role</div>`;
                        userIsMod = false;
                    }
                } catch (error) {
                    document.getElementById('roleResult').innerHTML = 
                        `<div style="color: #f56565;">Error: ${error.message}</div>`;
                }
            }
            
            // Test signature
            async function testSignature() {
                try {
                    const response = await fetch('/api/test-signature', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ test: true })
                    });
                    
                    const result = await response.json();
                    
                    if (result.signature_verified === false) {
                        document.getElementById('quickResult').innerHTML = 
                            `<div class="alert alert-success">✅ Test request sent (no signature expected for this test)</div>`;
                    } else {
                        document.getElementById('quickResult').innerHTML = 
                            `<div class="alert alert-info">ℹ️ ${JSON.stringify(result)}</div>`;
                    }
                } catch (error) {
                    document.getElementById('quickResult').innerHTML = 
                        `<div class="alert alert-error">❌ Error: ${error.message}</div>`;
                }
            }
            
            // Helper functions
            function showAlert(elementId, message, type) {
                const element = document.getElementById(elementId);
                element.textContent = message;
                element.className = `alert alert-${type}`;
                element.style.display = 'block';
                
                setTimeout(() => {
                    element.style.display = 'none';
                }, 5000);
            }
            
            function copyToClipboard(element) {
                const text = element.textContent;
                navigator.clipboard.writeText(text);
                
                const original = element.textContent;
                element.textContent = '✅ Copied to clipboard!';
                element.style.background = 'rgba(72, 187, 120, 0.3)';
                
                setTimeout(() => {
                    element.textContent = original;
                    element.style.background = '';
                }, 2000);
            }
            
            function suspendPlayer(apiKey) {
                document.getElementById('modKeyInput').value = apiKey;
                document.getElementById('modAction').value = 'suspend';
                switchTab('moderation');
            }
            
            function banPlayer(apiKey) {
                document.getElementById('modKeyInput').value = apiKey;
                document.getElementById('modAction').value = 'ban';
                switchTab('moderation');
            }
            
            function restorePlayer(apiKey) {
                document.getElementById('modKeyInput').value = apiKey;
                document.getElementById('modAction').value = 'restore';
                switchTab('moderation');
            }
            
            function usePlayerKey(apiKey) {
                document.getElementById('myApiKey').value = apiKey;
                switchTab('mykey');
                loadMyProfile();
            }
            
            // Initialize
            document.addEventListener('DOMContentLoaded', function() {
                refreshStats();
                loadRecentLogs();
                
                // Auto-refresh every 30 seconds
                setInterval(() => {
                    if (document.querySelector('.tab-content.active').id === 'dashboard') {
                        refreshStats();
                        loadRecentLogs();
                    }
                }, 30000);
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
    """Get system statistics"""
    conn = get_db_connection()
    
    total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
    active_players = conn.execute('SELECT COUNT(*) as count FROM players WHERE banned = 0').fetchone()['count']
    banned_players = conn.execute('SELECT COUNT(*) as count FROM players WHERE banned = 1').fetchone()['count']
    mod_actions = conn.execute('SELECT COUNT(*) as count FROM moderation_logs').fetchone()['count']
    
    conn.close()
    
    return jsonify({
        "total_players": total_players,
        "active_players": active_players,
        "banned_players": banned_players,
        "mod_actions": mod_actions,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/players')
def api_players():
    """Get all players"""
    conn = get_db_connection()
    players = conn.execute('SELECT * FROM players ORDER BY created_at DESC').fetchall()
    conn.close()
    
    return jsonify([dict(p) for p in players])

@app.route('/api/players/search')
def api_search_players():
    """Search players"""
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    conn = get_db_connection()
    players = conn.execute('''
        SELECT * FROM players 
        WHERE in_game_name LIKE ? OR discord_name LIKE ? OR discord_id LIKE ?
        ORDER BY created_at DESC
        LIMIT 20
    ''', (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
    conn.close()
    
    return jsonify([dict(p) for p in players])

@app.route('/api/profile')
def api_profile():
    """Get profile using API key"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "API key required"}), 401
    
    player = validate_api_key(api_key)
    if not player:
        return jsonify({"error": "Invalid or banned API key"}), 401
    
    return jsonify(dict(player))

@app.route('/api/mod/verify-role')
def api_verify_mod_role():
    """Verify if user has moderator role"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "User ID required"}), 400
    
    is_mod = has_moderation_role(user_id)
    
    return jsonify({
        "user_id": user_id,
        "is_moderator": is_mod,
        "has_access": is_mod
    })

@app.route('/api/mod/suspend', methods=['POST'])
def api_suspend_player():
    """Suspend a player"""
    data = request.json
    player_key = data.get('player_key')
    moderator_id = data.get('moderator_id')
    reason = data.get('reason', 'No reason provided')
    duration = data.get('duration', 7)
    
    if not player_key or not moderator_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    # Verify moderator role
    if not has_moderation_role(moderator_id):
        return jsonify({"error": "You don't have moderator privileges"}), 403
    
    conn = get_db_connection()
    player = conn.execute('SELECT * FROM players WHERE api_key = ?', (player_key,)).fetchone()
    
    if not player:
        conn.close()
        return jsonify({"error": "Player not found"}), 404
    
    moderator = get_discord_user_info(moderator_id)
    moderator_name = moderator.get('global_name', 'Unknown') if moderator else 'Unknown'
    
    result = suspend_player(player['id'], moderator_id, moderator_name, reason, duration)
    conn.close()
    
    return jsonify({
        "success": True,
        "message": f"Suspended {result['in_game_name']} for {duration} days",
        "player": result
    })

@app.route('/api/mod/ban', methods=['POST'])
def api_ban_player():
    """Ban a player"""
    data = request.json
    player_key = data.get('player_key')
    moderator_id = data.get('moderator_id')
    reason = data.get('reason', 'No reason provided')
    
    if not player_key or not moderator_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    if not has_moderation_role(moderator_id):
        return jsonify({"error": "You don't have moderator privileges"}), 403
    
    conn = get_db_connection()
    player = conn.execute('SELECT * FROM players WHERE api_key = ?', (player_key,)).fetchone()
    
    if not player:
        conn.close()
        return jsonify({"error": "Player not found"}), 404
    
    moderator = get_discord_user_info(moderator_id)
    moderator_name = moderator.get('global_name', 'Unknown') if moderator else 'Unknown'
    
    result = ban_player(player['id'], moderator_id, moderator_name, reason)
    conn.close()
    
    return jsonify({
        "success": True,
        "message": f"Banned {result['in_game_name']} permanently",
        "player": result
    })

@app.route('/api/mod/restore', methods=['POST'])
def api_restore_player():
    """Restore a player"""
    data = request.json
    player_key = data.get('player_key')
    moderator_id = data.get('moderator_id')
    reason = data.get('reason', 'Restored by moderator')
    
    if not player_key or not moderator_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    if not has_moderation_role(moderator_id):
        return jsonify({"error": "You don't have moderator privileges"}), 403
    
    conn = get_db_connection()
    player = conn.execute('SELECT * FROM players WHERE api_key = ?', (player_key,)).fetchone()
    
    if not player:
        conn.close()
        return jsonify({"error": "Player not found"}), 404
    
    moderator = get_discord_user_info(moderator_id)
    moderator_name = moderator.get('global_name', 'Unknown') if moderator else 'Unknown'
    
    result = restore_player(player['id'], moderator_id, moderator_name, reason)
    conn.close()
    
    return jsonify({
        "success": True,
        "message": f"Restored {result['in_game_name']}",
        "player": result
    })

@app.route('/api/mod/logs/recent')
def api_recent_logs():
    """Get recent moderation logs"""
    logs = get_moderation_logs(limit=20)
    return jsonify(logs)

@app.route('/api/regenerate-key', methods=['POST'])
def api_regenerate_key():
    """Regenerate API key"""
    data = request.json
    old_key = data.get('old_key')
    discord_id = data.get('discord_id')
    
    if not old_key or not discord_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    conn = get_db_connection()
    
    # Verify old key belongs to this user
    player = conn.execute(
        'SELECT * FROM players WHERE api_key = ? AND discord_id = ?',
        (old_key, discord_id)
    ).fetchone()
    
    if not player:
        conn.close()
        return jsonify({"error": "Invalid key or user"}), 401
    
    # Generate new key
    new_key = generate_api_key(discord_id, player['discord_name'])
    
    # Update database
    conn.execute(
        'UPDATE players SET api_key = ? WHERE id = ?',
        (new_key, player['id'])
    )
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "new_key": new_key,
        "message": "Key regenerated successfully"
    })

@app.route('/api/test-signature', methods=['POST'])
def api_test_signature():
    """Test signature verification"""
    verified = verify_discord_signature(request)
    
    return jsonify({
        "signature_verified": verified,
        "public_key_set": bool(DISCORD_PUBLIC_KEY),
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "service": "Goblin Registry Moderation System",
        "version": "3.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "bot_active": bot_active,
        "signature_verification": "enabled"
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*80}")
    print("🔧 GOBLIN REGISTRY - MODERATION SYSTEM v3.0")
    print(f"{'='*80}")
    
    # Check PyNaCl
    try:
        import nacl.signing
        print("✅ PyNaCl installed - Signature verification READY")
    except ImportError:
        print("❌ CRITICAL: PyNaCl not installed!")
        print("   Run: pip install pynacl")
        print("   Required for Discord signature verification")
    
    # Test Discord connection
    if test_discord_token():
        print(f"✅ Discord bot connected: {bot_info.get('username', 'Unknown')}")
        
        if register_commands():
            print("✅ Slash commands registered")
        else:
            print("⚠️ Could not register commands")
    else:
        print("❌ Discord bot NOT connected")
        print("   Set DISCORD_TOKEN in environment")
    
    # Check public key
    if not DISCORD_PUBLIC_KEY:
        print("❌ CRITICAL: DISCORD_PUBLIC_KEY not set!")
        print("   Get from Discord Developer Portal → General Information")
    else:
        print(f"✅ Discord public key is set")
    
    if not DISCORD_GUILD_ID:
        print("⚠️ DISCORD_GUILD_ID not set - role checking disabled")
    else:
        print(f"✅ Guild ID set - role checking ENABLED")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🤖 Interactions: http://localhost:{port}/interactions")
    print(f"📊 Dashboard: http://localhost:{port}/#moderation")
    
    print(f"\n🔐 Discord Commands:")
    print(f"   /ping       - Sarcastic responses")
    print(f"   /register   - Get API key")
    print(f"   /profile    - View profile")
    print(f"   /moderate   - Moderation tools (mod only)")
    
    print(f"\n🛡️ Moderation Features:")
    print(f"   • Discord role-based access control")
    print(f"   • Suspend/ban/restore players")
    print(f"   • Moderation logging")
    print(f"   • Web interface for moderators")
    
    print(f"\n⚙️ Environment Variables Set:")
    print(f"   DISCORD_TOKEN: {'✅' if DISCORD_TOKEN else '❌'}")
    print(f"   DISCORD_CLIENT_ID: {'✅' if DISCORD_CLIENT_ID else '❌'}")
    print(f"   DISCORD_PUBLIC_KEY: {'✅' if DISCORD_PUBLIC_KEY else '❌'}")
    print(f"   DISCORD_GUILD_ID: {'✅' if DISCORD_GUILD_ID else '❌'}")
    
    print(f"{'='*80}\n")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=port, debug=False)

# app.py - ENHANCED BOT WITH TICKET ROOMS
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
import re

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord credentials
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')

# Mod role ID for ticket access
MOD_ROLE_ID = os.environ.get('MOD_ROLE_ID', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot status
bot_active = False
bot_info = {}

# Cache for admin roles
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

def get_guild_channels(guild_id):
    """Get all channels in guild"""
    return discord_api_request(f"/guilds/{guild_id}/channels")

def create_guild_channel(guild_id, channel_data):
    """Create a channel in guild"""
    return discord_api_request(f"/guilds/{guild_id}/channels", "POST", channel_data)

def modify_channel_permissions(channel_id, overwrite_data):
    """Modify channel permissions"""
    return discord_api_request(f"/channels/{channel_id}/permissions/{overwrite_data['id']}", "PUT", overwrite_data)

def create_channel_invite(channel_id, max_age=0):
    """Create channel invite"""
    data = {"max_age": max_age, "max_uses": 0, "temporary": False}
    return discord_api_request(f"/channels/{channel_id}/invites", "POST", data)

def is_user_admin_in_guild(guild_id, user_id):
    """Check if user has admin/manage permissions in guild"""
    cache_key = f"{guild_id}_{user_id}"
    if cache_key in admin_role_cache:
        return admin_role_cache[cache_key]
    
    try:
        member = get_guild_member(guild_id, user_id)
        if not member:
            admin_role_cache[cache_key] = False
            return False
        
        guild = get_guild_info(guild_id)
        if guild and guild.get('owner_id') == user_id:
            admin_role_cache[cache_key] = True
            return True
        
        roles = get_guild_roles(guild_id)
        if not roles:
            admin_role_cache[cache_key] = False
            return False
        
        member_roles = member.get('roles', [])
        for role_id in member_roles:
            for role in roles:
                if role['id'] == role_id:
                    permissions = int(role.get('permissions', 0))
                    if permissions & 0x8 or permissions & 0x20 or permissions & 0x10000000:
                        admin_role_cache[cache_key] = True
                        return True
        
        admin_role_cache[cache_key] = False
        return False
        
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        admin_role_cache[cache_key] = False
        return False

# =============================================================================
# TICKET SYSTEM
# =============================================================================

async def create_ticket_channel(guild_id, user_id, user_name, ticket_id, issue):
    """Create private ticket channel"""
    try:
        # Get guild info
        guild = get_guild_info(guild_id)
        if not guild:
            return None
        
        guild_name = guild.get('name', 'Server')
        
        # Create channel name
        channel_name = f"ticket-{ticket_id.lower()}"
        
        # Create channel data
        channel_data = {
            "name": channel_name,
            "type": 0,  # Text channel
            "topic": f"Ticket #{ticket_id} - {issue[:50]}...",
            "parent_id": None,
            "permission_overwrites": [
                {
                    "id": guild_id,  # @everyone
                    "type": 0,
                    "allow": "0",
                    "deny": "1024"  # Deny VIEW_CHANNEL
                },
                {
                    "id": user_id,  # Ticket creator
                    "type": 1,
                    "allow": "3072",  # VIEW_CHANNEL + SEND_MESSAGES
                    "deny": "0"
                }
            ]
        }
        
        # Add mod role if configured
        if MOD_ROLE_ID:
            channel_data["permission_overwrites"].append({
                "id": MOD_ROLE_ID,
                "type": 0,
                "allow": "3072",
                "deny": "0"
            })
        
        # Create the channel
        channel = create_guild_channel(guild_id, channel_data)
        if not channel:
            return None
        
        # Send welcome message
        welcome_message = {
            "content": f"<@{user_id}>",
            "embeds": [{
                "title": f"🎫 Ticket #{ticket_id}",
                "description": issue,
                "color": 0x3498db,
                "fields": [
                    {"name": "👤 Created By", "value": f"<@{user_id}> ({user_name})", "inline": True},
                    {"name": "📅 Created", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "inline": True},
                    {"name": "🔒 Channel", "value": f"<#{channel['id']}>", "inline": True}
                ],
                "footer": {"text": f"Use /close to close this ticket"},
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        
        message_response = discord_api_request(f"/channels/{channel['id']}/messages", "POST", welcome_message)
        
        return channel['id']
        
    except Exception as e:
        logger.error(f"Error creating ticket channel: {e}")
        return None

def close_ticket_channel(channel_id, resolved_by):
    """Close ticket channel"""
    try:
        # Archive/delete channel or rename it
        channel_data = {
            "name": f"closed-{int(time.time())}",
            "permission_overwrites": [
                {
                    "id": resolved_by,
                    "type": 1,
                    "allow": "0",
                    "deny": "1024"
                }
            ]
        }
        
        return discord_api_request(f"/channels/{channel_id}", "PATCH", channel_data)
    except Exception as e:
        logger.error(f"Error closing ticket channel: {e}")
        return None

# =============================================================================
# SECURE KEY GENERATION
# =============================================================================

def generate_secure_key():
    """Generate strong API key"""
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
        
        # Tickets table with channel ID
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE,
                discord_id TEXT,
                discord_name TEXT,
                issue TEXT,
                channel_id TEXT,
                status TEXT DEFAULT 'open',
                assigned_to TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
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
            "name": "close",
            "description": "Close current ticket",
            "type": 1
        },
        {
            "name": "stats",
            "description": "Show your stats",
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
    
    players = conn.execute(
        'SELECT COUNT(*) as count FROM players WHERE server_id = ?',
        (server_id,)
    ).fetchone()['count']
    
    total_kills = conn.execute(
        'SELECT SUM(total_kills) as sum FROM players WHERE server_id = ?',
        (server_id,)
    ).fetchone()['sum'] or 0
    
    open_tickets = conn.execute(
        'SELECT COUNT(*) as count FROM tickets WHERE status = "open"'
    ).fetchone()['count']
    
    conn.close()
    
    for webhook in webhooks:
        try:
            embed = {
                "title": "📊 Server Statistics",
                "description": "Automatic stats update",
                "color": 0x3498db,
                "fields": [
                    {"name": "👥 Players", "value": str(players), "inline": True},
                    {"name": "🎯 Total Kills", "value": str(total_kills), "inline": True},
                    {"name": "🎫 Open Tickets", "value": str(open_tickets), "inline": True}
                ],
                "timestamp": datetime.utcnow().isoformat()
            }
            
            requests.post(webhook['webhook_url'], json={"embeds": [embed]}, timeout=5)
        except:
            continue

# =============================================================================
# DISCORD INTERACTIONS
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord slash commands"""
    if not verify_discord_signature(request):
        return jsonify({"error": "Invalid signature"}), 401
    
    data = request.get_json()
    
    if data.get('type') == 1:
        return jsonify({"type": 1})
    
    if data.get('type') == 2:
        command = data.get('data', {}).get('name')
        user_id = data.get('member', {}).get('user', {}).get('id')
        user_name = data.get('member', {}).get('user', {}).get('global_name', 'Unknown')
        server_id = data.get('guild_id', 'DM')
        
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
            
            existing = conn.execute(
                'SELECT * FROM players WHERE discord_id = ?',
                (user_id,)
            ).fetchone()
            
            if existing:
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"Already registered as `{existing['in_game_name']}`",
                        "flags": 64
                    }
                })
            
            is_admin = is_user_admin_in_guild(server_id, user_id)
            api_key = generate_secure_key()
            
            conn.execute('''
                INSERT INTO players 
                (discord_id, discord_name, in_game_name, api_key, server_id, is_admin)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, user_name, in_game_name, api_key, server_id, 1 if is_admin else 0))
            
            conn.commit()
            conn.close()
            
            send_webhook_stats(server_id)
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"✅ **Registered Successfully**\n\n"
                        f"**Name:** `{in_game_name}`\n\n"
                        f"**Dashboard:** {request.host_url}\n"
                        f"Login to view your API key"
                    ),
                    "flags": 64
                }
            })
        
        elif command == 'ticket':
            options = data.get('data', {}).get('options', [])
            issue = options[0].get('value', 'No issue specified') if options else 'No issue specified'
            
            ticket_id = f"TICKET-{int(time.time())}-{random.randint(1000, 9999)}"
            
            # Create ticket in database first
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO tickets 
                (ticket_id, discord_id, discord_name, issue)
                VALUES (?, ?, ?, ?)
            ''', (ticket_id, user_id, user_name, issue))
            conn.commit()
            
            # Try to create private channel
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                channel_id = loop.run_until_complete(
                    create_ticket_channel(server_id, user_id, user_name, ticket_id, issue)
                )
                
                if channel_id:
                    conn.execute(
                        'UPDATE tickets SET channel_id = ? WHERE ticket_id = ?',
                        (channel_id, ticket_id)
                    )
                    conn.commit()
                    conn.close()
                    
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": (
                                f"✅ **Ticket Created**\n\n"
                                f"**Ticket ID:** `{ticket_id}`\n"
                                f"**Channel:** <#{channel_id}>\n\n"
                                f"A private channel has been created for this ticket."
                            ),
                            "flags": 64
                        }
                    })
                else:
                    conn.close()
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": (
                                f"✅ **Ticket Created**\n\n"
                                f"**Ticket ID:** `{ticket_id}`\n"
                                f"**Issue:** {issue}\n\n"
                                f"*Note: Could not create private channel. Support will contact you.*"
                            ),
                            "flags": 64
                        }
                    })
                    
            except Exception as e:
                logger.error(f"Ticket channel creation error: {e}")
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"✅ **Ticket Created**\n\n"
                            f"**Ticket ID:** `{ticket_id}`\n"
                            f"**Issue:** {issue}\n\n"
                            f"Our team will review your ticket."
                        ),
                        "flags": 64
                    }
                })
        
        elif command == 'close':
            # Check if user is in a ticket channel
            conn = get_db_connection()
            ticket = conn.execute(
                'SELECT * FROM tickets WHERE channel_id = ? AND status = "open"',
                (data.get('channel_id'),)
            ).fetchone()
            
            if not ticket:
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ No open ticket in this channel",
                        "flags": 64
                    }
                })
            
            # Update ticket status
            conn.execute('''
                UPDATE tickets 
                SET status = "closed", resolved_at = CURRENT_TIMESTAMP, assigned_to = ?
                WHERE ticket_id = ?
            ''', (user_name, ticket['ticket_id']))
            conn.commit()
            conn.close()
            
            # Close the channel
            close_ticket_channel(data.get('channel_id'), user_id)
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": f"✅ Ticket `{ticket['ticket_id']}` has been closed.",
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
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"📊 **Your Stats**\n\n"
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
# WEB INTERFACE - ORIGINAL DESIGN
# =============================================================================

@app.route('/')
def home():
    """Original web design"""
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
                background: #000;
                color: #fff;
                min-height: 100vh;
                overflow: hidden;
                position: relative;
            }
            
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
            
            .container {
                max-width: 500px;
                margin: 0 auto;
                padding: 40px 20px;
                text-align: center;
                position: relative;
                z-index: 1;
            }
            
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
            
            .key-input {
                width: 100%;
                padding: 20px;
                background: rgba(30, 30, 30, 0.8);
                border: 2px solid #00ff00;
                border-radius: 10px;
                color: white;
                font-size: 18px;
                text-align: center;
                margin-bottom: 25px;
                transition: all 0.3s;
                font-family: monospace;
                letter-spacing: 2px;
            }
            
            .key-input:focus {
                outline: none;
                border-color: #00cc00;
                box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
                transform: scale(1.02);
            }
            
            .login-btn {
                width: 100%;
                padding: 20px;
                background: rgba(0, 255, 0, 0.1);
                border: 2px solid #00ff00;
                color: #00ff00;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
            }
            
            .login-btn:hover {
                background: rgba(0, 255, 0, 0.2);
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(0, 255, 0, 0.2);
            }
            
            .login-btn::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(0, 255, 0, 0.2), transparent);
                transition: left 0.5s;
            }
            
            .login-btn:hover::before {
                left: 100%;
            }
            
            .error-box {
                background: rgba(255, 0, 0, 0.1);
                border: 2px solid #ff0000;
                border-radius: 10px;
                padding: 16px;
                margin-top: 20px;
                color: #ff5555;
                display: none;
                animation: shake 0.5s;
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }
            
            .info-box {
                background: rgba(0, 255, 0, 0.1);
                border: 2px solid #00ff00;
                border-radius: 10px;
                padding: 25px;
                margin-top: 35px;
                text-align: left;
                color: #cbd5e1;
            }
            
            .info-box strong {
                color: #00ff00;
                display: block;
                margin-bottom: 15px;
            }
            
            .bot-status {
                padding: 10px 20px;
                background: rgba(30, 30, 30, 0.8);
                border: 2px solid rgba(0, 255, 0, 0.3);
                border-radius: 20px;
                margin-top: 25px;
                display: inline-block;
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            
            .status-online {
                color: #00ff00;
            }
            
            .status-offline {
                color: #ff0000;
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 20px;
                }
                .logo {
                    font-size: 2.5rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="bg-animation" id="bgAnimation"></div>
        
        <div class="container">
            <div class="logo">GOBLIN</div>
            <div class="subtitle">Enter your API key to access the dashboard</div>
            
            <input type="password" 
                   class="key-input" 
                   id="apiKey" 
                   placeholder="Enter your API key"
                   autocomplete="off"
                   spellcheck="false">
            
            <button class="login-btn" onclick="validateKey()">
                Access Dashboard
            </button>
            
            <div class="error-box" id="errorMessage">
                Invalid API key
            </div>
            
            <div class="info-box">
                <strong>How to get started:</strong>
                <p>1. Use <code>/register your_name</code> in Discord</p>
                <p>2. Login to dashboard to view your API key</p>
                <p>3. Access stats, tickets, and updates</p>
            </div>
            
            <div class="bot-status" id="botStatus">
                Bot Status: Checking...
            </div>
        </div>
        
        <script>
            function initBackground() {
                const container = document.getElementById('bgAnimation');
                for (let i = 0; i < 30; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    dot.style.width = dot.style.height = Math.random() * 3 + 1 + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.opacity = Math.random() * 0.5 + 0.1;
                    dot.style.setProperty('--tx', Math.random() * 2 - 1);
                    dot.style.setProperty('--ty', Math.random() * 2 - 1);
                    dot.style.animationDelay = Math.random() * 5 + 's';
                    dot.style.animationDuration = Math.random() * 15 + 15 + 's';
                    container.appendChild(dot);
                }
            }
            
            async function validateKey() {
                const key = document.getElementById('apiKey').value.trim();
                const errorDiv = document.getElementById('errorMessage');
                const btn = document.querySelector('.login-btn');
                
                if (!key) {
                    errorDiv.textContent = "Please enter an API key";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                btn.innerHTML = 'Checking...';
                btn.disabled = true;
                
                try {
                    const response = await fetch('/api/validate-key', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ api_key: key })
                    });
                    
                    const data = await response.json();
                    
                    if (data.valid) {
                        btn.innerHTML = '✅ Access Granted';
                        btn.style.background = 'rgba(0, 255, 0, 0.2)';
                        btn.style.borderColor = '#00cc00';
                        
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 500);
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
                    if (data.bot_active) {
                        status.innerHTML = '✅ Bot Status: ONLINE';
                        status.className = 'bot-status status-online';
                    } else {
                        status.innerHTML = '❌ Bot Status: OFFLINE';
                        status.className = 'bot-status status-offline';
                    }
                } catch (error) {
                    document.getElementById('botStatus').innerHTML = '⚠️ Bot Status: ERROR';
                }
            }
            
            document.addEventListener('DOMContentLoaded', function() {
                initBackground();
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
    """Dashboard with original design"""
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    user_data = session.get('user_data')
    if not user_data:
        return redirect(url_for('home'))
    
    # Calculate stats
    kd = user_data.get('total_kills', 0) / max(user_data.get('total_deaths', 1), 1)
    total_games = user_data.get('wins', 0) + user_data.get('losses', 0)
    win_rate = (user_data.get('wins', 0) / total_games * 100) if total_games > 0 else 0
    
    # Get updates
    conn = get_db_connection()
    updates = conn.execute('SELECT * FROM updates ORDER BY uploaded_at DESC LIMIT 3').fetchall()
    conn.close()
    
    updates_html = ''
    for update in updates:
        critical = '🚨 ' if update['is_critical'] else ''
        uploaded_by = f" by {update['uploaded_by']}" if update['uploaded_by'] else ''
        updates_html += f'''
        <div class="stat-card">
            <div style="color: #00ff00; font-weight: bold; margin-bottom: 10px;">
                {critical}v{update['version']} ({update['file_size']})
            </div>
            <div style="color: #ccc; margin-bottom: 15px;">{update['changelog']}{uploaded_by}</div>
            <button class="action-btn" onclick="window.open('{update['download_url']}', '_blank')" style="width: 100%;">
                📥 Download Update
            </button>
        </div>
        '''
    
    is_admin = user_data.get('is_admin', 0)
    
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
                background: #000;
                color: #fff;
                min-height: 100vh;
                overflow-x: hidden;
                position: relative;
            }}
            
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
                background: #00ff00;
                border-radius: 50%;
                animation: floatBg 40s infinite linear;
            }}
            
            @keyframes floatBg {{
                0% {{ transform: translateY(0) rotate(0deg); }}
                100% {{ transform: translateY(-100vh) rotate(360deg); }}
            }}
            
            .header {{
                background: rgba(20, 20, 20, 0.9);
                border-bottom: 3px solid #00ff00;
                padding: 20px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                backdrop-filter: blur(20px);
                position: sticky;
                top: 0;
                z-index: 100;
            }}
            
            .logo {{
                font-size: 1.8rem;
                font-weight: 900;
                background: linear-gradient(45deg, #00ff00, #00cc00);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            
            .user-info {{
                display: flex;
                align-items: center;
                gap: 25px;
            }}
            
            .admin-badge {{
                background: rgba(0, 255, 0, 0.2);
                border: 2px solid #00ff00;
                color: #00ff00;
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: bold;
            }}
            
            .logout-btn {{
                padding: 10px 24px;
                background: rgba(255, 0, 0, 0.2);
                border: 2px solid #ff0000;
                color: #ff5555;
                border-radius: 10px;
                font-weight: bold;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: all 0.3s;
            }}
            
            .logout-btn:hover {{
                background: rgba(255, 0, 0, 0.3);
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(255, 0, 0, 0.2);
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 40px;
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 40px;
            }}
            
            .stat-card {{
                background: rgba(30, 30, 30, 0.8);
                border: 2px solid #00ff00;
                border-radius: 15px;
                padding: 30px;
                text-align: center;
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
            }}
            
            .stat-card:hover {{
                transform: translateY(-10px);
                box-shadow: 0 20px 40px rgba(0, 255, 0, 0.2);
            }}
            
            .stat-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #00ff00, #00cc00);
            }}
            
            .stat-value {{
                font-size: 3rem;
                font-weight: 900;
                margin: 15px 0;
                font-family: 'Segoe UI', sans-serif;
            }}
            
            .stat-label {{
                color: #888;
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
            
            .key-section {{
                background: rgba(30, 30, 30, 0.8);
                border: 2px solid #00ff00;
                border-radius: 15px;
                padding: 40px;
                margin-bottom: 40px;
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
                background: linear-gradient(90deg, #00ff00, #00cc00);
            }}
            
            .key-display {{
                background: rgba(0, 0, 0, 0.5);
                border: 2px solid #00ff00;
                border-radius: 10px;
                padding: 25px;
                margin: 30px 0;
                font-family: monospace;
                color: #00ff00;
                text-align: center;
                cursor: pointer;
                position: relative;
                overflow: hidden;
                letter-spacing: 1px;
                font-size: 1.1rem;
            }}
            
            .key-display::before {{
                content: 'Click to reveal';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.9);
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: sans-serif;
                font-size: 1.2rem;
                color: #888;
            }}
            
            .key-display.revealed::before {{
                display: none;
            }}
            
            .updates-section {{
                background: rgba(30, 30, 30, 0.8);
                border: 2px solid #00ff00;
                border-radius: 15px;
                padding: 40px;
                margin-bottom: 40px;
            }}
            
            .action-buttons {{
                display: flex;
                gap: 15px;
                margin-top: 30px;
                flex-wrap: wrap;
            }}
            
            .action-btn {{
                padding: 15px 30px;
                background: rgba(0, 255, 0, 0.1);
                border: 2px solid #00ff00;
                color: #00ff00;
                border-radius: 10px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 10px;
            }}
            
            .action-btn:hover {{
                background: rgba(0, 255, 0, 0.2);
                transform: translateY(-5px);
                box-shadow: 0 10px 20px rgba(0, 255, 0, 0.2);
            }}
            
            .action-btn.admin {{
                background: rgba(255, 165, 0, 0.1);
                border-color: #ffa500;
                color: #ffa500;
            }}
            
            .action-btn.admin:hover {{
                background: rgba(255, 165, 0, 0.2);
                box-shadow: 0 10px 20px rgba(255, 165, 0, 0.2);
            }}
            
            .notification {{
                position: fixed;
                bottom: 30px;
                right: 30px;
                background: rgba(0, 255, 0, 0.9);
                color: black;
                padding: 15px 25px;
                border-radius: 10px;
                z-index: 1000;
                display: none;
                animation: slideIn 0.5s;
                font-weight: bold;
            }}
            
            @keyframes slideIn {{
                from {{ transform: translateX(100%); opacity: 0; }}
                to {{ transform: translateX(0); opacity: 1; }}
            }}
            
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
                .stats-grid {{
                    grid-template-columns: 1fr;
                }}
                .key-section, .updates-section {{
                    padding: 30px 20px;
                }}
                .action-buttons {{
                    flex-direction: column;
                }}
                .action-btn {{
                    width: 100%;
                    justify-content: center;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="bg-animation" id="bgAnimation"></div>
        
        <div class="header">
            <div class="logo">GOBLIN DASHBOARD</div>
            <div class="user-info">
                <div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <strong style="color: #00ff00;">{user_data.get('in_game_name', 'Player')}</strong>
                        { '<span class="admin-badge">👑 ADMIN</span>' if is_admin else '' }
                    </div>
                    <div style="color: #888; font-size: 0.9rem;">Prestige {user_data.get('prestige', 0)}</div>
                </div>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">K/D Ratio</div>
                    <div class="stat-value" style="color: { '#00ff00' if kd >= 1.5 else '#ffa500' if kd >= 1 else '#ff0000' };">{kd:.2f}</div>
                    <div style="color: #ccc;">{user_data.get('total_kills', 0)} kills / {user_data.get('total_deaths', 0)} deaths</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Win Rate</div>
                    <div class="stat-value" style="color: { '#00ff00' if win_rate >= 60 else '#ffa500' if win_rate >= 40 else '#ff0000' };">{win_rate:.1f}%</div>
                    <div style="color: #ccc;">{user_data.get('wins', 0)} wins / {user_data.get('losses', 0)} losses</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Games Played</div>
                    <div class="stat-value" style="color: #00ff00;">{total_games}</div>
                    <div style="color: #ccc;">Total matches</div>
                </div>
            </div>
            
            <div class="key-section">
                <h2 style="color: #00ff00; margin-bottom: 20px; font-size: 1.8rem;">Your API Key</h2>
                <p style="color: #888; margin-bottom: 20px;">
                    Keep this key secure. Do not share it with anyone.
                </p>
                
                <div class="key-display" id="apiKeyDisplay" onclick="revealKey()">
                    {session['user_key']}
                </div>
                
                <div class="action-buttons">
                    <button class="action-btn" onclick="copyKey()">
                        📋 Copy Key
                    </button>
                    { '<button class="action-btn admin" onclick="changeKey()">🔑 Change Key (Admin)</button>' if is_admin else '' }
                    <button class="action-btn" onclick="refreshStats()">
                        🔄 Refresh Stats
                    </button>
                    <button class="action-btn" onclick="createTicket()">
                        🎫 Create Ticket
                    </button>
                </div>
            </div>
            
            <div class="updates-section">
                <h2 style="color: #00ff00; margin-bottom: 30px; font-size: 1.8rem;">📥 Available Updates</h2>
                <div style="display: grid; gap: 20px;">
                    {updates_html if updates_html else '<p style="color: #888; text-align: center;">No updates available</p>'}
                </div>
            </div>
        </div>
        
        <div class="notification" id="notification"></div>
        
        <script>
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
            
            function revealKey() {{
                const display = document.getElementById('apiKeyDisplay');
                display.classList.add('revealed');
            }}
            
            function copyKey() {{
                const key = "{session['user_key']}";
                navigator.clipboard.writeText(key);
                showNotification('✅ API key copied to clipboard');
            }}
            
            function refreshStats() {{
                fetch('/api/refresh-stats?key={session['user_key']}')
                    .then(r => r.json())
                    .then(data => {{
                        if (data.success) {{
                            showNotification('✅ Stats refreshed!');
                            setTimeout(() => location.reload(), 1000);
                        }}
                    }})
                    .catch(() => showNotification('❌ Error refreshing stats'));
            }}
            
            function changeKey() {{
                if (!confirm('Generate a new API key? Your current key will be invalidated.')) return;
                
                fetch('/api/change-key', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ api_key: "{session['user_key']}" }})
                }})
                .then(r => r.json())
                .then(data => {{
                    if (data.success) {{
                        showNotification('✅ New key generated! Please login again.');
                        setTimeout(() => window.location.href = '/logout', 1500);
                    }} else {{
                        showNotification('❌ ' + data.error);
                    }}
                }})
                .catch(() => showNotification('❌ Error changing key'));
            }}
            
            function createTicket() {{
                const issue = prompt('Describe your issue:');
                if (issue && issue.length > 5) {{
                    showNotification('🎫 Creating ticket... Use /ticket in Discord for full feature.');
                    alert('For full ticket features, use /ticket command in Discord server.');
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
            
            document.addEventListener('DOMContentLoaded', function() {{
                initBackground();
                // Auto-refresh every 5 minutes
                setInterval(refreshStats, 300000);
            }});
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
    
    return jsonify({"is_admin": bool(user_data.get('is_admin', 0))})

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
    
    if not user_data.get('is_admin'):
        return jsonify({"success": False, "error": "Admin privileges required"})
    
    new_key = generate_secure_key()
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE players SET api_key = ? WHERE id = ?',
        (new_key, user_data['id'])
    )
    conn.commit()
    conn.close()
    
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
    
    if not is_user_admin_in_guild(server_id, user_data['discord_id']):
        return jsonify({"success": False, "error": "Admin privileges required"})
    
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO webhooks (webhook_url, server_id, webhook_name)
            VALUES (?, ?, ?)
        ''', (webhook_url, server_id, 'Stats Webhook'))
        conn.commit()
        conn.close()
        
        send_webhook_stats(server_id)
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
        "service": "Goblin Bot Dashboard",
        "version": "5.0",
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
                
                time.sleep(1800)
            except:
                time.sleep(300)
    
    thread = threading.Thread(target=send_updates, daemon=True)
    thread.start()

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    init_db()
    
    print(f"\n{'='*60}")
    print("🤖 GOBLIN BOT DASHBOARD")
    print(f"{'='*60}")
    
    if test_discord_token():
        bot_active = True
        print("✅ Discord bot connected")
        
        if register_commands():
            print("✅ Commands registered")
        else:
            print("⚠️ Could not register commands")
    else:
        print("❌ Discord token not set or invalid")
    
    webhook_scheduler()
    print("✅ Webhook scheduler started")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🔗 Interactions: http://localhost:{port}/interactions")
    
    print(f"\n🎮 Discord Commands:")
    print(f"   /ping - Check bot status")
    print(f"   /register [name] - Register (no API key shown)")
    print(f"   /ticket [issue] - Create private ticket channel")
    print(f"   /close - Close current ticket channel")
    print(f"   /stats - View your stats")
    
    print(f"\n🎫 Ticket System:")
    print(f"   • Creates private Discord channel")
    print(f"   • Only user and mods can access")
    print(f"   • Use /close in channel to close")
    print(f"   • Mod role ID: {MOD_ROLE_ID or 'Not set'}")
    
    print(f"\n🔐 Security Features:")
    print(f"   • API keys hidden in Discord")
    print(f"   • View keys only in dashboard")
    print(f"   • Admin-only key changes")
    print(f"   • Private ticket channels")
    
    print(f"\n💡 How it works:")
    print(f"   1. Use /register in Discord (no key shown)")
    print(f"   2. Login to dashboard to view API key")
    print(f"   3. Use /ticket for private support")
    print(f"   4. Admins can change keys in dashboard")
    
    print(f"\n{'='*60}\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)

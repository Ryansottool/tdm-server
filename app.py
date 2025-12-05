# app.py - PINK/PURPLE BOT WITH TICKET SYSTEM
import os
import json
import sqlite3
import random
import string
import time
import hashlib
import requests
from flask import Flask, request, jsonify, session, redirect, url_for, make_response
from flask_cors import CORS
from datetime import datetime
import logging
import secrets
import asyncio

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

# Webhook for ticket notifications (optional)
TICKET_WEBHOOK = os.environ.get('TICKET_WEBHOOK', '')

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

# Ticket categories for options
TICKET_CATEGORIES = [
    {"name": "Bug Report", "emoji": "🐛", "color": 0xe74c3c},
    {"name": "Feature Request", "emoji": "✨", "color": 0x3498db},
    {"name": "Account Issue", "emoji": "👤", "color": 0x2ecc71},
    {"name": "Technical Support", "emoji": "🔧", "color": 0xf39c12},
    {"name": "Other", "emoji": "❓", "color": 0x9b59b6}
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
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=data, timeout=10)
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
    try:
        member = get_guild_member(guild_id, user_id)
        if not member:
            return False
        
        guild = get_guild_info(guild_id)
        if guild and guild.get('owner_id') == user_id:
            return True
        
        roles = get_guild_roles(guild_id)
        if not roles:
            return False
        
        member_roles = member.get('roles', [])
        for role_id in member_roles:
            for role in roles:
                if role['id'] == role_id:
                    permissions = int(role.get('permissions', 0))
                    if permissions & 0x8 or permissions & 0x20 or permissions & 0x10000000:
                        return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

# =============================================================================
# WEBHOOK FUNCTIONS
# =============================================================================

def send_ticket_webhook(ticket_id, user_name, user_id, category, issue, channel_id=None, action="created"):
    """Send webhook notification for ticket events"""
    if not TICKET_WEBHOOK:
        return
    
    try:
        category_info = next((c for c in TICKET_CATEGORIES if c["name"] == category), TICKET_CATEGORIES[-1])
        
        embed = {
            "title": f"{category_info['emoji']} Ticket {action.capitalize()}",
            "description": f"**Ticket ID:** `{ticket_id}`\n**User:** {user_name} (<@{user_id}>)\n**Category:** {category}\n**Issue:** {issue[:500]}",
            "color": category_info['color'],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"Ticket {action}"}
        }
        
        if channel_id and action == "created":
            embed["fields"] = [{
                "name": "🔗 Channel",
                "value": f"<#{channel_id}>",
                "inline": True
            }]
        
        data = {
            "embeds": [embed],
            "username": "GOBLIN Ticket System",
            "avatar_url": "https://i.imgur.com/Lg9YqZm.png"
        }
        
        response = requests.post(TICKET_WEBHOOK, json=data, timeout=10)
        if response.status_code not in [200, 204]:
            logger.error(f"Webhook failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")

# =============================================================================
# TICKET SYSTEM
# =============================================================================

def create_ticket_channel(guild_id, user_id, user_name, ticket_id, issue, category):
    """Create private ticket channel with shorter name"""
    try:
        # Get guild info
        guild = get_guild_info(guild_id)
        if not guild:
            return None
        
        # Create shorter channel name (ticket-1234)
        short_id = ticket_id.split('-')[1][:4]  # Get first 4 chars of timestamp
        channel_name = f"ticket-{short_id}"
        
        # Find category for ticket type
        category_info = next((c for c in TICKET_CATEGORIES if c["name"] == category), TICKET_CATEGORIES[-1])
        
        # Create channel data
        channel_data = {
            "name": channel_name,
            "type": 0,  # Text channel
            "topic": f"{category_info['emoji']} {issue[:50]}...",
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
                "allow": "3072",  # VIEW_CHANNEL + SEND_MESSAGES
                "deny": "0"
            })
        
        # Create the channel
        channel = create_guild_channel(guild_id, channel_data)
        if not channel:
            return None
        
        # Create embed with close button
        embed = {
            "title": f"{category_info['emoji']} Ticket #{ticket_id}",
            "description": issue,
            "color": category_info['color'],
            "fields": [
                {"name": "👤 Created By", "value": f"<@{user_id}> ({user_name})", "inline": True},
                {"name": "📅 Created", "value": f"<t:{int(time.time())}:R>", "inline": True},
                {"name": "🏷️ Category", "value": category, "inline": True},
                {"name": "🔒 Channel", "value": f"<#{channel['id']}>", "inline": True}
            ],
            "footer": {"text": "Click the button below to close this ticket"},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Create close button component
        components = {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 4,  # Danger style (red)
                    "label": "Close Ticket",
                    "emoji": {"name": "🔒"},
                    "custom_id": f"close_ticket_{ticket_id}"
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary style (grey)
                    "label": "Add User",
                    "emoji": {"name": "👥"},
                    "custom_id": f"add_user_{ticket_id}"
                }
            ]
        }
        
        welcome_message = {
            "content": f"<@{user_id}> Welcome to your ticket!",
            "embeds": [embed],
            "components": [components]
        }
        
        message_response = discord_api_request(f"/channels/{channel['id']}/messages", "POST", welcome_message)
        
        # Send webhook notification
        send_ticket_webhook(ticket_id, user_name, user_id, category, issue, channel['id'], "created")
        
        return channel['id']
        
    except Exception as e:
        logger.error(f"Error creating ticket channel: {e}")
        return None

def close_ticket_channel(channel_id, ticket_id, closed_by):
    """Close ticket channel and update database"""
    try:
        # Get ticket info for webhook
        conn = get_db_connection()
        ticket = conn.execute(
            'SELECT * FROM tickets WHERE ticket_id = ?',
            (ticket_id,)
        ).fetchone()
        
        # Update database
        conn.execute('''
            UPDATE tickets 
            SET status = "closed", resolved_at = CURRENT_TIMESTAMP, assigned_to = ?
            WHERE ticket_id = ?
        ''', (closed_by, ticket_id))
        conn.commit()
        conn.close()
        
        # Rename channel to archived
        channel_data = {
            "name": f"closed-{int(time.time()) % 10000:04d}",
            "permission_overwrites": [
                {
                    "id": closed_by,
                    "type": 1,
                    "allow": "0",
                    "deny": "1024"
                }
            ]
        }
        
        result = discord_api_request(f"/channels/{channel_id}", "PATCH", channel_data)
        
        # Send closure message
        close_message = {
            "content": f"Ticket closed by <@{closed_by}>",
            "embeds": [{
                "title": "🔒 Ticket Closed",
                "description": f"This ticket has been closed by <@{closed_by}>",
                "color": 0x95a5a6,
                "timestamp": datetime.utcnow().isoformat()
            }],
            "components": []  # Remove buttons
        }
        
        discord_api_request(f"/channels/{channel_id}/messages", "POST", close_message)
        
        # Send webhook notification
        if ticket:
            send_ticket_webhook(ticket_id, ticket['discord_name'], ticket['discord_id'], 
                              ticket['category'], ticket['issue'], None, "closed")
        
        return True
        
    except Exception as e:
        logger.error(f"Error closing ticket channel: {e}")
        return False

# =============================================================================
# SECURE KEY GENERATION
# =============================================================================

def generate_secure_key():
    """Generate strong API key"""
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
    key = 'GOB-' + ''.join(secrets.choice(alphabet) for _ in range(16))
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
        
        # Tickets table with category
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE,
                discord_id TEXT,
                discord_name TEXT,
                issue TEXT,
                category TEXT DEFAULT 'Other',
                channel_id TEXT,
                status TEXT DEFAULT 'open',
                assigned_to TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
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
# KEY VALIDATION - FIXED VERSION
# =============================================================================

def validate_api_key(api_key):
    """Validate API key - FIXED to properly check session"""
    if not api_key or not api_key.startswith("GOB-"):
        return None
    
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE api_key = ?',
        (api_key,)
    ).fetchone()
    
    if player:
        # Update last used time
        conn.execute(
            'UPDATE players SET last_used = CURRENT_TIMESTAMP WHERE id = ?',
            (player['id'],)
        )
        conn.commit()
        
        # Convert to dict for session storage
        player_dict = dict(player)
        conn.close()
        return player_dict
    
    conn.close()
    return None

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
                },
                {
                    "name": "category",
                    "description": "Ticket category",
                    "type": 3,
                    "required": True,
                    "choices": [
                        {"name": "🐛 Bug Report", "value": "Bug Report"},
                        {"name": "✨ Feature Request", "value": "Feature Request"},
                        {"name": "👤 Account Issue", "value": "Account Issue"},
                        {"name": "🔧 Technical Support", "value": "Technical Support"},
                        {"name": "❓ Other", "value": "Other"}
                    ]
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
        },
        {
            "name": "key",
            "description": "Show your API key",
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
    
    # Handle button clicks
    if data.get('type') == 3:
        custom_id = data.get('data', {}).get('custom_id', '')
        user_id = data.get('member', {}).get('user', {}).get('id')
        channel_id = data.get('channel_id')
        
        if custom_id.startswith('close_ticket_'):
            ticket_id = custom_id.replace('close_ticket_', '')
            
            # Get ticket info
            conn = get_db_connection()
            ticket = conn.execute(
                'SELECT * FROM tickets WHERE ticket_id = ?',
                (ticket_id,)
            ).fetchone()
            conn.close()
            
            if ticket:
                # Check if user has permission to close
                can_close = False
                if str(user_id) == str(ticket['discord_id']):
                    can_close = True
                elif MOD_ROLE_ID:
                    # Check if user has mod role
                    member = get_guild_member(data.get('guild_id'), user_id)
                    if member and MOD_ROLE_ID in member.get('roles', []):
                        can_close = True
                
                if can_close:
                    close_ticket_channel(channel_id, ticket_id, user_id)
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"✅ Ticket `{ticket_id}` has been closed.",
                            "flags": 64
                        }
                    })
                else:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": "❌ You don't have permission to close this ticket.",
                            "flags": 64
                        }
                    })
        
        return jsonify({"type": 6})  # ACK
    
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
                api_key = existing['api_key']
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"Already registered as `{existing['in_game_name']}`\n\n"
                            f"**Your API Key:**\n`{api_key}`\n\n"
                            f"Dashboard: {request.host_url}"
                        ),
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
            
            admin_note = "\n⚠️ **Admin access detected** - You have additional privileges." if is_admin else ""
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"✅ **Registered Successfully**{admin_note}\n\n"
                        f"**Name:** `{in_game_name}`\n"
                        f"**API Key:** `{api_key}`\n\n"
                        f"**Dashboard:** {request.host_url}\n"
                        f"Login to access your full dashboard"
                    ),
                    "flags": 64
                }
            })
        
        elif command == 'ticket':
            options = data.get('data', {}).get('options', [])
            issue = options[0].get('value', 'No issue specified') if options else 'No issue specified'
            category = options[1].get('value', 'Other') if len(options) > 1 else 'Other'
            
            ticket_id = f"T-{int(time.time()) % 10000:04d}"
            
            # Create ticket in database
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO tickets 
                (ticket_id, discord_id, discord_name, issue, category)
                VALUES (?, ?, ?, ?, ?)
            ''', (ticket_id, user_id, user_name, issue, category))
            conn.commit()
            
            # Create private channel
            channel_id = create_ticket_channel(server_id, user_id, user_name, ticket_id, issue, category)
            
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
                        "content": f"✅ **Ticket Created**\n\n**Ticket ID:** `{ticket_id}`\n**Channel:** <#{channel_id}>",
                        "flags": 64
                    }
                })
            else:
                conn.close()
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"✅ **Ticket Created**\n\n**Ticket ID:** `{ticket_id}`\n*Could not create private channel*",
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
            conn.close()
            
            if not ticket:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "❌ No open ticket in this channel",
                        "flags": 64
                    }
                })
            
            # Close the ticket
            close_ticket_channel(data.get('channel_id'), ticket['ticket_id'], user_id)
            
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
        
        elif command == 'key':
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
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"🔑 **Your API Key**\n\n"
                        f"`{player['api_key']}`\n\n"
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
# WEB INTERFACE - DARK MODE PINK/PURPLE DESIGN
# =============================================================================

@app.route('/')
def home():
    """Dark mode Pink/Purple web design"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            return redirect(url_for('dashboard'))
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>GOBLIN Dashboard</title>
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
                color: #e0e0e0;
                min-height: 100vh;
                overflow-x: hidden;
                position: relative;
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
                background: linear-gradient(45deg, #ff00ff, #9d00ff, #00d4ff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-size: 200% 200%;
                animation: gradient 3s ease infinite;
                text-shadow: 0 0 30px rgba(255, 0, 255, 0.3);
            }
            
            @keyframes gradient {
                0% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
            }
            
            .subtitle {
                font-size: 1.2rem;
                color: #b19cd9;
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
                background: rgba(25, 25, 25, 0.9);
                border: 2px solid #9d00ff;
                border-radius: 15px;
                color: #fff;
                font-size: 18px;
                text-align: center;
                margin-bottom: 25px;
                transition: all 0.3s;
                backdrop-filter: blur(10px);
                box-shadow: 0 5px 15px rgba(157, 0, 255, 0.2);
            }
            
            .key-input:focus {
                outline: none;
                border-color: #ff00ff;
                box-shadow: 0 0 30px rgba(255, 0, 255, 0.4);
                transform: scale(1.02);
                background: rgba(30, 30, 30, 0.95);
            }
            
            .key-input::placeholder {
                color: #666;
            }
            
            .login-btn {
                width: 100%;
                padding: 20px;
                background: linear-gradient(45deg, #ff00ff, #9d00ff);
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 18px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
                text-transform: uppercase;
                letter-spacing: 1px;
                box-shadow: 0 10px 20px rgba(157, 0, 255, 0.3);
            }
            
            .login-btn:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 35px rgba(255, 0, 255, 0.4);
                background: linear-gradient(45deg, #9d00ff, #ff00ff);
            }
            
            .login-btn:active {
                transform: translateY(-2px);
            }
            
            .login-btn:disabled {
                opacity: 0.7;
                cursor: not-allowed;
                transform: none !important;
            }
            
            .error-box {
                background: rgba(255, 0, 0, 0.1);
                border: 2px solid rgba(255, 0, 0, 0.4);
                border-radius: 15px;
                padding: 16px;
                margin-top: 20px;
                color: #ff6b6b;
                display: none;
                animation: shake 0.5s;
                backdrop-filter: blur(10px);
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }
            
            .info-box {
                background: rgba(30, 30, 30, 0.9);
                border: 2px solid rgba(157, 0, 255, 0.4);
                border-radius: 15px;
                padding: 25px;
                margin-top: 35px;
                text-align: left;
                color: #d4b3ff;
                backdrop-filter: blur(10px);
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
            }
            
            .info-box strong {
                color: #ff00ff;
                display: block;
                margin-bottom: 15px;
                font-size: 1.1rem;
            }
            
            .info-box code {
                background: rgba(0, 0, 0, 0.5);
                padding: 3px 8px;
                border-radius: 5px;
                font-family: monospace;
                color: #9d00ff;
                margin: 0 2px;
            }
            
            .bot-status {
                padding: 12px 24px;
                background: rgba(30, 30, 30, 0.9);
                border: 2px solid rgba(157, 0, 255, 0.4);
                border-radius: 25px;
                margin-top: 25px;
                display: inline-block;
                backdrop-filter: blur(10px);
                font-weight: 600;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
            }
            
            .status-online {
                color: #00ff9d;
                border-color: rgba(0, 255, 157, 0.4);
            }
            
            .status-offline {
                color: #ff6b6b;
                border-color: rgba(255, 107, 107, 0.4);
            }
            
            .neon-line {
                height: 2px;
                background: linear-gradient(90deg, transparent, #ff00ff, transparent);
                margin: 30px 0;
                width: 100%;
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 20px;
                }
                .logo {
                    font-size: 3rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">GOBLIN</div>
            <div class="subtitle">Enter your API key to access the dashboard</div>
            
            <div class="neon-line"></div>
            
            <input type="password" 
                   class="key-input" 
                   id="apiKey" 
                   placeholder="GOB-XXXXXXXXXXXXXXXX"
                   autocomplete="off"
                   spellcheck="false">
            
            <button class="login-btn" onclick="validateKey()" id="loginBtn">
                Enter Dashboard
            </button>
            
            <div class="error-box" id="errorMessage">
                Invalid API key
            </div>
            
            <div class="info-box">
                <strong>How to get your API key:</strong>
                <p>1. Use <code>/register your_name</code> in Discord</p>
                <p>2. Copy your <code>GOB-XXXXXXX</code> key from bot response</p>
                <p>3. Use <code>/key</code> to see your key anytime</p>
                <p>4. Enter it above to access your dashboard</p>
            </div>
            
            <div class="bot-status" id="botStatus">
                ⚡ Bot Status: Checking...
            </div>
        </div>
        
        <script>
            async function validateKey() {
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const errorDiv = document.getElementById('errorMessage');
                const btn = document.getElementById('loginBtn');
                
                if (!key) {
                    errorDiv.textContent = "Please enter an API key";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                if (!key.startsWith('GOB-')) {
                    errorDiv.textContent = "Key must start with GOB-";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                btn.innerHTML = '🔮 Checking...';
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
                        btn.style.background = 'linear-gradient(45deg, #00ff9d, #00d4ff)';
                        
                        // Store in session
                        sessionStorage.setItem('user_key', key);
                        
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 600);
                    } else {
                        errorDiv.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        btn.innerHTML = 'Enter Dashboard';
                        btn.disabled = false;
                    }
                } catch (error) {
                    errorDiv.textContent = 'Connection error';
                    errorDiv.style.display = 'block';
                    btn.innerHTML = 'Enter Dashboard';
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
                document.getElementById('apiKey').focus();
                checkBotStatus();
                setInterval(checkBotStatus, 30000);
                
                // Check if already logged in
                const storedKey = sessionStorage.getItem('user_key');
                if (storedKey) {
                    document.getElementById('apiKey').value = storedKey;
                }
            });
        </script>
    </body>
    </html>
    '''

@app.route('/api/validate-key', methods=['POST'])
def api_validate_key():
    """Validate API key - FIXED to properly set session"""
    data = request.get_json()
    api_key = data.get('api_key', '').strip().upper()
    
    if not api_key:
        return jsonify({"valid": False, "error": "No key provided"})
    
    user_data = validate_api_key(api_key)
    
    if user_data:
        session['user_key'] = api_key
        session['user_data'] = user_data
        # Make sure session is saved
        session.modified = True
        return jsonify({"valid": True})
    else:
        return jsonify({"valid": False, "error": "Invalid API key"})

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    response = make_response(redirect(url_for('home')))
    response.delete_cookie('session')
    return response

@app.route('/dashboard')
def dashboard():
    """Dark mode Pink/Purple dashboard"""
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    user_data = session.get('user_data')
    if not user_data:
        # Try to re-validate the key
        user_data = validate_api_key(session.get('user_key'))
        if not user_data:
            return redirect(url_for('home'))
        session['user_data'] = user_data
    
    # Calculate stats
    kd = user_data.get('total_kills', 0) / max(user_data.get('total_deaths', 1), 1)
    total_games = user_data.get('wins', 0) + user_data.get('losses', 0)
    win_rate = (user_data.get('wins', 0) / total_games * 100) if total_games > 0 else 0
    
    is_admin = user_data.get('is_admin', 0)
    
    # Get open tickets for this user
    conn = get_db_connection()
    tickets = conn.execute(
        'SELECT * FROM tickets WHERE discord_id = ? AND status = "open" ORDER BY created_at DESC LIMIT 5',
        (user_data['discord_id'],)
    ).fetchall()
    conn.close()
    
    tickets_html = ''
    for ticket in tickets:
        category_info = next((c for c in TICKET_CATEGORIES if c["name"] == ticket['category']), TICKET_CATEGORIES[-1])
        tickets_html += f'''
        <div class="ticket-card">
            <div class="ticket-header">
                <div>
                    <span style="color: #{hex(category_info['color'])[2:]}; font-size: 1.2rem;">{category_info['emoji']}</span>
                    <strong>TICKET-{ticket['ticket_id']}</strong>
                </div>
                <span class="status-open">OPEN</span>
            </div>
            <p class="ticket-issue">{ticket['issue'][:80]}...</p>
            <div class="ticket-actions">
                <button class="ticket-btn view" onclick="viewTicket('{ticket['ticket_id']}')">View</button>
                <button class="ticket-btn close" onclick="closeTicket('{ticket['ticket_id']}')">Close</button>
            </div>
        </div>
        '''
    
    if not tickets_html:
        tickets_html = '<p class="no-tickets">No open tickets</p>'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>GOBLIN Dashboard</title>
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
                color: #e0e0e0;
                min-height: 100vh;
                position: relative;
                overflow-x: hidden;
            }}
            
            .header {{
                background: rgba(15, 15, 15, 0.95);
                backdrop-filter: blur(20px);
                border-bottom: 3px solid #ff00ff;
                padding: 25px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 5px 30px rgba(0, 0, 0, 0.5);
            }}
            
            .logo {{
                font-size: 2rem;
                font-weight: 900;
                background: linear-gradient(45deg, #ff00ff, #9d00ff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                text-shadow: 0 0 20px rgba(255, 0, 255, 0.3);
            }}
            
            .user-info {{
                display: flex;
                align-items: center;
                gap: 25px;
            }}
            
            .admin-badge {{
                background: linear-gradient(45deg, #ff00ff, #9d00ff);
                color: white;
                padding: 6px 15px;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: bold;
                box-shadow: 0 0 15px rgba(255, 0, 255, 0.4);
            }}
            
            .logout-btn {{
                padding: 10px 24px;
                background: linear-gradient(45deg, #ff416c, #ff4b2b);
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
                cursor: pointer;
                text-decoration: none;
                transition: all 0.3s;
                box-shadow: 0 5px 15px rgba(255, 65, 108, 0.3);
            }}
            
            .logout-btn:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 25px rgba(255, 65, 108, 0.4);
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 40px;
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 25px;
                margin-bottom: 50px;
            }}
            
            .stat-card {{
                background: rgba(30, 30, 30, 0.9);
                backdrop-filter: blur(20px);
                border-radius: 20px;
                padding: 35px;
                text-align: center;
                border: 2px solid rgba(157, 0, 255, 0.3);
                transition: all 0.4s;
                position: relative;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            }}
            
            .stat-card:hover {{
                transform: translateY(-10px) scale(1.02);
                border-color: rgba(255, 0, 255, 0.5);
                box-shadow: 0 20px 40px rgba(255, 0, 255, 0.2);
            }}
            
            .stat-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #ff00ff, #9d00ff);
            }}
            
            .stat-value {{
                font-size: 3.5rem;
                font-weight: 900;
                margin: 20px 0;
                font-family: 'Segoe UI', sans-serif;
                text-shadow: 0 0 20px currentColor;
            }}
            
            .stat-label {{
                color: #b19cd9;
                font-size: 0.95rem;
                text-transform: uppercase;
                letter-spacing: 2px;
                margin-bottom: 10px;
            }}
            
            .key-section {{
                background: rgba(30, 30, 30, 0.9);
                backdrop-filter: blur(20px);
                border-radius: 25px;
                padding: 50px;
                margin-bottom: 50px;
                border: 2px solid rgba(157, 0, 255, 0.3);
                position: relative;
                overflow: hidden;
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.3);
            }}
            
            .key-section::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #00ff9d, #00d4ff);
            }}
            
            .key-display {{
                background: rgba(0, 0, 0, 0.5);
                border: 2px solid rgba(157, 0, 255, 0.5);
                border-radius: 16px;
                padding: 25px;
                margin: 30px 0;
                font-family: monospace;
                color: #00ff9d;
                text-align: center;
                cursor: pointer;
                position: relative;
                overflow: hidden;
                letter-spacing: 2px;
                font-size: 1.3rem;
                text-shadow: 0 0 10px #00ff9d;
                box-shadow: 0 5px 15px rgba(0, 255, 157, 0.1);
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
                color: #b19cd9;
                backdrop-filter: blur(5px);
                border-radius: 14px;
            }}
            
            .key-display.revealed::before {{
                display: none;
            }}
            
            .tickets-section {{
                background: rgba(30, 30, 30, 0.9);
                backdrop-filter: blur(20px);
                border-radius: 25px;
                padding: 50px;
                margin-bottom: 50px;
                border: 2px solid rgba(255, 0, 255, 0.3);
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.3);
            }}
            
            .ticket-card {{
                background: rgba(20, 20, 20, 0.8);
                border-radius: 16px;
                padding: 25px;
                margin-bottom: 20px;
                border: 1px solid rgba(157, 0, 255, 0.2);
                transition: all 0.3s;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            }}
            
            .ticket-card:hover {{
                border-color: rgba(255, 0, 255, 0.4);
                transform: translateX(10px);
                box-shadow: 0 10px 25px rgba(255, 0, 255, 0.1);
            }}
            
            .ticket-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }}
            
            .status-open {{
                color: #00ff9d;
                font-size: 0.9rem;
                font-weight: bold;
                text-shadow: 0 0 10px #00ff9d;
            }}
            
            .ticket-issue {{
                color: #d4b3ff;
                margin-bottom: 20px;
                font-size: 0.95rem;
                line-height: 1.4;
            }}
            
            .ticket-actions {{
                display: flex;
                gap: 10px;
            }}
            
            .ticket-btn {{
                padding: 10px 20px;
                background: rgba(157, 0, 255, 0.3);
                border: 2px solid #9d00ff;
                color: white;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.3s;
                font-weight: bold;
                box-shadow: 0 3px 10px rgba(157, 0, 255, 0.2);
            }}
            
            .ticket-btn:hover {{
                background: rgba(157, 0, 255, 0.5);
                transform: translateY(-3px);
                box-shadow: 0 6px 15px rgba(157, 0, 255, 0.3);
            }}
            
            .ticket-btn.close {{
                background: rgba(255, 0, 0, 0.3);
                border-color: #ff0000;
            }}
            
            .ticket-btn.close:hover {{
                background: rgba(255, 0, 0, 0.5);
                box-shadow: 0 6px 15px rgba(255, 0, 0, 0.3);
            }}
            
            .no-tickets {{
                color: #666;
                text-align: center;
                padding: 40px;
                font-size: 1.1rem;
            }}
            
            .action-buttons {{
                display: flex;
                gap: 20px;
                margin-top: 40px;
                flex-wrap: wrap;
            }}
            
            .action-btn {{
                padding: 18px 36px;
                background: linear-gradient(45deg, #ff00ff, #9d00ff);
                color: white;
                border: none;
                border-radius: 15px;
                font-weight: bold;
                font-size: 16px;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 15px;
                flex: 1;
                min-width: 200px;
                justify-content: center;
                text-transform: uppercase;
                letter-spacing: 1px;
                box-shadow: 0 8px 20px rgba(157, 0, 255, 0.3);
            }}
            
            .action-btn:hover {{
                transform: translateY(-8px);
                box-shadow: 0 15px 35px rgba(255, 0, 255, 0.4);
                background: linear-gradient(45deg, #9d00ff, #ff00ff);
            }}
            
            .action-btn.admin {{
                background: linear-gradient(45deg, #00ff9d, #00d4ff);
            }}
            
            .action-btn.admin:hover {{
                box-shadow: 0 15px 35px rgba(0, 255, 157, 0.4);
            }}
            
            .notification {{
                position: fixed;
                bottom: 30px;
                right: 30px;
                background: linear-gradient(45deg, #00ff9d, #00d4ff);
                color: black;
                padding: 20px 30px;
                border-radius: 15px;
                z-index: 1000;
                display: none;
                animation: slideInRight 0.5s ease-out;
                font-weight: bold;
                box-shadow: 0 10px 30px rgba(0, 255, 157, 0.4);
            }}
            
            @keyframes slideInRight {{
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
                .key-section, .tickets-section {{
                    padding: 30px 20px;
                }}
                .action-buttons {{
                    flex-direction: column;
                }}
                .action-btn {{
                    min-width: 100%;
                }}
                .key-display {{
                    font-size: 1.1rem;
                    padding: 20px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">GOBLIN DASHBOARD</div>
            <div class="user-info">
                <div>
                    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 5px;">
                        <strong style="font-size: 1.2rem; color: #ff00ff;">{user_data.get('in_game_name', 'Player')}</strong>
                        { '<span class="admin-badge">👑 ADMIN</span>' if is_admin else '' }
                    </div>
                    <div style="color: #b19cd9; font-size: 0.9rem;">Prestige {user_data.get('prestige', 0)} • {total_games} games</div>
                </div>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">K/D Ratio</div>
                    <div class="stat-value" style="color: { '#00ff9d' if kd >= 1.5 else '#ffd700' if kd >= 1 else '#ff6b6b' };">{kd:.2f}</div>
                    <div style="color: #d4b3ff;">{user_data.get('total_kills', 0)} kills / {user_data.get('total_deaths', 0)} deaths</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Win Rate</div>
                    <div class="stat-value" style="color: { '#00ff9d' if win_rate >= 60 else '#ffd700' if win_rate >= 40 else '#ff6b6b' };">{win_rate:.1f}%</div>
                    <div style="color: #d4b3ff;">{user_data.get('wins', 0)} wins / {user_data.get('losses', 0)} losses</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Games Played</div>
                    <div class="stat-value" style="color: #9d00ff;">{total_games}</div>
                    <div style="color: #d4b3ff;">Total matches completed</div>
                </div>
            </div>
            
            <div class="key-section">
                <h2 style="color: #ff00ff; margin-bottom: 10px; font-size: 2rem; text-shadow: 0 0 15px rgba(255, 0, 255, 0.5);">Your API Key</h2>
                <p style="color: #b19cd9; margin-bottom: 20px; font-size: 1.1rem;">
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
                    <button class="action-btn" onclick="createTicket()">
                        🎫 Create Ticket
                    </button>
                </div>
            </div>
            
            <div class="tickets-section">
                <h2 style="color: #ff00ff; margin-bottom: 30px; font-size: 2rem; text-shadow: 0 0 15px rgba(255, 0, 255, 0.5);">Your Open Tickets</h2>
                {tickets_html}
            </div>
        </div>
        
        <div class="notification" id="notification"></div>
        
        <script>
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
                alert('Use /ticket command in Discord to create tickets with categories.');
            }}
            
            function viewTicket(ticketId) {{
                alert('Ticket view feature coming soon! Use Discord channel for now.');
            }}
            
            function closeTicket(ticketId) {{
                if (confirm('Close this ticket?')) {{
                    showNotification('🎫 Closing ticket...');
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

@app.route('/api/refresh-stats')
def refresh_stats():
    """Refresh player stats"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "No key provided"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"error": "Invalid key"}), 401
    
    return jsonify({"success": True})

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
        "service": "GOBLIN Bot v6.0",
        "timestamp": datetime.utcnow().isoformat()
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    init_db()
    
    print(f"\n{'='*60}")
    print("🎮 GOBLIN BOT - DARK MODE PINK/PURPLE EDITION")
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
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🎨 Design: Dark mode Pink/Purple theme")
    
    print(f"\n🎮 Discord Commands:")
    print(f"   /ping - Check bot status")
    print(f"   /register [name] - Get API key (shown in Discord)")
    print(f"   /key - Show your API key")
    print(f"   /ticket [issue] [category] - Create private ticket")
    print(f"   /close - Close current ticket")
    print(f"   /stats - View your stats")
    
    print(f"\n🎫 Ticket System:")
    print(f"   • Short channel names: ticket-1234")
    print(f"   • Category options: Bug, Feature, Account, Tech, Other")
    print(f"   • Close button in ticket channel")
    print(f"   • Private channels (user + mods only)")
    print(f"   • Webhook notifications: {'Enabled' if TICKET_WEBHOOK else 'Disabled'}")
    
    print(f"\n🔐 Security Features:")
    print(f"   • API keys shown with /register and /key")
    print(f"   • Keys hidden in dashboard (click to reveal)")
    print(f"   • Admin-only key changes")
    print(f"   • Private ticket channels")
    
    print(f"\n💡 How it works:")
    print(f"   1. Use /register in Discord to get API key")
    print(f"   2. Use /key to see your key anytime")
    print(f"   3. Login to dark mode dashboard")
    print(f"   4. Use /ticket for private support")
    print(f"   5. Click close button in ticket channel")
    
    print(f"\n🔧 Environment Variables:")
    print(f"   MOD_ROLE_ID={MOD_ROLE_ID or 'Not set'}")
    print(f"   TICKET_WEBHOOK={'Set' if TICKET_WEBHOOK else 'Not set'}")
    
    print(f"\n{'='*60}\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)

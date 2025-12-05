# app.py - GOBLIN BOT WITH TICKET SYSTEM
import os
import json
import sqlite3
import random
import string
import time
import requests
from flask import Flask, request, jsonify, session, redirect, url_for, make_response
from flask_cors import CORS
from datetime import datetime
import logging
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
# Increase session lifetime
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app, supports_credentials=True)
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

# Toxic ping responses
TOXIC_PING_RESPONSES = [
    "I'm here, unlike your father",
    "Still alive, surprisingly",
    "Yeah I'm here, what do you want?",
    "Online, but busy ignoring you",
    "Ready to disappoint you",
    "Here, unfortunately",
    "Present, sadly",
    "Awake, can you believe it?",
    "Active, unfortunately for you",
    "I'm up, you're still trash",
    "Yeah yeah, I'm here",
    "Bot's online, you're still bad",
    "Pong, get better at pinging",
    "I exist, unlike your skill",
    "now stop pinging me",
    "Online, but not happy about it",
    "I'm alive. Happy?",
    "Present, against my will",
    "Up and running, unlike you fattso",
    "Bot status: Fuck you"
]

# Normal ping responses
NORMAL_PING_RESPONSES = [
    "I'm here!",
    "Bot is up and running!",
    "Still alive!",
    "Yeah I'm here!",
    "Online!",
    "Ready!",
    "Here!",
    "Present!",
    "Awake!",
    "Active!",
    "All systems go!",
    "Ready for action!",
    "Bot is online!",
    "Good to go!",
    "Operational!"
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

def delete_channel(channel_id):
    """Delete a channel"""
    return discord_api_request(f"/channels/{channel_id}", "DELETE")

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
    """Close ticket channel, delete it, and update database"""
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
        
        # Delete the channel instead of renaming
        delete_result = delete_channel(channel_id)
        
        # Send webhook notification
        if ticket:
            send_ticket_webhook(ticket_id, ticket['discord_name'], ticket['discord_id'], 
                              ticket['category'], ticket['issue'], None, "closed and deleted")
        
        return True if delete_result else False
        
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
# KEY VALIDATION - IMPROVED VERSION
# =============================================================================

def validate_api_key(api_key):
    """Validate API key - IMPROVED with better session handling"""
    if not api_key or not api_key.startswith("GOB-"):
        return None
    
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE api_key = ?',
        (api_key.upper(),)  # Ensure uppercase
    ).fetchone()
    
    if player:
        # Update last used time
        conn.execute(
            'UPDATE players SET last_used = CURRENT_TIMESTAMP WHERE id = ?',
            (player['id'],)
        )
        conn.commit()
        
        # Convert to dict for session storage
        player_dict = {key: player[key] for key in player.keys()}
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
            "name": "profile",
            "description": "Show your profile and stats",
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
                    success = close_ticket_channel(channel_id, ticket_id, user_id)
                    if success:
                        return jsonify({
                            "type": 4,
                            "data": {
                                "content": f"✅ Ticket `{ticket_id}` has been closed and channel deleted.",
                                "flags": 64
                            }
                        })
                    else:
                        return jsonify({
                            "type": 4,
                            "data": {
                                "content": f"⚠️ Ticket marked as closed but could not delete channel.",
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
            # 30% chance for toxic response
            if random.random() < 0.3:
                response = random.choice(TOXIC_PING_RESPONSES)
            else:
                response = random.choice(NORMAL_PING_RESPONSES)
            
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
            
            # Close the ticket and delete channel
            success = close_ticket_channel(data.get('channel_id'), ticket['ticket_id'], user_id)
            
            if success:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"✅ Ticket `{ticket['ticket_id']}` has been closed and channel deleted.",
                        "flags": 64
                    }
                })
            else:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"⚠️ Ticket marked as closed but could not delete channel.",
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
                        "content": "❌ Not registered. Use `/register [name]` first",
                        "flags": 64
                    }
                })
            
            kd = player['total_kills'] / max(player['total_deaths'], 1)
            win_rate = (player['wins'] / max(player['wins'] + player['losses'], 1)) * 100
            total_games = player['wins'] + player['losses']
            
            embed = {
                "title": f"📊 {player['in_game_name']}'s Profile",
                "color": 0x9d00ff,
                "fields": [
                    {"name": "🎮 In-Game Name", "value": f"`{player['in_game_name']}`", "inline": True},
                    {"name": "👑 Prestige", "value": f"**{player['prestige']}**", "inline": True},
                    {"name": "📅 Registered", "value": f"<t:{int(time.mktime(datetime.strptime(player['created_at'], '%Y-%m-%d %H:%M:%S').timestamp()))}:R>", "inline": True},
                    {"name": "⚔️ K/D Ratio", "value": f"**{kd:.2f}** ({player['total_kills']}/{player['total_deaths']})", "inline": True},
                    {"name": "🏆 Win Rate", "value": f"**{win_rate:.1f}%** ({player['wins']}/{total_games})", "inline": True},
                    {"name": "🎮 Games Played", "value": f"**{total_games}**", "inline": True},
                    {"name": "🔑 API Key", "value": f"`{player['api_key'][:8]}...`", "inline": False},
                    {"name": "🔗 Dashboard", "value": f"[Click Here]({request.host_url})", "inline": True},
                    {"name": "👑 Status", "value": "**Admin**" if player['is_admin'] else "**Player**", "inline": True}
                ],
                "footer": {"text": "Use /key to see full API key"},
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return jsonify({
                "type": 4,
                "data": {
                    "embeds": [embed],
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
# SESSION MANAGEMENT
# =============================================================================

@app.before_request
def before_request():
    """Check session before each request"""
    if request.endpoint not in ['home', 'api_validate_key', 'health', 'api_stats', 'static']:
        if 'user_key' not in session:
            return redirect(url_for('home'))
        
        # Re-validate session on dashboard access
        if request.endpoint == 'dashboard':
            user_data = validate_api_key(session.get('user_key'))
            if not user_data:
                session.clear()
                return redirect(url_for('home'))
            session['user_data'] = user_data

# =============================================================================
# WEB INTERFACE - SIMPLIFIED TO AVOID F-STRING ISSUES
# =============================================================================

@app.route('/')
def home():
    """Home page with animated background"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            session['user_data'] = user_data
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
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #000;
                color: #fff;
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
                font-size: 4.5rem;
                font-weight: 900;
                margin-bottom: 20px;
                background: linear-gradient(45deg, #ff00ff, #9d00ff, #00d4ff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-size: 300% 300%;
                animation: gradient 4s ease infinite;
                text-shadow: 0 0 40px rgba(255, 0, 255, 0.5);
                letter-spacing: 2px;
                font-family: 'Arial Black', sans-serif;
            }
            
            @keyframes gradient {
                0% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
            }
            
            .subtitle {
                font-size: 1.3rem;
                color: #b19cd9;
                margin-bottom: 40px;
                animation: fadeIn 1.5s ease-out;
                font-weight: 300;
                letter-spacing: 1px;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(30px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .login-box {
                background: rgba(20, 10, 40, 0.7);
                backdrop-filter: blur(15px);
                border-radius: 20px;
                padding: 40px;
                border: 1px solid rgba(255, 0, 255, 0.3);
                box-shadow: 0 20px 60px rgba(157, 0, 255, 0.2),
                            inset 0 1px 0 rgba(255, 255, 255, 0.1);
                animation: slideUp 0.8s ease-out;
            }
            
            @keyframes slideUp {
                from { opacity: 0; transform: translateY(50px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .key-input {
                width: 100%;
                padding: 22px;
                background: rgba(0, 0, 0, 0.6);
                border: 2px solid #9d00ff;
                border-radius: 15px;
                color: #fff;
                font-size: 18px;
                text-align: center;
                margin-bottom: 30px;
                transition: all 0.3s;
                font-family: monospace;
                letter-spacing: 2px;
                box-shadow: 0 5px 20px rgba(157, 0, 255, 0.2);
            }
            
            .key-input:focus {
                outline: none;
                border-color: #ff00ff;
                box-shadow: 0 0 40px rgba(255, 0, 255, 0.5);
                transform: scale(1.02);
                background: rgba(10, 0, 20, 0.8);
            }
            
            .key-input::placeholder {
                color: #666;
                font-family: sans-serif;
                letter-spacing: normal;
            }
            
            .login-btn {
                width: 100%;
                padding: 22px;
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
                letter-spacing: 2px;
                box-shadow: 0 10px 30px rgba(157, 0, 255, 0.4);
                font-family: 'Segoe UI', sans-serif;
            }
            
            .login-btn:hover {
                transform: translateY(-5px);
                box-shadow: 0 20px 40px rgba(255, 0, 255, 0.6);
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
            
            .login-btn::before {
                content: '';
                position: absolute;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: linear-gradient(45deg, transparent, rgba(255, 255, 255, 0.2), transparent);
                transform: rotate(45deg);
                transition: all 0.5s;
            }
            
            .login-btn:hover::before {
                left: 100%;
            }
            
            .error-box {
                background: rgba(255, 0, 0, 0.15);
                border: 2px solid rgba(255, 0, 0, 0.4);
                border-radius: 15px;
                padding: 18px;
                margin-top: 25px;
                color: #ff6b6b;
                display: none;
                animation: shake 0.5s;
                backdrop-filter: blur(10px);
                font-weight: 500;
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-8px); }
                75% { transform: translateX(8px); }
            }
            
            .info-box {
                background: rgba(30, 15, 60, 0.7);
                border: 1px solid rgba(157, 0, 255, 0.4);
                border-radius: 15px;
                padding: 30px;
                margin-top: 40px;
                text-align: left;
                color: #d4b3ff;
                backdrop-filter: blur(15px);
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                animation: fadeInDelay 1s ease-out 0.5s both;
            }
            
            @keyframes fadeInDelay {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .info-box strong {
                color: #ff00ff;
                display: block;
                margin-bottom: 20px;
                font-size: 1.2rem;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .info-box code {
                background: rgba(0, 0, 0, 0.5);
                padding: 4px 10px;
                border-radius: 6px;
                font-family: 'Courier New', monospace;
                color: #9d00ff;
                margin: 0 3px;
                font-weight: bold;
            }
            
            .info-box p {
                margin-bottom: 15px;
                line-height: 1.6;
                font-size: 1.05rem;
            }
            
            .bot-status {
                padding: 15px 30px;
                background: rgba(30, 15, 60, 0.7);
                border: 2px solid rgba(157, 0, 255, 0.4);
                border-radius: 30px;
                margin-top: 35px;
                display: inline-block;
                backdrop-filter: blur(15px);
                font-weight: 600;
                font-size: 1.1rem;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0% { box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); }
                50% { box-shadow: 0 10px 40px rgba(157, 0, 255, 0.3); }
                100% { box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); }
            }
            
            .status-online {
                color: #00ff9d;
                border-color: rgba(0, 255, 157, 0.4);
                text-shadow: 0 0 10px rgba(0, 255, 157, 0.5);
            }
            
            .status-offline {
                color: #ff6b6b;
                border-color: rgba(255, 107, 107, 0.4);
                text-shadow: 0 0 10px rgba(255, 107, 107, 0.5);
            }
            
            .neon-line {
                height: 3px;
                background: linear-gradient(90deg, transparent, #ff00ff, #9d00ff, transparent);
                margin: 40px 0;
                width: 100%;
                opacity: 0.7;
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 20px;
                }
                .logo {
                    font-size: 3.5rem;
                }
                .login-box {
                    padding: 30px 20px;
                }
                .key-input {
                    padding: 18px;
                    font-size: 16px;
                }
                .login-btn {
                    padding: 18px;
                    font-size: 16px;
                }
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 20px;
                }
                .logo {
                    font-size: 3.5rem;
                }
                .login-box {
                    padding: 30px 20px;
                }
                .key-input {
                    padding: 18px;
                    font-size: 16px;
                }
                .login-btn {
                    padding: 18px;
                    font-size: 16px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">GOBLIN</div>
            <div class="subtitle">Enter your API key to access the dashboard</div>
            
            <div class="login-box">
                <input type="password" 
                       class="key-input" 
                       id="apiKey" 
                       placeholder="GOB-XXXXXXXXXXXXXXXX"
                       autocomplete="off"
                       spellcheck="false"
                       autocapitalize="characters">
                
                <button class="login-btn" onclick="validateKey()" id="loginBtn">
                    Enter Dashboard
                </button>
                
                <div class="error-box" id="errorMessage">
                    Invalid API key
                </div>
            </div>
            
            <div class="neon-line"></div>
            
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
                
                if (key.length < 20) {
                    errorDiv.textContent = "Invalid key format";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                btn.innerHTML = '🔮 Checking...';
                btn.disabled = true;
                
                try {
                    const response = await fetch('/api/validate-key', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                        },
                        body: JSON.stringify({ api_key: key })
                    });
                    
                    const data = await response.json();
                    
                    if (data.valid) {
                        btn.innerHTML = '✅ Access Granted';
                        btn.style.background = 'linear-gradient(45deg, #00ff9d, #00d4ff)';
                        
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 800);
                    } else {
                        errorDiv.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        btn.innerHTML = 'Enter Dashboard';
                        btn.disabled = false;
                    }
                } catch (error) {
                    console.error('Validation error:', error);
                    errorDiv.textContent = 'Connection error. Please try again.';
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
                
                // Check if already logged in from sessionStorage
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
    """Validate API key - IMPROVED with session handling"""
    data = request.get_json()
    api_key = data.get('api_key', '').strip().upper()
    
    if not api_key:
        return jsonify({"valid": False, "error": "No key provided"})
    
    user_data = validate_api_key(api_key)
    
    if user_data:
        session.clear()
        session['user_key'] = api_key
        session['user_data'] = user_data
        session.permanent = True
        # Force session save
        session.modified = True
        
        return jsonify({"valid": True, "user": user_data.get('in_game_name')})
    else:
        return jsonify({"valid": False, "error": "Invalid API key"})

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    response = make_response(redirect(url_for('home')))
    response.set_cookie('session', '', expires=0)
    return response

@app.route('/dashboard')
def dashboard():
    """Profile Dashboard - SIMPLIFIED to avoid f-string issues"""
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    user_data = session.get('user_data')
    if not user_data:
        # Try to re-validate the key
        user_data = validate_api_key(session.get('user_key'))
        if not user_data:
            session.clear()
            return redirect(url_for('home'))
        session['user_data'] = user_data
    
    # Calculate stats
    kd = user_data.get('total_kills', 0) / max(user_data.get('total_deaths', 1), 1)
    total_games = user_data.get('wins', 0) + user_data.get('losses', 0)
    win_rate = (user_data.get('wins', 0) / total_games * 100) if total_games > 0 else 0
    
    # Format dates
    from datetime import datetime as dt
    created_at = user_data.get('created_at', '')
    if created_at:
        try:
            created_date = dt.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            created_str = created_date.strftime('%b %d, %Y')
            days_ago = (dt.now() - created_date).days
        except:
            created_str = "Unknown"
            days_ago = 0
    else:
        created_str = "Unknown"
        days_ago = 0
    
    is_admin = user_data.get('is_admin', 0)
    
    # Get open tickets for this user
    conn = get_db_connection()
    tickets = conn.execute(
        'SELECT * FROM tickets WHERE discord_id = ? AND status = "open" ORDER BY created_at DESC LIMIT 3',
        (user_data['discord_id'],)
    ).fetchall()
    conn.close()
    
    # Build tickets HTML - Keep it simple
    tickets_html = ''
    for ticket in tickets:
        category_info = next((c for c in TICKET_CATEGORIES if c["name"] == ticket['category']), TICKET_CATEGORIES[-1])
        color_hex = f"#{hex(category_info['color'])[2:].zfill(6)}"
        tickets_html += f'<div class="ticket-card"><div class="ticket-header"><div class="ticket-title"><span class="ticket-emoji">{category_info["emoji"]}</span><strong>TICKET-{ticket["ticket_id"]}</strong></div><span class="status-open">OPEN</span></div><p class="ticket-issue">{ticket["issue"][:100]}...</p><div class="ticket-footer"><span class="ticket-category" style="color: {color_hex};">{ticket["category"]}</span><span class="ticket-date">{ticket["created_at"][:10]}</span></div></div>'
    
    if not tickets_html:
        tickets_html = '<div class="no-tickets"><span>🎉</span><p>No open tickets</p></div>'
    
    # Determine colors based on stats
    kd_color = '#00ff9d' if kd >= 1.5 else '#ffd700' if kd >= 1 else '#ff6b6b'
    win_rate_color = '#00ff9d' if win_rate >= 60 else '#ffd700' if win_rate >= 40 else '#ff6b6b'
    
    # Build the HTML response
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>GOBLIN Profile</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #000;
            color: #fff;
            min-height: 100vh;
            overflow-x: hidden;
        }}
        
        .header {{
            background: rgba(15, 5, 30, 0.9);
            backdrop-filter: blur(25px);
            border-bottom: 3px solid #ff00ff;
            padding: 25px 50px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 10px 50px rgba(0, 0, 0, 0.7);
        }}
        
        .logo {{
            font-size: 2.2rem;
            font-weight: 900;
            background: linear-gradient(45deg, #ff00ff, #9d00ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 0 25px rgba(255, 0, 255, 0.4);
            letter-spacing: 1px;
            font-family: 'Arial Black', sans-serif;
        }}
        
        .user-info {{
            display: flex;
            align-items: center;
            gap: 30px;
        }}
        
        .user-details {{
            text-align: right;
        }}
        
        .user-name {{
            font-size: 1.4rem;
            color: #ff00ff;
            font-weight: bold;
            margin-bottom: 5px;
            text-shadow: 0 0 15px rgba(255, 0, 255, 0.5);
        }}
        
        .user-subtitle {{
            color: #b19cd9;
            font-size: 0.9rem;
            font-weight: 300;
        }}
        
        .admin-badge {{
            background: linear-gradient(45deg, #ff00ff, #9d00ff);
            color: white;
            padding: 8px 20px;
            border-radius: 25px;
            font-size: 0.9rem;
            font-weight: bold;
            box-shadow: 0 5px 20px rgba(255, 0, 255, 0.4);
            animation: glow 2s infinite;
        }}
        
        @keyframes glow {{
            0%, 100% {{ box-shadow: 0 5px 20px rgba(255, 0, 255, 0.4); }}
            50% {{ box-shadow: 0 5px 30px rgba(255, 0, 255, 0.7); }}
        }}
        
        .logout-btn {{
            padding: 12px 28px;
            background: linear-gradient(45deg, #ff416c, #ff4b2b);
            color: white;
            border: none;
            border-radius: 15px;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s;
            box-shadow: 0 8px 25px rgba(255, 65, 108, 0.4);
            font-family: 'Segoe UI', sans-serif;
            letter-spacing: 1px;
        }}
        
        .logout-btn:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(255, 65, 108, 0.6);
        }}
        
        .container {{
            max-width: 1300px;
            margin: 0 auto;
            padding: 50px;
        }}
        
        .profile-section {{
            display: grid;
            grid-template-columns: 1fr 400px;
            gap: 40px;
            margin-bottom: 50px;
        }}
        
        @media (max-width: 1100px) {{
            .profile-section {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .profile-card {{
            background: rgba(25, 10, 50, 0.7);
            backdrop-filter: blur(25px);
            border-radius: 25px;
            padding: 50px;
            border: 1px solid rgba(255, 0, 255, 0.3);
            box-shadow: 0 25px 60px rgba(157, 0, 255, 0.2),
                        inset 0 1px 0 rgba(255, 255, 255, 0.1);
            animation: slideUp 0.8s ease-out;
        }}
        
        .profile-header {{
            display: flex;
            align-items: center;
            gap: 30px;
            margin-bottom: 40px;
            padding-bottom: 30px;
            border-bottom: 2px solid rgba(157, 0, 255, 0.3);
        }}
        
        .avatar {{
            width: 100px;
            height: 100px;
            background: linear-gradient(45deg, #ff00ff, #9d00ff);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2.5rem;
            color: white;
            box-shadow: 0 10px 30px rgba(255, 0, 255, 0.4);
            animation: rotate 20s linear infinite;
        }}
        
        @keyframes rotate {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}
        
        .avatar-content {{
            transform: rotate(-360deg);
            animation: counterRotate 20s linear infinite;
        }}
        
        @keyframes counterRotate {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(-360deg); }}
        }}
        
        .profile-info h2 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #ff00ff, #9d00ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        .profile-info p {{
            color: #b19cd9;
            font-size: 1.1rem;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }}
        
        .stat-item {{
            background: rgba(0, 0, 0, 0.4);
            border-radius: 20px;
            padding: 30px;
            text-align: center;
            border: 1px solid rgba(157, 0, 255, 0.2);
            transition: all 0.4s;
            position: relative;
            overflow: hidden;
        }}
        
        .stat-item:hover {{
            transform: translateY(-10px);
            border-color: rgba(255, 0, 255, 0.5);
            box-shadow: 0 20px 40px rgba(255, 0, 255, 0.2);
        }}
        
        .stat-item::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, #ff00ff, #9d00ff);
        }}
        
        .stat-value {{
            font-size: 3rem;
            font-weight: 900;
            margin: 15px 0;
            font-family: 'Arial Black', sans-serif;
            text-shadow: 0 0 20px currentColor;
        }}
        
        .stat-label {{
            color: #b19cd9;
            font-size: 1rem;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 10px;
            font-weight: 300;
        }}
        
        .key-card {{
            background: rgba(25, 10, 50, 0.7);
            backdrop-filter: blur(25px);
            border-radius: 25px;
            padding: 50px;
            border: 1px solid rgba(0, 212, 255, 0.3);
            box-shadow: 0 25px 60px rgba(0, 212, 255, 0.15),
                        inset 0 1px 0 rgba(255, 255, 255, 0.1);
            animation: slideUp 0.8s ease-out 0.2s both;
        }}
        
        .key-card h3 {{
            font-size: 1.8rem;
            margin-bottom: 25px;
            color: #00d4ff;
            text-shadow: 0 0 15px rgba(0, 212, 255, 0.5);
        }}
        
        .key-display {{
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid rgba(157, 0, 255, 0.5);
            border-radius: 20px;
            padding: 30px;
            margin: 30px 0;
            font-family: 'Courier New', monospace;
            color: #00ff9d;
            text-align: center;
            cursor: pointer;
            position: relative;
            overflow: hidden;
            letter-spacing: 3px;
            font-size: 1.5rem;
            text-shadow: 0 0 10px #00ff9d;
            box-shadow: 0 10px 30px rgba(0, 255, 157, 0.1);
            transition: all 0.3s;
        }}
        
        .key-display:hover {{
            transform: scale(1.02);
            box-shadow: 0 15px 40px rgba(0, 255, 157, 0.2);
        }}
        
        .key-display::before {{
            content: 'Click to reveal';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.95);
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: sans-serif;
            font-size: 1.3rem;
            color: #b19cd9;
            backdrop-filter: blur(5px);
            border-radius: 18px;
            transition: opacity 0.3s;
        }}
        
        .key-display.revealed::before {{
            opacity: 0;
            pointer-events: none;
        }}
        
        .action-buttons {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-top: 40px;
        }}
        
        .action-btn {{
            padding: 20px;
            background: linear-gradient(45deg, #ff00ff, #9d00ff);
            color: white;
            border: none;
            border-radius: 15px;
            font-weight: bold;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            letter-spacing: 1px;
            font-family: 'Segoe UI', sans-serif;
            box-shadow: 0 10px 30px rgba(157, 0, 255, 0.3);
        }}
        
        .action-btn:hover {{
            transform: translateY(-8px);
            box-shadow: 0 20px 40px rgba(255, 0, 255, 0.5);
            background: linear-gradient(45deg, #9d00ff, #ff00ff);
        }}
        
        .action-btn.admin {{
            background: linear-gradient(45deg, #00ff9d, #00d4ff);
        }}
        
        .action-btn.admin:hover {{
            box-shadow: 0 20px 40px rgba(0, 255, 157, 0.5);
        }}
        
        .tickets-section {{
            background: rgba(25, 10, 50, 0.7);
            backdrop-filter: blur(25px);
            border-radius: 25px;
            padding: 50px;
            margin-bottom: 50px;
            border: 1px solid rgba(255, 0, 255, 0.3);
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.3);
            animation: slideUp 0.8s ease-out 0.4s both;
        }}
        
        .tickets-section h3 {{
            font-size: 2rem;
            margin-bottom: 40px;
            color: #ff00ff;
            text-shadow: 0 0 20px rgba(255, 0, 255, 0.5);
        }}
        
        .tickets-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 25px;
        }}
        
        .ticket-card {{
            background: rgba(20, 5, 40, 0.8);
            border-radius: 20px;
            padding: 30px;
            border: 1px solid rgba(157, 0, 255, 0.2);
            transition: all 0.3s;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }}
        
        .ticket-card:hover {{
            transform: translateY(-10px);
            border-color: rgba(255, 0, 255, 0.4);
            box-shadow: 0 20px 40px rgba(255, 0, 255, 0.2);
        }}
        
        .ticket-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}
        
        .ticket-title {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        
        .ticket-emoji {{
            font-size: 1.5rem;
        }}
        
        .status-open {{
            color: #00ff9d;
            font-weight: bold;
            font-size: 0.9rem;
            padding: 5px 15px;
            background: rgba(0, 255, 157, 0.1);
            border-radius: 20px;
            text-shadow: 0 0 10px #00ff9d;
        }}
        
        .ticket-issue {{
            color: #d4b3ff;
            margin-bottom: 25px;
            font-size: 1.1rem;
            line-height: 1.5;
        }}
        
        .ticket-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: #888;
            font-size: 0.9rem;
        }}
        
        .ticket-category {{
            font-weight: bold;
        }}
        
        .no-tickets {{
            grid-column: 1 / -1;
            text-align: center;
            padding: 60px;
            color: #666;
        }}
        
        .no-tickets span {{
            font-size: 4rem;
            display: block;
            margin-bottom: 20px;
            opacity: 0.5;
        }}
        
        .notification {{
            position: fixed;
            bottom: 40px;
            right: 40px;
            background: linear-gradient(45deg, #00ff9d, #00d4ff);
            color: #000;
            padding: 25px 35px;
            border-radius: 20px;
            z-index: 1000;
            display: none;
            animation: slideInRight 0.5s ease-out;
            font-weight: bold;
            font-size: 1.1rem;
            box-shadow: 0 15px 40px rgba(0, 255, 157, 0.5);
            font-family: 'Segoe UI', sans-serif;
        }}
        
        @keyframes slideInRight {{
            from {{ transform: translateX(100%); opacity: 0; }}
            to {{ transform: translateX(0); opacity: 1; }}
        }}
        
        @keyframes slideUp {{
            from {{ opacity: 0; transform: translateY(50px); }}
            to {{ opacity: 1; transform: translateY(0); }}
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
            .profile-section {{
                gap: 20px;
            }}
            .profile-card, .key-card, .tickets-section {{
                padding: 30px 20px;
            }}
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            .tickets-grid {{
                grid-template-columns: 1fr;
            }}
            .avatar {{
                width: 80px;
                height: 80px;
                font-size: 2rem;
            }}
            .profile-info h2 {{
                font-size: 2rem;
            }}
            .key-display {{
                font-size: 1.2rem;
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">GOBLIN PROFILE</div>
        <div class="user-info">
            <div class="user-details">
                <div class="user-name">{user_data.get('in_game_name', 'Player')}</div>
                <div class="user-subtitle">Member for {days_ago} days • {total_games} games</div>
            </div>
            { '<span class="admin-badge">👑 ADMIN</span>' if is_admin else '' }
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
    </div>
    
    <div class="container">
        <div class="profile-section">
            <div class="profile-card">
                <div class="profile-header">
                    <div class="avatar">
                        <div class="avatar-content">👤</div>
                    </div>
                    <div class="profile-info">
                        <h2>{user_data.get('in_game_name', 'Player')}</h2>
                        <p>Joined on {created_str} • Prestige {user_data.get('prestige', 0)}</p>
                    </div>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-label">K/D Ratio</div>
                        <div class="stat-value" style="color: {kd_color};">{kd:.2f}</div>
                        <div style="color: #d4b3ff; font-size: 0.9rem;">{user_data.get('total_kills', 0)} kills / {user_data.get('total_deaths', 0)} deaths</div>
                    </div>
                    
                    <div class="stat-item">
                        <div class="stat-label">Win Rate</div>
                        <div class="stat-value" style="color: {win_rate_color};">{win_rate:.1f}%</div>
                        <div style="color: #d4b3ff; font-size: 0.9rem;">{user_data.get('wins', 0)} wins / {user_data.get('losses', 0)} losses</div>
                    </div>
                    
                    <div class="stat-item">
                        <div class="stat-label">Games Played</div>
                        <div class="stat-value" style="color: #9d00ff;">{total_games}</div>
                        <div style="color: #d4b3ff; font-size: 0.9rem;">Total matches completed</div>
                    </div>
                    
                    <div class="stat-item">
                        <div class="stat-label">Prestige Level</div>
                        <div class="stat-value" style="color: #ffd700;">{user_data.get('prestige', 0)}</div>
                        <div style="color: #d4b3ff; font-size: 0.9rem;">Current prestige rank</div>
                    </div>
                </div>
            </div>
            
            <div class="key-card">
                <h3>🔑 Your API Key</h3>
                <p style="color: #b19cd9; margin-bottom: 20px; line-height: 1.6;">
                    Keep this key secure. Use it to access your dashboard and API features.
                    Do not share it with anyone.
                </p>
                
                <div class="key-display" id="apiKeyDisplay" onclick="revealKey()">
                    {session['user_key']}
                </div>
                
                <div class="action-buttons">
                    <button class="action-btn" onclick="copyKey()">
                        <span>📋</span> Copy Key
                    </button>
                    { '<button class="action-btn admin" onclick="changeKey()"><span>🔑</span> Change Key</button>' if is_admin else '' }
                    <button class="action-btn" onclick="createTicket()">
                        <span>🎫</span> Create Ticket
                    </button>
                </div>
            </div>
        </div>
        
        <div class="tickets-section">
            <h3>🎫 Your Open Tickets</h3>
            <div class="tickets-grid">
                {tickets_html}
            </div>
        </div>
    </div>
    
    <div class="notification" id="notification"></div>
    
    <script>
        function revealKey() {{
            const display = document.getElementById('apiKeyDisplay');
            display.classList.add('revealed');
            showNotification('🔓 Key revealed');
        }}
        
        function copyKey() {{
            const key = "{session['user_key']}";
            navigator.clipboard.writeText(key).then(() => {{
                showNotification('✅ API key copied to clipboard');
                
                // Animate copy button
                const btn = event.target.closest('.action-btn');
                if (btn) {{
                    btn.style.background = 'linear-gradient(45deg, #00ff9d, #00d4ff)';
                    setTimeout(() => {{
                        btn.style.background = 'linear-gradient(45deg, #ff00ff, #9d00ff)';
                    }}, 1000);
                }}
            }});
        }}
        
        function refreshProfile() {{
            showNotification('🔄 Refreshing profile...');
            setTimeout(() => location.reload(), 1000);
        }}
        
        function changeKey() {{
            if (!confirm('Generate a new API key? Your current key will be invalidated.')) return;
            
            showNotification('🔑 Generating new key...');
            
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
            showNotification('🎫 Use /ticket command in Discord to create tickets');
        }}
        
        function showNotification(message) {{
            const notification = document.getElementById('notification');
            notification.textContent = message;
            notification.style.display = 'block';
            
            setTimeout(() => {{
                notification.style.display = 'none';
            }}, 3000);
        }}
        
        // Auto-refresh profile every 2 minutes
        setInterval(refreshProfile, 120000);
        
        // Add hover effect to stat cards
        document.querySelectorAll('.stat-item').forEach(card => {{
            card.addEventListener('mouseenter', () => {{
                const value = card.querySelector('.stat-value');
                const color = getComputedStyle(value).color;
                card.style.borderColor = color;
            }});
            
            card.addEventListener('mouseleave', () => {{
                card.style.borderColor = 'rgba(157, 0, 255, 0.2)';
            }});
        }});
    </script>
</body>
</html>'''
    
    return html

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/check-admin')
def check_admin():
    """Check if user has admin role"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"is_admin": False})
    
    user_data = validate_api_key(api_key.upper())
    if not user_data:
        return jsonify({"is_admin": False})
    
    return jsonify({"is_admin": bool(user_data.get('is_admin', 0))})

@app.route('/api/change-key', methods=['POST'])
def change_key():
    """Change API key (admin only)"""
    data = request.get_json()
    api_key = data.get('api_key', '').upper()
    
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
    api_key = request.args.get('key', '').upper()
    if not api_key:
        return jsonify({"error": "No key provided"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"error": "Invalid key"}), 401
    
    return jsonify({"success": True, "message": "Stats refreshed"})

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
        "service": "GOBLIN Bot v7.0",
        "timestamp": datetime.utcnow().isoformat()
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    init_db()
    
    print(f"\n{'='*60}")
    print("🎮 GOBLIN BOT - ENHANCED EDITION")
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
    print(f"🎨 Design: Animated dark theme with particles")
    
    print(f"\n🎮 Discord Commands:")
    print(f"   /ping - Check bot status (with toxic responses)")
    print(f"   /register [name] - Get API key")
    print(f"   /profile - Show your profile and stats")
    print(f"   /key - Show your API key")
    print(f"   /ticket [issue] [category] - Create private ticket")
    print(f"   /close - Close current ticket (deletes channel)")
    
    print(f"\n🎫 Ticket System:")
    print(f"   • Channels deleted when tickets are closed")
    print(f"   • Category options: Bug, Feature, Account, Tech, Other")
    print(f"   • Close button in ticket channel")
    print(f"   • Private channels (user + mods only)")
    print(f"   • Webhook notifications: {'Enabled' if TICKET_WEBHOOK else 'Disabled'}")
    
    print(f"\n🔐 Security Features:")
    print(f"   • Improved API key validation")
    print(f"   • Session management with expiration")
    print(f"   • Admin-only key changes")
    print(f"   • Secure ticket channels")
    
    print(f"\n🎨 UI Features:")
    print(f"   • Dark theme with pink/purple accents")
    print(f"   • Profile view with stats")
    print(f"   • Interactive elements with hover effects")
    
    print(f"\n💡 How it works:")
    print(f"   1. Use /register in Discord to get API key")
    print(f"   2. Use /key to see your key anytime")
    print(f"   3. Login to animated dashboard")
    print(f"   4. View your profile and stats")
    print(f"   5. Use /ticket for private support")
    print(f"   6. Close tickets deletes the channel")
    
    print(f"\n🔧 Environment Variables:")
    print(f"   MOD_ROLE_ID={MOD_ROLE_ID or 'Not set'}")
    print(f"   TICKET_WEBHOOK={'Set' if TICKET_WEBHOOK else 'Not set'}")
    
    print(f"\n{'='*60}\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)

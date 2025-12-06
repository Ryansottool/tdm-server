# app.py - GOBLIN HUT BOT
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
    {"name": "Bug Report", "emoji": "", "color": 0xe74c3c},
    {"name": "Feature Request", "emoji": "", "color": 0x3498db},
    {"name": "Account Issue", "emoji": "", "color": 0x2ecc71},
    {"name": "Technical Support", "emoji": "", "color": 0xf39c12},
    {"name": "Other", "emoji": "", "color": 0x9b59b6}
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
            response = requests.get(url, headers=headers, timeout=5)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=5)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data, timeout=5)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=5)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=data, timeout=5)
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
            "title": f"Ticket {action.capitalize()}",
            "description": f"**Ticket ID:** `{ticket_id}`\n**User:** {user_name} (<@{user_id}>)\n**Category:** {category}\n**Issue:** {issue[:500]}",
            "color": category_info['color'],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"Ticket {action}"}
        }
        
        if channel_id and action == "created":
            embed["fields"] = [{
                "name": "Channel",
                "value": f"<#{channel_id}>",
                "inline": True
            }]
        
        data = {
            "embeds": [embed],
            "username": "Goblin Hut Ticket System",
            "avatar_url": "https://i.imgur.com/Lg9YqZm.png"
        }
        
        response = requests.post(TICKET_WEBHOOK, json=data, timeout=5)
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
            "topic": f"{issue[:50]}...",
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
            "title": f"Ticket #{ticket_id}",
            "description": issue,
            "color": category_info['color'],
            "fields": [
                {"name": "Created By", "value": f"<@{user_id}> ({user_name})", "inline": True},
                {"name": "Created", "value": f"<t:{int(time.time())}:R>", "inline": True},
                {"name": "Category", "value": category, "inline": True},
                {"name": "Channel", "value": f"<#{channel['id']}>", "inline": True}
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
                    "custom_id": f"close_ticket_{ticket_id}"
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary style (grey)
                    "label": "Add User",
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
# SECURE KEY GENERATION - FIXED LENGTH
# =============================================================================

def generate_secure_key():
    """Generate strong API key - FIXED LENGTH (24 chars total)"""
    alphabet = string.ascii_letters + string.digits
    key = 'GOB-' + ''.join(secrets.choice(alphabet) for _ in range(20))  # 4 + 20 = 24 chars
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
        logger.info("Database initialized")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# KEY VALIDATION - FIXED VERSION
# =============================================================================

def validate_api_key(api_key):
    """Validate API key - FIXED VERSION"""
    if not api_key:
        return None
    
    # Clean the API key
    api_key = api_key.strip().upper()
    
    if not api_key.startswith("GOB-"):
        return None
    
    # Check minimum length (GOB- + 20 chars = 24 total)
    if len(api_key) != 24:
        logger.error(f"Invalid API key length: {len(api_key)} chars (expected 24)")
        return None
    
    conn = get_db_connection()
    try:
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
            player_dict = {key: player[key] for key in player.keys()}
            logger.info(f"Validated API key for user: {player['in_game_name']}")
            return player_dict
        else:
            logger.error(f"No player found for API key: {api_key}")
            return None
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        return None
    finally:
        conn.close()

# =============================================================================
# DISCORD BOT FUNCTIONS
# =============================================================================

def test_discord_token():
    """Test if Discord token is valid"""
    global bot_active, bot_info
    
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN not set")
        return False
    
    try:
        url = "https://discord.com/api/v10/users/@me"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            bot_info = response.json()
            bot_active = True
            logger.info(f"Discord bot is ACTIVE: {bot_info['username']}")
            return True
        else:
            logger.error(f"Invalid Discord token: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Discord API error: {e}")
        return False

def register_commands():
    """Register slash commands"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        logger.error("Cannot register commands")
        return False
    
    commands = [
        {
            "name": "ping",
            "description": "Check if bot is online",
            "type": 1
        },
        {
            "name": "register",
            "description": "Register and get API key (use once)",
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
                        {"name": "Bug Report", "value": "Bug Report"},
                        {"name": "Feature Request", "value": "Feature Request"},
                        {"name": "Account Issue", "value": "Account Issue"},
                        {"name": "Technical Support", "value": "Technical Support"},
                        {"name": "Other", "value": "Other"}
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
            logger.info("Registered commands")
            return True
        else:
            logger.error(f"Failed to register commands: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error registering commands: {e}")
        return False

# =============================================================================
# DISCORD INTERACTIONS
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord slash commands"""
    # Log the incoming request
    logger.info("Received interaction request")
    
    # Check if Discord signature verification is required
    signature = request.headers.get('X-Signature-Ed25519')
    timestamp = request.headers.get('X-Signature-Timestamp')
    
    # If signature headers are present, verify them
    if signature and timestamp and DISCORD_PUBLIC_KEY:
        if not verify_discord_signature(request):
            logger.error("Invalid Discord signature")
            return jsonify({"error": "Invalid signature"}), 401
    
    data = request.get_json()
    
    # Handle PING
    if data.get('type') == 1:
        logger.info("Responding to PING")
        return jsonify({"type": 1})
    
    # Handle button clicks (type 3)
    if data.get('type') == 3:
        custom_id = data.get('data', {}).get('custom_id', '')
        user_id = data.get('member', {}).get('user', {}).get('id')
        channel_id = data.get('channel_id')
        
        logger.info(f"Button click: {custom_id} by {user_id}")
        
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
                                "content": f"Ticket {ticket_id} has been closed and channel deleted.",
                                "flags": 64
                            }
                        })
                    else:
                        return jsonify({
                            "type": 4,
                            "data": {
                                "content": f"Ticket marked as closed but could not delete channel.",
                                "flags": 64
                            }
                        })
                else:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": "You don't have permission to close this ticket.",
                            "flags": 64
                        }
                    })
        
        return jsonify({"type": 6})  # ACK for other button clicks
    
    # Handle slash commands (type 2)
    if data.get('type') == 2:
        command = data.get('data', {}).get('name')
        user_id = data.get('member', {}).get('user', {}).get('id')
        user_name = data.get('member', {}).get('user', {}).get('global_name', 'Unknown')
        server_id = data.get('guild_id', 'DM')
        
        logger.info(f"Command received: {command} from {user_name} ({user_id})")
        
        # PING COMMAND
        if command == 'ping':
            # 30% chance for toxic response
            if random.random() < 0.3:
                response = random.choice(TOXIC_PING_RESPONSES)
            else:
                response = random.choice(NORMAL_PING_RESPONSES)
            
            logger.info(f"Responding to ping: {response}")
            return jsonify({
                "type": 4,
                "data": {
                    "content": response
                }
            })
        
        # REGISTER COMMAND - FIXED TO PREVENT REUSE
        elif command == 'register':
            options = data.get('data', {}).get('options', [])
            in_game_name = options[0].get('value', 'Unknown') if options else 'Unknown'
            
            logger.info(f"Registering user {user_name} with name {in_game_name}")
            
            conn = get_db_connection()
            
            existing = conn.execute(
                'SELECT * FROM players WHERE discord_id = ?',
                (user_id,)
            ).fetchone()
            
            if existing:
                api_key = existing['api_key']
                conn.close()
                logger.info(f"User {user_name} already registered")
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"You are already registered as **{existing['in_game_name']}**\n\n"
                            f"**Your API Key:**\n```{api_key}```\n\n"
                            f"**Dashboard:** {request.host_url}\n"
                            f"Use `/key` to see your key again anytime"
                        ),
                        "flags": 64
                    }
                })
            
            is_admin = is_user_admin_in_guild(server_id, user_id)
            api_key = generate_secure_key()
            
            # Log full API key for debugging
            logger.info(f"Generated API key for {user_name}: {api_key}")
            
            # Insert new player
            conn.execute('''
                INSERT INTO players 
                (discord_id, discord_name, in_game_name, api_key, server_id, is_admin)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, user_name, in_game_name, api_key, server_id, 1 if is_admin else 0))
            
            conn.commit()
            conn.close()
            
            admin_note = "\n**Admin access detected** - You have additional privileges." if is_admin else ""
            logger.info(f"User {user_name} registered successfully")
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"**Registration Successful!**{admin_note}\n\n"
                        f"**Name:** {in_game_name}\n"
                        f"**API Key:**\n```{api_key}```\n\n"
                        f"**Dashboard:** {request.host_url}\n"
                        f"Login to access your full dashboard\n\n"
                        f"**Note:** You can only register once. Use `/key` to see your key again."
                    ),
                    "flags": 64
                }
            })
        
        # TICKET COMMAND
        elif command == 'ticket':
            options = data.get('data', {}).get('options', [])
            issue = options[0].get('value', 'No issue specified') if options else 'No issue specified'
            category = options[1].get('value', 'Other') if len(options) > 1 else 'Other'
            
            ticket_id = f"T-{int(time.time()) % 10000:04d}"
            
            logger.info(f"Creating ticket {ticket_id} for user {user_name}: {issue[:50]}...")
            
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
                
                logger.info(f"Ticket {ticket_id} created with channel {channel_id}")
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"**Ticket Created**\n\n**Ticket ID:** {ticket_id}\n**Channel:** <#{channel_id}>",
                        "flags": 64
                    }
                })
            else:
                conn.close()
                logger.warning(f"Ticket {ticket_id} created but channel creation failed")
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"**Ticket Created**\n\n**Ticket ID:** {ticket_id}\n*Could not create private channel*",
                        "flags": 64
                    }
                })
        
        # CLOSE COMMAND
        elif command == 'close':
            channel_id = data.get('channel_id')
            logger.info(f"Close command in channel {channel_id} by {user_name}")
            
            # Check if user is in a ticket channel
            conn = get_db_connection()
            ticket = conn.execute(
                'SELECT * FROM tickets WHERE channel_id = ? AND status = "open"',
                (channel_id,)
            ).fetchone()
            conn.close()
            
            if not ticket:
                logger.info(f"No open ticket found in channel {channel_id}")
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "No open ticket in this channel",
                        "flags": 64
                    }
                })
            
            # Close the ticket and delete channel
            logger.info(f"Closing ticket {ticket['ticket_id']}")
            success = close_ticket_channel(channel_id, ticket['ticket_id'], user_id)
            
            if success:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"Ticket {ticket['ticket_id']} has been closed and channel deleted.",
                        "flags": 64
                    }
                })
            else:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"Ticket marked as closed but could not delete channel.",
                        "flags": 64
                    }
                })
        
        # PROFILE COMMAND - FIXED VERSION
        elif command == 'profile':
            logger.info(f"Profile command from {user_name}")
            
            conn = get_db_connection()
            player = conn.execute(
                'SELECT * FROM players WHERE discord_id = ?',
                (user_id,)
            ).fetchone()
            conn.close()
            
            if not player:
                logger.info(f"User {user_name} not registered")
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "You are not registered. Use `/register [name]` first.",
                        "flags": 64
                    }
                })
            
            # Calculate stats
            total_kills = player['total_kills'] or 0
            total_deaths = player['total_deaths'] or 1
            wins = player['wins'] or 0
            losses = player['losses'] or 0
            
            kd = total_kills / total_deaths
            total_games = wins + losses
            win_rate = (wins / total_games * 100) if total_games > 0 else 0
            
            # Format date
            created_at = player['created_at']
            try:
                created_date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                timestamp = int(created_date.timestamp())
            except:
                timestamp = int(time.time())
            
            embed = {
                "title": f"{player['in_game_name']}'s Profile",
                "color": 0x9d00ff,
                "fields": [
                    {"name": "In-Game Name", "value": f"`{player['in_game_name']}`", "inline": True},
                    {"name": "Prestige", "value": f"**{player['prestige']}**", "inline": True},
                    {"name": "Registered", "value": f"<t:{timestamp}:R>", "inline": True},
                    {"name": "K/D Ratio", "value": f"**{kd:.2f}** ({total_kills}/{total_deaths})", "inline": True},
                    {"name": "Win Rate", "value": f"**{win_rate:.1f}%** ({wins}/{total_games})", "inline": True},
                    {"name": "Games Played", "value": f"**{total_games}**", "inline": True},
                    {"name": "API Key", "value": f"`{player['api_key'][:8]}...`", "inline": False},
                    {"name": "Dashboard", "value": f"[Click Here]({request.host_url})", "inline": True},
                    {"name": "Status", "value": "**Admin**" if player['is_admin'] else "**Player**", "inline": True}
                ],
                "footer": {"text": "Use /key to see full API key"},
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Showing profile for {player['in_game_name']}")
            
            return jsonify({
                "type": 4,
                "data": {
                    "embeds": [embed],
                    "flags": 64
                }
            })
        
        # KEY COMMAND
        elif command == 'key':
            logger.info(f"Key command from {user_name}")
            
            conn = get_db_connection()
            player = conn.execute(
                'SELECT * FROM players WHERE discord_id = ?',
                (user_id,)
            ).fetchone()
            conn.close()
            
            if not player:
                logger.info(f"User {user_name} not registered")
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "You are not registered. Use `/register [name]` first.",
                        "flags": 64
                    }
                })
            
            logger.info(f"Showing key for {player['in_game_name']}")
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": (
                        f"**Your API Key**\n\n"
                        f"```{player['api_key']}```\n\n"
                        f"**Dashboard:** {request.host_url}\n"
                        f"Use this key to login to your dashboard"
                    ),
                    "flags": 64
                }
            })
    
    # Unknown command type
    logger.warning(f"Unknown interaction type: {data.get('type')}")
    return jsonify({
        "type": 4,
        "data": {
            "content": "Unknown command",
            "flags": 64
        }
    })

def verify_discord_signature(request):
    """Verify Discord request signature"""
    try:
        signature = request.headers.get('X-Signature-Ed25519')
        timestamp = request.headers.get('X-Signature-Timestamp')
        body = request.get_data().decode('utf-8')
        
        if not signature or not timestamp:
            logger.error("Missing signature headers")
            return False
        
        if not DISCORD_PUBLIC_KEY:
            logger.error("DISCORD_PUBLIC_KEY not set")
            return False
        
        # Import nacl if available
        try:
            import nacl.signing
            import nacl.exceptions
            
            message = f"{timestamp}{body}".encode('utf-8')
            signature_bytes = bytes.fromhex(signature)
            verify_key = nacl.signing.VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
            verify_key.verify(message, signature_bytes)
            
            logger.info("Discord signature verified")
            return True
            
        except ImportError:
            logger.warning("nacl library not installed, skipping signature verification")
            return True  # Skip verification if nacl not installed
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error in verify_discord_signature: {e}")
        return False

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@app.before_request
def before_request():
    """Check session before each request"""
    if request.endpoint not in ['home', 'api_validate_key', 'health', 'api_stats', 'static', 'interactions']:
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
# WEB INTERFACE
# =============================================================================

@app.route('/')
def home():
    """Home page - Goblin Hut"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            session['user_data'] = user_data
            return redirect(url_for('dashboard'))
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Goblin Hut</title>
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
                background: #0a0015;
                color: #fff;
                min-height: 100vh;
            }
            
            .container {
                max-width: 500px;
                margin: 0 auto;
                padding: 40px 20px;
                text-align: center;
            }
            
            .logo {
                font-size: 4rem;
                font-weight: bold;
                margin-bottom: 10px;
                color: #9d00ff;
                letter-spacing: 2px;
                font-family: 'Arial Black', sans-serif;
            }
            
            .subtitle {
                font-size: 1.3rem;
                color: #b19cd9;
                margin-bottom: 40px;
                font-weight: 300;
            }
            
            .login-box {
                background: rgba(20, 10, 40, 0.9);
                border-radius: 15px;
                padding: 40px;
                border: 1px solid #9d00ff;
            }
            
            .key-input {
                width: 100%;
                padding: 18px;
                background: rgba(0, 0, 0, 0.6);
                border: 2px solid #9d00ff;
                border-radius: 12px;
                color: #fff;
                font-size: 16px;
                text-align: center;
                margin-bottom: 25px;
                font-family: monospace;
                letter-spacing: 1px;
            }
            
            .key-input:focus {
                outline: none;
                border-color: #00d4ff;
            }
            
            .login-btn {
                width: 100%;
                padding: 18px;
                background: #9d00ff;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
            }
            
            .login-btn:hover {
                background: #ff00ff;
            }
            
            .login-btn:disabled {
                opacity: 0.7;
                cursor: not-allowed;
            }
            
            .error-box {
                background: rgba(255, 0, 0, 0.1);
                border: 1px solid #ff0000;
                border-radius: 10px;
                padding: 15px;
                margin-top: 20px;
                color: #ff6b6b;
                display: none;
            }
            
            .info-box {
                background: rgba(30, 15, 60, 0.9);
                border: 1px solid #9d00ff;
                border-radius: 15px;
                padding: 25px;
                margin-top: 30px;
                text-align: left;
                color: #d4b3ff;
            }
            
            .info-box strong {
                color: #00d4ff;
                display: block;
                margin-bottom: 15px;
                font-size: 1.1rem;
            }
            
            .info-box code {
                background: rgba(0, 0, 0, 0.5);
                padding: 3px 8px;
                border-radius: 5px;
                font-family: 'Courier New', monospace;
                color: #9d00ff;
            }
            
            .bot-status {
                padding: 12px 25px;
                background: rgba(30, 15, 60, 0.9);
                border: 1px solid #9d00ff;
                border-radius: 25px;
                margin-top: 30px;
                display: inline-block;
                font-weight: 600;
                font-size: 1rem;
            }
            
            .status-online {
                color: #00ff9d;
                border-color: #00ff9d;
            }
            
            .status-offline {
                color: #ff6b6b;
                border-color: #ff6b6b;
            }
            
            @media (max-width: 768px) {
                .container { padding: 20px; }
                .logo { font-size: 3rem; }
                .login-box { padding: 30px 20px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">GOBLIN HUT</div>
            <div class="subtitle">Enter your API key to enter the cave</div>
            
            <div class="login-box">
                <input type="password" 
                       class="key-input" 
                       id="apiKey" 
                       placeholder="GOB-XXXXXXXXXXXXXXXXXXXX"
                       autocomplete="off">
                
                <button class="login-btn" onclick="validateKey()" id="loginBtn">
                    Enter Cave
                </button>
                
                <div class="error-box" id="errorMessage">
                    Invalid API key
                </div>
            </div>
            
            <div class="info-box">
                <strong>How to get your API key:</strong>
                <p>1. Use <code>/register your_name</code> in Discord <em>(one-time only)</em></p>
                <p>2. Copy your <code>GOB-XXXXXXXXXXXXXXX</code> key from bot response</p>
                <p>3. Use <code>/key</code> to see your key anytime</p>
                <p>4. Enter it above to access your dashboard</p>
            </div>
            
            <div class="bot-status" id="botStatus">
                Bot Status: Checking...
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
                
                if (key.length !== 24) {
                    errorDiv.textContent = "Key must be 24 characters long (GOB- + 20 chars)";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                btn.innerHTML = 'Entering cave...';
                btn.disabled = true;
                
                try {
                    const response = await fetch('/api/validate-key', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ api_key: key })
                    });
                    
                    const data = await response.json();
                    
                    if (data.valid) {
                        btn.innerHTML = 'Access granted!';
                        setTimeout(() => window.location.href = '/dashboard', 500);
                    } else {
                        errorDiv.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        btn.innerHTML = 'Enter Cave';
                        btn.disabled = false;
                    }
                } catch (error) {
                    errorDiv.textContent = 'Connection error. Please try again.';
                    errorDiv.style.display = 'block';
                    btn.innerHTML = 'Enter Cave';
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
                        status.innerHTML = 'Bot Status: ONLINE';
                        status.className = 'bot-status status-online';
                    } else {
                        status.innerHTML = 'Bot Status: OFFLINE';
                        status.className = 'bot-status status-offline';
                    }
                } catch (error) {
                    document.getElementById('botStatus').innerHTML = 'Bot Status: ERROR';
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
    """Validate API key - FIXED VERSION"""
    data = request.get_json()
    api_key = data.get('api_key', '').strip().upper()
    
    if not api_key:
        return jsonify({"valid": False, "error": "No key provided"})
    
    # Validate format
    if not api_key.startswith('GOB-'):
        return jsonify({"valid": False, "error": "Key must start with GOB-"})
    
    if len(api_key) != 24:
        logger.error(f"Invalid key length: {len(api_key)} chars for key: {api_key}")
        return jsonify({"valid": False, "error": "Invalid key length (must be 24 characters)"})
    
    user_data = validate_api_key(api_key)
    
    if user_data:
        session.clear()
        session['user_key'] = api_key
        session['user_data'] = user_data
        session.permanent = True
        session.modified = True
        
        logger.info(f"API key validated successfully for user: {user_data.get('in_game_name')}")
        return jsonify({"valid": True, "user": user_data.get('in_game_name')})
    else:
        logger.error(f"API key validation failed for key: {api_key}")
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
    """Profile Dashboard - Goblin Hut"""
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    user_data = session.get('user_data')
    if not user_data:
        user_data = validate_api_key(session.get('user_key'))
        if not user_data:
            session.clear()
            return redirect(url_for('home'))
        session['user_data'] = user_data
    
    # Calculate stats
    total_kills = user_data.get('total_kills', 0)
    total_deaths = max(user_data.get('total_deaths', 1), 1)
    wins = user_data.get('wins', 0)
    losses = user_data.get('losses', 0)
    
    kd = total_kills / total_deaths
    total_games = wins + losses
    win_rate = (wins / total_games * 100) if total_games > 0 else 0
    
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
    
    # Simple dashboard HTML
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Goblin Hut - Profile</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: Arial, sans-serif;
            background: #0a0015;
            color: #fff;
            min-height: 100vh;
        }}
        
        .header {{
            background: #0f051e;
            border-bottom: 1px solid #9d00ff;
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .logo {{
            font-size: 1.8rem;
            font-weight: bold;
            color: #9d00ff;
        }}
        
        .user-info {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        
        .user-name {{
            font-size: 1.2rem;
            color: #00d4ff;
            font-weight: bold;
        }}
        
        .logout-btn {{
            padding: 10px 20px;
            background: #ff416c;
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
        }}
        
        .logout-btn:hover {{
            background: #ff4b2b;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 30px;
        }}
        
        .profile-section {{
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 30px;
            margin-bottom: 40px;
        }}
        
        @media (max-width: 1100px) {{
            .profile-section {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .profile-card, .key-card {{
            background: #190a32;
            border-radius: 15px;
            padding: 30px;
            border: 1px solid #9d00ff;
        }}
        
        .profile-header {{
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #9d00ff;
        }}
        
        .avatar {{
            width: 80px;
            height: 80px;
            background: #9d00ff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            color: white;
        }}
        
        .profile-info h2 {{
            font-size: 2rem;
            margin-bottom: 5px;
            color: #9d00ff;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-item {{
            background: rgba(0, 0, 0, 0.4);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            border: 1px solid #9d00ff;
        }}
        
        .stat-value {{
            font-size: 2.5rem;
            font-weight: bold;
            margin: 10px 0;
        }}
        
        .stat-label {{
            color: #b19cd9;
            font-size: 0.9rem;
        }}
        
        .key-display {{
            background: rgba(0, 0, 0, 0.6);
            border: 1px solid #9d00ff;
            border-radius: 15px;
            padding: 20px;
            margin: 20px 0;
            font-family: 'Courier New', monospace;
            color: #00ff9d;
            text-align: center;
            cursor: pointer;
            word-break: break-all;
        }}
        
        .action-btn {{
            width: 100%;
            padding: 15px;
            background: #9d00ff;
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: bold;
            cursor: pointer;
            margin: 10px 0;
        }}
        
        .action-btn:hover {{
            background: #ff00ff;
        }}
        
        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 15px;
                text-align: center;
                padding: 15px;
            }}
            .container {{
                padding: 15px;
            }}
            .profile-card, .key-card {{
                padding: 20px 15px;
            }}
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">GOBLIN HUT</div>
        <div class="user-info">
            <div class="user-name">{user_data.get('in_game_name', 'Player')}</div>
            <a href="/logout" class="logout-btn">Exit Cave</a>
        </div>
    </div>
    
    <div class="container">
        <div class="profile-section">
            <div class="profile-card">
                <div class="profile-header">
                    <div class="avatar">
                        ?
                    </div>
                    <div class="profile-info">
                        <h2>{user_data.get('in_game_name', 'Player')}</h2>
                        <p style="color: #b19cd9;">Joined on {created_str} • {total_games} games</p>
                    </div>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-label">K/D Ratio</div>
                        <div class="stat-value" style="color: #00ff9d;">{kd:.2f}</div>
                        <div style="color: #d4b3ff; font-size: 0.8rem;">{total_kills} kills / {total_deaths} deaths</div>
                    </div>
                    
                    <div class="stat-item">
                        <div class="stat-label">Win Rate</div>
                        <div class="stat-value" style="color: #00ff9d;">{win_rate:.1f}%</div>
                        <div style="color: #d4b3ff; font-size: 0.8rem;">{wins} wins / {losses} losses</div>
                    </div>
                    
                    <div class="stat-item">
                        <div class="stat-label">Games Played</div>
                        <div class="stat-value" style="color: #9d00ff;">{total_games}</div>
                        <div style="color: #d4b3ff; font-size: 0.8rem;">Total matches</div>
                    </div>
                    
                    <div class="stat-item">
                        <div class="stat-label">Prestige Level</div>
                        <div class="stat-value" style="color: #ffd700;">{user_data.get('prestige', 0)}</div>
                        <div style="color: #d4b3ff; font-size: 0.8rem;">Current rank</div>
                    </div>
                </div>
            </div>
            
            <div class="key-card">
                <h3 style="color: #00d4ff; margin-bottom: 20px;">Your API Key</h3>
                
                <div class="key-display" onclick="this.classList.add('revealed')">
                    {session['user_key']}
                </div>
                
                <button class="action-btn" onclick="copyKey()">
                    Copy Key
                </button>
                
                <button class="action-btn" onclick="createTicket()">
                    Create Ticket
                </button>
                
                { '<button class="action-btn" onclick="changeKey()" style="background: #00ff9d;">Change Key (Admin)</button>' if is_admin else '' }
            </div>
        </div>
    </div>
    
    <script>
        function copyKey() {{
            const key = "{session['user_key']}";
            navigator.clipboard.writeText(key).then(() => {{
                alert('API key copied to clipboard');
            }});
        }}
        
        function createTicket() {{
            alert('Use /ticket command in Discord to create tickets');
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
                    alert('New key generated! Please login again.');
                    window.location.href = '/logout';
                }} else {{
                    alert(data.error);
                }}
            }});
        }}
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
        "service": "Goblin Hut Bot",
        "timestamp": datetime.utcnow().isoformat()
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    init_db()
    
    print("\n" + "="*60)
    print("GOBLIN HUT BOT")
    print("="*60)
    
    if test_discord_token():
        bot_active = True
        print("Discord bot connected")
        
        if register_commands():
            print("Commands registered")
        else:
            print("Could not register commands")
    else:
        print("Discord token not set or invalid")
    
    print(f"\nWeb Interface: http://localhost:{port}")
    print(f"Bot Endpoint: /interactions")
    
    print("\nDiscord Commands:")
    print("   /ping - Check bot status")
    print("   /register [name] - Get API key (one-time only, 24 chars)")
    print("   /profile - Show your profile and stats")
    print("   /key - Show your API key")
    print("   /ticket [issue] [category] - Create support ticket")
    print("   /close - Close current ticket")
    
    print("\nAPI Key Format:")
    print("   Format: GOB-XXXXXXXXXXXXXXXXXXXX")
    print("   Length: 24 characters total (GOB- + 20 chars)")
    print("   Characters: Letters and numbers only")
    
    print("\nEnvironment Check:")
    print(f"   DISCORD_TOKEN: {'Set' if DISCORD_TOKEN else 'Not set'}")
    print(f"   DISCORD_CLIENT_ID: {'Set' if DISCORD_CLIENT_ID else 'Not set'}")
    print(f"   DISCORD_PUBLIC_KEY: {'Set' if DISCORD_PUBLIC_KEY else 'Not set'}")
    
    print("\nInstall required library:")
    print("   pip install pynacl")
    
    print("\n" + "="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)

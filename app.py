# app.py - GOBLIN HUT BOT
import os
import json
import sqlite3
import random
import string
import time
import requests
import re
import threading
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

# Webhook for score tracking
SCORE_WEBHOOK = os.environ.get('SCORE_WEBHOOK', '')

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

# Score tracking
score_matches = {}  # Store ongoing matches: {match_id: {team1: {players: [], score: 0}, team2: {players: [], score: 0}}}

# =============================================================================
# SERVER PING - KEEP ALIVE
# =============================================================================

def ping_server():
    """Ping the server every 5 minutes to keep it alive"""
    try:
        response = requests.get(f"http://localhost:{port}/health", timeout=10)
        logger.info(f"Server ping response: {response.status_code}")
    except Exception as e:
        logger.error(f"Server ping failed: {e}")

def start_ping_scheduler():
    """Start the ping scheduler"""
    def scheduler():
        while True:
            time.sleep(300)  # 5 minutes
            ping_server()
    
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    logger.info("Server ping scheduler started")

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

def get_discord_user(user_id):
    """Get Discord user info including avatar"""
    return discord_api_request(f"/users/{user_id}")

def get_discord_avatar_url(user_id, avatar_hash, size=256):
    """Get Discord avatar URL"""
    if not avatar_hash:
        return None
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size={size}"

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

def send_score_update(match_id, team1_score, team2_score, team1_players, team2_players):
    """Send score update to webhook"""
    if not SCORE_WEBHOOK:
        return
    
    try:
        embed = {
            "title": "🏆 Score Update",
            "description": f"Match ID: `{match_id}`",
            "color": 0x00ff9d,
            "fields": [
                {
                    "name": "Team 1",
                    "value": f"Score: **{team1_score}**\nPlayers: {', '.join(team1_players)}",
                    "inline": True
                },
                {
                    "name": "Team 2",
                    "value": f"Score: **{team2_score}**\nPlayers: {', '.join(team2_players)}",
                    "inline": True
                }
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Goblin Hut Score Tracker"}
        }
        
        data = {
            "embeds": [embed],
            "username": "Goblin Hut Score Tracker",
            "avatar_url": "https://i.imgur.com/Lg9YqZm.png"
        }
        
        response = requests.post(SCORE_WEBHOOK, json=data, timeout=5)
        if response.status_code not in [200, 204]:
            logger.error(f"Score webhook failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Score webhook error: {e}")

def send_match_start(match_id, team1_players, team2_players):
    """Send match start notification"""
    if not SCORE_WEBHOOK:
        return
    
    try:
        embed = {
            "title": "🎮 Match Started",
            "description": f"Match ID: `{match_id}`",
            "color": 0x9d00ff,
            "fields": [
                {
                    "name": "Team 1",
                    "value": f"Players: {', '.join(team1_players)}",
                    "inline": True
                },
                {
                    "name": "Team 2",
                    "value": f"Players: {', '.join(team2_players)}",
                    "inline": True
                }
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Goblin Hut Score Tracker"}
        }
        
        data = {
            "embeds": [embed],
            "username": "Goblin Hut Score Tracker",
            "avatar_url": "https://i.imgur.com/Lg9YqZm.png"
        }
        
        response = requests.post(SCORE_WEBHOOK, json=data, timeout=5)
        if response.status_code not in [200, 204]:
            logger.error(f"Match start webhook failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Match start webhook error: {e}")

def send_match_end(match_id, winner_team, team1_score, team2_score, team1_players, team2_players):
    """Send match end notification"""
    if not SCORE_WEBHOOK:
        return
    
    try:
        embed = {
            "title": "🏁 Match Ended",
            "description": f"Match ID: `{match_id}`\n**Winner: {winner_team}**",
            "color": 0xffd700,
            "fields": [
                {
                    "name": "Team 1",
                    "value": f"Score: **{team1_score}**\nPlayers: {', '.join(team1_players)}",
                    "inline": True
                },
                {
                    "name": "Team 2",
                    "value": f"Score: **{team2_score}**\nPlayers: {', '.join(team2_players)}",
                    "inline": True
                }
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Goblin Hut Score Tracker"}
        }
        
        data = {
            "embeds": [embed],
            "username": "Goblin Hut Score Tracker",
            "avatar_url": "https://i.imgur.com/Lg9YqZm.png"
        }
        
        response = requests.post(SCORE_WEBHOOK, json=data, timeout=5)
        if response.status_code not in [200, 204]:
            logger.error(f"Match end webhook failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Match end webhook error: {e}")

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
                "allow": "3072",  # VIEW_CHANNEL + SEND_MESSAGES + MANAGE_CHANNELS
                "deny": "0"
            })
        
        # Add ticket creator permission to manage their own channel
        channel_data["permission_overwrites"].append({
            "id": user_id,
            "type": 1,
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
                    "label": "Delete Channel",
                    "custom_id": f"delete_channel_{ticket_id}",
                    "emoji": {"name": "🗑️"}
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
    """Generate strong API key with consistent format: GOB- + 20 uppercase alphanumeric chars"""
    alphabet = string.ascii_uppercase + string.digits  # Only uppercase and digits
    # GOB- + 20 characters = total 24 characters
    key = 'GOB-' + ''.join(secrets.choice(alphabet) for _ in range(20))
    return key

# =============================================================================
# DATABASE SETUP
# =============================================================================

def init_db():
    """Initialize database"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Players table with CHECK constraint for API key length
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                discord_name TEXT,
                discord_avatar TEXT,
                in_game_name TEXT,
                api_key TEXT UNIQUE CHECK(LENGTH(api_key) = 24),
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
        
        # Matches table for score tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT UNIQUE,
                team1_players TEXT,
                team2_players TEXT,
                team1_score INTEGER DEFAULT 0,
                team2_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'ongoing',
                winner TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP
            )
        ''')
        
        # Player stats per match
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT,
                player_id TEXT,
                player_name TEXT,
                team INTEGER,
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                assists INTEGER DEFAULT 0
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
    """Validate API key with proper format and length checking"""
    if not api_key:
        logger.warning("No API key provided")
        return None
    
    # Clean the API key
    api_key = api_key.strip().upper()
    
    # Validate format: GOB- followed by exactly 20 alphanumeric characters
    pattern = r'^GOB-[A-Z0-9]{20}$'
    
    if not re.match(pattern, api_key):
        logger.warning(f"Invalid API key format: {api_key} (Length: {len(api_key)})")
        return None
    
    logger.info(f"Validating key: {api_key}, Length: {len(api_key)}, Pattern match: OK")
    
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
            logger.info(f"API key validated successfully for user: {player_dict.get('in_game_name')}")
            return player_dict
        else:
            logger.warning(f"API key not found in database: {api_key}")
            return None
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        return None
    finally:
        conn.close()

def fix_existing_keys():
    """Fix existing keys to correct format"""
    conn = get_db_connection()
    players = conn.execute('SELECT id, api_key FROM players').fetchall()
    
    fixed_count = 0
    for player in players:
        old_key = player['api_key']
        if old_key and (not old_key.startswith('GOB-') or len(old_key) != 24):
            new_key = generate_secure_key()
            logger.info(f"Fixing key for player {player['id']}: {old_key} -> {new_key}")
            conn.execute('UPDATE players SET api_key = ? WHERE id = ?', 
                       (new_key, player['id']))
            fixed_count += 1
    
    if fixed_count > 0:
        conn.commit()
        logger.info(f"Fixed {fixed_count} API keys")
    
    conn.close()
    return fixed_count

def test_key_validation():
    """Test key validation for debugging"""
    test_keys = [
        "GOB-ABCDEFGHIJKLMNOPQRST",  # Valid - 20 chars after GOB-
        "GOB-ABCDEFGHIJKLMNOPQRS",    # Invalid - 19 chars
        "GOB-ABCDEFGHIJKLMNOPQRSTU",  # Invalid - 21 chars
        "gob-ABCDEFGHIJKLMNOPQRST",   # Valid after uppercase conversion
        "GOB-ABCDEFGHIJKLMNOPQR",     # Invalid - 18 chars
        "GOB-1234567890ABCDEFGHIJ",   # Valid - mix of numbers and letters
        "WRONG-ABCDEFGHIJKLMNOPQR",   # Invalid prefix
        "GOB-ABCDEFGHIJKLMNOPQRSTUVWXYZ",  # Too long
        "GOB-ABCDEFGHIJ1234567890",   # Valid - numbers
        "",                           # Empty
        None,                         # None
    ]
    
    print("\n" + "="*60)
    print("API KEY VALIDATION TEST")
    print("="*60)
    
    for key in test_keys:
        result = validate_api_key(key)
        length = len(key) if key else 0
        print(f"Key: {str(key):40} Length: {length:2} Valid: {bool(result)}")
    
    print("="*60 + "\n")

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
        },
        {
            "name": "match",
            "description": "Match management commands",
            "type": 1,
            "options": [
                {
                    "name": "start",
                    "description": "Start a new match",
                    "type": 1,
                    "options": [
                        {
                            "name": "team1",
                            "description": "Team 1 players (comma separated)",
                            "type": 3,
                            "required": True
                        },
                        {
                            "name": "team2",
                            "description": "Team 2 players (comma separated)",
                            "type": 3,
                            "required": True
                        }
                    ]
                },
                {
                    "name": "score",
                    "description": "Update match score",
                    "type": 1,
                    "options": [
                        {
                            "name": "match_id",
                            "description": "Match ID",
                            "type": 3,
                            "required": True
                        },
                        {
                            "name": "team1_score",
                            "description": "Team 1 score",
                            "type": 4,
                            "required": True
                        },
                        {
                            "name": "team2_score",
                            "description": "Team 2 score",
                            "type": 4,
                            "required": True
                        }
                    ]
                },
                {
                    "name": "end",
                    "description": "End a match",
                    "type": 1,
                    "options": [
                        {
                            "name": "match_id",
                            "description": "Match ID",
                            "type": 3,
                            "required": True
                        }
                    ]
                },
                {
                    "name": "stats",
                    "description": "Show match stats",
                    "type": 1,
                    "options": [
                        {
                            "name": "match_id",
                            "description": "Match ID",
                            "type": 3,
                            "required": True
                        }
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
            logger.info("Registered commands")
            return True
        else:
            logger.error(f"Failed to register commands: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error registering commands: {e}")
        return False

# =============================================================================
# SCORE TRACKING FUNCTIONS
# =============================================================================

def start_match(team1_players, team2_players):
    """Start a new match"""
    match_id = f"MATCH-{int(time.time()) % 1000000:06d}"
    
    # Store in memory
    score_matches[match_id] = {
        'team1': {'players': team1_players, 'score': 0},
        'team2': {'players': team2_players, 'score': 0},
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Store in database
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO matches (match_id, team1_players, team2_players, status)
        VALUES (?, ?, ?, 'ongoing')
    ''', (match_id, ','.join(team1_players), ','.join(team2_players)))
    conn.commit()
    conn.close()
    
    # Send webhook
    send_match_start(match_id, team1_players, team2_players)
    
    return match_id

def update_score(match_id, team1_score, team2_score):
    """Update match score"""
    if match_id not in score_matches:
        return False
    
    score_matches[match_id]['team1']['score'] = team1_score
    score_matches[match_id]['team2']['score'] = team2_score
    
    # Update database
    conn = get_db_connection()
    conn.execute('''
        UPDATE matches 
        SET team1_score = ?, team2_score = ?
        WHERE match_id = ?
    ''', (team1_score, team2_score, match_id))
    conn.commit()
    conn.close()
    
    # Send webhook
    send_score_update(
        match_id,
        team1_score,
        team2_score,
        score_matches[match_id]['team1']['players'],
        score_matches[match_id]['team2']['players']
    )
    
    return True

def end_match(match_id):
    """End a match"""
    if match_id not in score_matches:
        return False
    
    match_data = score_matches[match_id]
    team1_score = match_data['team1']['score']
    team2_score = match_data['team2']['score']
    
    # Determine winner
    if team1_score > team2_score:
        winner = "Team 1"
    elif team2_score > team1_score:
        winner = "Team 2"
    else:
        winner = "Draw"
    
    # Update database
    conn = get_db_connection()
    conn.execute('''
        UPDATE matches 
        SET status = 'ended', winner = ?, ended_at = CURRENT_TIMESTAMP
        WHERE match_id = ?
    ''', (winner, match_id))
    
    # Update player stats
    # TODO: Add individual player stats update
    
    conn.commit()
    conn.close()
    
    # Send webhook
    send_match_end(
        match_id,
        winner,
        team1_score,
        team2_score,
        match_data['team1']['players'],
        match_data['team2']['players']
    )
    
    # Remove from memory
    del score_matches[match_id]
    
    return True

def get_match_stats(match_id):
    """Get match statistics"""
    conn = get_db_connection()
    match = conn.execute(
        'SELECT * FROM matches WHERE match_id = ?',
        (match_id,)
    ).fetchone()
    
    stats = None
    if match:
        stats = {
            'match_id': match['match_id'],
            'team1_players': match['team1_players'].split(','),
            'team2_players': match['team2_players'].split(','),
            'team1_score': match['team1_score'],
            'team2_score': match['team2_score'],
            'status': match['status'],
            'winner': match['winner'],
            'started_at': match['started_at'],
            'ended_at': match['ended_at']
        }
    
    conn.close()
    return stats

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
        guild_id = data.get('guild_id')
        
        logger.info(f"Button click: {custom_id} by {user_id}")
        
        # CLOSE TICKET BUTTON
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
                    member = get_guild_member(guild_id, user_id)
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
        
        # DELETE CHANNEL BUTTON
        elif custom_id.startswith('delete_channel_'):
            ticket_id = custom_id.replace('delete_channel_', '')
            
            # Check if user has permission to delete channel
            can_delete = False
            
            # Ticket creator can delete
            conn = get_db_connection()
            ticket = conn.execute(
                'SELECT * FROM tickets WHERE ticket_id = ?',
                (ticket_id,)
            ).fetchone()
            conn.close()
            
            if ticket and str(user_id) == str(ticket['discord_id']):
                can_delete = True
            
            # Admins/mods can delete
            if not can_delete and MOD_ROLE_ID:
                member = get_guild_member(guild_id, user_id)
                if member and MOD_ROLE_ID in member.get('roles', []):
                    can_delete = True
            
            if can_delete:
                # Delete the channel
                delete_result = delete_channel(channel_id)
                if delete_result:
                    # Update database
                    conn = get_db_connection()
                    conn.execute('''
                        UPDATE tickets 
                        SET status = "deleted", resolved_at = CURRENT_TIMESTAMP, assigned_to = ?
                        WHERE ticket_id = ?
                    ''', (user_id, ticket_id))
                    conn.commit()
                    conn.close()
                    
                    # Send webhook
                    if ticket:
                        send_ticket_webhook(ticket_id, ticket['discord_name'], ticket['discord_id'], 
                                          ticket['category'], ticket['issue'], None, "channel deleted")
                    
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"Channel has been deleted.",
                            "flags": 64
                        }
                    })
                else:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"Could not delete channel.",
                            "flags": 64
                        }
                    })
            else:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "You don't have permission to delete this channel.",
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
            
            # Get Discord avatar
            discord_user = get_discord_user(user_id)
            discord_avatar = discord_user.get('avatar') if discord_user else None
            
            # Insert new player
            conn.execute('''
                INSERT INTO players 
                (discord_id, discord_name, discord_avatar, in_game_name, api_key, server_id, is_admin)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, user_name, discord_avatar, in_game_name, api_key, server_id, 1 if is_admin else 0))
            
            conn.commit()
            conn.close()
            
            admin_note = "\n**Admin access detected** - You have additional privileges." if is_admin else ""
            logger.info(f"User {user_name} registered successfully with key {api_key}")
            
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
        
        # MATCH COMMAND
        elif command == 'match':
            options = data.get('data', {}).get('options', [])
            subcommand = options[0].get('name') if options else None
            
            # Check if user is admin
            is_admin = is_user_admin_in_guild(server_id, user_id)
            if not is_admin:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "You need admin privileges to manage matches.",
                        "flags": 64
                    }
                })
            
            # START MATCH
            if subcommand == 'start':
                sub_options = options[0].get('options', [])
                team1_str = sub_options[0].get('value', '') if len(sub_options) > 0 else ''
                team2_str = sub_options[1].get('value', '') if len(sub_options) > 1 else ''
                
                team1_players = [p.strip() for p in team1_str.split(',')]
                team2_players = [p.strip() for p in team2_str.split(',')]
                
                match_id = start_match(team1_players, team2_players)
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"**Match Started**\n\n**Match ID:** `{match_id}`\n**Team 1:** {', '.join(team1_players)}\n**Team 2:** {', '.join(team2_players)}",
                        "flags": 64
                    }
                })
            
            # UPDATE SCORE
            elif subcommand == 'score':
                sub_options = options[0].get('options', [])
                match_id = sub_options[0].get('value', '') if len(sub_options) > 0 else ''
                team1_score = sub_options[1].get('value', 0) if len(sub_options) > 1 else 0
                team2_score = sub_options[2].get('value', 0) if len(sub_options) > 2 else 0
                
                success = update_score(match_id, team1_score, team2_score)
                
                if success:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"**Score Updated**\n\n**Match ID:** `{match_id}`\n**Team 1:** {team1_score}\n**Team 2:** {team2_score}",
                            "flags": 64
                        }
                    })
                else:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"Match `{match_id}` not found.",
                            "flags": 64
                        }
                    })
            
            # END MATCH
            elif subcommand == 'end':
                sub_options = options[0].get('options', [])
                match_id = sub_options[0].get('value', '') if len(sub_options) > 0 else ''
                
                success = end_match(match_id)
                
                if success:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"**Match Ended**\n\n**Match ID:** `{match_id}`\nMatch has been ended and stats recorded.",
                            "flags": 64
                        }
                    })
                else:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"Match `{match_id}` not found.",
                            "flags": 64
                        }
                    })
            
            # MATCH STATS
            elif subcommand == 'stats':
                sub_options = options[0].get('options', [])
                match_id = sub_options[0].get('value', '') if len(sub_options) > 0 else ''
                
                stats = get_match_stats(match_id)
                
                if stats:
                    embed = {
                        "title": f"Match Stats - {match_id}",
                        "color": 0x00ff9d,
                        "fields": [
                            {"name": "Team 1", "value": f"Players: {', '.join(stats['team1_players'])}\nScore: **{stats['team1_score']}**", "inline": True},
                            {"name": "Team 2", "value": f"Players: {', '.join(stats['team2_players'])}\nScore: **{stats['team2_score']}**", "inline": True},
                            {"name": "Status", "value": stats['status'].upper(), "inline": True},
                            {"name": "Winner", "value": stats['winner'] or "TBD", "inline": True},
                            {"name": "Started", "value": f"<t:{int(datetime.strptime(stats['started_at'], '%Y-%m-%d %H:%M:%S').timestamp())}:R>", "inline": True}
                        ],
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    if stats['ended_at']:
                        embed["fields"].append({"name": "Ended", "value": f"<t:{int(datetime.strptime(stats['ended_at'], '%Y-%m-%d %H:%M:%S').timestamp())}:R>", "inline": True})
                    
                    return jsonify({
                        "type": 4,
                        "data": {
                            "embeds": [embed],
                            "flags": 64
                        }
                    })
                else:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"Match `{match_id}` not found.",
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
    if request.endpoint not in ['home', 'api_validate_key', 'health', 'api_stats', 'api_leaderboard', 'static', 'interactions']:
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
# WEB INTERFACE WITH SUBTLE ANIMATIONS
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
                overflow-x: hidden;
            }
            
            .background-glow {
                position: fixed;
                width: 500px;
                height: 500px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(157, 0, 255, 0.1) 0%, transparent 70%);
                filter: blur(60px);
                animation: float 20s infinite linear;
                z-index: -1;
            }
            
            @keyframes float {
                0% { transform: translate(0, 0) rotate(0deg); }
                25% { transform: translate(100px, 100px) rotate(90deg); }
                50% { transform: translate(0, 200px) rotate(180deg); }
                75% { transform: translate(-100px, 100px) rotate(270deg); }
                100% { transform: translate(0, 0) rotate(360deg); }
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 40px 20px;
                display: grid;
                grid-template-columns: 1fr 400px;
                gap: 40px;
                position: relative;
                z-index: 1;
            }
            
            @media (max-width: 1100px) {
                .container {
                    grid-template-columns: 1fr;
                    max-width: 500px;
                }
            }
            
            .login-section {
                animation: fadeIn 1s ease-out;
            }
            
            .leaderboard-section {
                animation: fadeIn 1.5s ease-out;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .logo {
                font-size: 4rem;
                font-weight: 900;
                margin-bottom: 10px;
                background: linear-gradient(45deg, #9d00ff, #00d4ff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                letter-spacing: 2px;
                font-family: 'Arial Black', sans-serif;
                text-shadow: 0 0 20px rgba(157, 0, 255, 0.3);
            }
            
            .subtitle {
                font-size: 1.3rem;
                color: #b19cd9;
                margin-bottom: 40px;
                animation: fadeIn 1.5s ease-out;
                font-weight: 300;
            }
            
            .login-box {
                background: rgba(20, 10, 40, 0.8);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 40px;
                border: 1px solid rgba(157, 0, 255, 0.2);
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                animation: slideUp 0.8s ease-out;
            }
            
            @keyframes slideUp {
                from { opacity: 0; transform: translateY(30px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .key-input {
                width: 100%;
                padding: 18px;
                background: rgba(0, 0, 0, 0.5);
                border: 2px solid #9d00ff;
                border-radius: 12px;
                color: #fff;
                font-size: 16px;
                text-align: center;
                margin-bottom: 25px;
                transition: all 0.3s;
                font-family: monospace;
                letter-spacing: 1px;
            }
            
            .key-input:focus {
                outline: none;
                border-color: #00d4ff;
                box-shadow: 0 0 15px rgba(0, 212, 255, 0.3);
                transform: scale(1.02);
            }
            
            .login-btn {
                width: 100%;
                padding: 18px;
                background: linear-gradient(45deg, #9d00ff, #00d4ff);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
            }
            
            .login-btn:hover {
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(157, 0, 255, 0.3);
            }
            
            .login-btn:disabled {
                opacity: 0.7;
                cursor: not-allowed;
                transform: none !important;
            }
            
            .error-box {
                background: rgba(255, 0, 0, 0.1);
                border: 1px solid rgba(255, 0, 0, 0.3);
                border-radius: 10px;
                padding: 15px;
                margin-top: 20px;
                color: #ff6b6b;
                display: none;
                animation: shake 0.5s;
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }
            
            .info-box {
                background: rgba(30, 15, 60, 0.8);
                border: 1px solid rgba(157, 0, 255, 0.2);
                border-radius: 15px;
                padding: 25px;
                margin-top: 30px;
                text-align: left;
                color: #d4b3ff;
                backdrop-filter: blur(10px);
                animation: fadeInDelay 1s ease-out 0.5s both;
            }
            
            @keyframes fadeInDelay {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
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
                margin: 0 2px;
            }
            
            .leaderboard-box {
                background: rgba(20, 10, 40, 0.9);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                border: 1px solid rgba(157, 0, 255, 0.2);
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                height: fit-content;
                animation: slideUp 1s ease-out;
            }
            
            .leaderboard-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 25px;
                padding-bottom: 15px;
                border-bottom: 1px solid rgba(157, 0, 255, 0.3);
            }
            
            .leaderboard-title {
                font-size: 1.8rem;
                background: linear-gradient(45deg, #00ff9d, #00d4ff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-weight: bold;
            }
            
            .refresh-btn {
                background: rgba(157, 0, 255, 0.2);
                border: 1px solid rgba(157, 0, 255, 0.4);
                color: #b19cd9;
                border-radius: 8px;
                padding: 8px 15px;
                cursor: pointer;
                font-size: 0.9rem;
                transition: all 0.3s;
            }
            
            .refresh-btn:hover {
                background: rgba(157, 0, 255, 0.3);
                transform: scale(1.05);
            }
            
            .leaderboard-list {
                list-style: none;
            }
            
            .leaderboard-item {
                display: flex;
                align-items: center;
                padding: 15px;
                margin-bottom: 12px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: all 0.3s;
            }
            
            .leaderboard-item:hover {
                transform: translateX(5px);
                border-color: rgba(157, 0, 255, 0.3);
                background: rgba(157, 0, 255, 0.1);
            }
            
            .rank {
                font-size: 1.5rem;
                font-weight: bold;
                width: 40px;
                text-align: center;
                margin-right: 15px;
            }
            
            .rank-1 { color: #ffd700; }
            .rank-2 { color: #c0c0c0; }
            .rank-3 { color: #cd7f32; }
            .rank-other { color: #00d4ff; }
            
            .player-info {
                flex-grow: 1;
            }
            
            .player-name {
                font-weight: bold;
                margin-bottom: 5px;
                color: #fff;
            }
            
            .player-stats {
                display: flex;
                gap: 15px;
                font-size: 0.85rem;
                color: #b19cd9;
            }
            
            .stat {
                display: flex;
                align-items: center;
                gap: 5px;
            }
            
            .stat-value {
                color: #00ff9d;
                font-weight: bold;
            }
            
            .prestige-badge {
                background: linear-gradient(45deg, #ffd700, #ffa500);
                color: #000;
                padding: 3px 8px;
                border-radius: 10px;
                font-size: 0.8rem;
                font-weight: bold;
                margin-left: 10px;
            }
            
            .empty-leaderboard {
                text-align: center;
                padding: 40px;
                color: #666;
                font-size: 1.1rem;
            }
            
            .bot-status {
                padding: 12px 25px;
                background: rgba(30, 15, 60, 0.8);
                border: 1px solid rgba(157, 0, 255, 0.3);
                border-radius: 25px;
                margin-top: 30px;
                display: inline-block;
                font-weight: 600;
                font-size: 1rem;
                backdrop-filter: blur(10px);
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2); }
                50% { box-shadow: 0 5px 20px rgba(157, 0, 255, 0.2); }
            }
            
            .status-online {
                color: #00ff9d;
                border-color: rgba(0, 255, 157, 0.3);
            }
            
            .status-offline {
                color: #ff6b6b;
                border-color: rgba(255, 107, 107, 0.3);
            }
            
            .divider {
                height: 1px;
                background: linear-gradient(90deg, transparent, #9d00ff, transparent);
                margin: 30px 0;
                width: 100%;
            }
            
            .github-link {
                display: block;
                margin-top: 20px;
                text-align: center;
                color: #b19cd9;
                font-size: 0.9rem;
            }
            
            .github-link a {
                color: #00d4ff;
                text-decoration: none;
            }
            
            .github-link a:hover {
                text-decoration: underline;
            }
            
            @media (max-width: 768px) {
                .container { 
                    padding: 20px;
                    grid-template-columns: 1fr;
                }
                .logo { font-size: 3rem; }
                .login-box { padding: 30px 20px; }
                .key-input { padding: 15px; }
                .login-btn { padding: 15px; }
                .leaderboard-box { padding: 20px; }
            }
        </style>
    </head>
    <body>
        <div class="background-glow" style="top: 10%; left: 10%; animation-delay: 0s;"></div>
        <div class="background-glow" style="top: 60%; right: 10%; animation-delay: -5s; background: radial-gradient(circle, rgba(0, 212, 255, 0.08) 0%, transparent 70%);"></div>
        <div class="background-glow" style="bottom: 10%; left: 30%; animation-delay: -16s; background: radial-gradient(circle, rgba(157, 0, 255, 0.06) 0%, transparent 70%);"></div>
        
        <div class="container">
            <div class="login-section">
                <div class="logo">GOBLIN HUT</div>
                <div class="subtitle">Enter your API key to enter the cave</div>
                
                <div class="login-box">
                    <input type="text" 
                           class="key-input" 
                           id="apiKey" 
                           placeholder="GOB-XXXXXXXXXXXXXXXXXXXX"
                           pattern="GOB-[A-Z0-9]{20}"
                           title="Format: GOB- followed by 20 uppercase letters/numbers"
                           autocomplete="off">
                    
                    <button class="login-btn" onclick="validateKey()" id="loginBtn">
                        Enter Cave
                    </button>
                    
                    <div class="error-box" id="errorMessage">
                        Invalid API key
                    </div>
                </div>
                
                <div class="divider"></div>
                
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
            
            <div class="leaderboard-section">
                <div class="leaderboard-box">
                    <div class="leaderboard-header">
                        <div class="leaderboard-title">🏆 Leaderboard</div>
                        <button class="refresh-btn" onclick="loadLeaderboard()">
                            ↻ Refresh
                        </button>
                    </div>
                    
                    <div id="leaderboardContainer">
                        <div class="empty-leaderboard">
                            Loading leaderboard...
                        </div>
                    </div>
                    
                    <div class="github-link">
                        <p>Want to climb the ranks? <a href="#" onclick="downloadTool()">Download our tool</a></p>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            async function validateKey() {
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const errorDiv = document.getElementById('errorMessage');
                const btn = document.getElementById('loginBtn');
                
                // Frontend format validation
                const keyPattern = /^GOB-[A-Z0-9]{20}$/;
                
                if (!key) {
                    errorDiv.textContent = "Please enter an API key";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                if (!keyPattern.test(key)) {
                    errorDiv.textContent = "Invalid format. Key must be: GOB- followed by 20 uppercase letters/numbers";
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
                        btn.style.background = 'linear-gradient(45deg, #00ff9d, #00d4ff)';
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
            
            async function loadLeaderboard() {
                const container = document.getElementById('leaderboardContainer');
                const refreshBtn = document.querySelector('.refresh-btn');
                
                refreshBtn.innerHTML = '↻ Loading...';
                refreshBtn.disabled = true;
                
                try {
                    const response = await fetch('/api/leaderboard');
                    const data = await response.json();
                    
                    if (data.leaderboard && data.leaderboard.length > 0) {
                        let html = '<ul class="leaderboard-list">';
                        
                        data.leaderboard.forEach(player => {
                            const rankClass = `rank-${player.rank}`;
                            
                            html += `
                                <li class="leaderboard-item">
                                    <div class="rank ${rankClass}">#${player.rank}</div>
                                    <div class="player-info">
                                        <div class="player-name">
                                            ${player.name}
                                            ${player.prestige > 0 ? `<span class="prestige-badge">P${player.prestige}</span>` : ''}
                                        </div>
                                        <div class="player-stats">
                                            <div class="stat">
                                                <span class="stat-label">K/D:</span>
                                                <span class="stat-value">${player.kd}</span>
                                            </div>
                                            <div class="stat">
                                                <span class="stat-label">Kills:</span>
                                                <span class="stat-value">${player.kills}</span>
                                            </div>
                                            <div class="stat">
                                                <span class="stat-label">W/L:</span>
                                                <span class="stat-value">${player.wins}/${player.losses}</span>
                                            </div>
                                        </div>
                                    </div>
                                </li>
                            `;
                        });
                        
                        html += '</ul>';
                        container.innerHTML = html;
                    } else {
                        container.innerHTML = '<div class="empty-leaderboard">No players yet. Be the first!</div>';
                    }
                } catch (error) {
                    console.error('Error loading leaderboard:', error);
                    container.innerHTML = '<div class="empty-leaderboard">Failed to load leaderboard</div>';
                }
                
                refreshBtn.innerHTML = '↻ Refresh';
                refreshBtn.disabled = false;
            }
            
            function downloadTool() {
                // Replace with your actual GitHub release URL
                const githubReleaseUrl = 'https://github.com/yourusername/goblin-hut-tool/releases/latest/download/tool.exe';
                
                // Create hidden download link
                const link = document.createElement('a');
                link.href = githubReleaseUrl;
                link.download = 'goblin_hut_tool.exe';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                // Optional: Show download started message
                alert('Download started! Check your downloads folder.');
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
                loadLeaderboard();
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
    
    user_data = validate_api_key(api_key)
    
    if user_data:
        session.clear()
        session['user_key'] = api_key
        session['user_data'] = user_data
        session.permanent = True
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
    
    # Get Discord avatar URL
    discord_avatar = user_data.get('discord_avatar')
    avatar_url = None
    if discord_avatar:
        avatar_url = get_discord_avatar_url(user_data['discord_id'], discord_avatar, 256)
    
    # Get open tickets for this user
    conn = get_db_connection()
    tickets = conn.execute(
        'SELECT * FROM tickets WHERE discord_id = ? AND status = "open" ORDER BY created_at DESC LIMIT 3',
        (user_data['discord_id'],)
    ).fetchall()
    conn.close()
    
    # Build tickets HTML
    tickets_html = ''
    for ticket in tickets:
        category_info = next((c for c in TICKET_CATEGORIES if c["name"] == ticket['category']), TICKET_CATEGORIES[-1])
        color_hex = f"#{hex(category_info['color'])[2:].zfill(6)}"
        tickets_html += f'<div class="ticket-card"><div class="ticket-header"><div class="ticket-title"><strong>TICKET-{ticket["ticket_id"]}</strong></div><span class="status-open">OPEN</span></div><p class="ticket-issue">{ticket["issue"][:100]}...</p><div class="ticket-footer"><span class="ticket-category" style="color: {color_hex};">{ticket["category"]}</span><span class="ticket-date">{ticket["created_at"][:10]}</span></div></div>'
    
    if not tickets_html:
        tickets_html = '<div class="no-tickets"><p>No open tickets</p></div>'
    
    # Avatar HTML
    avatar_html = f'<img src="{avatar_url}" alt="Avatar" style="width: 100px; height: 100px; border-radius: 50%; border: 3px solid #9d00ff;">' if avatar_url else '<div class="avatar">?</div>'
    
    # Build the HTML response
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
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0015;
            color: #fff;
            min-height: 100vh;
            overflow-x: hidden;
        }}
        
        .background-glow {{
            position: fixed;
            width: 600px;
            height: 600px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(157, 0, 255, 0.08) 0%, transparent 70%);
            filter: blur(80px);
            animation: float 25s infinite linear;
            z-index: -1;
        }}
        
        @keyframes float {{
            0% {{ transform: translate(0, 0) rotate(0deg); }}
            33% {{ transform: translate(200px, 200px) rotate(120deg); }}
            66% {{ transform: translate(-200px, 100px) rotate(240deg); }}
            100% {{ transform: translate(0, 0) rotate(360deg); }}
        }}
        
        .header {{
            background: rgba(15, 5, 30, 0.9);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(157, 0, 255, 0.3);
            padding: 25px 50px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        .logo {{
            font-size: 2rem;
            font-weight: 900;
            background: linear-gradient(45deg, #9d00ff, #00d4ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-family: 'Arial Black', sans-serif;
        }}
        
        .user-info {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        
        .user-name {{
            font-size: 1.3rem;
            color: #00d4ff;
            font-weight: bold;
        }}
        
        .logout-btn {{
            padding: 10px 25px;
            background: linear-gradient(45deg, #ff416c, #ff4b2b);
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s;
        }}
        
        .logout-btn:hover {{
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(255, 65, 108, 0.3);
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px;
        }}
        
        .profile-section {{
            display: grid;
            grid-template-columns: 1fr 400px;
            gap: 30px;
            margin-bottom: 40px;
        }}
        
        @media (max-width: 1100px) {{
            .profile-section {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .profile-card, .key-card {{
            background: rgba(25, 10, 50, 0.8);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            border: 1px solid rgba(157, 0, 255, 0.2);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            animation: slideUp 0.8s ease-out;
        }}
        
        .key-card {{
            animation-delay: 0.2s;
        }}
        
        @keyframes slideUp {{
            from {{ opacity: 0; transform: translateY(30px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .profile-header {{
            display: flex;
            align-items: center;
            gap: 25px;
            margin-bottom: 30px;
            padding-bottom: 25px;
            border-bottom: 1px solid rgba(157, 0, 255, 0.3);
        }}
        
        .avatar {{
            width: 100px;
            height: 100px;
            background: linear-gradient(45deg, #9d00ff, #00d4ff);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2.5rem;
            color: white;
            animation: rotate 20s linear infinite;
        }}
        
        @keyframes rotate {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}
        
        .profile-info h2 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            background: linear-gradient(45deg, #9d00ff, #00d4ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        .profile-info p {{
            color: #b19cd9;
            font-size: 1rem;
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
            padding: 25px;
            text-align: center;
            border: 1px solid rgba(157, 0, 255, 0.2);
            transition: all 0.3s;
        }}
        
        .stat-item:hover {{
            transform: translateY(-5px);
            border-color: rgba(0, 212, 255, 0.4);
            box-shadow: 0 10px 20px rgba(0, 212, 255, 0.1);
        }}
        
        .stat-value {{
            font-size: 2.5rem;
            font-weight: 900;
            margin: 10px 0;
            font-family: 'Arial Black', sans-serif;
        }}
        
        .stat-label {{
            color: #b19cd9;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
        }}
        
        .key-display {{
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(157, 0, 255, 0.4);
            border-radius: 15px;
            padding: 25px;
            margin: 25px 0;
            font-family: 'Courier New', monospace;
            color: #00ff9d;
            text-align: center;
            cursor: pointer;
            word-break: break-all;
            transition: all 0.3s;
        }}
        
        .key-display:hover {{
            border-color: rgba(0, 212, 255, 0.6);
            box-shadow: 0 0 15px rgba(0, 212, 255, 0.2);
        }}
        
        .action-btn {{
            width: 100%;
            padding: 16px;
            background: linear-gradient(45deg, #9d00ff, #00d4ff);
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: bold;
            cursor: pointer;
            margin: 10px 0;
            transition: all 0.3s;
        }}
        
        .action-btn:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(157, 0, 255, 0.2);
        }}
        
        .admin-btn {{
            background: linear-gradient(45deg, #00ff9d, #00d4ff);
        }}
        
        .tickets-section {{
            background: rgba(25, 10, 50, 0.8);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            border: 1px solid rgba(157, 0, 255, 0.2);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            animation: slideUp 0.8s ease-out 0.4s both;
        }}
        
        .tickets-section h3 {{
            font-size: 1.8rem;
            margin-bottom: 30px;
            color: #00d4ff;
        }}
        
        .tickets-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        
        .ticket-card {{
            background: rgba(20, 5, 40, 0.9);
            border-radius: 15px;
            padding: 25px;
            border: 1px solid rgba(157, 0, 255, 0.2);
            transition: all 0.3s;
        }}
        
        .ticket-card:hover {{
            transform: translateY(-5px);
            border-color: rgba(0, 212, 255, 0.4);
            box-shadow: 0 10px 20px rgba(0, 212, 255, 0.1);
        }}
        
        .ticket-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        
        .status-open {{
            color: #00ff9d;
            font-weight: bold;
            font-size: 0.8rem;
            padding: 5px 12px;
            background: rgba(0, 255, 157, 0.1);
            border-radius: 15px;
        }}
        
        .ticket-issue {{
            color: #d4b3ff;
            margin-bottom: 20px;
            font-size: 1rem;
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
            text-align: center;
            padding: 40px;
            color: #666;
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
            .profile-section {{
                gap: 20px;
            }}
            .profile-card, .key-card, .tickets-section {{
                padding: 25px 20px;
            }}
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            .tickets-grid {{
                grid-template-columns: 1fr;
            }}
            .avatar, .avatar img {{
                width: 80px;
                height: 80px;
                font-size: 2rem;
            }}
            .profile-info h2 {{
                font-size: 1.8rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="background-glow" style="top: 10%; left: 5%; animation-delay: 0s;"></div>
    <div class="background-glow" style="top: 60%; right: 5%; animation-delay: -8s; background: radial-gradient(circle, rgba(0, 212, 255, 0.06) 0%, transparent 70%);"></div>
    <div class="background-glow" style="bottom: 10%; left: 30%; animation-delay: -16s; background: radial-gradient(circle, rgba(157, 0, 255, 0.06) 0%, transparent 70%);"></div>
    
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
                    {avatar_html}
                    <div class="profile-info">
                        <h2>{user_data.get('in_game_name', 'Player')}</h2>
                        <p>Member for {days_ago} days • {total_games} games • Prestige {user_data.get('prestige', 0)}</p>
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
                        <div style="color: #d4b3ff; font-size: 0.8rem;">Total matches completed</div>
                    </div>
                    
                    <div class="stat-item">
                        <div class="stat-label">Prestige Level</div>
                        <div class="stat-value" style="color: #ffd700;">{user_data.get('prestige', 0)}</div>
                        <div style="color: #d4b3ff; font-size: 0.8rem;">Current prestige rank</div>
                    </div>
                </div>
            </div>
            
            <div class="key-card">
                <h3 style="color: #00d4ff; margin-bottom: 20px;">Your API Key</h3>
                <p style="color: #b19cd9; margin-bottom: 20px; line-height: 1.5;">
                    Keep this key secure. Use it to access your dashboard and API features.
                    Do not share it with anyone.
                </p>
                
                <div class="key-display" id="apiKeyDisplay" onclick="this.classList.add('revealed')">
                    {session['user_key']}
                </div>
                
                <button class="action-btn" onclick="copyKey()">
                    Copy Key
                </button>
                
                <button class="action-btn" onclick="downloadTool()" style="background: linear-gradient(45deg, #00ff9d, #00d4ff);">
                    🛠️ Download Tool
                </button>
                
                { '<button class="action-btn admin-btn" onclick="changeKey()">Change Key (Admin)</button>' if is_admin else '' }
            </div>
        </div>
        
        <div class="tickets-section">
            <h3>Your Open Tickets</h3>
            <div class="tickets-grid">
                {tickets_html}
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
        
        function downloadTool() {{
            // Replace with your actual GitHub release URL
            const githubReleaseUrl = 'https://github.com/yourusername/goblin-hut-tool/releases/latest/download/goblin_hut_tool.exe';
            
            // Create hidden download link
            const link = document.createElement('a');
            link.href = githubReleaseUrl;
            link.download = 'goblin_hut_tool.exe';
            link.style.display = 'none';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            // Show download started message
            alert('Download started! Check your downloads folder.');
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

@app.route('/api/leaderboard')
def api_leaderboard():
    """Get leaderboard data"""
    conn = get_db_connection()
    
    # Get top 10 players by K/D ratio (minimum 10 kills)
    top_players = conn.execute('''
        SELECT discord_name, in_game_name, total_kills, total_deaths, 
               CAST(total_kills AS FLOAT) / MAX(total_deaths, 1) as kd_ratio,
               wins, losses, prestige
        FROM players 
        WHERE total_kills >= 10
        ORDER BY kd_ratio DESC, total_kills DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    leaderboard = []
    for i, player in enumerate(top_players, 1):
        leaderboard.append({
            "rank": i,
            "name": player['in_game_name'] or player['discord_name'],
            "kills": player['total_kills'],
            "deaths": player['total_deaths'],
            "kd": round(player['kd_ratio'], 2),
            "wins": player['wins'],
            "losses": player['losses'],
            "prestige": player['prestige']
        })
    
    return jsonify({"leaderboard": leaderboard})

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
# SCORE TRACKING API ENDPOINTS
# =============================================================================

@app.route('/api/match/start', methods=['POST'])
def api_start_match():
    """Start a new match via API"""
    data = request.get_json()
    api_key = data.get('api_key', '').upper()
    
    if not api_key:
        return jsonify({"success": False, "error": "Missing API key"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"success": False, "error": "Invalid API key"}), 401
    
    if not user_data.get('is_admin'):
        return jsonify({"success": False, "error": "Admin privileges required"}), 403
    
    team1_players = data.get('team1_players', [])
    team2_players = data.get('team2_players', [])
    
    if not team1_players or not team2_players:
        return jsonify({"success": False, "error": "Both teams must have players"}), 400
    
    match_id = start_match(team1_players, team2_players)
    
    return jsonify({
        "success": True,
        "match_id": match_id,
        "message": "Match started"
    })

@app.route('/api/match/update', methods=['POST'])
def api_update_score():
    """Update match score via API"""
    data = request.get_json()
    api_key = data.get('api_key', '').upper()
    
    if not api_key:
        return jsonify({"success": False, "error": "Missing API key"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"success": False, "error": "Invalid API key"}), 401
    
    if not user_data.get('is_admin'):
        return jsonify({"success": False, "error": "Admin privileges required"}), 403
    
    match_id = data.get('match_id')
    team1_score = data.get('team1_score', 0)
    team2_score = data.get('team2_score', 0)
    
    if not match_id:
        return jsonify({"success": False, "error": "Missing match_id"}), 400
    
    success = update_score(match_id, team1_score, team2_score)
    
    if success:
        return jsonify({
            "success": True,
            "message": "Score updated"
        })
    else:
        return jsonify({
            "success": False,
            "error": "Match not found"
        }), 404

@app.route('/api/match/end', methods=['POST'])
def api_end_match():
    """End a match via API"""
    data = request.get_json()
    api_key = data.get('api_key', '').upper()
    
    if not api_key:
        return jsonify({"success": False, "error": "Missing API key"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"success": False, "error": "Invalid API key"}), 401
    
    if not user_data.get('is_admin'):
        return jsonify({"success": False, "error": "Admin privileges required"}), 403
    
    match_id = data.get('match_id')
    
    if not match_id:
        return jsonify({"success": False, "error": "Missing match_id"}), 400
    
    success = end_match(match_id)
    
    if success:
        return jsonify({
            "success": True,
            "message": "Match ended"
        })
    else:
        return jsonify({
            "success": False,
            "error": "Match not found"
        }), 404

@app.route('/api/match/stats/<match_id>')
def api_get_match_stats(match_id):
    """Get match stats via API"""
    api_key = request.args.get('key', '').upper()
    
    if not api_key:
        return jsonify({"success": False, "error": "Missing API key"}), 401
    
    user_data = validate_api_key(api_key)
    if not user_data:
        return jsonify({"success": False, "error": "Invalid API key"}), 401
    
    stats = get_match_stats(match_id)
    
    if stats:
        return jsonify({
            "success": True,
            "match": stats
        })
    else:
        return jsonify({
            "success": False,
            "error": "Match not found"
        }), 404

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    init_db()
    
    # Fix any existing keys that don't match the correct format
    fixed_keys = fix_existing_keys()
    if fixed_keys > 0:
        print(f"Fixed {fixed_keys} API keys to correct format")
    
    # Run validation test
    test_key_validation()
    
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
    
    # Start ping scheduler
    start_ping_scheduler()
    
    print(f"\nWeb Interface: http://localhost:{port}")
    print(f"Bot Endpoint: /interactions")
    
    print("\nNew Features:")
    print("   • Leaderboard on login screen")
    print("   • Direct tool download from dashboard")
    print("   • Tool download link: https://github.com/yourusername/goblin-hut-tool/releases")
    
    print("\nDiscord Commands:")
    print("   /ping - Check bot status")
    print("   /register [name] - Get API key (one-time only)")
    print("   /profile - Show your profile and stats")
    print("   /key - Show your API key")
    print("   /ticket [issue] [category] - Create support ticket")
    print("   /close - Close current ticket")
    print("   /match start [team1] [team2] - Start a new match (Admin only)")
    print("   /match score [match_id] [team1_score] [team2_score] - Update match score (Admin only)")
    print("   /match end [match_id] - End a match (Admin only)")
    print("   /match stats [match_id] - Show match stats")
    
    print("\nKey Features:")
    print("   • Discord profile pictures on web dashboard")
    print("   • Ticket channel delete permission for creators/admins")
    print("   • Auto ping every 5 minutes to prevent shutdown")
    print("   • Score tracking with webhook notifications")
    print("   • Match management via Discord commands")
    print("   • API endpoints for external tools")
    print("   • API Key Format: GOB- + 20 uppercase alphanumeric chars")
    print("   • Database constraint: Keys must be exactly 24 characters")
    print("   • Leaderboard showing top players by K/D ratio")
    print("   • Direct tool download from dashboard")
    
    print("\nEnvironment Check:")
    print(f"   DISCORD_TOKEN: {'Set' if DISCORD_TOKEN else 'Not set'}")
    print(f"   DISCORD_CLIENT_ID: {'Set' if DISCORD_CLIENT_ID else 'Not set'}")
    print(f"   DISCORD_PUBLIC_KEY: {'Set' if DISCORD_PUBLIC_KEY else 'Not set'}")
    print(f"   SCORE_WEBHOOK: {'Set' if SCORE_WEBHOOK else 'Not set'}")
    
    print("\nTroubleshooting:")
    print("   1. Install required libraries: pip install pynacl requests flask flask-cors")
    print("   2. Set all Discord environment variables")
    print("   3. Check bot has proper permissions")
    print("   4. View logs for detailed errors")
    print("   5. Run key validation test: test_key_validation()")
    
    print("\n" + "="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)

# app.py - GOBLIN HUT BOT - COMPLETE WITH WEBHOOKS
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
from datetime import datetime, timedelta
import logging
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = 86400
CORS(app, supports_credentials=True)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord credentials
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')

# Webhooks
REGISTRATION_WEBHOOK = os.environ.get('REGISTRATION_WEBHOOK', '')
LOGIN_WEBHOOK = os.environ.get('LOGIN_WEBHOOK', '')
TICKET_WEBHOOK = os.environ.get('TICKET_WEBHOOK', '')
SCORE_WEBHOOK = os.environ.get('SCORE_WEBHOOK', '')
STATS_WEBHOOK = os.environ.get('STATS_WEBHOOK', '')

# Key Database Channel
KEY_DATABASE_CHANNEL_ID = os.environ.get('KEY_DATABASE_CHANNEL_ID', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot status
bot_active = False
bot_info = {}

# Ping responses
PING_RESPONSES = [
    "I'm here!", "Bot is up!", "Still alive!", "Online!",
    "Ready!", "Here!", "Awake!", "Active!"
]

# Ticket categories
TICKET_CATEGORIES = [
    {"name": "Bug Report", "color": 0xe74c3c},
    {"name": "Feature Request", "color": 0x3498db},
    {"name": "Account Issue", "color": 0x2ecc71},
    {"name": "Technical Support", "color": 0xf39c12},
    {"name": "Other", "color": 0x9b59b6}
]

# =============================================================================
# DISCORD API HELPERS - COMPLETE
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

def get_guild_info(guild_id):
    """Get guild information"""
    return discord_api_request(f"/guilds/{guild_id}")

def create_guild_channel(guild_id, channel_data):
    """Create a channel in guild"""
    return discord_api_request(f"/guilds/{guild_id}/channels", "POST", channel_data)

def delete_channel(channel_id):
    """Delete a channel"""
    return discord_api_request(f"/channels/{channel_id}", "DELETE")

def get_discord_user(user_id):
    """Get Discord user info"""
    return discord_api_request(f"/users/{user_id}")

# =============================================================================
# KEY DATABASE CHANNEL SYSTEM - COMPLETE
# =============================================================================

def create_key_database_channel(guild_id):
    """Create private channel to store key-user information"""
    try:
        # Get guild info
        guild = get_guild_info(guild_id)
        if not guild:
            return None
        
        # Create channel data
        channel_data = {
            "name": "key-database",
            "type": 0,  # Text channel
            "topic": "Key Database - DO NOT DELETE",
            "parent_id": None,
            "permission_overwrites": [
                {
                    "id": guild_id,  # @everyone
                    "type": 0,
                    "allow": "0",
                    "deny": "1024"  # Deny VIEW_CHANNEL
                },
                {
                    "id": DISCORD_CLIENT_ID,  # Bot
                    "type": 2,
                    "allow": "3072",  # VIEW_CHANNEL + SEND_MESSAGES
                    "deny": "0"
                }
            ]
        }
        
        # Create the channel
        channel = create_guild_channel(guild_id, channel_data)
        if not channel:
            return None
        
        # Send initial message
        welcome_message = {
            "content": "# 🔑 Key Database Channel\n\nThis channel stores all API key registrations.\n**DO NOT DELETE THIS CHANNEL.**\n\nFormat: `KEY|DiscordID|DiscordName|InGameName|Date|APIKey`",
            "embeds": []
        }
        
        discord_api_request(f"/channels/{channel['id']}/messages", "POST", welcome_message)
        
        logger.info(f"Created key database channel: {channel['id']}")
        return channel['id']
        
    except Exception as e:
        logger.error(f"Error creating key database channel: {e}")
        return None

def save_key_to_channel(discord_id, discord_name, in_game_name, api_key):
    """Save key registration to channel"""
    global KEY_DATABASE_CHANNEL_ID
    
    if not KEY_DATABASE_CHANNEL_ID:
        logger.warning("No key database channel ID set")
        return False
    
    try:
        # Format: KEY|DiscordID|DiscordName|InGameName|Date|APIKey
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        message = f"KEY|{discord_id}|{discord_name}|{in_game_name}|{timestamp}|{api_key}"
        
        # Send to channel
        discord_api_request(f"/channels/{KEY_DATABASE_CHANNEL_ID}/messages", "POST", {
            "content": f"```{message}```"
        })
        
        logger.info(f"Saved key registration to channel: {discord_name} -> {in_game_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving key to channel: {e}")
        return False

# =============================================================================
# WEBHOOK FUNCTIONS - COMPLETE
# =============================================================================

def send_webhook(webhook_url, embed, username="Goblin Hut Bot"):
    """Send embed to webhook"""
    if not webhook_url:
        return
    
    try:
        data = {
            "embeds": [embed],
            "username": username,
            "avatar_url": "https://i.imgur.com/Lg9YqZm.png"
        }
        
        response = requests.post(webhook_url, json=data, timeout=5)
        if response.status_code not in [200, 204]:
            logger.error(f"Webhook failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")

def send_registration_webhook(discord_id, discord_name, in_game_name, api_key):
    """Send registration to webhook"""
    embed = {
        "title": "🔑 New Registration",
        "color": 0x00ff9d,
        "fields": [
            {"name": "Discord User", "value": f"{discord_name} (<@{discord_id}>)", "inline": True},
            {"name": "In-Game Name", "value": in_game_name, "inline": True},
            {"name": "API Key", "value": f"`{api_key}`", "inline": False},
            {"name": "Date", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Goblin Hut Registration"}
    }
    
    send_webhook(REGISTRATION_WEBHOOK, embed, "Goblin Hut Registration")

def send_login_webhook(discord_name, in_game_name, ip_address=None):
    """Send login to webhook"""
    embed = {
        "title": "🚪 User Login",
        "color": 0x9d00ff,
        "fields": [
            {"name": "User", "value": f"{discord_name} ({in_game_name})", "inline": True},
            {"name": "Time", "value": datetime.utcnow().strftime("%H:%M:%S"), "inline": True}
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Goblin Hut Login"}
    }
    
    if ip_address:
        embed["fields"].append({"name": "IP", "value": ip_address, "inline": True})
    
    send_webhook(LOGIN_WEBHOOK, embed, "Goblin Hut Login")

def send_ticket_webhook(ticket_id, user_name, user_id, category, issue, action="created"):
    """Send ticket event to webhook"""
    category_info = next((c for c in TICKET_CATEGORIES if c["name"] == category), TICKET_CATEGORIES[-1])
    
    embed = {
        "title": f"🎫 Ticket {action.capitalize()}",
        "description": f"**Ticket ID:** `{ticket_id}`\n**User:** {user_name} (<@{user_id}>)\n**Category:** {category}\n**Issue:** {issue[:200]}",
        "color": category_info['color'],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": f"Ticket {action}"}
    }
    
    send_webhook(TICKET_WEBHOOK, embed, "Goblin Hut Tickets")

def send_stats_webhook(total_players, total_kills, total_games):
    """Send stats to webhook"""
    embed = {
        "title": "📊 Bot Statistics",
        "color": 0xffd700,
        "fields": [
            {"name": "Total Players", "value": str(total_players), "inline": True},
            {"name": "Total Kills", "value": str(total_kills), "inline": True},
            {"name": "Total Games", "value": str(total_games), "inline": True},
            {"name": "Bot Status", "value": "🟢 Online" if bot_active else "🔴 Offline", "inline": True}
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Updated every hour"}
    }
    
    send_webhook(STATS_WEBHOOK, embed, "Goblin Hut Stats")

def send_score_webhook(match_id, team1_score, team2_score, action="update"):
    """Send score to webhook"""
    if action == "start":
        title = "🎮 Match Started"
        color = 0x9d00ff
    elif action == "end":
        title = "🏁 Match Ended"
        color = 0xffd700
    else:
        title = "🏆 Score Update"
        color = 0x00ff9d
    
    embed = {
        "title": title,
        "description": f"Match ID: `{match_id}`",
        "color": color,
        "fields": [
            {"name": "Team 1", "value": f"Score: **{team1_score}**", "inline": True},
            {"name": "Team 2", "value": f"Score: **{team2_score}**", "inline": True}
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Goblin Hut Score Tracker"}
    }
    
    send_webhook(SCORE_WEBHOOK, embed, "Goblin Hut Scores")

# =============================================================================
# TICKET SYSTEM - COMPLETE
# =============================================================================

def create_ticket_channel(guild_id, user_id, user_name, ticket_id, issue, category):
    """Create private ticket channel"""
    try:
        guild = get_guild_info(guild_id)
        if not guild:
            return None
        
        short_id = ticket_id.split('-')[1][:4]
        channel_name = f"ticket-{short_id}"
        
        category_info = next((c for c in TICKET_CATEGORIES if c["name"] == category), TICKET_CATEGORIES[-1])
        
        channel_data = {
            "name": channel_name,
            "type": 0,
            "topic": f"{issue[:50]}...",
            "parent_id": None,
            "permission_overwrites": [
                {
                    "id": guild_id,
                    "type": 0,
                    "allow": "0",
                    "deny": "1024"
                },
                {
                    "id": user_id,
                    "type": 1,
                    "allow": "3072",
                    "deny": "0"
                },
                {
                    "id": DISCORD_CLIENT_ID,
                    "type": 2,
                    "allow": "3072",
                    "deny": "0"
                }
            ]
        }
        
        channel = create_guild_channel(guild_id, channel_data)
        if not channel:
            return None
        
        embed = {
            "title": f"Ticket #{ticket_id}",
            "description": issue,
            "color": category_info['color'],
            "fields": [
                {"name": "Created By", "value": f"<@{user_id}> ({user_name})", "inline": True},
                {"name": "Created", "value": f"<t:{int(time.time())}:R>", "inline": True},
                {"name": "Category", "value": category, "inline": True}
            ],
            "footer": {"text": "Use /close to close this ticket"},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        components = {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 4,
                    "label": "Close Ticket",
                    "custom_id": f"close_ticket_{ticket_id}"
                }
            ]
        }
        
        welcome_message = {
            "content": f"<@{user_id}> Welcome to your ticket!",
            "embeds": [embed],
            "components": [components]
        }
        
        discord_api_request(f"/channels/{channel['id']}/messages", "POST", welcome_message)
        
        # Send webhook
        send_ticket_webhook(ticket_id, user_name, user_id, category, issue, "created")
        
        return channel['id']
        
    except Exception as e:
        logger.error(f"Error creating ticket channel: {e}")
        return None

def close_ticket_channel(channel_id, ticket_id, closed_by):
    """Close ticket channel"""
    try:
        conn = get_db_connection()
        ticket = conn.execute(
            'SELECT * FROM tickets WHERE ticket_id = ?',
            (ticket_id,)
        ).fetchone()
        
        conn.execute('''
            UPDATE tickets 
            SET status = "closed", resolved_at = CURRENT_TIMESTAMP
            WHERE ticket_id = ?
        ''', (ticket_id,))
        conn.commit()
        conn.close()
        
        delete_result = delete_channel(channel_id)
        
        # Send webhook
        if ticket:
            send_ticket_webhook(ticket_id, ticket['discord_name'], ticket['discord_id'], 
                              ticket['category'], ticket['issue'], "closed")
        
        return True if delete_result else False
        
    except Exception as e:
        logger.error(f"Error closing ticket channel: {e}")
        return False

# =============================================================================
# DATABASE SETUP - COMPLETE
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
                discord_avatar TEXT,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                category TEXT DEFAULT 'Other',
                channel_id TEXT,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            )
        ''')
        
        # Matches table
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
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# KEY VALIDATION - COMPLETE
# =============================================================================

def validate_api_key(api_key):
    """Validate API key"""
    if not api_key:
        return None
    
    api_key = api_key.strip().upper()
    
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
            
            # Convert to dict
            player_dict = {key: player[key] for key in player.keys()}
            return player_dict
        else:
            return None
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        return None
    finally:
        conn.close()

def generate_api_key():
    """Generate API key"""
    return f"GOB-{''.join(random.choices(string.ascii_uppercase + string.digits, k=20))}"

# =============================================================================
# DISCORD BOT FUNCTIONS - COMPLETE
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
            "name": "setup",
            "description": "Setup key database channel",
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
# SCORE TRACKING - COMPLETE
# =============================================================================

score_matches = {}

def start_match(team1_players, team2_players):
    """Start a new match"""
    match_id = f"MATCH-{int(time.time()) % 1000000:06d}"
    
    score_matches[match_id] = {
        'team1': {'players': team1_players, 'score': 0},
        'team2': {'players': team2_players, 'score': 0}
    }
    
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO matches (match_id, team1_players, team2_players)
        VALUES (?, ?, ?)
    ''', (match_id, ','.join(team1_players), ','.join(team2_players)))
    conn.commit()
    conn.close()
    
    send_score_webhook(match_id, 0, 0, "start")
    
    return match_id

def update_score(match_id, team1_score, team2_score):
    """Update match score"""
    if match_id not in score_matches:
        return False
    
    score_matches[match_id]['team1']['score'] = team1_score
    score_matches[match_id]['team2']['score'] = team2_score
    
    conn = get_db_connection()
    conn.execute('''
        UPDATE matches 
        SET team1_score = ?, team2_score = ?
        WHERE match_id = ?
    ''', (team1_score, team2_score, match_id))
    conn.commit()
    conn.close()
    
    send_score_webhook(match_id, team1_score, team2_score, "update")
    
    return True

def end_match(match_id):
    """End a match"""
    if match_id not in score_matches:
        return False
    
    match_data = score_matches[match_id]
    team1_score = match_data['team1']['score']
    team2_score = match_data['team2']['score']
    
    winner = "Team 1" if team1_score > team2_score else "Team 2" if team2_score > team1_score else "Draw"
    
    conn = get_db_connection()
    conn.execute('''
        UPDATE matches 
        SET status = 'ended', winner = ?, ended_at = CURRENT_TIMESTAMP
        WHERE match_id = ?
    ''', (winner, match_id))
    conn.commit()
    conn.close()
    
    send_score_webhook(match_id, team1_score, team2_score, "end")
    
    del score_matches[match_id]
    
    return True

# =============================================================================
# DISCORD INTERACTIONS - COMPLETE
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord slash commands"""
    data = request.get_json()
    
    # Handle PING
    if data.get('type') == 1:
        return jsonify({"type": 1})
    
    # Handle button clicks
    if data.get('type') == 3:
        custom_id = data.get('data', {}).get('custom_id', '')
        user_id = data.get('member', {}).get('user', {}).get('id')
        channel_id = data.get('channel_id')
        
        # CLOSE TICKET BUTTON
        if custom_id.startswith('close_ticket_'):
            ticket_id = custom_id.replace('close_ticket_', '')
            
            conn = get_db_connection()
            ticket = conn.execute(
                'SELECT * FROM tickets WHERE ticket_id = ?',
                (ticket_id,)
            ).fetchone()
            conn.close()
            
            if ticket and str(user_id) == str(ticket['discord_id']):
                success = close_ticket_channel(channel_id, ticket_id, user_id)
                if success:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"Ticket {ticket_id} has been closed.",
                            "flags": 64
                        }
                    })
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": "You don't have permission to close this ticket.",
                    "flags": 64
                }
            })
        
        return jsonify({"type": 6})
    
    # Handle slash commands
    if data.get('type') == 2:
        command = data.get('data', {}).get('name')
        user_id = data.get('member', {}).get('user', {}).get('id')
        user_name = data.get('member', {}).get('user', {}).get('global_name', 'Unknown')
        server_id = data.get('guild_id', 'DM')
        
        logger.info(f"Command: {command} from {user_name}")
        
        # PING COMMAND
        if command == 'ping':
            return jsonify({
                "type": 4,
                "data": {
                    "content": random.choice(PING_RESPONSES)
                }
            })
        
        # REGISTER COMMAND
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
                        "content": f"You are already registered as **{existing['in_game_name']}**\n\n**Your API Key:**\n```{api_key}```\n\n**Dashboard:** {request.host_url}\nUse this key to login to your dashboard.",
                        "flags": 64
                    }
                })
            
            # Generate key
            api_key = generate_api_key()
            
            # Get Discord user info
            discord_user = get_discord_user(user_id)
            discord_avatar = discord_user.get('avatar') if discord_user else None
            
            conn.execute('''
                INSERT INTO players 
                (discord_id, discord_name, discord_avatar, in_game_name, api_key, server_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, user_name, discord_avatar, in_game_name, api_key, server_id))
            conn.commit()
            conn.close()
            
            # Save to key database channel
            save_key_to_channel(user_id, user_name, in_game_name, api_key)
            
            # Send webhooks
            send_registration_webhook(user_id, user_name, in_game_name, api_key)
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": f"**Registration Successful!**\n\n**Name:** {in_game_name}\n**API Key:**\n```{api_key}```\n\n**Dashboard:** {request.host_url}\nUse this key to login to your dashboard.",
                    "flags": 64
                }
            })
        
        # TICKET COMMAND
        elif command == 'ticket':
            options = data.get('data', {}).get('options', [])
            issue = options[0].get('value', 'No issue specified') if options else 'No issue specified'
            category = options[1].get('value', 'Other') if len(options) > 1 else 'Other'
            
            ticket_id = f"T-{int(time.time()) % 10000:04d}"
            
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO tickets 
                (ticket_id, discord_id, discord_name, issue, category)
                VALUES (?, ?, ?, ?, ?)
            ''', (ticket_id, user_id, user_name, issue, category))
            conn.commit()
            
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
                        "content": f"**Ticket Created**\n\n**Ticket ID:** {ticket_id}\n**Channel:** <#{channel_id}>",
                        "flags": 64
                    }
                })
            else:
                conn.close()
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
            
            conn = get_db_connection()
            ticket = conn.execute(
                'SELECT * FROM tickets WHERE channel_id = ? AND status = "open"',
                (channel_id,)
            ).fetchone()
            conn.close()
            
            if not ticket:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "No open ticket in this channel",
                        "flags": 64
                    }
                })
            
            success = close_ticket_channel(channel_id, ticket['ticket_id'], user_id)
            
            if success:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"Ticket {ticket['ticket_id']} has been closed.",
                        "flags": 64
                    }
                })
            else:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "Failed to close ticket.",
                        "flags": 64
                    }
                })
        
        # PROFILE COMMAND
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
                        "content": "You are not registered. Use `/register [name]` first.",
                        "flags": 64
                    }
                })
            
            total_kills = player['total_kills'] or 0
            total_deaths = max(player['total_deaths'] or 1, 1)
            wins = player['wins'] or 0
            losses = player['losses'] or 0
            
            kd = total_kills / total_deaths
            total_games = wins + losses
            win_rate = (wins / total_games * 100) if total_games > 0 else 0
            
            embed = {
                "title": f"{player['in_game_name']}'s Profile",
                "color": 0x9d00ff,
                "fields": [
                    {"name": "In-Game Name", "value": f"`{player['in_game_name']}`", "inline": True},
                    {"name": "Prestige", "value": f"**{player['prestige']}**", "inline": True},
                    {"name": "K/D Ratio", "value": f"**{kd:.2f}**", "inline": True},
                    {"name": "Win Rate", "value": f"**{win_rate:.1f}%**", "inline": True},
                    {"name": "Games", "value": f"**{total_games}**", "inline": True},
                    {"name": "Dashboard", "value": f"[Click Here]({request.host_url})", "inline": True}
                ],
                "footer": {"text": f"Registered: {player['created_at'][:10]}"}
            }
            
            return jsonify({
                "type": 4,
                "data": {
                    "embeds": [embed],
                    "flags": 64
                }
            })
        
        # KEY COMMAND
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
                        "content": "You are not registered. Use `/register [name]` first.",
                        "flags": 64
                    }
                })
            
            return jsonify({
                "type": 4,
                "data": {
                    "content": f"**Your API Key**\n\n```{player['api_key']}```\n\n**Dashboard:** {request.host_url}",
                    "flags": 64
                }
            })
        
        # SETUP COMMAND
        elif command == 'setup':
            global KEY_DATABASE_CHANNEL_ID
            
            if KEY_DATABASE_CHANNEL_ID:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"Key database channel already exists: <#{KEY_DATABASE_CHANNEL_ID}>",
                        "flags": 64
                    }
                })
            
            channel_id = create_key_database_channel(server_id)
            
            if channel_id:
                KEY_DATABASE_CHANNEL_ID = channel_id
                
                # Save all existing keys to channel
                conn = get_db_connection()
                players = conn.execute('SELECT discord_id, discord_name, in_game_name, api_key FROM players').fetchall()
                conn.close()
                
                for player in players:
                    save_key_to_channel(
                        player['discord_id'],
                        player['discord_name'],
                        player['in_game_name'],
                        player['api_key']
                    )
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"**Key Database Channel Created**\n\n**Channel:** <#{channel_id}>\n\nThis channel will store all API key registrations. DO NOT DELETE IT.\n\nExisting keys have been saved to the channel.",
                        "flags": 64
                    }
                })
            else:
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "Failed to create key database channel. Check bot permissions.",
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
# WEB INTERFACE - COMPLETE
# =============================================================================

@app.route('/')
def home():
    """Home page"""
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
                           pattern="GOB-[A-Z0-9]{23}"
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
    """Validate API key"""
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
        
        # Send login webhook
        send_login_webhook(
            user_data.get('discord_name', 'Unknown'),
            user_data.get('in_game_name', 'Unknown'),
            request.remote_addr
        )
        
        return jsonify({"valid": True, "user": user_data.get('in_game_name')})
    else:
        return jsonify({"valid": False, "error": "Invalid API key"})

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    """Profile Dashboard"""
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
    
    # Get avatar URL
    avatar_url = None
    if user_data.get('discord_avatar'):
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_data['discord_id']}/{user_data['discord_avatar']}.png?size=256"
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Goblin Hut - Dashboard</title>
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
        
        .user-avatar {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            border: 2px solid #9d00ff;
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
        }}
        
        .avatar img {{
            width: 100%;
            height: 100%;
            border-radius: 50%;
            object-fit: cover;
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
            .profile-card, .key-card {{
                padding: 25px 20px;
            }}
            .stats-grid {{
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
            {'<img src="' + avatar_url + '" alt="Avatar" class="user-avatar">' if avatar_url else '<div class="user-avatar"></div>'}
            <div class="user-name">{user_data.get('in_game_name', 'Player')}</div>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
    </div>
    
    <div class="container">
        <div class="profile-section">
            <div class="profile-card">
                <div class="profile-header">
                    {'<img src="' + avatar_url + '" alt="Avatar">' if avatar_url else '<div class="avatar">?</div>'}
                    <div class="profile-info">
                        <h2>{user_data.get('in_game_name', 'Player')}</h2>
                        <p>Member since {user_data.get('created_at', 'Unknown')[:10]} • {total_games} games • Prestige {user_data.get('prestige', 0)}</p>
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
                
                <div class="key-display" id="apiKeyDisplay">
                    {session['user_key']}
                </div>
                
                <button class="action-btn" onclick="copyKey()">
                    Copy Key
                </button>
                
                <button class="action-btn" onclick="downloadTool()" style="background: linear-gradient(45deg, #00ff9d, #00d4ff);">
                    🛠️ Download Tool
                </button>
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
        
        function downloadTool() {{
            const githubReleaseUrl = 'https://github.com/yourusername/goblin-hut-tool/releases/latest/download/goblin_hut_tool.exe';
            
            const link = document.createElement('a');
            link.href = githubReleaseUrl;
            link.download = 'goblin_hut_tool.exe';
            link.style.display = 'none';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            alert('Download started! Check your downloads folder.');
        }}
    </script>
</body>
</html>'''
    
    return html

# =============================================================================
# API ENDPOINTS - COMPLETE
# =============================================================================

@app.route('/api/stats')
def api_stats():
    """Get global stats"""
    conn = get_db_connection()
    
    total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
    total_kills = conn.execute('SELECT SUM(total_kills) as sum FROM players').fetchone()['sum'] or 0
    total_games = conn.execute('SELECT SUM(wins + losses) as sum FROM players').fetchone()['sum'] or 0
    
    conn.close()
    
    # Send to webhook
    send_stats_webhook(total_players, total_kills, total_games)
    
    return jsonify({
        "total_players": total_players,
        "total_kills": total_kills,
        "total_games": total_games,
        "bot_active": bot_active,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/leaderboard')
def api_leaderboard():
    """Get leaderboard"""
    conn = get_db_connection()
    
    players = conn.execute('''
        SELECT in_game_name, total_kills, total_deaths, wins, losses, prestige
        FROM players 
        WHERE total_kills > 0
        ORDER BY CAST(total_kills AS FLOAT) / MAX(total_deaths, 1) DESC 
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    leaderboard = []
    for i, player in enumerate(players, 1):
        total_deaths = max(player['total_deaths'] or 1, 1)
        kd = (player['total_kills'] or 0) / total_deaths
        
        leaderboard.append({
            "rank": i,
            "name": player['in_game_name'] or "Unknown",
            "kills": player['total_kills'] or 0,
            "deaths": player['total_deaths'] or 0,
            "kd": round(kd, 2),
            "wins": player['wins'] or 0,
            "losses": player['losses'] or 0,
            "prestige": player['prestige'] or 0
        })
    
    return jsonify({"leaderboard": leaderboard})

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy" if bot_active else "offline",
        "bot_active": bot_active,
        "timestamp": datetime.utcnow().isoformat()
    })

# =============================================================================
# SCHEDULERS - COMPLETE
# =============================================================================

def stats_scheduler():
    """Send stats to webhook every hour"""
    def scheduler():
        while True:
            time.sleep(3600)  # 1 hour
            try:
                if STATS_WEBHOOK:
                    conn = get_db_connection()
                    total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
                    total_kills = conn.execute('SELECT SUM(total_kills) as sum FROM players').fetchone()['sum'] or 0
                    total_games = conn.execute('SELECT SUM(wins + losses) as sum FROM players').fetchone()['sum'] or 0
                    conn.close()
                    
                    send_stats_webhook(total_players, total_kills, total_games)
                    logger.info("Sent hourly stats to webhook")
                    
            except Exception as e:
                logger.error(f"Stats scheduler error: {e}")
    
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    logger.info("Stats scheduler started")

def ping_scheduler():
    """Ping server to keep it alive"""
    def scheduler():
        while True:
            time.sleep(300)  # 5 minutes
            try:
                requests.get(f"http://localhost:{port}/health", timeout=10)
            except:
                pass
    
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    logger.info("Ping scheduler started")

# =============================================================================
# STARTUP - COMPLETE
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print("\n" + "="*60)
    print("GOBLIN HUT BOT - COMPLETE VERSION")
    print("="*60)
    
    # Test Discord connection
    if test_discord_token():
        bot_active = True
        print("✓ Discord bot connected")
        
        if register_commands():
            print("✓ Commands registered")
        else:
            print("✗ Could not register commands")
    else:
        print("✗ Discord token not set or invalid")
        print("  The web interface will work but Discord commands won't")
    
    # Start schedulers
    stats_scheduler()
    ping_scheduler()
    
    print(f"\n📊 Web Interface: http://localhost:{port}")
    print("🤖 Bot Endpoint: /interactions")
    
    print("\n📋 Available Commands:")
    print("   /ping          - Check if bot is online")
    print("   /register      - Register and get API key")
    print("   /ticket        - Create a support ticket")
    print("   /close         - Close current ticket")
    print("   /profile       - Show your profile and stats")
    print("   /key           - Show your API key")
    print("   /setup         - Create key database channel")
    
    print("\n🔑 Key Database Channel:")
    print("   • Stores all API key registrations")
    print("   • Format: KEY|DiscordID|DiscordName|InGameName|Date|Key")
    print("   • Created with /setup command")
    
    print("\n🌐 Webhooks:")
    print(f"   • Registrations: {'✅ Set' if REGISTRATION_WEBHOOK else '❌ Not set'}")
    print(f"   • Logins: {'✅ Set' if LOGIN_WEBHOOK else '❌ Not set'}")
    print(f"   • Tickets: {'✅ Set' if TICKET_WEBHOOK else '❌ Not set'}")
    print(f"   • Scores: {'✅ Set' if SCORE_WEBHOOK else '❌ Not set'}")
    print(f"   • Stats: {'✅ Set' if STATS_WEBHOOK else '❌ Not set'}")
    
    print(f"\n🗄️  Key Database Channel: {'✅ ' + KEY_DATABASE_CHANNEL_ID if KEY_DATABASE_CHANNEL_ID else '❌ Not created (use /setup)'}")
    
    print("\n" + "="*60)
    print("🚀 Starting server...")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)

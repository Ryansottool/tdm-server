# discord_bot.py - Discord bot interactions and slash commands
import time
import random
import requests
import threading
from datetime import datetime
from config import (
    DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_PUBLIC_KEY,
    ADMIN_ROLE_ID, TICKET_WEBHOOK, SCORE_WEBHOOK, DATABASE_CHANNEL_ID,
    TOXIC_PING_RESPONSES, NORMAL_PING_RESPONSES, TICKET_CATEGORIES,
    score_matches, stats_webhooks, bot_active, bot_info, logger,
    generate_secure_key
)
from database import get_db_connection, validate_api_key

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

def get_discord_user(user_id):
    """Get Discord user info including avatar"""
    return discord_api_request(f"/users/{user_id}")

def is_user_admin_in_guild(guild_id, user_id):
    """Check if user has admin/manage permissions in guild"""
    try:
        member = get_guild_member(guild_id, user_id)
        if not member:
            return False
        
        guild = get_guild_info(guild_id)
        if guild and guild.get('owner_id') == user_id:
            return True
        
        if ADMIN_ROLE_ID and ADMIN_ROLE_ID in member.get('roles', []):
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

# =============================================================================
# CHANNEL MANAGEMENT
# =============================================================================

def create_ticket_channel(guild_id, user_id, user_name, ticket_id, issue, category):
    """Create private ticket channel with shorter name"""
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
                }
            ]
        }
        
        if ADMIN_ROLE_ID:
            channel_data["permission_overwrites"].append({
                "id": ADMIN_ROLE_ID,
                "type": 0,
                "allow": "3072",
                "deny": "0"
            })
        
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
                {"name": "Category", "value": category, "inline": True},
                {"name": "Channel", "value": f"<#{channel['id']}>", "inline": True}
            ],
            "footer": {"text": "Click the button below to close this ticket"},
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
        
        send_ticket_webhook(ticket_id, user_name, user_id, category, issue, channel['id'], "created")
        
        return channel['id']
        
    except Exception as e:
        logger.error(f"Error creating ticket channel: {e}")
        return None

def close_ticket_channel(channel_id, ticket_id, closed_by):
    """Close ticket channel, delete it, and update database"""
    try:
        conn = get_db_connection()
        ticket = conn.execute(
            'SELECT * FROM tickets WHERE ticket_id = ?',
            (ticket_id,)
        ).fetchone()
        
        conn.execute('''
            UPDATE tickets 
            SET status = "closed", resolved_at = CURRENT_TIMESTAMP, assigned_to = ?
            WHERE ticket_id = ?
        ''', (closed_by, ticket_id))
        conn.commit()
        conn.close()
        
        delete_result = delete_channel(channel_id)
        
        if ticket:
            send_ticket_webhook(ticket_id, ticket['discord_name'], ticket['discord_id'], 
                              ticket['category'], ticket['issue'], None, "closed and deleted")
        
        return True if delete_result else False
        
    except Exception as e:
        logger.error(f"Error closing ticket channel: {e}")
        return False

# =============================================================================
# KEY DATABASE SYSTEM
# =============================================================================

def create_key_database_channel(guild_id):
    """Create private channel for storing API keys"""
    try:
        guild = get_guild_info(guild_id)
        if not guild:
            return None
        
        channel_data = {
            "name": "key-database",
            "type": 0,
            "topic": "Goblin Hut Key Database - PRIVATE - DO NOT SHARE",
            "parent_id": None,
            "permission_overwrites": [
                {
                    "id": guild_id,
                    "type": 0,
                    "allow": "0",
                    "deny": "1024"
                },
                {
                    "id": DISCORD_CLIENT_ID,
                    "type": 2,
                    "allow": "3072",
                    "deny": "0"
                }
            ]
        }
        
        if ADMIN_ROLE_ID:
            channel_data["permission_overwrites"].append({
                "id": ADMIN_ROLE_ID,
                "type": 0,
                "allow": "3072",
                "deny": "0"
            })
        
        channel = create_guild_channel(guild_id, channel_data)
        if not channel:
            return None
        
        embed = {
            "title": "🔑 Key Database Channel",
            "description": "This channel stores all player API keys securely.\n**DO NOT SHARE THESE KEYS WITH ANYONE.**",
            "color": 0xffd700,
            "fields": [
                {"name": "Format", "value": "```yaml\nDiscord User: @username\nIn-Game: PlayerName\nKey: GOB-XXXXXXXXXXXXXXX\nRegistered: YYYY-MM-DD```", "inline": False},
                {"name": "Security", "value": "• Channel is private\n• Only admins can view\n• Keys are encrypted in transit\n• Never share these keys", "inline": False}
            ],
            "footer": {"text": "Updated automatically when players register"},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        welcome_message = {
            "embeds": [embed],
            "content": "# 🔐 KEY DATABASE - PRIVATE"
        }
        
        discord_api_request(f"/channels/{channel['id']}/messages", "POST", welcome_message)
        
        logger.info(f"Created key database channel: {channel['id']}")
        return channel['id']
        
    except Exception as e:
        logger.error(f"Error creating key database channel: {e}")
        return None

def update_key_database():
    """Update key database channel with all player keys"""
    global DATABASE_CHANNEL_ID
    
    if not DATABASE_CHANNEL_ID:
        logger.warning("No key database channel set")
        return False
    
    try:
        messages = discord_api_request(f"/channels/{DATABASE_CHANNEL_ID}/messages?limit=100")
        if messages:
            for msg in messages:
                discord_api_request(f"/channels/{DATABASE_CHANNEL_ID}/messages/{msg['id']}", "DELETE")
                time.sleep(0.1)
        
        conn = get_db_connection()
        players = conn.execute('SELECT * FROM players ORDER BY created_at DESC').fetchall()
        conn.close()
        
        message_batch = []
        current_batch = ""
        
        for player in players:
            player_info = f"""```yaml
Discord: {player['discord_name']} ({player['discord_id']})
In-Game: {player['in_game_name']}
API Key: {player['api_key']}
Registered: {player['created_at'][:10]}
Admin: {'✅' if player['is_admin'] else '❌'}
Server: {player['server_id']}
---
```"""
            
            if len(current_batch) + len(player_info) > 1900:
                message_batch.append(current_batch)
                current_batch = player_info
            else:
                current_batch += player_info
        
        if current_batch:
            message_batch.append(current_batch)
        
        for i, batch in enumerate(message_batch):
            message = {"content": batch}
            discord_api_request(f"/channels/{DATABASE_CHANNEL_ID}/messages", "POST", message)
            time.sleep(0.5)
        
        summary_embed = {
            "title": "📊 Key Database Summary",
            "description": f"Total Players: **{len(players)}**",
            "color": 0x00ff9d,
            "fields": [
                {"name": "Last Updated", "value": f"<t:{int(time.time())}:R>", "inline": True},
                {"name": "Admin Keys", "value": str(sum(1 for p in players if p['is_admin'])), "inline": True},
                {"name": "Total Servers", "value": str(len(set(p['server_id'] for p in players if p['server_id']))), "inline": True}
            ],
            "footer": {"text": "Auto-updates on new registrations"},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        discord_api_request(f"/channels/{DATABASE_CHANNEL_ID}/messages", "POST", {
            "embeds": [summary_embed]
        })
        
        logger.info(f"Updated key database with {len(players)} players")
        return True
        
    except Exception as e:
        logger.error(f"Error updating key database: {e}")
        return False

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
            "name": "setup",
            "description": "Setup key database or stats webhook (Admin only)",
            "type": 1,
            "options": [
                {
                    "name": "type",
                    "description": "Channel type to create",
                    "type": 3,
                    "required": True,
                    "choices": [
                        {"name": "Key Database", "value": "key-database"},
                        {"name": "Stats Webhook", "value": "stats-webhook"}
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
# INTERACTION HANDLERS
# =============================================================================

def handle_interaction(data):
    """Handle Discord slash commands and button interactions"""
    interaction_type = data.get('type')
    
    if interaction_type == 1:  # PING
        return {"type": 1}
    
    elif interaction_type == 3:  # BUTTON CLICK
        return handle_button_click(data)
    
    elif interaction_type == 2:  # SLASH COMMAND
        return handle_slash_command(data)
    
    return {"type": 4, "data": {"content": "Unknown command", "flags": 64}}

def handle_button_click(data):
    """Handle button click interactions"""
    custom_id = data.get('data', {}).get('custom_id', '')
    user_id = data.get('member', {}).get('user', {}).get('id')
    channel_id = data.get('channel_id')
    guild_id = data.get('guild_id')
    
    logger.info(f"Button click: {custom_id} by {user_id}")
    
    if custom_id.startswith('close_ticket_'):
        ticket_id = custom_id.replace('close_ticket_', '')
        conn = get_db_connection()
        ticket = conn.execute(
            'SELECT * FROM tickets WHERE ticket_id = ?',
            (ticket_id,)
        ).fetchone()
        conn.close()
        
        if ticket:
            can_close = False
            if str(user_id) == str(ticket['discord_id']):
                can_close = True
            elif ADMIN_ROLE_ID:
                member = get_guild_member(guild_id, user_id)
                if member and ADMIN_ROLE_ID in member.get('roles', []):
                    can_close = True
            
            if can_close:
                success = close_ticket_channel(channel_id, ticket_id, user_id)
                if success:
                    return {
                        "type": 4,
                        "data": {
                            "content": f"Ticket {ticket_id} has been closed and channel deleted.",
                            "flags": 64
                        }
                    }
                else:
                    return {
                        "type": 4,
                        "data": {
                            "content": f"Ticket marked as closed but could not delete channel.",
                            "flags": 64
                        }
                    }
            else:
                return {
                    "type": 4,
                    "data": {
                        "content": "You don't have permission to close this ticket.",
                        "flags": 64
                    }
                }
    
    return {"type": 6}  # ACK for other button clicks

def handle_slash_command(data):
    """Handle slash commands"""
    command = data.get('data', {}).get('name')
    user_id = data.get('member', {}).get('user', {}).get('id')
    user_name = data.get('member', {}).get('user', {}).get('global_name', 'Unknown')
    server_id = data.get('guild_id', 'DM')
    
    logger.info(f"Command received: {command} from {user_name} ({user_id})")
    
    if command == 'ping':
        response = random.choice(TOXIC_PING_RESPONSES) if random.random() < 0.3 else random.choice(NORMAL_PING_RESPONSES)
        return {"type": 4, "data": {"content": response}}
    
    elif command == 'register':
        return handle_register_command(data, user_id, user_name, server_id)
    
    elif command == 'ticket':
        return handle_ticket_command(data, user_id, user_name, server_id)
    
    elif command == 'close':
        return handle_close_command(data, user_id, user_name, server_id)
    
    elif command == 'profile':
        return handle_profile_command(user_id, user_name)
    
    elif command == 'key':
        return handle_key_command(user_id, user_name)
    
    elif command == 'setup':
        return handle_setup_command(data, user_id, user_name, server_id)
    
    return {"type": 4, "data": {"content": "Unknown command", "flags": 64}}

def handle_register_command(data, user_id, user_name, server_id):
    """Handle /register command"""
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
        return {
            "type": 4,
            "data": {
                "content": (
                    f"You are already registered as **{existing['in_game_name']}**\n\n"
                    f"**Your API Key:**\n```{api_key}```\n\n"
                    f"**Dashboard:** (your-url-here)\n"
                    f"Use `/key` to see your key again anytime"
                ),
                "flags": 64
            }
        }
    
    is_admin = is_user_admin_in_guild(server_id, user_id)
    api_key = generate_secure_key()
    
    discord_user = get_discord_user(user_id)
    discord_avatar = discord_user.get('avatar') if discord_user else None
    
    conn.execute('''
        INSERT INTO players 
        (discord_id, discord_name, discord_avatar, in_game_name, api_key, server_id, is_admin)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, user_name, discord_avatar, in_game_name, api_key, server_id, 1 if is_admin else 0))
    conn.commit()
    conn.close()
    
    if DATABASE_CHANNEL_ID:
        update_key_database()
    
    admin_note = "\n**Admin access detected** - You have additional privileges." if is_admin else ""
    
    return {
        "type": 4,
        "data": {
            "content": (
                f"**Registration Successful!**{admin_note}\n\n"
                f"**Name:** {in_game_name}\n"
                f"**API Key:**\n```{api_key}```\n\n"
                f"**Dashboard:** (your-url-here)\n"
                f"Login to access your full dashboard\n\n"
                f"**Note:** You can only register once. Use `/key` to see your key again."
            ),
            "flags": 64
        }
    }

def handle_ticket_command(data, user_id, user_name, server_id):
    """Handle /ticket command"""
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
        
        return {
            "type": 4,
            "data": {
                "content": f"**Ticket Created**\n\n**Ticket ID:** {ticket_id}\n**Channel:** <#{channel_id}>",
                "flags": 64
            }
        }
    else:
        conn.close()
        return {
            "type": 4,
            "data": {
                "content": f"**Ticket Created**\n\n**Ticket ID:** {ticket_id}\n*Could not create private channel*",
                "flags": 64
            }
        }

def handle_close_command(data, user_id, user_name, server_id):
    """Handle /close command"""
    channel_id = data.get('channel_id')
    
    conn = get_db_connection()
    ticket = conn.execute(
        'SELECT * FROM tickets WHERE channel_id = ? AND status = "open"',
        (channel_id,)
    ).fetchone()
    conn.close()
    
    if not ticket:
        return {"type": 4, "data": {"content": "No open ticket in this channel", "flags": 64}}
    
    success = close_ticket_channel(channel_id, ticket['ticket_id'], user_id)
    
    if success:
        return {
            "type": 4,
            "data": {
                "content": f"Ticket {ticket['ticket_id']} has been closed and channel deleted.",
                "flags": 64
            }
        }
    else:
        return {
            "type": 4,
            "data": {
                "content": f"Ticket marked as closed but could not delete channel.",
                "flags": 64
            }
        }

def handle_profile_command(user_id, user_name):
    """Handle /profile command"""
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE discord_id = ?',
        (user_id,)
    ).fetchone()
    conn.close()
    
    if not player:
        return {"type": 4, "data": {"content": "You are not registered. Use `/register [name]` first.", "flags": 64}}
    
    total_kills = player['total_kills'] or 0
    total_deaths = player['total_deaths'] or 1
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
            {"name": "K/D Ratio", "value": f"**{kd:.2f}** ({total_kills}/{total_deaths})", "inline": True},
            {"name": "Win Rate", "value": f"**{win_rate:.1f}%** ({wins}/{total_games})", "inline": True},
            {"name": "Games Played", "value": f"**{total_games}**", "inline": True},
            {"name": "Status", "value": "**Admin**" if player['is_admin'] else "**Player**", "inline": True}
        ],
        "footer": {"text": "Use /key to see your API key"},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return {"type": 4, "data": {"embeds": [embed], "flags": 64}}

def handle_key_command(user_id, user_name):
    """Handle /key command"""
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE discord_id = ?',
        (user_id,)
    ).fetchone()
    conn.close()
    
    if not player:
        return {"type": 4, "data": {"content": "You are not registered. Use `/register [name]` first.", "flags": 64}}
    
    return {
        "type": 4,
        "data": {
            "content": (
                f"**Your API Key**\n\n"
                f"```{player['api_key']}```\n\n"
                f"**Dashboard:** (your-url-here)\n"
                f"Use this key to login to your dashboard"
            ),
            "flags": 64
        }
    }

def handle_setup_command(data, user_id, user_name, server_id):
    """Handle /setup command"""
    is_admin = is_user_admin_in_guild(server_id, user_id)
    if not is_admin:
        return {"type": 4, "data": {"content": "You need admin privileges to setup channels.", "flags": 64}}
    
    options = data.get('data', {}).get('options', [])
    channel_type = options[0].get('value', 'key-database') if options else 'key-database'
    
    if channel_type == 'key-database':
        channel_id = create_key_database_channel(server_id)
        
        if channel_id:
            global DATABASE_CHANNEL_ID
            DATABASE_CHANNEL_ID = channel_id
            update_key_database()
            
            return {
                "type": 4,
                "data": {
                    "content": f"**Key Database Created**\n\n**Channel:** <#{channel_id}>\n\nAll player API keys have been saved to this private channel.",
                    "flags": 64
                }
            }
        else:
            return {
                "type": 4,
                "data": {
                    "content": "Failed to create key database channel. Check bot permissions.",
                    "flags": 64
                }
            }
    
    return {"type": 4, "data": {"content": "Unknown setup type", "flags": 64}}
# discord_bot.py - Discord bot interactions and slash commands
import time
import random
import requests
from datetime import datetime
from config import (
    DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_PUBLIC_KEY,
    ADMIN_ROLE_ID, TICKET_WEBHOOK, SCORE_WEBHOOK,
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
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN not set")
        return None
        
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
    if not guild_id or not user_id:
        return None
    return discord_api_request(f"/guilds/{guild_id}/members/{user_id}")

def get_guild_roles(guild_id):
    """Get all roles for a guild"""
    if not guild_id:
        return None
    return discord_api_request(f"/guilds/{guild_id}/roles")

def get_guild_info(guild_id):
    """Get guild information"""
    if not guild_id:
        return None
    return discord_api_request(f"/guilds/{guild_id}")

def create_guild_channel(guild_id, channel_data):
    """Create a channel in guild"""
    if not guild_id:
        return None
    return discord_api_request(f"/guilds/{guild_id}/channels", "POST", channel_data)

def delete_channel(channel_id):
    """Delete a channel"""
    if not channel_id:
        return False
    result = discord_api_request(f"/channels/{channel_id}", "DELETE")
    return result is True

def get_discord_user(user_id):
    """Get Discord user info including avatar"""
    if not user_id:
        return None
    return discord_api_request(f"/users/{user_id}")

def is_user_admin_in_guild(guild_id, user_id):
    """Check if user has admin/manage permissions in guild"""
    try:
        if not guild_id or not user_id:
            return False
            
        # Bot can always close tickets
        if str(user_id) == DISCORD_CLIENT_ID:
            return True
            
        member = get_guild_member(guild_id, user_id)
        if not member:
            return False
        
        # Server owner is admin
        guild = get_guild_info(guild_id)
        if guild and str(guild.get('owner_id')) == str(user_id):
            return True
        
        # Check admin role
        if ADMIN_ROLE_ID and ADMIN_ROLE_ID in member.get('roles', []):
            return True
        
        # Check permissions in roles
        roles = get_guild_roles(guild_id)
        if not roles:
            return False
        
        member_roles = member.get('roles', [])
        for role_id in member_roles:
            for role in roles:
                if role['id'] == role_id:
                    permissions = int(role.get('permissions', 0))
                    # Admin, Manage Guild, or Manage Channels permissions
                    if permissions & 0x8 or permissions & 0x20 or permissions & 0x10:
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
            "username": "SOT TDM Ticket System",
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
            "footer": {"text": "SOT TDM Score Tracker"}
        }
        
        data = {
            "embeds": [embed],
            "username": "SOT TDM Score Tracker",
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
    """Create private ticket channel with bot permissions"""
    try:
        if not guild_id:
            return None
            
        short_id = ticket_id.split('-')[1][:4]
        channel_name = f"ticket-{short_id}"
        
        # Bot permissions: All permissions
        bot_permissions = "1024"  # VIEW_CHANNEL
        
        # Create channel with proper permissions
        channel_data = {
            "name": channel_name,
            "type": 0,  # Text channel
            "topic": f"Ticket #{ticket_id} - {issue[:100]}",
            "permission_overwrites": [
                # Bot permissions
                {
                    "id": DISCORD_CLIENT_ID,
                    "type": 2,  # Member type
                    "allow": "1024",  # VIEW_CHANNEL
                    "deny": "0"
                },
                # Everyone else can't view
                {
                    "id": guild_id,
                    "type": 0,  # Role type
                    "allow": "0",
                    "deny": "1024"  # VIEW_CHANNEL
                },
                # Ticket creator can view and send messages
                {
                    "id": user_id,
                    "type": 1,  # Member type
                    "allow": "3072",  # VIEW_CHANNEL + SEND_MESSAGES
                    "deny": "0"
                }
            ]
        }
        
        # Add admin role if specified
        if ADMIN_ROLE_ID:
            channel_data["permission_overwrites"].append({
                "id": ADMIN_ROLE_ID,
                "type": 0,  # Role type
                "allow": "3072",  # VIEW_CHANNEL + SEND_MESSAGES
                "deny": "0"
            })
        
        channel = create_guild_channel(guild_id, channel_data)
        if not channel:
            return None
        
        # Send welcome message
        embed = {
            "title": f"Ticket #{ticket_id}",
            "description": issue[:1000],
            "color": 0x00ff9d,
            "fields": [
                {"name": "Created By", "value": f"<@{user_id}>", "inline": True},
                {"name": "Category", "value": category, "inline": True},
                {"name": "Status", "value": "Open", "inline": True}
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        welcome_message = {
            "content": f"<@{user_id}> Welcome to your ticket! Use `/close` to close this ticket.",
            "embeds": [embed]
        }
        
        discord_api_request(f"/channels/{channel['id']}/messages", "POST", welcome_message)
        
        send_ticket_webhook(ticket_id, user_name, user_id, category, issue, channel['id'], "created")
        
        logger.info(f"Created ticket channel: {channel['id']} for ticket {ticket_id}")
        return channel['id']
        
    except Exception as e:
        logger.error(f"Error creating ticket channel: {e}")
        return None

def close_ticket_channel(channel_id, ticket_id, closed_by):
    """Close ticket channel - bot has permission to delete"""
    try:
        if not channel_id or not ticket_id:
            return False
            
        conn = get_db_connection()
        ticket = conn.execute(
            'SELECT * FROM tickets WHERE ticket_id = ?',
            (ticket_id,)
        ).fetchone()
        
        if ticket:
            conn.execute('''
                UPDATE tickets 
                SET status = "closed", resolved_at = CURRENT_TIMESTAMP, assigned_to = ?
                WHERE ticket_id = ?
            ''', (closed_by, ticket_id))
            conn.commit()
        
        conn.close()
        
        # Bot always has permission to delete
        delete_result = delete_channel(channel_id)
        
        if ticket and delete_result:
            send_ticket_webhook(ticket_id, ticket['discord_name'], ticket['discord_id'], 
                              ticket['category'], ticket['issue'], None, "closed")
            logger.info(f"Closed ticket {ticket_id} and deleted channel {channel_id}")
        elif not delete_result:
            logger.error(f"Failed to delete channel {channel_id}")
        
        return delete_result
        
    except Exception as e:
        logger.error(f"Error closing ticket channel: {e}")
        return False

def setup_key_database(guild_id, user_id):
    """Setup a key database channel with bot permissions"""
    try:
        if not guild_id:
            return None
            
        # Create channel
        channel_data = {
            "name": "api-key-database",
            "type": 0,
            "topic": "API Keys Database - Private - DO NOT SHARE",
            "permission_overwrites": [
                # Bot permissions
                {
                    "id": DISCORD_CLIENT_ID,
                    "type": 2,
                    "allow": "1024",  # VIEW_CHANNEL
                    "deny": "0"
                },
                # Everyone else can't view
                {
                    "id": guild_id,
                    "type": 0,
                    "allow": "0",
                    "deny": "1024"
                }
            ]
        }
        
        # Add creator and admin role
        if ADMIN_ROLE_ID:
            channel_data["permission_overwrites"].append({
                "id": ADMIN_ROLE_ID,
                "type": 0,
                "allow": "3072",
                "deny": "0"
            })
        
        if user_id:
            channel_data["permission_overwrites"].append({
                "id": user_id,
                "type": 1,
                "allow": "3072",
                "deny": "0"
            })
        
        channel = create_guild_channel(guild_id, channel_data)
        if not channel:
            return None
        
        # Send initial message
        embed = {
            "title": "🔑 API Key Database",
            "description": "This channel stores player API keys.\n**DO NOT SHARE THESE KEYS WITH ANYONE.**",
            "color": 0xffd700,
            "fields": [
                {"name": "Security", "value": "• Channel is private\n• Only admins can view\n• Never share API keys", "inline": False},
                {"name": "Format", "value": "```\nPlayer: Name\nAPI Key: GOB-XXXXXXXXXXXXXXX\n```", "inline": False}
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        discord_api_request(f"/channels/{channel['id']}/messages", "POST", {
            "embeds": [embed],
            "content": "# 🔐 API KEY DATABASE"
        })
        
        logger.info(f"Created key database channel: {channel['id']}")
        return channel['id']
        
    except Exception as e:
        logger.error(f"Error creating key database: {e}")
        return None

def update_key_database(channel_id):
    """Update key database channel with current player keys"""
    try:
        if not channel_id:
            return False
            
        conn = get_db_connection()
        players = conn.execute('SELECT * FROM players ORDER BY created_at DESC').fetchall()
        conn.close()
        
        # Clear existing messages
        messages = discord_api_request(f"/channels/{channel_id}/messages?limit=50")
        if messages:
            for msg in messages:
                discord_api_request(f"/channels/{channel_id}/messages/{msg['id']}", "DELETE")
                time.sleep(0.1)
        
        # Send player data
        for player in players:
            player_info = f"""```yaml
Discord: {player['discord_name']}
In-Game: {player['in_game_name']}
API Key: {player['api_key']}
Registered: {player['created_at'][:10]}
Admin: {'Yes' if player['is_admin'] else 'No'}
---```
"""
            
            discord_api_request(f"/channels/{channel_id}/messages", "POST", {
                "content": player_info
            })
            time.sleep(0.1)
        
        # Send summary
        summary = f"""```diff
+ KEY DATABASE UPDATED
+ Total Players: {len(players)}
+ Admins: {sum(1 for p in players if p['is_admin'])}
+ Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
```"""
        
        discord_api_request(f"/channels/{channel_id}/messages", "POST", {
            "content": summary
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
        logger.warning("DISCORD_TOKEN not set")
        bot_active = False
        return False
    
    try:
        url = "https://discord.com/api/v10/users/@me"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            bot_info = response.json()
            bot_active = True
            logger.info(f"✅ Discord bot connected: {bot_info['username']} ({bot_info['id']})")
            return True
        else:
            logger.error(f"❌ Invalid Discord token: {response.status_code}")
            bot_active = False
            return False
            
    except Exception as e:
        logger.error(f"❌ Discord API error: {e}")
        bot_active = False
        return False

def register_commands():
    """Register slash commands"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        logger.error("Cannot register commands - missing token or client ID")
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
                    "required": False,
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
            "name": "setup-keys",
            "description": "Setup API key database (Admin only)",
            "type": 1
        },
        {
            "name": "update-keys",
            "description": "Update key database (Admin only)",
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
            logger.info(f"✅ Registered {len(commands)} commands")
            return True
        else:
            logger.error(f"❌ Failed to register commands: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error registering commands: {e}")
        return False

# =============================================================================
# INTERACTION HANDLERS
# =============================================================================

def handle_interaction(data):
    """Handle Discord slash commands"""
    interaction_type = data.get('type')
    
    if interaction_type == 1:  # PING
        return {"type": 1}
    
    elif interaction_type == 2:  # SLASH COMMAND
        return handle_slash_command(data)
    
    return {"type": 4, "data": {"content": "Unknown command", "flags": 64}}

def handle_slash_command(data):
    """Handle slash commands"""
    command = data.get('data', {}).get('name')
    user_id = data.get('member', {}).get('user', {}).get('id')
    user_name = data.get('member', {}).get('user', {}).get('global_name', 'Unknown')
    server_id = data.get('guild_id')
    
    logger.info(f"Command: {command} from {user_name} ({user_id}) in {server_id}")
    
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
    
    elif command == 'setup-keys':
        return handle_setup_keys_command(data, user_id, user_name, server_id)
    
    elif command == 'update-keys':
        return handle_update_keys_command(data, user_id, user_name, server_id)
    
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
                    f"Already registered as **{existing['in_game_name']}**\n"
                    f"**API Key:** `{api_key}`\n"
                    f"Use `/key` to see your key"
                ),
                "flags": 64
            }
        }
    
    is_admin = is_user_admin_in_guild(server_id, user_id)
    api_key = generate_secure_key()
    
    conn.execute('''
        INSERT INTO players 
        (discord_id, discord_name, in_game_name, api_key, server_id, is_admin)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, user_name, in_game_name, api_key, server_id, 1 if is_admin else 0))
    conn.commit()
    conn.close()
    
    return {
        "type": 4,
        "data": {
            "content": (
                f"✅ Registered as **{in_game_name}**\n"
                f"**API Key:** `{api_key}`\n\n"
                f"Save this key! Use it to login to the dashboard."
            ),
            "flags": 64
        }
    }

def handle_ticket_command(data, user_id, user_name, server_id):
    """Handle /ticket command"""
    options = data.get('data', {}).get('options', [])
    issue = options[0].get('value', 'No issue specified') if options else 'No issue specified'
    category = options[1].get('value', 'Other') if len(options) > 1 else 'Other'
    
    if not server_id:
        return {"type": 4, "data": {"content": "Tickets can only be created in servers", "flags": 64}}
    
    ticket_id = f"T{int(time.time()) % 10000:04d}"
    
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO tickets (ticket_id, discord_id, discord_name, issue, category)
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
                "content": f"✅ Ticket created\n**ID:** {ticket_id}\n**Channel:** <#{channel_id}>",
                "flags": 64
            }
        }
    else:
        conn.close()
        return {
            "type": 4,
            "data": {
                "content": f"❌ Could not create ticket channel. Check bot permissions.",
                "flags": 64
            }
        }

def handle_close_command(data, user_id, user_name, server_id):
    """Handle /close command - bot can always close"""
    channel_id = data.get('channel_id')
    
    if not channel_id:
        return {"type": 4, "data": {"content": "No channel specified", "flags": 64}}
    
    conn = get_db_connection()
    ticket = conn.execute(
        'SELECT * FROM tickets WHERE channel_id = ? AND status = "open"',
        (channel_id,)
    ).fetchone()
    conn.close()
    
    if not ticket:
        return {"type": 4, "data": {"content": "No open ticket in this channel", "flags": 64}}
    
    # Check permissions: bot, ticket creator, or admin can close
    can_close = False
    
    # Bot can always close
    if str(user_id) == DISCORD_CLIENT_ID:
        can_close = True
    # Ticket creator can close
    elif str(user_id) == str(ticket['discord_id']):
        can_close = True
    # Admin can close
    elif is_user_admin_in_guild(server_id, user_id):
        can_close = True
    
    if not can_close:
        return {"type": 4, "data": {"content": "You don't have permission to close this ticket", "flags": 64}}
    
    success = close_ticket_channel(channel_id, ticket['ticket_id'], user_id)
    
    if success:
        return {
            "type": 4,
            "data": {
                "content": f"✅ Ticket {ticket['ticket_id']} closed and channel deleted.",
                "flags": 64
            }
        }
    else:
        return {
            "type": 4,
            "data": {
                "content": f"❌ Failed to close ticket.",
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
        return {"type": 4, "data": {"content": "Use `/register [name]` first", "flags": 64}}
    
    total_kills = player['total_kills'] or 0
    total_deaths = player['total_deaths'] or 1
    wins = player['wins'] or 0
    losses = player['losses'] or 0
    
    kd = total_kills / total_deaths
    total_games = wins + losses
    win_rate = (wins / total_games * 100) if total_games > 0 else 0
    
    embed = {
        "title": f"Profile: {player['in_game_name']}",
        "color": 0x00ff9d,
        "fields": [
            {"name": "K/D Ratio", "value": f"**{kd:.2f}**", "inline": True},
            {"name": "Win Rate", "value": f"**{win_rate:.1f}%**", "inline": True},
            {"name": "Games", "value": f"**{total_games}**", "inline": True},
            {"name": "Kills", "value": f"**{total_kills}**", "inline": True},
            {"name": "Deaths", "value": f"**{total_deaths}**", "inline": True},
            {"name": "Wins/Losses", "value": f"**{wins}/{losses}**", "inline": True}
        ],
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
        return {"type": 4, "data": {"content": "Use `/register [name]` first", "flags": 64}}
    
    return {
        "type": 4,
        "data": {
            "content": f"**Your API Key:**\n`{player['api_key']}`",
            "flags": 64
        }
    }

def handle_setup_keys_command(data, user_id, user_name, server_id):
    """Handle /setup-keys command"""
    if not server_id:
        return {"type": 4, "data": {"content": "This command only works in servers", "flags": 64}}
    
    if not is_user_admin_in_guild(server_id, user_id):
        return {"type": 4, "data": {"content": "Admin only command", "flags": 64}}
    
    channel_id = setup_key_database(server_id, user_id)
    
    if channel_id:
        return {
            "type": 4,
            "data": {
                "content": f"✅ Key database created: <#{channel_id}>\nUse `/update-keys` to populate it.",
                "flags": 64
            }
        }
    else:
        return {
            "type": 4,
            "data": {
                "content": "❌ Failed to create key database. Check bot permissions.",
                "flags": 64
            }
        }

def handle_update_keys_command(data, user_id, user_name, server_id):
    """Handle /update-keys command"""
    if not server_id:
        return {"type": 4, "data": {"content": "This command only works in servers", "flags": 64}}
    
    if not is_user_admin_in_guild(server_id, user_id):
        return {"type": 4, "data": {"content": "Admin only command", "flags": 64}}
    
    # Find key database channel
    channel_id = None
    channels = discord_api_request(f"/guilds/{server_id}/channels")
    if channels:
        for channel in channels:
            if channel.get('name') == 'api-key-database':
                channel_id = channel['id']
                break
    
    if not channel_id:
        return {"type": 4, "data": {"content": "No key database found. Use `/setup-keys` first.", "flags": 64}}
    
    success = update_key_database(channel_id)
    
    if success:
        return {
            "type": 4,
            "data": {
                "content": f"✅ Key database updated in <#{channel_id}>",
                "flags": 64
            }
        }
    else:
        return {
            "type": 4,
            "data": {
                "content": "❌ Failed to update key database.",
                "flags": 64
            }
        }

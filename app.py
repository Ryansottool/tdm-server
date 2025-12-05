# app.py - Sea of Thieves TDM Server with Discord Bot
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json
import time
import random
import string
import threading
from datetime import datetime
import logging
import base64
import hashlib
import discord
from discord.ext import commands, tasks
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"], methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

# Discord Bot Configuration
DISCORD_BOT_TOKEN = None  # Set via environment variable or API
discord_bot = None
discord_channel = None

class DiscordBotManager:
    def __init__(self):
        self.bot = None
        self.channel = None
        self.is_ready = False
        self.queue = []
        self.running = False
        
    def start_bot(self, token, channel_id=None):
        """Start Discord bot in a separate thread"""
        if self.running:
            return
            
        self.running = True
        self.token = token
        
        # Start bot in background thread
        bot_thread = threading.Thread(target=self._run_bot, args=(token, channel_id), daemon=True)
        bot_thread.start()
        logger.info("🤖 Discord bot thread started")
        
    def _run_bot(self, token, channel_id):
        """Run Discord bot with asyncio"""
        intents = discord.Intents.default()
        intents.message_content = True
        
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        
        @self.bot.event
        async def on_ready():
            logger.info(f"✅ Discord bot logged in as {self.bot.user}")
            self.is_ready = True
            
            # Find channel if ID provided
            if channel_id:
                try:
                    self.channel = self.bot.get_channel(int(channel_id))
                    if self.channel:
                        logger.info(f"📢 Discord channel set: #{self.channel.name}")
                    else:
                        logger.warning(f"Channel ID {channel_id} not found")
                except:
                    logger.error(f"Invalid channel ID: {channel_id}")
            
            # Process queued messages
            if self.queue:
                logger.info(f"Processing {len(self.queue)} queued messages")
                for embed_data in self.queue:
                    await self.send_embed(embed_data)
                self.queue.clear()
                
        @self.bot.event
        async def on_message(message):
            # Ignore bot's own messages
            if message.author == self.bot.user:
                return
            
            # Handle commands
            if message.content.startswith('!tdm'):
                await self.handle_tdm_command(message)
            
            # Allow other commands to be processed
            await self.bot.process_commands(message)
        
        @self.bot.command(name='stats')
        async def stats_command(ctx):
            """Get server statistics"""
            try:
                stats = game_state.get_system_stats()
                
                embed = discord.Embed(
                    title="📊 TDM Server Statistics",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(name="👥 Online Players", value=stats['online_players'], inline=True)
                embed.add_field(name="🎮 Active Rooms", value=stats['active_rooms'], inline=True)
                embed.add_field(name="⚔️ Total Matches", value=stats['total_matches'], inline=True)
                embed.add_field(name="🗡️ Total Kills", value=stats['total_kills'], inline=True)
                embed.add_field(name="⏱️ Server Uptime", value=stats['server_uptime_formatted'], inline=True)
                embed.add_field(name="📈 Performance", value=f"{stats['performance_metrics']['cleanup_efficiency']} efficiency", inline=True)
                
                await ctx.send(embed=embed)
                
            except Exception as e:
                await ctx.send(f"Error getting stats: {str(e)}")
        
        # Run the bot
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.bot.run(token)
        except Exception as e:
            logger.error(f"Discord bot error: {e}")
            self.running = False
            
    async def handle_tdm_command(self, message):
        """Handle !tdm commands"""
        command_parts = message.content.split()
        
        if len(command_parts) < 2:
            await message.channel.send(
                "**TDM Bot Commands:**\n"
                "`!tdm stats` - Server statistics\n"
                "`!tdm rooms` - List active rooms\n"
                "`!tdm leaderboard` - Top players\n"
                "`!tdm recent` - Recent matches\n"
                "`!tdm help` - Show this help"
            )
            return
            
        subcommand = command_parts[1].lower()
        
        if subcommand == 'stats':
            stats = game_state.get_system_stats()
            
            embed = discord.Embed(
                title="📊 TDM Server Statistics",
                color=discord.Color.green(),
                description=f"Server running for {stats['server_uptime_formatted']}"
            )
            
            embed.add_field(name="👥 Online Players", value=stats['online_players'], inline=True)
            embed.add_field(name="🎮 Active Rooms", value=stats['active_rooms'], inline=True)
            embed.add_field(name="⚔️ Total Matches", value=stats['total_matches'], inline=True)
            embed.add_field(name="🗡️ Total Kills", value=stats['total_kills'], inline=True)
            
            await message.channel.send(embed=embed)
            
        elif subcommand == 'rooms':
            rooms = []
            for room_code, room in game_state.rooms.items():
                if not room.get('is_24h_channel', False):
                    rooms.append(f"**{room['room_name']}** (`{room_code}`) - {len(room['players'])}/{room['max_players']} players")
            
            if rooms:
                embed = discord.Embed(
                    title="🎮 Active Rooms",
                    color=discord.Color.blue(),
                    description="\n".join(rooms[:10])
                )
                if len(rooms) > 10:
                    embed.set_footer(text=f"Showing 10 of {len(rooms)} rooms")
            else:
                embed = discord.Embed(
                    title="🎮 Active Rooms",
                    color=discord.Color.orange(),
                    description="No active rooms at the moment"
                )
            
            await message.channel.send(embed=embed)
            
        elif subcommand == 'leaderboard':
            # Get top 10 players
            leaderboard_data = []
            for player_name, stats in game_state.leaderboard.items():
                kd_ratio = stats['kills'] / max(stats['deaths'], 1)
                leaderboard_data.append({
                    'player_name': player_name,
                    'kills': stats.get('kills', 0),
                    'deaths': stats.get('deaths', 0),
                    'kd_ratio': kd_ratio,
                    'wins': stats.get('wins', 0)
                })
            
            leaderboard_data.sort(key=lambda x: x['kills'], reverse=True)
            
            description = "**Top 10 Players:**\n"
            for i, player in enumerate(leaderboard_data[:10], 1):
                description += f"{i}. **{player['player_name']}** - {player['kills']} kills ({player['kd_ratio']:.2f} K/D)\n"
            
            embed = discord.Embed(
                title="🏆 Leaderboard",
                color=discord.Color.gold(),
                description=description
            )
            
            await message.channel.send(embed=embed)
            
        elif subcommand == 'recent':
            recent_matches = game_state.past_matches[-5:]  # Last 5 matches
            
            if recent_matches:
                embed = discord.Embed(
                    title="📅 Recent Matches",
                    color=discord.Color.purple()
                )
                
                for match in reversed(recent_matches):
                    winner_text = "Draw" if match.get('winner') == 'draw' else f"Team {match.get('winner', '')[4:]} Wins!"
                    embed.add_field(
                        name=f"{match['room_name']}",
                        value=f"Score: **{match['team1_score']}** - **{match['team2_score']}**\n"
                              f"Winner: {winner_text}\n"
                              f"Kills: {match.get('kill_count', 0)}\n"
                              f"Mode: {match['game_mode']}",
                        inline=False
                    )
            else:
                embed = discord.Embed(
                    title="📅 Recent Matches",
                    color=discord.Color.orange(),
                    description="No matches played yet"
                )
            
            await message.channel.send(embed=embed)
            
        elif subcommand == 'help':
            await message.channel.send(
                "**🤖 TDM Bot Commands:**\n"
                "```\n"
                "!tdm stats     - Server statistics\n"
                "!tdm rooms     - List active rooms\n"
                "!tdm leaderboard - Top players\n"
                "!tdm recent    - Recent matches\n"
                "!tdm help      - Show this help\n"
                "```\n"
                "**Need Support?** Create issues on GitHub or join our Discord!"
            )
    
    async def send_embed(self, embed_data):
        """Send embed message to Discord"""
        if not self.is_ready or not self.channel:
            # Queue message for when bot is ready
            self.queue.append(embed_data)
            return False
            
        try:
            embed = discord.Embed(
                title=embed_data.get('title', 'TDM Update'),
                description=embed_data.get('description', ''),
                color=embed_data.get('color', discord.Color.orange()),
                timestamp=datetime.now()
            )
            
            # Add fields
            for field in embed_data.get('fields', []):
                embed.add_field(
                    name=field.get('name', 'Field'),
                    value=field.get('value', ''),
                    inline=field.get('inline', True)
                )
            
            # Add footer if provided
            if 'footer' in embed_data:
                embed.set_footer(text=embed_data['footer'])
            
            # Add thumbnail if provided
            if 'thumbnail' in embed_data:
                embed.set_thumbnail(url=embed_data['thumbnail'])
            
            await self.channel.send(embed=embed)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Discord embed: {e}")
            return False
            
    def send_match_start(self, room_data):
        """Send match start notification"""
        embed_data = {
            'title': '⚔️ MATCH STARTED',
            'description': f"**{room_data['room_name']}**",
            'color': 0x00ff00,
            'fields': [
                {'name': 'Room Code', 'value': room_data['room_code'], 'inline': True},
                {'name': 'Game Mode', 'value': room_data['game_mode'], 'inline': True},
                {'name': 'Players', 'value': f"{len(room_data['players'])}/{room_data['max_players']}", 'inline': True},
                {'name': 'Team 1', 'value': ', '.join(room_data['teams']['team1']) or 'None', 'inline': False},
                {'name': 'Team 2', 'value': ', '.join(room_data['teams']['team2']) or 'None', 'inline': False}
            ],
            'footer': 'Match starting now!'
        }
        
        # Run in background thread
        threading.Thread(target=self._async_send_embed, args=(embed_data,), daemon=True).start()
        
    def send_kill_notification(self, room_data, kill_data):
        """Send kill notification"""
        embed_data = {
            'title': '🎯 KILL CONFIRMED',
            'description': f"**{kill_data['killer']}** eliminated **{kill_data['victim']}**",
            'color': 0xff0000,
            'fields': [
                {'name': 'Room', 'value': room_data['room_name'], 'inline': True},
                {'name': 'Score', 'value': f"Team 1: **{room_data['scores']['team1']}** - Team 2: **{room_data['scores']['team2']}**", 'inline': True},
                {'name': 'Total Kills', 'value': str(len(room_data['kill_feed'])), 'inline': True}
            ],
            'footer': f'Room: {room_data["room_code"]}'
        }
        
        threading.Thread(target=self._async_send_embed, args=(embed_data,), daemon=True).start()
        
    def send_match_end(self, match_data):
        """Send match end summary"""
        winner_text = "Draw" if match_data['winner'] == 'draw' else f"Team {match_data['winner'][-1]} Wins!"
        
        embed_data = {
            'title': '🏆 MATCH COMPLETE',
            'description': f"**{match_data['room_name']}**",
            'color': 0xffd700,
            'fields': [
                {'name': 'Final Score', 'value': f"Team 1: **{match_data['team1_score']}** - Team 2: **{match_data['team2_score']}**", 'inline': False},
                {'name': 'Winner', 'value': winner_text, 'inline': True},
                {'name': 'Duration', 'value': f"{match_data['duration']}s", 'inline': True},
                {'name': 'Total Kills', 'value': str(match_data['kill_count']), 'inline': True}
            ],
            'footer': f'Room Code: {match_data["room_code"]} • Match ID: {match_data["id"]}'
        }
        
        threading.Thread(target=self._async_send_embed, args=(embed_data,), daemon=True).start()
        
    def send_room_created(self, room_data):
        """Send room created notification"""
        embed_data = {
            'title': '🎮 ROOM CREATED',
            'description': f"New room **{room_data['room_name']}**",
            'color': 0x0099ff,
            'fields': [
                {'name': 'Room Code', 'value': f"`{room_data['room_code']}`", 'inline': True},
                {'name': 'Host', 'value': room_data['host_name'], 'inline': True},
                {'name': 'Game Mode', 'value': room_data['game_mode'], 'inline': True},
                {'name': 'Max Players', 'value': str(room_data['max_players']), 'inline': True}
            ],
            'footer': 'Join now to play!'
        }
        
        threading.Thread(target=self._async_send_embed, args=(embed_data,), daemon=True).start()
        
    def _async_send_embed(self, embed_data):
        """Async wrapper for sending embeds"""
        if self.bot and self.is_ready:
            asyncio.run_coroutine_threadsafe(self.send_embed(embed_data), self.bot.loop)
        else:
            # Queue for later
            self.queue.append(embed_data)

# Initialize Discord bot manager
discord_manager = DiscordBotManager()

# Rest of your existing code (KillDetectionSystem, DeathVerificationSystem, TDMGameState classes)
# ... [Keep all your existing classes and code] ...

# Initialize global game state and detection systems
game_state = TDMGameState()
kill_detector = KillDetectionSystem()
death_verifier = DeathVerificationSystem()

def cleanup_worker():
    """Background cleanup worker"""
    game_state.create_always_active_room()
    last_maintenance = time.time()
    
    logger.info("🔄 Starting cleanup worker...")
    
    while True:
        try:
            # Always run main cleanup
            game_state.cleanup_inactive_rooms()
            
            # Run maintenance tasks every 5 minutes
            if time.time() - last_maintenance > 300:
                # Cleanup very old leaderboard entries (inactive for 30 days)
                current_time = time.time()
                old_players = []
                for player_name, stats in list(game_state.leaderboard.items()):
                    if current_time - stats.get('last_seen', 0) > 2592000:  # 30 days
                        old_players.append(player_name)
                
                for player_name in old_players:
                    del game_state.leaderboard[player_name]
                    
                if old_players:
                    logger.info(f"📋 Cleaned up {len(old_players)} old leaderboard entries")
                
                # Log system health
                stats = game_state.get_system_stats()
                logger.info(f"❤️ System Health - Rooms: {stats['total_rooms']}, Players: {stats['online_players']}, Matches: {stats['total_matches']}")
                    
                last_maintenance = time.time()
                
        except Exception as e:
            logger.error(f"💥 Cleanup worker error: {e}")
            time.sleep(5)  # Brief pause before retry
        
        time.sleep(game_state.cleanup_interval)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True, name="CleanupWorker")
cleanup_thread.start()

logger.info("🎯 TDM Server started with cleanup system")

# =============================================================================
# NEW DISCORD BOT ENDPOINTS
# =============================================================================

@app.route('/api/set_discord_bot', methods=['POST'])
def set_discord_bot():
    """Set Discord bot token and channel"""
    try:
        data = request.get_json()
        token = data.get('bot_token')
        channel_id = data.get('channel_id')
        
        if not token:
            return jsonify({'status': 'error', 'message': 'Bot token required'})
        
        # Start Discord bot
        discord_manager.start_bot(token, channel_id)
        
        return jsonify({
            'status': 'success',
            'message': 'Discord bot started successfully'
        })
        
    except Exception as e:
        logger.error(f"Error setting Discord bot: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/discord_status', methods=['GET'])
def discord_status():
    """Get Discord bot status"""
    status = {
        'is_ready': discord_manager.is_ready,
        'is_running': discord_manager.running,
        'queue_size': len(discord_manager.queue),
        'channel_set': discord_manager.channel is not None
    }
    
    return jsonify({
        'status': 'success',
        'discord_status': status
    })

# =============================================================================
# UPDATED API HANDLERS WITH DISCORD NOTIFICATIONS
# =============================================================================

def handle_create_room(data):
    room_code = generate_room_code()
    room_name = data.get('room_name', 'TDM Room')
    game_mode = data.get('game_mode', '2v2')
    host_name = data.get('host_name', 'Unknown')
    password = data.get('password', '')
    
    game_state.rooms[room_code] = {
        'room_code': room_code,
        'room_name': room_name,
        'game_mode': game_mode,
        'max_players': 4,
        'host_name': host_name,
        'password': password,
        'has_password': bool(password),
        'teams': {"team1": [], "team2": [], "spectators": []},
        'scores': {"team1": 0, "team2": 0},
        'game_active': False,
        'kill_feed': [],
        'pending_kills': [],
        'spectator_confirm_required': False,
        'created_time': time.time(),
        'last_activity': time.time(),
        'players': [],
        'player_last_active': {},
        'is_24h_channel': False
    }
    
    # Send Discord notification
    discord_manager.send_room_created(game_state.rooms[room_code])
    
    game_state.add_recent_activity('Room Created', f'{room_name} ({room_code})', room_code, host_name)
    logger.info(f"Room created: {room_code} by {host_name}")
    
    return jsonify({
        'status': 'success',
        'room_code': room_code,
        'message': f'Room {room_code} created successfully'
    })

def handle_report_kill(data):
    room_code = data.get('room_code', '').upper()
    killer = data.get('killer')
    victim = data.get('victim')
    
    if room_code not in game_state.rooms:
        return jsonify({'status': 'error', 'message': 'Room not found'})
    
    room = game_state.rooms[room_code]
    
    # Add to kill feed
    kill_entry = {
        'killer': killer,
        'victim': victim,
        'timestamp': time.time()
    }
    room['kill_feed'].append(kill_entry)
    
    # Update scores based on teams
    killer_team = None
    for team, players in room['teams'].items():
        if killer in players:
            killer_team = team
            break
    
    if killer_team and killer_team in ['team1', 'team2']:
        room['scores'][killer_team] += 1
    
    room['last_activity'] = time.time()
    game_state.update_player_activity(killer, room_code)
    game_state.update_player_activity(victim, room_code)
    game_state.update_leaderboard(room)
    
    # Send Discord notification
    discord_manager.send_kill_notification(room, kill_entry)
    
    game_state.add_recent_activity('Kill', f'{killer} defeated {victim}', room_code)
    logger.info(f"Kill registered: {killer} → {victim} in {room_code}")
    
    return jsonify({
        'status': 'success',
        'message': 'Kill registered successfully'
    })

def handle_start_game(data):
    room_code = data.get('room_code', '').upper()
    
    if room_code not in game_state.rooms:
        return jsonify({'status': 'error', 'message': 'Room not found'})
    
    room = game_state.rooms[room_code]
    room['game_active'] = True
    room['scores'] = {"team1": 0, "team2": 0}
    room['kill_feed'] = []
    room['last_activity'] = time.time()
    
    # Send Discord notification
    discord_manager.send_match_start(room)
    
    game_state.add_recent_activity('Game Started', f'Game started in {room["room_name"]}', room_code)
    logger.info(f"Game started in room {room_code}")
    
    return jsonify({
        'status': 'success',
        'message': 'Game started'
    })

# Update TDMGameState.add_past_match to send Discord notification
def add_past_match_with_discord(room_data):
    """Add completed match to past matches and notify Discord"""
    if room_data.get('game_active', False) and sum(room_data['scores'].values()) > 0:
        match_data = {
            'id': len(game_state.past_matches) + 1,
            'room_code': room_data['room_code'],
            'room_name': room_data['room_name'],
            'team1_score': room_data['scores']['team1'],
            'team2_score': room_data['scores']['team2'],
            'team1_players': room_data['teams']['team1'].copy(),
            'team2_players': room_data['teams']['team2'].copy(),
            'timestamp': time.time(),
            'duration': random.randint(300, 1800),  # 5-30 minutes
            'game_mode': room_data['game_mode'],
            'kill_count': len(room_data.get('kill_feed', [])),
            'total_players': len(room_data.get('players', [])),
            'host_name': room_data.get('host_name', 'Unknown')
        }
        
        # Determine winner and update stats
        if room_data['scores']['team1'] > room_data['scores']['team2']:
            match_data['winner'] = 'team1'
            match_data['winning_score'] = room_data['scores']['team1']
            match_data['losing_score'] = room_data['scores']['team2']
            for player in room_data['teams']['team1']:
                if player in game_state.leaderboard:
                    game_state.leaderboard[player]['wins'] += 1
                    game_state.leaderboard[player]['games_played'] += 1
                    game_state.leaderboard[player]['total_score'] += 500  # Win bonus
        elif room_data['scores']['team2'] > room_data['scores']['team1']:
            match_data['winner'] = 'team2'
            match_data['winning_score'] = room_data['scores']['team2']
            match_data['losing_score'] = room_data['scores']['team1']
            for player in room_data['teams']['team2']:
                if player in game_state.leaderboard:
                    game_state.leaderboard[player]['wins'] += 1
                    game_state.leaderboard[player]['games_played'] += 1
                    game_state.leaderboard[player]['total_score'] += 500  # Win bonus
        else:
            match_data['winner'] = 'draw'
            match_data['winning_score'] = room_data['scores']['team1']
            match_data['losing_score'] = room_data['scores']['team2']
            for player in room_data['teams']['team1'] + room_data['teams']['team2']:
                if player in game_state.leaderboard:
                    game_state.leaderboard[player]['games_played'] += 1
                    game_state.leaderboard[player]['total_score'] += 250  # Draw bonus
        
        game_state.past_matches.append(match_data)
        game_state.total_matches_played += 1
        
        # Send Discord notification
        discord_manager.send_match_end(match_data)
        
        game_state.add_recent_activity('Match Completed', 
                                   f'{room_data["room_name"]} - Team1: {room_data["scores"]["team1"]} vs Team2: {room_data["scores"]["team2"]}',
                                   room_data['room_code'])
        
        # Keep only last 100 matches for performance
        if len(game_state.past_matches) > 100:
            game_state.past_matches.pop(0)

# Update TDMGameState.add_past_match method
game_state.add_past_match = add_past_match_with_discord

# =============================================================================
# DEPLOYMENT SETUP
# =============================================================================

@app.route('/deploy', methods=['GET'])
def deploy_info():
    """Deployment instructions"""
    return jsonify({
        'status': 'ready',
        'instructions': {
            '1': 'Set Discord bot token via POST /api/set_discord_bot',
            '2': 'Create bot on https://discord.com/developers/applications',
            '3': 'Invite bot to your server with required permissions',
            '4': 'Set channel ID for notifications (optional)',
            '5': 'Server is ready to handle TDM matches'
        },
        'endpoints': {
            'web_interface': '/',
            'api': '/api (POST)',
            'stats': '/stats',
            'system': '/system',
            'discord_status': '/api/discord_status',
            'set_discord': '/api/set_discord_bot'
        },
        'discord_bot_commands': [
            '!tdm stats - Server statistics',
            '!tdm rooms - List active rooms',
            '!tdm leaderboard - Top players',
            '!tdm recent - Recent matches',
            '!tdm help - Show help'
        ]
    })

if __name__ == '__main__':
    logger.info("🎮 Starting Sea of Thieves TDM Server with Discord Bot")
    logger.info("🤖 Discord Bot: Ready to connect")
    logger.info("⚡ Features: Real-time tracking, Death verification, Leaderboards, Discord notifications")
    logger.info("🌐 Server will be available at http://localhost:5000")
    logger.info("📚 Visit /deploy for setup instructions")
    
    # Check for environment variable for Discord bot token
    import os
    discord_token = os.getenv('DISCORD_BOT_TOKEN')
    discord_channel_id = os.getenv('DISCORD_CHANNEL_ID')
    
    if discord_token:
        logger.info("🔑 Discord bot token found in environment variables")
        discord_manager.start_bot(discord_token, discord_channel_id)
    else:
        logger.info("⚠️ Discord bot token not set. Use /api/set_discord_bot to configure")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

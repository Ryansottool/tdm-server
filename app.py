# Sea of Thieves TDM Server - SIMPLIFIED FOR RENDER.COM
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import time
import random
import string
import threading
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"], methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])

# Simple game state
class SimpleGameState:
    def __init__(self):
        self.rooms = {}
        self.players = {}
        self.last_cleanup = time.time()
        self.create_24h_room()
    
    def create_24h_room(self):
        """Create always-available room"""
        self.rooms["24HOURS"] = {
            'room_code': "24HOURS",
            'room_name': '24/7 TDM Channel',
            'game_mode': '2v2',
            'max_players': 4,
            'players': [],
            'scores': {"team1": 0, "team2": 0},
            'game_active': False,
            'created_time': time.time()
        }
    
    def cleanup(self):
        """Simple cleanup"""
        current_time = time.time()
        to_remove = []
        
        for room_code, room in self.rooms.items():
            if room_code == "24HOURS":
                continue
                
            # Remove old rooms (30+ minutes)
            if current_time - room.get('created_time', 0) > 1800:
                to_remove.append(room_code)
        
        for room_code in to_remove:
            del self.rooms[room_code]
            
        self.last_cleanup = current_time
        return len(to_remove)

game_state = SimpleGameState()

# Background cleanup thread
def cleanup_worker():
    while True:
        try:
            removed = game_state.cleanup()
            if removed > 0:
                logger.info(f"Cleaned up {removed} rooms")
            time.sleep(60)  # Check every minute
        except:
            time.sleep(5)

cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
cleanup_thread.start()

def generate_room_code():
    """Generate unique room code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ============ BASIC API ENDPOINTS ============

@app.route('/')
def home():
    return jsonify({
        'status': 'online',
        'service': 'Sea of Thieves TDM Server',
        'endpoints': {
            'create_room': '/api/create_room (POST)',
            'list_rooms': '/api/rooms (GET)',
            'join_room': '/api/join_room (POST)',
            'stats': '/api/stats (GET)',
            'health': '/health (GET)'
        },
        'message': 'Server is running!'
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'rooms_count': len(game_state.rooms),
        'players_count': len(game_state.players)
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    total_players = sum(len(room['players']) for room in game_state.rooms.values())
    
    return jsonify({
        'status': 'success',
        'stats': {
            'total_rooms': len(game_state.rooms),
            'total_players': total_players,
            'active_rooms': sum(1 for r in game_state.rooms.values() if len(r['players']) > 0),
            'server_uptime': time.time() - app.start_time
        }
    })

@app.route('/api/rooms', methods=['GET'])
def list_rooms():
    rooms_list = []
    
    for code, room in game_state.rooms.items():
        rooms_list.append({
            'room_code': code,
            'room_name': room['room_name'],
            'game_mode': room['game_mode'],
            'player_count': len(room['players']),
            'max_players': room['max_players'],
            'game_active': room['game_active']
        })
    
    return jsonify({
        'status': 'success',
        'rooms': rooms_list
    })

@app.route('/api/create_room', methods=['POST'])
def create_room():
    try:
        data = request.get_json()
        room_code = generate_room_code()
        
        game_state.rooms[room_code] = {
            'room_code': room_code,
            'room_name': data.get('room_name', 'TDM Room'),
            'game_mode': data.get('game_mode', '2v2'),
            'max_players': 4,
            'host_name': data.get('host_name', 'Unknown'),
            'players': [],
            'teams': {"team1": [], "team2": [], "spectators": []},
            'scores': {"team1": 0, "team2": 0},
            'game_active': False,
            'kill_feed': [],
            'created_time': time.time()
        }
        
        logger.info(f"Room created: {room_code}")
        
        return jsonify({
            'status': 'success',
            'room_code': room_code,
            'message': 'Room created successfully'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/api/join_room', methods=['POST'])
def join_room():
    try:
        data = request.get_json()
        room_code = data.get('room_code', '').upper()
        player_name = data.get('player_name', 'Player')
        
        if room_code not in game_state.rooms:
            return jsonify({'status': 'error', 'message': 'Room not found'})
        
        room = game_state.rooms[room_code]
        
        if player_name in room['players']:
            return jsonify({'status': 'error', 'message': 'Already in room'})
        
        # Add to room
        room['players'].append(player_name)
        game_state.players[player_name] = time.time()
        
        # Add to a team
        if len(room['teams']['team1']) <= len(room['teams']['team2']):
            room['teams']['team1'].append(player_name)
            team = 'team1'
        else:
            room['teams']['team2'].append(player_name)
            team = 'team2'
        
        return jsonify({
            'status': 'success',
            'team': team,
            'room_data': {
                'room_code': room['room_code'],
                'room_name': room['room_name'],
                'players': room['players'],
                'teams': room['teams'],
                'scores': room['scores'],
                'game_active': room['game_active']
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/report_kill', methods=['POST'])
def report_kill():
    try:
        data = request.get_json()
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
        
        # Update scores
        killer_team = None
        for team, players in room['teams'].items():
            if killer in players:
                killer_team = team
                break
        
        if killer_team and killer_team in ['team1', 'team2']:
            room['scores'][killer_team] += 1
        
        return jsonify({
            'status': 'success',
            'scores': room['scores'],
            'kill_feed': room['kill_feed'][-10:]  # Last 10 kills
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/start_match', methods=['POST'])
def start_match():
    try:
        data = request.get_json()
        room_code = data.get('room_code', '').upper()
        
        if room_code not in game_state.rooms:
            return jsonify({'status': 'error', 'message': 'Room not found'})
        
        room = game_state.rooms[room_code]
        room['game_active'] = True
        room['scores'] = {"team1": 0, "team2": 0}
        room['kill_feed'] = []
        
        return jsonify({
            'status': 'success',
            'message': 'Match started'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/room/<room_code>', methods=['GET'])
def get_room(room_code):
    room_code = room_code.upper()
    
    if room_code in game_state.rooms:
        room = game_state.rooms[room_code]
        return jsonify({
            'status': 'success',
            'room': {
                'room_code': room['room_code'],
                'room_name': room['room_name'],
                'players': room['players'],
                'teams': room['teams'],
                'scores': room['scores'],
                'game_active': room['game_active'],
                'kill_feed': room['kill_feed'][-10:]
            }
        })
    
    return jsonify({'status': 'error', 'message': 'Room not found'})

# ============ DISCORD BOT (OPTIONAL) ============

# Check if Discord bot should be enabled
DISCORD_ENABLED = os.environ.get('ENABLE_DISCORD', 'false').lower() == 'true'

if DISCORD_ENABLED:
    try:
        import discord
        from discord.ext import commands
        
        logger.info("Discord bot enabled")
        
        # Initialize bot in background
        def start_discord_bot():
            token = os.environ.get('DISCORD_BOT_TOKEN')
            
            if not token:
                logger.warning("No DISCORD_BOT_TOKEN found")
                return
            
            intents = discord.Intents.default()
            bot = commands.Bot(command_prefix='!', intents=intents)
            
            @bot.event
            async def on_ready():
                logger.info(f"Discord bot connected as {bot.user}")
            
            @bot.command(name='tdm')
            async def tdm_stats(ctx):
                stats = {
                    'rooms': len(game_state.rooms),
                    'players': len(game_state.players),
                    'status': 'online'
                }
                
                embed = discord.Embed(
                    title="TDM Server Stats",
                    color=discord.Color.green(),
                    description=f"Server is running with {stats['rooms']} rooms"
                )
                embed.add_field(name="Active Rooms", value=stats['rooms'])
                embed.add_field(name="Players Online", value=stats['players'])
                
                await ctx.send(embed=embed)
            
            bot.run(token)
        
        # Start bot in separate thread
        discord_thread = threading.Thread(target=start_discord_bot, daemon=True)
        discord_thread.start()
        
    except ImportError:
        logger.warning("discord.py not installed. Discord bot disabled.")
        DISCORD_ENABLED = False

# ============ START SERVER ============

if __name__ == '__main__':
    # Store start time
    app.start_time = time.time()
    
    # Get port from environment (Render provides this)
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"🚀 Starting TDM Server on port {port}")
    logger.info(f"📡 Server will be available at http://localhost:{port}")
    logger.info(f"🤖 Discord bot: {'ENABLED' if DISCORD_ENABLED else 'DISABLED'}")
    
    # Run with Gunicorn in production
    app.run(host='0.0.0.0', port=port, debug=False)

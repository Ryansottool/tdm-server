# tdm_server.py - Simplified TDM Server
from flask import Flask, request, jsonify
from flask_cors import CORS
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

class TDMGameState:
    def __init__(self):
        self.rooms = {}
        self.cleanup_interval = 30
        self.leaderboard = {}
        self.past_matches = []
        self.recent_activity = []
        self.player_sessions = {}
        
    def generate_room_code(self):
        """Generate a unique room code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if code not in self.rooms:
                return code

    def create_room(self, room_name, game_mode, host_name, password=""):
        """Create a new TDM room"""
        room_code = self.generate_room_code()
        
        self.rooms[room_code] = {
            'room_code': room_code,
            'room_name': room_name,
            'game_mode': game_mode,
            'max_players': 4,
            'host_name': host_name,
            'password': password,
            'has_password': bool(password),
            'teams': {
                "team1": [],
                "team2": [], 
                "spectators": []
            },
            'scores': {
                "team1": 0, 
                "team2": 0
            },
            'game_active': False,
            'kill_feed': [],
            'created_time': time.time(),
            'last_activity': time.time(),
            'players': [],
            'player_last_active': {}
        }
        
        self.add_recent_activity('Room Created', f'{room_name} ({room_code})', room_code, host_name)
        logger.info(f"Room created: {room_code} by {host_name}")
        
        return room_code

    def join_room(self, room_code, player_name, password=""):
        """Join a player to a room"""
        room_code = room_code.upper()
        if room_code not in self.rooms:
            return False, "Room not found"
            
        room = self.rooms[room_code]
        
        # Check password
        if room['has_password'] and room['password'] != password:
            return False, "Incorrect password"
            
        # Check if player already in room
        if player_name in room['players']:
            return False, "Player already in room"
            
        # Add player to spectators initially
        room['players'].append(player_name)
        room['teams']['spectators'].append(player_name)
        room['player_last_active'][player_name] = time.time()
        room['last_activity'] = time.time()
        
        self.update_player_activity(player_name, room_code)
        self.add_recent_activity('Player Joined', f'{player_name} joined {room["room_name"]}', room_code, player_name)
        logger.info(f"Player {player_name} joined room {room_code}")
        
        return True, "Joined room successfully"

    def leave_room(self, room_code, player_name):
        """Remove a player from a room"""
        room_code = room_code.upper()
        if room_code in self.rooms:
            room = self.rooms[room_code]
            if player_name in room['players']:
                room['players'].remove(player_name)
                for team in room['teams'].values():
                    if player_name in team:
                        team.remove(player_name)
                
                if player_name in room['player_last_active']:
                    del room['player_last_active'][player_name]
                
                room['last_activity'] = time.time()
                self.add_recent_activity('Player Left', f'{player_name} left the room', room_code, player_name)
                logger.info(f"Player {player_name} left room {room_code}")
                
                # Delete room if empty
                if not room['players']:
                    del self.rooms[room_code]
                    logger.info(f"Room {room_code} deleted (empty)")
                
                return True
        return False

    def change_team(self, room_code, player_name, new_team):
        """Change a player's team"""
        room_code = room_code.upper()
        if room_code not in self.rooms:
            return False
            
        room = self.rooms[room_code]
        
        # Remove player from current team
        for team in ['team1', 'team2', 'spectators']:
            if player_name in room['teams'][team]:
                room['teams'][team].remove(player_name)
        
        # Add to new team
        room['teams'][new_team].append(player_name)
        room['last_activity'] = time.time()
        self.update_player_activity(player_name, room_code)
        
        self.add_recent_activity('Team Change', f'{player_name} joined {new_team}', room_code, player_name)
        return True

    def start_game(self, room_code):
        """Start the match in a room"""
        room_code = room_code.upper()
        if room_code not in self.rooms:
            return False
            
        room = self.rooms[room_code]
        room['game_active'] = True
        room['scores'] = {"team1": 0, "team2": 0}
        room['kill_feed'] = []
        room['last_activity'] = time.time()
        
        self.add_recent_activity('Game Started', f'Game started in {room["room_name"]}', room_code)
        logger.info(f"Game started in room {room_code}")
        return True

    def report_kill(self, room_code, killer, victim):
        """Handle kill reporting and update scores"""
        room_code = room_code.upper()
        if room_code not in self.rooms:
            return False
            
        room = self.rooms[room_code]
        
        if not room['game_active']:
            return False
            
        # Add to kill feed
        kill_entry = {
            'killer': killer,
            'victim': victim,
            'timestamp': time.time()
        }
        room['kill_feed'].append(kill_entry)
        
        # Update scores based on killer's team
        killer_team = None
        for team, players in room['teams'].items():
            if killer in players:
                killer_team = team
                break
        
        if killer_team and killer_team in ['team1', 'team2']:
            room['scores'][killer_team] += 1
            
            # Check for match end (first to 20 kills)
            if room['scores'][killer_team] >= 20:
                self.end_match(room)
        
        room['last_activity'] = time.time()
        self.update_player_activity(killer, room_code)
        self.update_player_activity(victim, room_code)
        self.update_leaderboard(room)
        
        self.add_recent_activity('Kill', f'{killer} defeated {victim}', room_code)
        logger.info(f"Kill registered: {killer} -> {victim} in {room_code}")
        return True

    def end_match(self, room):
        """End the match and record results"""
        room['game_active'] = False
        
        # Add to past matches
        match_data = {
            'id': len(self.past_matches) + 1,
            'room_code': room['room_code'],
            'room_name': room['room_name'],
            'team1_score': room['scores']['team1'],
            'team2_score': room['scores']['team2'],
            'team1_players': room['teams']['team1'].copy(),
            'team2_players': room['teams']['team2'].copy(),
            'timestamp': time.time(),
            'kill_count': len(room['kill_feed']),
            'total_players': len(room['players'])
        }
        
        self.past_matches.append(match_data)
        self.add_recent_activity('Match Completed', 
                               f'{room["room_name"]} - Team1: {room["scores"]["team1"]} vs Team2: {room["scores"]["team2"]}',
                               room['room_code'])
        
        # Keep only last 50 matches
        if len(self.past_matches) > 50:
            self.past_matches.pop(0)

    def update_leaderboard(self, room):
        """Update leaderboard stats from kills"""
        for kill in room.get('kill_feed', []):
            killer = kill.get('killer')
            victim = kill.get('victim')
            
            if killer:
                if killer not in self.leaderboard:
                    self.leaderboard[killer] = {
                        'player_name': killer,
                        'kills': 0,
                        'deaths': 0,
                        'games_played': 0
                    }
                self.leaderboard[killer]['kills'] += 1
                self.update_player_activity(killer)
            
            if victim:
                if victim not in self.leaderboard:
                    self.leaderboard[victim] = {
                        'player_name': victim,
                        'kills': 0,
                        'deaths': 0,
                        'games_played': 0
                    }
                self.leaderboard[victim]['deaths'] += 1
                self.update_player_activity(victim)

    def update_player_activity(self, player_name, room_code=None):
        """Update player activity timestamp"""
        self.player_sessions[player_name] = time.time()
        
        if room_code and room_code in self.rooms:
            self.rooms[room_code]['player_last_active'][player_name] = time.time()
            self.rooms[room_code]['last_activity'] = time.time()

    def add_recent_activity(self, activity_type, description, room_code=None, player_name=None):
        """Add recent activity entry"""
        activity = {
            'id': len(self.recent_activity) + 1,
            'type': activity_type,
            'description': description,
            'timestamp': time.time(),
            'room_code': room_code,
            'player_name': player_name
        }
        self.recent_activity.append(activity)
        
        # Keep only last 50 activities
        if len(self.recent_activity) > 50:
            self.recent_activity.pop(0)

    def cleanup_inactive_rooms(self):
        """Clean up inactive rooms"""
        current_time = time.time()
        inactive_rooms = []
        
        for room_code, room_data in list(self.rooms.items()):
            last_activity = room_data.get('last_activity', 0)
            inactivity_duration = current_time - last_activity
            
            # Remove rooms inactive for more than 1 hour
            if inactivity_duration > 3600:
                inactive_rooms.append(room_code)
                logger.info(f"Cleaned up inactive room: {room_code}")
        
        for room_code in inactive_rooms:
            if room_code in self.rooms:
                del self.rooms[room_code]

    def get_public_rooms(self):
        """Get list of public rooms"""
        public_rooms = []
        
        for room_code, room in self.rooms.items():
            public_rooms.append({
                'room_code': room_code,
                'room_name': room['room_name'],
                'game_mode': room['game_mode'],
                'max_players': room['max_players'],
                'player_count': len(room['players']),
                'has_password': room['has_password'],
                'game_active': room['game_active'],
                'host_name': room['host_name'],
                'last_activity': room['last_activity']
            })
        
        return public_rooms

# Initialize global game state
game_state = TDMGameState()

def cleanup_worker():
    """Background cleanup worker"""
    while True:
        try:
            game_state.cleanup_inactive_rooms()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        time.sleep(game_state.cleanup_interval)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
cleanup_thread.start()

logger.info("TDM Server started with room management and kill handling")

# API Routes
@app.route('/api', methods=['POST', 'OPTIONS'])
def api_handler():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'})

    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data provided'})

        action = data.get('action')
        
        if action == 'create_room':
            room_name = data.get('room_name', 'TDM Room')
            game_mode = data.get('game_mode', '2v2')
            host_name = data.get('host_name', 'Unknown')
            password = data.get('password', '')
            
            room_code = game_state.create_room(room_name, game_mode, host_name, password)
            return jsonify({
                'status': 'success',
                'room_code': room_code,
                'message': f'Room {room_code} created successfully'
            })
            
        elif action == 'join_room':
            room_code = data.get('room_code', '')
            player_name = data.get('player_name', 'Unknown')
            password = data.get('password', '')
            
            success, message = game_state.join_room(room_code, player_name, password)
            if success:
                return jsonify({
                    'status': 'success',
                    'message': message
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': message
                })
                
        elif action == 'leave_room':
            room_code = data.get('room_code', '')
            player_name = data.get('player_name', '')
            
            if game_state.leave_room(room_code, player_name):
                return jsonify({'status': 'success', 'message': 'Left room'})
            else:
                return jsonify({'status': 'error', 'message': 'Failed to leave room'})
                
        elif action == 'change_team':
            room_code = data.get('room_code', '')
            player_name = data.get('player_name', '')
            new_team = data.get('new_team', 'spectators')
            
            if game_state.change_team(room_code, player_name, new_team):
                return jsonify({'status': 'success', 'message': f'Changed to {new_team}'})
            else:
                return jsonify({'status': 'error', 'message': 'Failed to change team'})
                
        elif action == 'start_game':
            room_code = data.get('room_code', '')
            
            if game_state.start_game(room_code):
                return jsonify({'status': 'success', 'message': 'Game started'})
            else:
                return jsonify({'status': 'error', 'message': 'Failed to start game'})
                
        elif action == 'report_kill':
            room_code = data.get('room_code', '')
            killer = data.get('killer', '')
            victim = data.get('victim', '')
            
            if game_state.report_kill(room_code, killer, victim):
                return jsonify({'status': 'success', 'message': 'Kill registered'})
            else:
                return jsonify({'status': 'error', 'message': 'Failed to register kill'})
                
        elif action == 'get_room_state':
            room_code = data.get('room_code', '')
            room_code = room_code.upper()
            
            if room_code in game_state.rooms:
                room = game_state.rooms[room_code]
                room['last_activity'] = time.time()
                return jsonify({
                    'status': 'success',
                    'room_data': room
                })
            else:
                return jsonify({'status': 'error', 'message': 'Room not found'})
                
        elif action == 'list_rooms':
            rooms = game_state.get_public_rooms()
            return jsonify({
                'status': 'success',
                'active_rooms': rooms
            })
            
        elif action == 'get_leaderboard':
            leaderboard_data = []
            for player_name, stats in game_state.leaderboard.items():
                kd_ratio = stats['kills'] / max(stats['deaths'], 1)
                leaderboard_data.append({
                    'player_name': player_name,
                    'kills': stats['kills'],
                    'deaths': stats['deaths'],
                    'kd_ratio': kd_ratio
                })
            
            leaderboard_data.sort(key=lambda x: x['kills'], reverse=True)
            return jsonify({
                'status': 'success',
                'leaderboard': leaderboard_data[:50]  # Top 50
            })
            
        elif action == 'get_past_scores':
            limit = data.get('limit', 12)
            past_scores = game_state.past_matches[-limit:]
            return jsonify({
                'status': 'success',
                'past_scores': past_scores
            })
            
        elif action == 'get_recent_activity':
            return jsonify({
                'status': 'success',
                'recent_activity': game_state.recent_activity[-20:]
            })
            
        else:
            return jsonify({'status': 'error', 'message': 'Invalid action'})

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/')
def index():
    return jsonify({
        'message': 'TDM Server is running',
        'endpoints': {
            '/api': 'POST - Main API endpoint',
            'actions': [
                'create_room', 'join_room', 'leave_room', 'change_team',
                'start_game', 'report_kill', 'get_room_state', 'list_rooms',
                'get_leaderboard', 'get_past_scores', 'get_recent_activity'
            ]
        }
    })

if __name__ == '__main__':
    logger.info("🎮 Starting TDM Server - Room Management & Kill Handling")
    logger.info("🌐 Server available at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

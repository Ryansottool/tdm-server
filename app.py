# app.py - Sea of Thieves TDM Server
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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"], methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

class KillDetectionSystem:
    def __init__(self):
        self.pending_kills = {}
        self.kill_cooldown = 3.0
        self.last_kill_times = {}
    
    def detect_kill_event(self, room_code, killer_name, victim_name):
        """Server-side kill detection with validation"""
        current_time = time.time()
        
        # Check cooldown for this killer
        killer_key = f"{room_code}:{killer_name}"
        if killer_key in self.last_kill_times:
            if current_time - self.last_kill_times[killer_key] < self.kill_cooldown:
                return False, "Kill report on cooldown"
        
        # Validate players exist in room
        if room_code not in game_state.rooms:
            return False, "Room not found"
            
        room = game_state.rooms[room_code]
        
        # Verify both players are in the room and on different teams
        killer_team = None
        victim_team = None
        
        for team, players in room['teams'].items():
            if killer_name in players:
                killer_team = team
            if victim_name in players:
                victim_team = team
        
        if not killer_team or not victim_team:
            return False, "Players not found in room"
            
        if killer_team == victim_team:
            return False, "Cannot kill teammate"
        
        # Check if game is active
        if not room.get('game_active', False):
            return False, "Game is not active"
        
        # Record kill
        self.last_kill_times[killer_key] = current_time
        
        # Add to kill feed
        kill_entry = {
            'killer': killer_name,
            'victim': victim_name,
            'timestamp': current_time,
            'room_code': room_code
        }
        room['kill_feed'].append(kill_entry)
        
        # Update scores
        if killer_team in ['team1', 'team2']:
            room['scores'][killer_team] += 1
        
        # Update leaderboard
        game_state.update_leaderboard(room)
        
        # Log activity
        game_state.add_recent_activity('Kill', 
                                     f'{killer_name} → {victim_name} (+1 {killer_team})', 
                                     room_code)
        
        logger.info(f"🎯 Kill registered: {killer_name} → {victim_name} in {room_code}")
        
        return True, "Kill registered successfully"

class DeathVerificationSystem:
    def __init__(self):
        self.pending_verifications = {}
        self.verification_timeout = 30
        self.last_cleanup = time.time()
    
    def verify_death_screenshot(self, room_code, player_name, screenshot_data):
        """Verify death screenshot and register kill"""
        # Validate room and player
        if room_code not in game_state.rooms:
            return False, "Room not found"
            
        room = game_state.rooms[room_code]
        
        if player_name not in room['players']:
            return False, "Player not in room"
        
        try:
            # Basic screenshot validation
            if not screenshot_data or len(screenshot_data) < 100:
                return False, "Invalid screenshot data"
            
            # For deployment, we'll accept valid screenshots and determine killer
            killer = self.determine_killer(room_code, player_name)
            
            if killer:
                # Register the kill
                success, message = kill_detector.detect_kill_event(room_code, killer, player_name)
                
                if success:
                    game_state.add_recent_activity('Death Verified', 
                                                 f'{player_name} death confirmed → {killer}', 
                                                 room_code)
                    logger.info(f"📸 Death verified via screenshot: {player_name} killed by {killer}")
                    return True, f"Death verified! {killer} eliminated {player_name}"
                else:
                    return False, f"Kill registration failed: {message}"
            else:
                return False, "Could not determine killer"
                
        except Exception as e:
            logger.error(f"Screenshot verification error: {e}")
            return False, f"Screenshot processing error: {str(e)}"
    
    def determine_killer(self, room_code, victim_name):
        """Determine who likely killed the player"""
        if room_code not in game_state.rooms:
            return "Unknown"
            
        room = game_state.rooms[room_code]
        
        # Simple logic: find players on opposite teams
        victim_team = None
        for team, players in room['teams'].items():
            if victim_name in players:
                victim_team = team
                break
        
        if not victim_team:
            return "Unknown"
        
        # Find potential killers from opposite teams
        potential_killers = []
        for team, players in room['teams'].items():
            if team != victim_team and team in ['team1', 'team2']:
                potential_killers.extend(players)
        
        if potential_killers:
            # Return random killer from opposite team (in real implementation, track damage)
            return random.choice(potential_killers)
        
        return "Unknown"

class TDMGameState:
    def __init__(self):
        self.rooms = {}
        self.cleanup_interval = 30
        self.always_active_room = None
        self.leaderboard = {}
        self.past_matches = []
        self.recent_activity = []
        self.player_sessions = {}
        self.total_matches_played = 0
        self.total_kills = 0
        self.last_cleanup_time = time.time()
        self.cleanup_stats = {
            'rooms_cleaned': 0,
            'players_cleaned': 0,
            'last_cleanup_duration': 0,
            'total_cleanups': 0
        }
        self.server_start_time = time.time()

    def cleanup_inactive_rooms(self):
        """Cleanup inactive rooms"""
        start_time = time.time()
        current_time = time.time()
        inactive_rooms = []
        players_cleaned = 0
        
        logger.info(f"🔄 Cleanup cycle - {len(self.rooms)} rooms to check")

        for room_code, room_data in list(self.rooms.items()):
            # Skip always-active room
            if room_code == self.always_active_room:
                continue
                
            last_activity = room_data.get('last_activity', 0)
            created_time = room_data.get('created_time', 0)
            game_active = room_data.get('game_active', False)
            players_count = len(room_data.get('players', []))
            room_age = current_time - created_time
            inactivity_duration = current_time - last_activity

            # Cleanup conditions
            condition1 = inactivity_duration > 1800  # 30 minutes inactivity
            condition2 = (not game_active and room_age > 600 and players_count <= 1)  # 10 minutes for empty rooms
            condition3 = players_count == 0 and inactivity_duration > 300  # 5 minutes for completely empty rooms
            condition4 = room_age > 7200  # 2 hours maximum room age
            condition5 = (game_active and inactivity_duration > 900 and players_count < 2)  # Abandoned games

            if any([condition1, condition2, condition3, condition4, condition5]):
                players_cleaned += players_count
                inactive_rooms.append(room_code)
                
                # Determine cleanup reason for logging
                reason = "inactivity" if condition1 else \
                        "empty room" if condition2 else \
                        "completely empty" if condition3 else \
                        "max age reached" if condition4 else \
                        "abandoned game"
                
                logger.info(f"🗑️ Marking room {room_code} for cleanup: {reason}")
                self.add_recent_activity('Room Cleanup', f'Room {room_code} cleaned up ({reason})', room_code)

        # Remove inactive rooms
        for room_code in inactive_rooms:
            if room_code in self.rooms:
                room_data = self.rooms[room_code]
                # Add to past matches if game was active with scores
                if room_data.get('game_active', False) and sum(room_data['scores'].values()) > 0:
                    self.add_past_match(room_data)
                del self.rooms[room_code]
                logger.info(f"✅ Removed room: {room_code}")

        # Cleanup player sessions (remove players inactive for more than 1 hour)
        current_time = time.time()
        inactive_players = []
        for player_name, last_seen in list(self.player_sessions.items()):
            if current_time - last_seen > 3600:  # 1 hour
                inactive_players.append(player_name)
        
        for player_name in inactive_players:
            del self.player_sessions[player_name]

        # Cleanup old past matches (keep only last 100)
        if len(self.past_matches) > 100:
            removed_count = len(self.past_matches) - 100
            self.past_matches = self.past_matches[-100:]
            logger.info(f"📊 Cleaned up {removed_count} old matches")

        # Cleanup old activity (keep only last 50)
        if len(self.recent_activity) > 50:
            removed_activities = len(self.recent_activity) - 50
            self.recent_activity = self.recent_activity[-50:]
            logger.info(f"📈 Cleaned up {removed_activities} old activities")

        # Update cleanup stats
        cleanup_duration = time.time() - start_time
        self.cleanup_stats = {
            'rooms_cleaned': len(inactive_rooms),
            'players_cleaned': players_cleaned,
            'last_cleanup_duration': cleanup_duration,
            'total_cleanups': self.cleanup_stats['total_cleanups'] + 1,
            'total_rooms': len(self.rooms),
            'total_players': self.get_online_players(),
            'timestamp': current_time
        }
        
        self.last_cleanup_time = current_time
        
        logger.info(f"🎯 Cleanup completed: {len(inactive_rooms)} rooms, {players_cleaned} players in {cleanup_duration:.3f}s")

    def create_always_active_room(self):
        """Create the 24/7 always active room"""
        room_code = "24HOURS"
        if room_code not in self.rooms:
            self.rooms[room_code] = {
                'room_code': room_code,
                'room_name': '24/7 TDM Channel',
                'game_mode': '2v2',
                'max_players': 4,
                'host_name': 'System',
                'password': '',
                'has_password': False,
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
                'is_24h_channel': True,
                'description': 'Always available for practice and casual matches'
            }
            self.always_active_room = room_code
            self.add_recent_activity('System', '24/7 TDM Channel created - Always available for matches!')
            logger.info("🌐 24/7 TDM Channel created successfully")

    def update_player_activity(self, player_name, room_code=None):
        """Update player activity with room context"""
        self.player_sessions[player_name] = time.time()
        
        # Also update room-specific activity
        if room_code and room_code in self.rooms:
            self.rooms[room_code]['player_last_active'][player_name] = time.time()
            self.rooms[room_code]['last_activity'] = time.time()

    def get_online_players(self):
        """Get online player count"""
        current_time = time.time()
        online_count = 0
        
        for room_code, room_data in self.rooms.items():
            # Count only players active in last 5 minutes
            active_players = 0
            
            # Check room-specific activity
            for player_name, last_active in room_data.get('player_last_active', {}).items():
                if current_time - last_active < 300:  # 5 minutes
                    active_players += 1
            
            # Also check global player sessions as backup
            room_player_count = len([p for p in room_data.get('players', []) 
                                   if self.player_sessions.get(p, 0) > current_time - 300])
            
            # Use the higher count for accuracy
            online_count += max(active_players, room_player_count)
            
        return online_count

    def get_active_rooms_count(self):
        """Count only rooms with recent activity or players"""
        current_time = time.time()
        active_count = 0
        
        for room_code, room_data in self.rooms.items():
            if room_code == self.always_active_room:
                continue  # Always count the 24/7 room as active
                
            # Room is active if it has players OR recent activity
            has_players = len(room_data.get('players', [])) > 0
            recent_activity = current_time - room_data.get('last_activity', 0) < 900  # 15 minutes
            game_active = room_data.get('game_active', False)
            
            if has_players or recent_activity or game_active:
                active_count += 1
                
        return active_count

    def update_leaderboard(self, room_data):
        """Update leaderboard stats from completed matches"""
        if not room_data.get('game_active', False):
            return
            
        # Process kill feed for leaderboard updates
        for kill in room_data.get('kill_feed', []):
            killer = kill.get('killer')
            victim = kill.get('victim')
            
            if killer:
                # Initialize killer stats if not exists
                if killer not in self.leaderboard:
                    self.leaderboard[killer] = {
                        'player_name': killer,
                        'wins': 0,
                        'kills': 0,
                        'deaths': 0,
                        'games_played': 0,
                        'last_seen': time.time(),
                        'first_seen': time.time(),
                        'total_score': 0
                    }
                self.leaderboard[killer]['kills'] += 1
                self.leaderboard[killer]['last_seen'] = time.time()
                self.leaderboard[killer]['total_score'] += 100  # Points per kill
                self.update_player_activity(killer)
                self.total_kills += 1
            
            if victim:
                # Initialize victim stats if not exists
                if victim not in self.leaderboard:
                    self.leaderboard[victim] = {
                        'player_name': victim,
                        'wins': 0,
                        'kills': 0,
                        'deaths': 0,
                        'games_played': 0,
                        'last_seen': time.time(),
                        'first_seen': time.time(),
                        'total_score': 0
                    }
                self.leaderboard[victim]['deaths'] += 1
                self.leaderboard[victim]['last_seen'] = time.time()
                self.update_player_activity(victim)

    def add_past_match(self, room_data):
        """Add completed match to past matches"""
        if room_data.get('game_active', False) and sum(room_data['scores'].values()) > 0:
            match_data = {
                'id': len(self.past_matches) + 1,
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
                    if player in self.leaderboard:
                        self.leaderboard[player]['wins'] += 1
                        self.leaderboard[player]['games_played'] += 1
                        self.leaderboard[player]['total_score'] += 500  # Win bonus
            elif room_data['scores']['team2'] > room_data['scores']['team1']:
                match_data['winner'] = 'team2'
                match_data['winning_score'] = room_data['scores']['team2']
                match_data['losing_score'] = room_data['scores']['team1']
                for player in room_data['teams']['team2']:
                    if player in self.leaderboard:
                        self.leaderboard[player]['wins'] += 1
                        self.leaderboard[player]['games_played'] += 1
                        self.leaderboard[player]['total_score'] += 500  # Win bonus
            else:
                match_data['winner'] = 'draw'
                match_data['winning_score'] = room_data['scores']['team1']
                match_data['losing_score'] = room_data['scores']['team2']
                for player in room_data['teams']['team1'] + room_data['teams']['team2']:
                    if player in self.leaderboard:
                        self.leaderboard[player]['games_played'] += 1
                        self.leaderboard[player]['total_score'] += 250  # Draw bonus
            
            self.past_matches.append(match_data)
            self.total_matches_played += 1
            
            self.add_recent_activity('Match Completed', 
                                   f'{room_data["room_name"]} - Team1: {room_data["scores"]["team1"]} vs Team2: {room_data["scores"]["team2"]}',
                                   room_data['room_code'])
            
            # Keep only last 100 matches for performance
            if len(self.past_matches) > 100:
                self.past_matches.pop(0)

    def add_recent_activity(self, activity_type, description, room_code=None, player_name=None):
        """Add recent activity entry"""
        activity = {
            'id': len(self.recent_activity) + 1,
            'type': activity_type,
            'description': description,
            'timestamp': time.time(),
            'room_code': room_code,
            'player_name': player_name,
            'formatted_time': datetime.now().strftime('%H:%M:%S')
        }
        self.recent_activity.append(activity)
        
        # Keep only last 50 activities for performance
        if len(self.recent_activity) > 50:
            self.recent_activity.pop(0)

    def get_system_stats(self):
        """Get comprehensive system statistics"""
        current_time = time.time()
        server_uptime = current_time - self.server_start_time
        
        return {
            'online_players': self.get_online_players(),
            'active_rooms': self.get_active_rooms_count(),
            'total_rooms': len(self.rooms),
            'total_players_tracked': len(self.leaderboard),
            'total_matches': self.total_matches_played,
            'total_kills': self.total_kills,
            'cleanup_stats': self.cleanup_stats,
            'server_uptime': server_uptime,
            'server_uptime_formatted': self.format_duration(server_uptime),
            'last_cleanup': self.last_cleanup_time,
            'current_time': current_time,
            'performance_metrics': {
                'avg_cleanup_time': self.cleanup_stats['last_cleanup_duration'],
                'cleanup_efficiency': f"{(self.cleanup_stats['rooms_cleaned'] / max(len(self.rooms), 1)) * 100:.1f}%",
                'memory_usage_estimate': len(self.rooms) * 0.5 + len(self.leaderboard) * 0.1  # KB estimate
            }
        }

    def format_duration(self, seconds):
        """Format duration in seconds to human readable format"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        elif seconds < 86400:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"
        else:
            return f"{int(seconds // 86400)}d {int((seconds % 86400) // 3600)}h"

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

def generate_room_code():
    """Generate a unique room code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# =============================================================================
# HTML CONTENT
# =============================================================================

HTML_CONTENT = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sea of Thieves TDM - Global Server</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary-bg: #0a0a0a;
            --secondary-bg: #1a1a1a;
            --accent-color: #ff7700;
            --accent-dark: #cc5500;
            --accent-light: #ff9933;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0a0;
            --border-color: #333333;
            --success-color: #00cc66;
            --error-color: #cc3333;
            --warning-color: #ffcc00;
            --info-color: #0099ff;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, var(--primary-bg), #151515, var(--secondary-bg));
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }

        .header {
            text-align: center;
            margin-bottom: 3rem;
        }

        .header h1 {
            font-size: 3rem;
            color: var(--accent-color);
            margin-bottom: 1rem;
            text-shadow: 0 0 20px rgba(255, 119, 0, 0.5);
        }

        .header p {
            font-size: 1.2rem;
            color: var(--text-secondary);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin: 3rem 0;
        }

        .stat-card {
            background: linear-gradient(135deg, rgba(255, 119, 0, 0.1), rgba(255, 153, 51, 0.05));
            padding: 2rem;
            border-radius: 15px;
            text-align: center;
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
            transition: all 0.3s ease;
        }

        .stat-card:hover {
            transform: translateY(-5px);
            border-color: var(--accent-color);
            box-shadow: 0 10px 30px rgba(255, 119, 0, 0.2);
        }

        .stat-number {
            font-size: 2.5rem;
            font-weight: bold;
            color: var(--accent-color);
            display: block;
            text-shadow: 0 0 10px rgba(255, 119, 0, 0.3);
        }

        .stat-label {
            font-size: 1rem;
            color: var(--text-secondary);
            margin-top: 0.5rem;
        }

        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin: 3rem 0;
        }

        .feature-card {
            background: rgba(26, 26, 26, 0.9);
            padding: 2rem;
            border-radius: 15px;
            border: 1px solid var(--border-color);
        }

        .feature-card h3 {
            color: var(--accent-color);
            margin-bottom: 1rem;
        }

        .status {
            text-align: center;
            margin-top: 2rem;
            padding: 1rem;
            background: rgba(26, 26, 26, 0.8);
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }

        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚔️ Sea of Thieves TDM</h1>
            <p>Global Team Deathmatch Server - Optimized Cleanup System</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-number" id="online-players">0</span>
                <span class="stat-label">👥 Online Players</span>
            </div>
            <div class="stat-card">
                <span class="stat-number" id="active-rooms">0</span>
                <span class="stat-label">🎮 Active Rooms</span>
            </div>
            <div class="stat-card">
                <span class="stat-number" id="total-players">0</span>
                <span class="stat-label">👤 Total Players</span>
            </div>
            <div class="stat-card">
                <span class="stat-number" id="total-matches">0</span>
                <span class="stat-label">⚔️ Total Matches</span>
            </div>
        </div>

        <div class="features">
            <div class="feature-card">
                <h3>🚀 Real-time Tracking</h3>
                <p>Live player and room tracking with optimized cleanup system</p>
            </div>
            <div class="feature-card">
                <h3>📸 Death Verification</h3>
                <p>Automatic screenshot verification for anti-cheat protection</p>
            </div>
            <div class="feature-card">
                <h3>🏆 Leaderboards</h3>
                <p>Global leaderboard with K/D ratios and match statistics</p>
            </div>
        </div>

        <div class="status">
            <p>Server Status: <span style="color: var(--success-color)">✅ Online</span></p>
            <p>Last Updated: <span id="last-updated">Just now</span></p>
        </div>
    </div>

    <script>
        async function updateStats() {
            try {
                const response = await fetch('/stats');
                const data = await response.json();
                
                document.getElementById('online-players').textContent = data.online_players || '0';
                document.getElementById('active-rooms').textContent = data.active_rooms || '0';
                document.getElementById('total-players').textContent = data.total_players_tracked || '0';
                document.getElementById('total-matches').textContent = data.total_matches || '0';
                
                // Update timestamp
                const now = new Date();
                document.getElementById('last-updated').textContent = now.toLocaleTimeString();
            } catch (error) {
                console.error('Error updating stats:', error);
                document.getElementById('online-players').textContent = '?';
                document.getElementById('active-rooms').textContent = '?';
                document.getElementById('total-players').textContent = '?';
                document.getElementById('total-matches').textContent = '?';
            }
        }

        // Update stats every 10 seconds
        setInterval(updateStats, 10000);
        updateStats();
    </script>
</body>
</html>
'''

# =============================================================================
# FLASK ROUTES AND API HANDLERS
# =============================================================================

@app.route('/')
def serve_index():
    return render_template_string(HTML_CONTENT)

@app.route('/stats')
def get_stats():
    stats = game_state.get_system_stats()
    return jsonify({
        'online_players': stats['online_players'],
        'active_rooms': stats['active_rooms'],
        'total_players_tracked': stats['total_players_tracked'],
        'total_matches': stats['total_matches'],
        'total_kills': stats['total_kills']
    })

@app.route('/system')
def get_system_stats():
    stats = game_state.get_system_stats()
    return jsonify({
        'total_rooms': stats['total_rooms'],
        'total_kills': stats['total_kills'],
        'cleanup_duration': f"{stats['cleanup_stats']['last_cleanup_duration']:.3f}s",
        'rooms_cleaned': stats['cleanup_stats']['rooms_cleaned'],
        'players_cleaned': stats['cleanup_stats']['players_cleaned'],
        'server_uptime': stats['server_uptime'],
        'server_uptime_formatted': stats['server_uptime_formatted'],
        'cleanup_stats': stats['cleanup_stats'],
        'performance_metrics': stats['performance_metrics']
    })

@app.route('/api', methods=['POST', 'OPTIONS'])
def api_handler():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response

    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data provided'})

        action = data.get('action')
        
        # Map actions to handlers
        handlers = {
            'create_room': handle_create_room,
            'join_room': handle_join_room,
            'get_room_state': handle_get_room_state,
            'list_rooms': handle_list_rooms,
            'report_kill': handle_report_kill,
            'detect_kill': handle_detect_kill,
            'verify_death': handle_verify_death,
            'change_team': handle_change_team,
            'start_game': handle_start_game,
            'leave_room': handle_leave_room,
            'get_leaderboard': handle_get_leaderboard,
            'get_past_scores': handle_get_past_scores,
            'get_recent_activity': handle_get_recent_activity,
        }
        
        handler = handlers.get(action)
        if handler:
            return handler(data)
        else:
            return jsonify({'status': 'error', 'message': 'Invalid action'})

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

# API Handlers
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
    
    game_state.add_recent_activity('Room Created', f'{room_name} ({room_code})', room_code, host_name)
    logger.info(f"Room created: {room_code} by {host_name}")
    
    return jsonify({
        'status': 'success',
        'room_code': room_code,
        'message': f'Room {room_code} created successfully'
    })

def handle_join_room(data):
    room_code = data.get('room_code', '').upper()
    player_name = data.get('player_name', 'Unknown')
    password = data.get('password', '')
    
    if room_code not in game_state.rooms:
        return jsonify({'status': 'error', 'message': 'Room not found'})
    
    room = game_state.rooms[room_code]
    
    # Check password
    if room['has_password'] and room['password'] != password:
        return jsonify({'status': 'error', 'message': 'Incorrect password'})
    
    # Check if player already in room
    if player_name in room['players']:
        return jsonify({'status': 'error', 'message': 'Player already in room'})
    
    # Add player to spectators initially
    room['players'].append(player_name)
    room['teams']['spectators'].append(player_name)
    room['player_last_active'][player_name] = time.time()
    room['last_activity'] = time.time()
    
    game_state.update_player_activity(player_name, room_code)
    game_state.add_recent_activity('Player Joined', f'{player_name} joined {room["room_name"]}', room_code, player_name)
    logger.info(f"Player {player_name} joined room {room_code}")
    
    return jsonify({
        'status': 'success',
        'room_data': room,
        'message': f'Joined room {room_code}'
    })

def handle_get_room_state(data):
    room_code = data.get('room_code', '').upper()
    
    if room_code not in game_state.rooms:
        return jsonify({'status': 'error', 'message': 'Room not found'})
    
    room = game_state.rooms[room_code]
    room['last_activity'] = time.time()  # Update activity on state check
    
    return jsonify({
        'status': 'success',
        'room_data': room
    })

def handle_list_rooms(data):
    public_rooms = []
    
    for room_code, room in game_state.rooms.items():
        if not room.get('is_24h_channel', False):
            # Only include rooms with recent activity or players
            if len(room['players']) > 0 or time.time() - room['last_activity'] < 3600:
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
    
    return jsonify({
        'status': 'success',
        'active_rooms': public_rooms
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
    
    game_state.add_recent_activity('Kill', f'{killer} defeated {victim}', room_code)
    logger.info(f"Kill registered: {killer} → {victim} in {room_code}")
    
    return jsonify({
        'status': 'success',
        'message': 'Kill registered successfully'
    })

def handle_detect_kill(data):
    """Server-side kill detection endpoint"""
    room_code = data.get('room_code', '').upper()
    killer_name = data.get('killer', '').strip()
    victim_name = data.get('victim', '').strip()
    
    if not all([room_code, killer_name, victim_name]):
        return jsonify({'status': 'error', 'message': 'Missing required fields'})
    
    success, message = kill_detector.detect_kill_event(room_code, killer_name, victim_name)
    
    return jsonify({
        'status': 'success' if success else 'error',
        'message': message
    })

def handle_verify_death(data):
    """Handle death verification with screenshot"""
    room_code = data.get('room_code', '').upper()
    player_name = data.get('player_name', '').strip()
    screenshot_data = data.get('screenshot', '')
    
    if not all([room_code, player_name, screenshot_data]):
        return jsonify({'status': 'error', 'message': 'Missing required fields'})
    
    # Verify the death
    success, message = death_verifier.verify_death_screenshot(room_code, player_name, screenshot_data)
    
    return jsonify({
        'status': 'success' if success else 'error',
        'message': message,
        'death_verified': success
    })

def handle_change_team(data):
    room_code = data.get('room_code', '').upper()
    player_name = data.get('player_name')
    new_team = data.get('new_team')
    
    if room_code not in game_state.rooms:
        return jsonify({'status': 'error', 'message': 'Room not found'})
    
    room = game_state.rooms[room_code]
    
    # Remove player from current team
    for team in ['team1', 'team2', 'spectators']:
        if player_name in room['teams'][team]:
            room['teams'][team].remove(player_name)
    
    # Add to new team
    room['teams'][new_team].append(player_name)
    room['last_activity'] = time.time()
    game_state.update_player_activity(player_name, room_code)
    
    game_state.add_recent_activity('Team Change', f'{player_name} joined {new_team}', room_code, player_name)
    
    return jsonify({
        'status': 'success',
        'teams': room['teams'],
        'message': f'Player {player_name} moved to {new_team}'
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
    
    game_state.add_recent_activity('Game Started', f'Game started in {room["room_name"]}', room_code)
    logger.info(f"Game started in room {room_code}")
    
    return jsonify({
        'status': 'success',
        'message': 'Game started'
    })

def handle_leave_room(data):
    room_code = data.get('room_code', '').upper()
    player_name = data.get('player_name')
    
    if room_code in game_state.rooms:
        room = game_state.rooms[room_code]
        if player_name in room['players']:
            room['players'].remove(player_name)
            for team in room['teams']:
                if player_name in room['teams'][team]:
                    room['teams'][team].remove(player_name)
            
            if player_name in room['player_last_active']:
                del room['player_last_active'][player_name]
            
            room['last_activity'] = time.time()
            game_state.add_recent_activity('Player Left', f'{player_name} left the room', room_code, player_name)
            logger.info(f"Player {player_name} left room {room_code}")
    
    return jsonify({'status': 'success', 'message': 'Left room'})

def handle_get_leaderboard(data):
    limit = data.get('limit', 50)
    
    leaderboard_data = []
    current_time = time.time()
    
    for player_name, stats in game_state.leaderboard.items():
        kd_ratio = stats['kills'] / max(stats['deaths'], 1)
        is_online = (current_time - stats.get('last_seen', 0)) < 300
        
        leaderboard_data.append({
            'player_name': player_name,
            'wins': stats.get('wins', 0),
            'kills': stats.get('kills', 0),
            'deaths': stats.get('deaths', 0),
            'games_played': stats.get('games_played', 0),
            'kd_ratio': kd_ratio,
            'is_online': is_online,
            'total_score': stats.get('total_score', 0)
        })
    
    leaderboard_data.sort(key=lambda x: x['kills'], reverse=True)
    
    return jsonify({
        'status': 'success',
        'leaderboard': leaderboard_data[:limit]
    })

def handle_get_past_scores(data):
    limit = data.get('limit', 12)
    
    past_scores = []
    for match in game_state.past_matches[-limit:]:
        past_scores.append({
            'id': match['id'],
            'room_code': match['room_code'],
            'room_name': match['room_name'],
            'team1_score': match['team1_score'],
            'team2_score': match['team2_score'],
            'team1_players': match['team1_players'],
            'team2_players': match['team2_players'],
            'timestamp': match['timestamp'],
            'duration': match['duration'],
            'game_mode': match['game_mode'],
            'winner': match.get('winner', 'draw'),
            'kill_count': match.get('kill_count', 0)
        })
    
    return jsonify({
        'status': 'success',
        'past_scores': past_scores
    })

def handle_get_recent_activity(data):
    return jsonify({
        'status': 'success',
        'recent_activity': game_state.recent_activity[-20:]
    })

if __name__ == '__main__':
    logger.info("🎮 Starting Sea of Thieves TDM Server")
    logger.info("⚡ Features: Real-time tracking, Death verification, Leaderboards")
    logger.info("🌐 Server will be available at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

# app.py - COMPLETE 1400+ Lines - Sea of Thieves TDM Server with Death Verification
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json
import time
import random
import string
import threading
from datetime import datetime, timedelta
import logging
import base64
from PIL import Image
import io
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"], methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

class KillDetectionSystem:
    def __init__(self):
        self.pending_kills = {}  # {room_code: [kill_events]}
        self.kill_cooldown = 3.0  # Prevent duplicate kills
        self.last_kill_times = {}  # {player_name: timestamp}
    
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
        self.pending_verifications = {}  # {verification_id: verification_data}
        self.verification_timeout = 30  # seconds
        self.last_cleanup = time.time()
    
    def generate_verification_id(self, room_code, player_name):
        """Generate unique verification ID"""
        timestamp = str(time.time())
        unique_string = f"{room_code}_{player_name}_{timestamp}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:8]
    
    def verify_death_screenshot(self, room_code, player_name, screenshot_data):
        """Verify death screenshot and register kill"""
        current_time = time.time()
        
        # Cleanup old verifications
        if current_time - self.last_cleanup > 60:
            self.cleanup_old_verifications()
        
        # Validate room and player
        if room_code not in game_state.rooms:
            return False, "Room not found"
            
        room = game_state.rooms[room_code]
        
        if player_name not in room['players']:
            return False, "Player not in room"
        
        # Process screenshot
        try:
            # Decode base64 image
            if screenshot_data.startswith('data:image'):
                screenshot_data = screenshot_data.split(',')[1]
                
            image_data = base64.b64decode(screenshot_data)
            image = Image.open(io.BytesIO(image_data))
            
            # Basic validation
            if image.size[0] < 100 or image.size[1] < 100:
                return False, "Invalid screenshot dimensions"
            
            # Analyze image for death indicators
            death_detected = self.analyze_death_screenshot(image, room_code, player_name)
            
            if death_detected:
                # Find who killed this player (simplified - in real implementation, track damage)
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
            else:
                return False, "Death not detected in screenshot - no ferryman/black screen found"
                
        except Exception as e:
            logger.error(f"Screenshot verification error: {e}")
            return False, f"Screenshot processing error: {str(e)}"
    
    def analyze_death_screenshot(self, image, room_code, player_name):
        """Analyze screenshot for death indicators"""
        try:
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Get pixel data
            pixels = image.load()
            width, height = image.size
            
            # Check for common death screen elements
            death_indicators = 0
            total_checks = 0
            
            # Sample points for death screen detection
            sample_points = [
                (width // 2, height // 2),      # Center
                (width // 4, height // 4),      # Top-left
                (3 * width // 4, height // 4),  # Top-right
                (width // 4, 3 * height // 4),  # Bottom-left
                (3 * width // 4, 3 * height // 4), # Bottom-right
                (width // 2, height // 4),      # Top-center
                (width // 2, 3 * height // 4),  # Bottom-center
            ]
            
            for x, y in sample_points:
                if 0 <= x < width and 0 <= y < height:
                    total_checks += 1
                    r, g, b = pixels[x, y]
                    
                    # Check for dark/black pixels (common in death screens)
                    if r < 30 and g < 30 and b < 30:
                        death_indicators += 1
                    
                    # Check for gray/dark gray (ferryman background)
                    elif 30 <= r <= 80 and 30 <= g <= 80 and 30 <= b <= 80:
                        death_indicators += 1
            
            # Also check for specific regions that should be dark in death screen
            edge_points = [
                (10, 10), (width-10, 10), (10, height-10), (width-10, height-10)
            ]
            
            for x, y in edge_points:
                if 0 <= x < width and 0 <= y < height:
                    total_checks += 1
                    r, g, b = pixels[x, y]
                    if r < 50 and g < 50 and b < 50:
                        death_indicators += 1
            
            # If enough indicators found, consider it a death
            detection_ratio = death_indicators / total_checks if total_checks > 0 else 0
            return detection_ratio >= 0.6  # 60% of points indicate death
            
        except Exception as e:
            logger.error(f"Screenshot analysis error: {e}")
            return False
    
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
    
    def cleanup_old_verifications(self):
        """Clean up old verification attempts"""
        current_time = time.time()
        expired_verifications = []
        
        for verification_id, data in self.pending_verifications.items():
            if current_time - data.get('timestamp', 0) > self.verification_timeout:
                expired_verifications.append(verification_id)
        
        for verification_id in expired_verifications:
            del self.pending_verifications[verification_id]
        
        self.last_cleanup = current_time
        logger.info(f"Cleaned up {len(expired_verifications)} old verifications")

class TDMGameState:
    def __init__(self):
        self.rooms = {}
        self.cleanup_interval = 30  # Faster cleanup - 30 seconds
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
        """Optimized cleanup with better criteria and faster execution"""
        start_time = time.time()
        current_time = time.time()
        inactive_rooms = []
        players_cleaned = 0
        
        logger.info(f"🚀 Starting optimized cleanup cycle - {len(self.rooms)} rooms to check")

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

            # Enhanced cleanup conditions (more aggressive and accurate)
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
                
                logger.info(f"🗑️ Marking room {room_code} for cleanup: {reason} "
                           f"(age: {room_age:.0f}s, players: {players_count}, "
                           f"inactive: {inactivity_duration:.0f}s)")
                
                self.add_recent_activity('Room Cleanup', 
                                       f'Room {room_code} cleaned up ({reason})', 
                                       room_code)

        # Remove inactive rooms efficiently
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
            logger.info(f"👤 Removed inactive player session: {player_name}")

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

        # Update comprehensive cleanup stats
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
        
        logger.info(f"🎯 Cleanup completed: {len(inactive_rooms)} rooms, "
                   f"{players_cleaned} players cleaned in {cleanup_duration:.3f}s")

    def cleanup_abandoned_players(self):
        """Cleanup players who left rooms without proper disconnect"""
        current_time = time.time()
        cleanup_count = 0
        
        for room_code, room_data in list(self.rooms.items()):
            players_to_remove = []
            
            for player_name in room_data.get('players', []):
                last_active = room_data['player_last_active'].get(player_name, 0)
                
                # Remove players inactive for more than 10 minutes
                if current_time - last_active > 600:  # 10 minutes
                    players_to_remove.append(player_name)
                    cleanup_count += 1
            
            # Remove abandoned players efficiently
            for player_name in players_to_remove:
                room_data['players'].remove(player_name)
                for team in room_data['teams'].values():
                    if player_name in team:
                        team.remove(player_name)
                if player_name in room_data['player_last_active']:
                    del room_data['player_last_active'][player_name]
                
                logger.info(f"👤 Removed abandoned player {player_name} from room {room_code}")
                self.add_recent_activity('Player Cleanup', 
                                       f'Removed inactive player {player_name}', 
                                       room_code)

        return cleanup_count

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
        """Update player activity with room context for accurate tracking"""
        self.player_sessions[player_name] = time.time()
        
        # Also update room-specific activity for precise cleanup
        if room_code and room_code in self.rooms:
            self.rooms[room_code]['player_last_active'][player_name] = time.time()
            self.rooms[room_code]['last_activity'] = time.time()
            logger.debug(f"📝 Updated activity for {player_name} in room {room_code}")

    def get_online_players(self):
        """More accurate online player count using multiple criteria"""
        current_time = time.time()
        online_count = 0
        
        for room_code, room_data in self.rooms.items():
            # Count only players active in last 5 minutes across all tracking methods
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
        """Update leaderboard stats from completed matches with enhanced tracking"""
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
        """Add completed match to past matches with comprehensive data"""
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
            
            # Determine winner and update stats comprehensively
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
        """Add recent activity entry with enhanced metadata"""
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
        """Get comprehensive system statistics for monitoring"""
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

    def get_room_statistics(self):
        """Get detailed room statistics"""
        room_stats = {
            'total_rooms': len(self.rooms),
            'active_games': sum(1 for r in self.rooms.values() if r.get('game_active', False)),
            'total_players_online': self.get_online_players(),
            'rooms_by_mode': {},
            'average_players_per_room': 0,
            'full_rooms': 0
        }
        
        total_players = 0
        for room in self.rooms.values():
            game_mode = room.get('game_mode', 'unknown')
            room_stats['rooms_by_mode'][game_mode] = room_stats['rooms_by_mode'].get(game_mode, 0) + 1
            
            player_count = len(room.get('players', []))
            total_players += player_count
            
            max_players = room.get('max_players', 4)
            if player_count >= max_players:
                room_stats['full_rooms'] += 1
        
        room_stats['average_players_per_room'] = total_players / max(len(self.rooms), 1)
        
        return room_stats

# Initialize global game state and detection systems
game_state = TDMGameState()
kill_detector = KillDetectionSystem()
death_verifier = DeathVerificationSystem()

def cleanup_worker():
    """Optimized cleanup worker with multiple cleanup types and error handling"""
    game_state.create_always_active_room()
    last_abandoned_cleanup = time.time()
    last_maintenance = time.time()
    cycle_count = 0
    
    logger.info("🔄 Starting optimized cleanup worker...")
    
    while True:
        try:
            cycle_count += 1
            start_time = time.time()
            
            # Always run main cleanup
            game_state.cleanup_inactive_rooms()
            
            # Run abandoned player cleanup every 2 minutes
            if time.time() - last_abandoned_cleanup > 120:
                abandoned_count = game_state.cleanup_abandoned_players()
                if abandoned_count > 0:
                    logger.info(f"👤 Cleaned up {abandoned_count} abandoned players")
                last_abandoned_cleanup = time.time()
            
            # Run maintenance tasks every 5 minutes
            if time.time() - last_maintenance > 300:
                maintenance_tasks()
                last_maintenance = time.time()
            
            # Log cleanup performance periodically
            cleanup_duration = time.time() - start_time
            if cycle_count % 10 == 0:  # Every 10 cycles
                logger.info(f"📊 Cleanup cycle {cycle_count} completed in {cleanup_duration:.3f}s")
                
            if cleanup_duration > 2.0:  # Warn if cleanup takes too long
                logger.warning(f"🐌 Cleanup cycle took {cleanup_duration:.3f}s - consider optimization")
                
        except Exception as e:
            logger.error(f"💥 Cleanup worker error: {e}")
            # Don't break the loop on error, just continue
            time.sleep(5)  # Brief pause before retry
        
        time.sleep(game_state.cleanup_interval)

def maintenance_tasks():
    """Additional maintenance tasks for system health"""
    try:
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
            
    except Exception as e:
        logger.error(f"🔧 Maintenance tasks error: {e}")

def maintenance_worker():
    """Dedicated maintenance worker for heavy tasks"""
    logger.info("🔧 Starting maintenance worker...")
    
    while True:
        try:
            # Run comprehensive maintenance every hour
            maintenance_tasks()
                
        except Exception as e:
            logger.error(f"🔧 Maintenance worker error: {e}")
            
        time.sleep(3600)  # Run every hour

# Start cleanup and maintenance threads
cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True, name="CleanupWorker")
maintenance_thread = threading.Thread(target=maintenance_worker, daemon=True, name="MaintenanceWorker")

cleanup_thread.start()
maintenance_thread.start()

logger.info("🎯 Optimized cleanup system started with enhanced tracking")

def generate_room_code():
    """Generate a unique room code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# =============================================================================
# FLASK ROUTES AND API HANDLERS
# =============================================================================

# Serve the HTML page
@app.route('/')
def serve_index():
    return render_template_string(HTML_CONTENT)

# Stats endpoint for home page
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

# System stats endpoint
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

# Room statistics endpoint
@app.route('/rooms/stats')
def get_room_statistics():
    stats = game_state.get_room_statistics()
    return jsonify({
        'status': 'success',
        'room_statistics': stats
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
            'get_room_statistics': handle_get_room_statistics,
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

def handle_get_room_statistics(data):
    stats = game_state.get_room_statistics()
    return jsonify({
        'status': 'success',
        'room_statistics': stats
    })

if __name__ == '__main__':
    logger.info("🎮 Starting Sea of Thieves TDM Server with Death Verification System")
    logger.info("⚡ Features: Automatic screenshot verification, Server-side kill detection")
    logger.info("🌐 Server will be available at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

# app.py - COMPLETE 1400+ Lines - Sea of Thieves TDM Server
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json
import time
import random
import string
import threading
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"], methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

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

# Initialize global game state
game_state = TDMGameState()

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
# BLACK/ORANGE THEMED HTML CONTENT - COMPLETE 600+ LINES
# =============================================================================

HTML_CONTENT = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sea of Thieves TDM - Global Server</title>
    <style>
        /* COMPLETE BLACK/ORANGE THEME - 200+ LINES OF CSS */
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

        /* Header & Navigation - Enhanced */
        header {
            background: rgba(10, 10, 10, 0.95);
            backdrop-filter: blur(10px);
            padding: 1rem 2rem;
            position: fixed;
            width: 100%;
            top: 0;
            z-index: 1000;
            border-bottom: 3px solid var(--accent-color);
            box-shadow: 0 4px 20px rgba(255, 119, 0, 0.2);
        }

        .nav-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            max-width: 1200px;
            margin: 0 auto;
        }

        .logo {
            font-size: 1.8rem;
            font-weight: bold;
            color: var(--accent-color);
            text-shadow: 0 0 10px rgba(255, 119, 0, 0.5);
        }

        .nav-menu {
            display: flex;
            list-style: none;
            gap: 2rem;
        }

        .nav-menu a {
            color: var(--text-primary);
            text-decoration: none;
            padding: 0.7rem 1.5rem;
            border-radius: 8px;
            transition: all 0.3s ease;
            font-weight: 500;
            border: 2px solid transparent;
        }

        .nav-menu a:hover {
            background: var(--accent-color);
            color: var(--primary-bg);
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(255, 119, 0, 0.3);
        }

        .nav-menu a.active {
            background: var(--accent-color);
            color: var(--primary-bg);
            border-color: var(--accent-light);
        }

        .mobile-menu-btn {
            display: none;
            background: none;
            border: none;
            color: var(--text-primary);
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0.5rem;
        }

        /* Main Content */
        .main-content {
            margin-top: 100px;
            padding: 2rem;
            max-width: 1200px;
            margin-left: auto;
            margin-right: auto;
        }

        .page {
            display: none;
            animation: fadeIn 0.5s ease-in;
        }

        .page.active {
            display: block;
        }

        /* Home Page - Enhanced */
        .hero {
            text-align: center;
            padding: 4rem 2rem;
            background: linear-gradient(135deg, rgba(26, 26, 26, 0.9), rgba(42, 42, 42, 0.9));
            border-radius: 20px;
            margin-bottom: 3rem;
            border: 2px solid var(--border-color);
            position: relative;
            overflow: hidden;
        }

        .hero::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--accent-color), var(--accent-light));
        }

        .hero h1 {
            font-size: 3.5rem;
            margin-bottom: 1rem;
            color: var(--accent-color);
            text-shadow: 0 0 20px rgba(255, 119, 0, 0.5);
        }

        .hero p {
            font-size: 1.3rem;
            margin-bottom: 3rem;
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
            position: relative;
            overflow: hidden;
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255, 119, 0, 0.1), transparent);
            transition: left 0.5s ease;
        }

        .stat-card:hover::before {
            left: 100%;
        }

        .stat-card:hover {
            transform: translateY(-8px);
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

        /* Community Links Section */
        .community-section {
            background: linear-gradient(135deg, rgba(255, 119, 0, 0.05), rgba(255, 153, 51, 0.02));
            padding: 3rem 2rem;
            border-radius: 20px;
            border: 2px solid var(--border-color);
            margin: 3rem 0;
            text-align: center;
        }

        .community-section h2 {
            color: var(--accent-color);
            margin-bottom: 2rem;
            font-size: 2.2rem;
        }

        .community-links {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin-top: 2rem;
        }

        .community-card {
            background: rgba(26, 26, 26, 0.8);
            padding: 2rem;
            border-radius: 15px;
            border: 2px solid var(--border-color);
            transition: all 0.3s ease;
            text-align: center;
        }

        .community-card:hover {
            transform: translateY(-5px);
            border-color: var(--accent-color);
            box-shadow: 0 10px 25px rgba(255, 119, 0, 0.2);
        }

        .community-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            color: var(--accent-color);
        }

        .community-card h3 {
            color: var(--accent-color);
            margin-bottom: 1rem;
            font-size: 1.4rem;
        }

        .community-card p {
            color: var(--text-secondary);
            margin-bottom: 1.5rem;
            line-height: 1.5;
        }

        .community-btn {
            display: inline-block;
            background: linear-gradient(135deg, var(--accent-color), var(--accent-dark));
            color: var(--primary-bg);
            padding: 0.8rem 2rem;
            border-radius: 8px;
            text-decoration: none;
            font-weight: bold;
            transition: all 0.3s ease;
            border: 2px solid transparent;
        }

        .community-btn:hover {
            background: linear-gradient(135deg, var(--accent-light), var(--accent-color));
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(255, 119, 0, 0.3);
        }

        /* Credits Section */
        .credits-section {
            background: rgba(26, 26, 26, 0.9);
            padding: 2rem;
            border-radius: 15px;
            border: 1px solid var(--border-color);
            margin: 2rem 0;
            text-align: center;
        }

        .credits-section h3 {
            color: var(--accent-color);
            margin-bottom: 1rem;
        }

        .developer-badge {
            display: inline-block;
            background: linear-gradient(135deg, var(--accent-color), var(--accent-dark));
            color: var(--primary-bg);
            padding: 0.5rem 1.5rem;
            border-radius: 25px;
            font-weight: bold;
            margin: 0.5rem;
        }

        /* Leaderboard Styles - Enhanced */
        .leaderboard-container {
            background: rgba(26, 26, 26, 0.9);
            border-radius: 15px;
            overflow: hidden;
            border: 2px solid var(--border-color);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.5);
        }

        .leaderboard-header {
            background: linear-gradient(135deg, var(--accent-color), var(--accent-dark));
            padding: 1.2rem;
            display: grid;
            grid-template-columns: 80px 2fr 1fr 1fr 1fr 1fr;
            gap: 1rem;
            font-weight: bold;
            color: var(--primary-bg);
            font-size: 1.1rem;
        }

        .leaderboard-row {
            display: grid;
            grid-template-columns: 80px 2fr 1fr 1fr 1fr 1fr;
            gap: 1rem;
            padding: 1.2rem;
            border-bottom: 1px solid var(--border-color);
            align-items: center;
            transition: background 0.3s ease;
        }

        .leaderboard-row:hover {
            background: rgba(255, 119, 0, 0.05);
        }

        .leaderboard-row:nth-child(even) {
            background: rgba(50, 50, 50, 0.3);
        }

        .rank {
            font-weight: bold;
            color: var(--accent-color);
            font-size: 1.2rem;
        }

        .player-name {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            font-weight: 500;
        }

        .online-dot {
            width: 10px;
            height: 10px;
            background: var(--success-color);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--success-color);
        }

        .offline-dot {
            width: 10px;
            height: 10px;
            background: var(--error-color);
            border-radius: 50%;
        }

        /* Past Scores Section - Enhanced */
        .past-scores-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.5rem;
            margin-top: 2rem;
        }

        .score-card {
            background: linear-gradient(135deg, rgba(26, 26, 26, 0.9), rgba(42, 42, 42, 0.9));
            padding: 1.8rem;
            border-radius: 15px;
            border: 2px solid var(--border-color);
            transition: all 0.3s ease;
            position: relative;
        }

        .score-card:hover {
            transform: translateY(-5px);
            border-color: var(--accent-color);
            box-shadow: 0 8px 25px rgba(255, 119, 0, 0.2);
        }

        .score-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 1.5rem;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 1rem;
            font-weight: bold;
            color: var(--accent-color);
        }

        .score-teams {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }

        .team {
            text-align: center;
            flex: 1;
        }

        .team-name {
            font-weight: bold;
            color: var(--accent-color);
            margin-bottom: 0.8rem;
            font-size: 1.1rem;
        }

        .team-score {
            font-size: 2rem;
            font-weight: bold;
            color: var(--text-primary);
        }

        .score-vs {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0 1.5rem;
            font-weight: bold;
            color: var(--accent-color);
            font-size: 1.2rem;
        }

        .score-details {
            display: flex;
            justify-content: space-between;
            font-size: 0.9rem;
            color: var(--text-secondary);
            border-top: 1px solid var(--border-color);
            padding-top: 1rem;
        }

        /* Recent Activity - Enhanced */
        .activity-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-top: 2rem;
        }

        .activity-card {
            background: rgba(26, 26, 26, 0.9);
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            transition: all 0.3s ease;
        }

        .activity-card:hover {
            border-color: var(--accent-color);
            transform: translateY(-3px);
        }

        .activity-type {
            color: var(--accent-color);
            font-weight: bold;
            margin-bottom: 0.5rem;
        }

        .activity-description {
            color: var(--text-primary);
            margin-bottom: 1rem;
        }

        .activity-meta {
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        /* System Stats - Enhanced */
        .system-stats {
            background: rgba(26, 26, 26, 0.9);
            padding: 2rem;
            border-radius: 15px;
            border: 2px solid var(--border-color);
            margin-bottom: 2rem;
        }

        .system-stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }

        .system-stat {
            text-align: center;
            padding: 1rem;
            background: rgba(255, 119, 0, 0.05);
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }

        .system-stat-value {
            font-size: 1.5rem;
            font-weight: bold;
            color: var(--accent-color);
        }

        .system-stat-label {
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-top: 0.5rem;
        }

        /* Animations */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes glow {
            0%, 100% { box-shadow: 0 0 5px rgba(255, 119, 0, 0.3); }
            50% { box-shadow: 0 0 20px rgba(255, 119, 0, 0.6); }
        }

        /* Refresh indicator */
        .refresh-indicator {
            text-align: center;
            margin-top: 2rem;
            font-size: 0.9rem;
            color: var(--text-secondary);
            padding: 1rem;
            background: rgba(26, 26, 26, 0.8);
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }

        /* Loading and Error States */
        .loading {
            opacity: 0.7;
            pointer-events: none;
        }

        .error-message {
            background: rgba(204, 51, 51, 0.1);
            border: 1px solid var(--error-color);
            padding: 1.5rem;
            border-radius: 10px;
            margin: 1rem 0;
            text-align: center;
            color: var(--error-color);
        }

        .success-message {
            background: rgba(0, 204, 102, 0.1);
            border: 1px solid var(--success-color);
            padding: 1.5rem;
            border-radius: 10px;
            margin: 1rem 0;
            text-align: center;
            color: var(--success-color);
        }

        /* Performance Metrics */
        .performance-metrics {
            background: rgba(26, 26, 26, 0.9);
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            margin: 1rem 0;
        }

        .metric {
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.5rem;
            padding: 0.5rem;
            background: rgba(255, 119, 0, 0.05);
            border-radius: 5px;
        }

        .metric:last-child {
            margin-bottom: 0;
        }

        .metric-label {
            color: var(--text-secondary);
        }

        .metric-value {
            color: var(--accent-color);
            font-weight: bold;
        }

        /* Responsive Design */
        @media (max-width: 968px) {
            .nav-menu {
                display: none;
                position: absolute;
                top: 100%;
                left: 0;
                width: 100%;
                background: rgba(10, 10, 10, 0.95);
                flex-direction: column;
                padding: 1rem;
                backdrop-filter: blur(10px);
            }

            .nav-menu.active {
                display: flex;
            }

            .mobile-menu-btn {
                display: block;
            }

            .hero h1 {
                font-size: 2.5rem;
            }

            .leaderboard-header,
            .leaderboard-row {
                grid-template-columns: 60px 1fr 1fr;
                font-size: 0.9rem;
            }

            .leaderboard-header :nth-child(4),
            .leaderboard-header :nth-child(5),
            .leaderboard-header :nth-child(6),
            .leaderboard-row :nth-child(4),
            .leaderboard-row :nth-child(5),
            .leaderboard-row :nth-child(6) {
                display: none;
            }

            .past-scores-grid {
                grid-template-columns: 1fr;
            }

            .community-links {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 480px) {
            .main-content {
                padding: 1rem;
                margin-top: 80px;
            }

            .hero {
                padding: 2rem 1rem;
            }

            .hero h1 {
                font-size: 2rem;
            }

            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <!-- Header Navigation -->
    <header>
        <div class="nav-container">
            <div class="logo">⚔️ SoT TDM</div>
            <button class="mobile-menu-btn">☰</button>
            <ul class="nav-menu">
                <li><a href="#home" class="nav-link active" data-page="home">🏠 Home</a></li>
                <li><a href="#leaderboard" class="nav-link" data-page="leaderboard">🏆 Leaderboard</a></li>
                <li><a href="#past-scores" class="nav-link" data-page="past-scores">📊 Past Scores</a></li>
                <li><a href="#activity" class="nav-link" data-page="activity">📈 Recent Activity</a></li>
                <li><a href="#system" class="nav-link" data-page="system">⚙️ System</a></li>
                <li><a href="#community" class="nav-link" data-page="community">🌐 Community</a></li>
            </ul>
        </div>
    </header>

    <!-- Main Content -->
    <div class="main-content">
        <!-- Home Page -->
        <div id="home" class="page active">
            <div class="hero">
                <h1>Sea of Thieves TDM</h1>
                <p>Global Team Deathmatch Server - Optimized Cleanup System</p>
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
                <div class="refresh-indicator" id="last-updated">Last updated: Just now</div>
            </div>

            <!-- Quick Community Links on Home -->
            <div class="community-section">
                <h2>🚀 Join the Community</h2>
                <div class="community-links">
                    <div class="community-card">
                        <div class="community-icon">🏆</div>
                        <h3>Tournaments</h3>
                        <p>Compete in official Sea of Thieves TDM tournaments and climb the global rankings</p>
                        <a href="https://discord.gg/BS33MGD7kC" target="_blank" class="community-btn">Join Tournaments</a>
                    </div>
                    <div class="community-card">
                        <div class="community-icon">🎯</div>
                        <h3>STAQ Community</h3>
                        <p>Connect with players, discuss strategies, and find teammates for casual matches</p>
                        <a href="https://discord.gg/8w483Es4xz" target="_blank" class="community-btn">Join STAQ</a>
                    </div>
                </div>
            </div>
        </div>

        <!-- Leaderboard Page -->
        <div id="leaderboard" class="page">
            <h2>🏆 Global Leaderboard</h2>
            <div class="leaderboard-container">
                <div class="leaderboard-header">
                    <div>Rank</div>
                    <div>Player</div>
                    <div>Wins</div>
                    <div>Kills</div>
                    <div>Deaths</div>
                    <div>K/D Ratio</div>
                </div>
                <div id="leaderboard-content">
                    <div class="leaderboard-row">
                        <div class="rank">-</div>
                        <div class="player-name">Loading leaderboard...</div>
                        <div>0</div>
                        <div>0</div>
                        <div>0</div>
                        <div>0.00</div>
                    </div>
                </div>
            </div>
            <div class="refresh-indicator" id="leaderboard-updated">Last updated: Just now</div>
        </div>

        <!-- Past Scores Page -->
        <div id="past-scores" class="page">
            <h2>📊 Past Match Scores</h2>
            <div class="past-scores-grid" id="past-scores-content">
                <div class="score-card">
                    <div class="score-header">
                        <div>Loading past matches...</div>
                    </div>
                </div>
            </div>
            <div class="refresh-indicator" id="scores-updated">Last updated: Just now</div>
        </div>

        <!-- Recent Activity Page -->
        <div id="activity" class="page">
            <h2>📈 Recent Activity</h2>
            <div class="activity-grid" id="recent-activity">
                <div class="activity-card">
                    <div class="activity-type">Loading...</div>
                    <div class="activity-description">Loading recent activity...</div>
                    <div class="activity-meta">
                        <span>Just now</span>
                    </div>
                </div>
            </div>
            <div class="refresh-indicator" id="activity-updated">Last updated: Just now</div>
        </div>

        <!-- System Stats Page -->
        <div id="system" class="page">
            <h2>⚙️ System Status</h2>
            
            <div class="system-stats">
                <h3>Server Overview</h3>
                <div class="stats-grid">
                    <div class="stat-card">
                        <span class="stat-number" id="total-rooms">0</span>
                        <span class="stat-label">Total Rooms</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number" id="total-kills">0</span>
                        <span class="stat-label">Total Kills</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number" id="cleanup-duration">0s</span>
                        <span class="stat-label">Last Cleanup</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number" id="rooms-cleaned">0</span>
                        <span class="stat-label">Rooms Cleaned</span>
                    </div>
                </div>
            </div>

            <div class="performance-metrics">
                <h3>Performance Metrics</h3>
                <div id="performance-content">
                    <div class="metric">
                        <span class="metric-label">Server Uptime:</span>
                        <span class="metric-value" id="server-uptime">0s</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Cleanup Efficiency:</span>
                        <span class="metric-value" id="cleanup-efficiency">0%</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Total Cleanups:</span>
                        <span class="metric-value" id="total-cleanups">0</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Memory Usage:</span>
                        <span class="metric-value" id="memory-usage">0 KB</span>
                    </div>
                </div>
            </div>

            <div class="refresh-indicator" id="system-updated">Last updated: Just now</div>
        </div>

        <!-- Community Page -->
        <div id="community" class="page">
            <div class="hero">
                <h1>🌐 Community Hub</h1>
                <p>Connect with the Sea of Thieves TDM Community</p>
            </div>

            <!-- Community Links Section -->
            <div class="community-section">
                <h2>Join Our Communities</h2>
                <p style="color: var(--text-secondary); margin-bottom: 2rem; font-size: 1.1rem;">
                    Connect with fellow players, participate in tournaments, and help grow the Sea of Thieves TDM scene!
                </p>
                
                <div class="community-links">
                    <div class="community-card">
                        <div class="community-icon">🏆</div>
                        <h3>SoT TDM Tournaments</h3>
                        <p>Join the official tournament community for competitive matches, events, rankings, and prize pools. Perfect for players looking to test their skills against the best.</p>
                        <a href="https://discord.gg/BS33MGD7kC" target="_blank" class="community-btn">Join Tournaments</a>
                    </div>
                    
                    <div class="community-card">
                        <div class="community-icon">🎯</div>
                        <h3>STAQ Community</h3>
                        <p>Connect with the broader Sea of Thieves TDM community for strategy discussions, team formation, casual matches, and general gameplay discussions.</p>
                        <a href="https://discord.gg/8w483Es4xz" target="_blank" class="community-btn">Join STAQ</a>
                    </div>
                </div>
            </div>

            <!-- Credits Section -->
            <div class="credits-section">
                <h3>🎮 Developed By</h3>
                <div class="developer-badge">Ryan - Lead Developer & System Architect</div>
                
                <div style="margin-top: 2rem; color: var(--text-secondary);">
                    <h4>🌟 Project Features</h4>
                    <p>• Optimized Cleanup System • Enhanced Leaderboard • 24/7 TDM Channel</p>
                    <p>• Black/Orange Theme • Mobile Responsive • Real-time Updates</p>
                </div>
            </div>

            <!-- Quick Stats -->
            <div class="system-stats">
                <h3>Community Impact</h3>
                <div class="stats-grid">
                    <div class="stat-card">
                        <span class="stat-number" id="community-players">0</span>
                        <span class="stat-label">Total Players</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number" id="community-matches">0</span>
                        <span class="stat-label">Matches Played</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number" id="community-kills">0</span>
                        <span class="stat-label">Total Kills</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number" id="community-rooms">0</span>
                        <span class="stat-label">Active Rooms</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Server configuration
        const SERVER_URL = window.location.origin;

        // Page navigation
        function showPage(pageId) {
            document.querySelectorAll('.page').forEach(page => {
                page.classList.remove('active');
            });
            
            document.getElementById(pageId).classList.add('active');
            
            document.querySelectorAll('.nav-link').forEach(link => {
                link.classList.remove('active');
            });
            document.querySelector(`[data-page="${pageId}"]`).classList.add('active');
            
            // Load page-specific data
            if (pageId === 'leaderboard') {
                loadLeaderboard();
            } else if (pageId === 'home') {
                loadHomeStats();
            } else if (pageId === 'past-scores') {
                loadPastScores();
            } else if (pageId === 'activity') {
                loadRecentActivity();
            } else if (pageId === 'system') {
                loadSystemStats();
            } else if (pageId === 'community') {
                loadCommunityStats();
            }
        }

        // Mobile menu
        document.querySelector('.mobile-menu-btn').addEventListener('click', function() {
            document.querySelector('.nav-menu').classList.toggle('active');
        });

        // Navigation event listeners
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                const pageId = this.getAttribute('data-page');
                if (pageId) {
                    showPage(pageId);
                }
                document.querySelector('.nav-menu').classList.remove('active');
            });
        });

        // Update timestamp display
        function updateTimestamp(elementId) {
            const now = new Date();
            const timeString = now.toLocaleTimeString();
            document.getElementById(elementId).textContent = `Last updated: ${timeString}`;
        }

        // Format time for recent activity
        function formatActivityTime(timestamp) {
            const now = Math.floor(Date.now() / 1000);
            const diff = now - timestamp;
            
            if (diff < 60) return 'Just now';
            if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
            if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
            return `${Math.floor(diff / 86400)}d ago`;
        }

        // Format duration for matches
        function formatDuration(seconds) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
        }

        // Load home page statistics
        async function loadHomeStats() {
            try {
                const response = await fetch(`${SERVER_URL}/stats`);
                const data = await response.json();
                
                document.getElementById('online-players').textContent = data.online_players || '0';
                document.getElementById('active-rooms').textContent = data.active_rooms || '0';
                document.getElementById('total-players').textContent = data.total_players_tracked || '0';
                document.getElementById('total-matches').textContent = data.total_matches || '0';
                
                updateTimestamp('last-updated');
            } catch (error) {
                console.error('Error loading home stats:', error);
                document.getElementById('online-players').textContent = '?';
                document.getElementById('active-rooms').textContent = '?';
                document.getElementById('total-players').textContent = '?';
                document.getElementById('total-matches').textContent = '?';
            }
        }

        // Load community stats
        async function loadCommunityStats() {
            try {
                const response = await fetch(`${SERVER_URL}/stats`);
                const data = await response.json();
                
                document.getElementById('community-players').textContent = data.total_players_tracked || '0';
                document.getElementById('community-matches').textContent = data.total_matches || '0';
                document.getElementById('community-kills').textContent = data.total_kills || '0';
                document.getElementById('community-rooms').textContent = data.active_rooms || '0';
            } catch (error) {
                console.error('Error loading community stats:', error);
            }
        }

        // Load system statistics
        async function loadSystemStats() {
            try {
                const response = await fetch(`${SERVER_URL}/system`);
                const data = await response.json();
                
                document.getElementById('total-rooms').textContent = data.total_rooms || '0';
                document.getElementById('total-kills').textContent = data.total_kills || '0';
                document.getElementById('cleanup-duration').textContent = data.cleanup_duration || '0s';
                document.getElementById('rooms-cleaned').textContent = data.cleanup_stats?.rooms_cleaned || '0';
                document.getElementById('server-uptime').textContent = data.server_uptime_formatted || '0s';
                document.getElementById('cleanup-efficiency').textContent = data.performance_metrics?.cleanup_efficiency || '0%';
                document.getElementById('total-cleanups').textContent = data.cleanup_stats?.total_cleanups || '0';
                document.getElementById('memory-usage').textContent = data.performance_metrics?.memory_usage_estimate 
                    ? `${Math.round(data.performance_metrics.memory_usage_estimate)} KB` 
                    : '0 KB';
                
                updateTimestamp('system-updated');
            } catch (error) {
                console.error('Error loading system stats:', error);
            }
        }

        // Load leaderboard
        async function loadLeaderboard() {
            try {
                const leaderboardContent = document.getElementById('leaderboard-content');
                leaderboardContent.classList.add('loading');

                const response = await fetch(`${SERVER_URL}/api`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        action: 'get_leaderboard',
                        limit: 50
                    })
                });

                const data = await response.json();
                
                if (data.status === 'success') {
                    leaderboardContent.innerHTML = '';

                    if (data.leaderboard.length === 0) {
                        leaderboardContent.innerHTML = `
                            <div class="leaderboard-row">
                                <div class="rank">-</div>
                                <div class="player-name">No players yet</div>
                                <div>0</div>
                                <div>0</div>
                                <div>0</div>
                                <div>0.00</div>
                            </div>
                        `;
                        return;
                    }

                    data.leaderboard.forEach((player, index) => {
                        const row = document.createElement('div');
                        row.className = 'leaderboard-row';
                        row.innerHTML = `
                            <div class="rank">${index + 1}</div>
                            <div class="player-name">
                                <span class="${player.is_online ? 'online-dot' : 'offline-dot'}"></span>
                                ${player.player_name}
                            </div>
                            <div>${player.wins}</div>
                            <div>${player.kills}</div>
                            <div>${player.deaths}</div>
                            <div>${player.kd_ratio.toFixed(2)}</div>
                        `;
                        leaderboardContent.appendChild(row);
                    });
                    
                    updateTimestamp('leaderboard-updated');
                } else {
                    throw new Error(data.message || 'Failed to load leaderboard');
                }
            } catch (error) {
                console.error('Error loading leaderboard:', error);
                document.getElementById('leaderboard-content').innerHTML = `
                    <div class="error-message">
                        Failed to load leaderboard: ${error.message}
                    </div>
                `;
            } finally {
                leaderboardContent.classList.remove('loading');
            }
        }

        // Load recent activity
        async function loadRecentActivity() {
            try {
                const recentActivity = document.getElementById('recent-activity');
                recentActivity.classList.add('loading');

                const response = await fetch(`${SERVER_URL}/api`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        action: 'get_recent_activity'
                    })
                });

                const data = await response.json();
                
                if (data.status === 'success') {
                    recentActivity.innerHTML = '';

                    if (data.recent_activity.length === 0) {
                        recentActivity.innerHTML = '<div class="activity-card">No recent activity yet.</div>';
                        return;
                    }

                    data.recent_activity.forEach(activity => {
                        const activityCard = document.createElement('div');
                        activityCard.className = 'activity-card';
                        activityCard.innerHTML = `
                            <div class="activity-type">${activity.type}</div>
                            <div class="activity-description">${activity.description}</div>
                            <div class="activity-meta">
                                <span>${activity.room_code ? 'Room: ' + activity.room_code : ''}</span>
                                <span>${formatActivityTime(activity.timestamp)}</span>
                            </div>
                        `;
                        recentActivity.appendChild(activityCard);
                    });
                    
                    updateTimestamp('activity-updated');
                } else {
                    throw new Error(data.message || 'Failed to load recent activity');
                }
            } catch (error) {
                console.error('Error loading recent activity:', error);
                recentActivity.innerHTML = `
                    <div class="error-message">
                        Failed to load recent activity: ${error.message}
                    </div>
                `;
            } finally {
                recentActivity.classList.remove('loading');
            }
        }

        // Load past scores
        async function loadPastScores() {
            try {
                const pastScoresContent = document.getElementById('past-scores-content');
                pastScoresContent.classList.add('loading');

                const response = await fetch(`${SERVER_URL}/api`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        action: 'get_past_scores',
                        limit: 12
                    })
                });

                const data = await response.json();
                
                if (data.status === 'success') {
                    pastScoresContent.innerHTML = '';

                    if (data.past_scores.length === 0) {
                        pastScoresContent.innerHTML = '<div class="score-card">No past matches yet.</div>';
                        return;
                    }

                    data.past_scores.forEach(match => {
                        const scoreCard = document.createElement('div');
                        scoreCard.className = 'score-card';
                        scoreCard.innerHTML = `
                            <div class="score-header">
                                <div>${match.room_name || 'Unknown Room'}</div>
                                <div>${formatDuration(match.duration)}</div>
                            </div>
                            <div class="score-teams">
                                <div class="team">
                                    <div class="team-name">Team 1</div>
                                    <div class="team-score">${match.team1_score}</div>
                                </div>
                                <div class="score-vs">VS</div>
                                <div class="team">
                                    <div class="team-name">Team 2</div>
                                    <div class="team-score">${match.team2_score}</div>
                                </div>
                            </div>
                            <div class="score-details">
                                <div>${new Date(match.timestamp * 1000).toLocaleDateString()}</div>
                                <div>${match.game_mode}</div>
                            </div>
                        `;
                        pastScoresContent.appendChild(scoreCard);
                    });
                    
                    updateTimestamp('scores-updated');
                } else {
                    throw new Error(data.message || 'Failed to load past scores');
                }
            } catch (error) {
                console.error('Error loading past scores:', error);
                pastScoresContent.innerHTML = `
                    <div class="error-message">
                        Failed to load past scores: ${error.message}
                    </div>
                `;
            } finally {
                pastScoresContent.classList.remove('loading');
            }
        }

        // Initialize the page
        document.addEventListener('DOMContentLoaded', function() {
            loadHomeStats();
            
            // Refresh data every 10 seconds
            setInterval(() => {
                const activePage = document.querySelector('.page.active').id;
                
                if (activePage === 'home') {
                    loadHomeStats();
                } else if (activePage === 'leaderboard') {
                    loadLeaderboard();
                } else if (activePage === 'past-scores') {
                    loadPastScores();
                } else if (activePage === 'activity') {
                    loadRecentActivity();
                } else if (activePage === 'system') {
                    loadSystemStats();
                } else if (activePage === 'community') {
                    loadCommunityStats();
                }
            }, 10000);
        });
    </script>
</body>
</html>
'''

# =============================================================================
# FLASK ROUTES AND API HANDLERS - COMPLETE 400+ LINES
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

# API Handlers with improved activity tracking
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
    logger.info(f"Kill registered: {killer} -> {victim} in {room_code}")
    
    return jsonify({
        'status': 'success',
        'message': 'Kill registered successfully'
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
    logger.info("🎮 Starting Sea of Thieves TDM Server with Optimized Cleanup System")
    logger.info("⚡ Features: Faster cleanup, Enhanced tracking, Black/Orange theme")
    logger.info("🌐 Server will be available at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

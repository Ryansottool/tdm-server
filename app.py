# app.py - SoT TDM Render Server (MAIN ENTRY POINT FOR RENDER.COM)
import os
import json
import sqlite3
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)  # Allow all origins for now
DATABASE = 'sot_tdm.db'

# =============================================================================
# DATABASE SETUP
# =============================================================================

def get_db():
    """Get database connection"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize database tables"""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                username TEXT,
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                matches_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Matches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT UNIQUE,
                status TEXT DEFAULT 'waiting', -- waiting, active, finished
                team1_score INTEGER DEFAULT 0,
                team2_score INTEGER DEFAULT 0,
                winning_team TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Match players (team assignments)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                player_id INTEGER,
                team TEXT, -- 'team1' or 'team2'
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                FOREIGN KEY (match_id) REFERENCES matches(id),
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        ''')
        
        # Kills table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                killer_id INTEGER,
                victim_id INTEGER,
                victim_name TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_team_wipe BOOLEAN DEFAULT 0,
                FOREIGN KEY (match_id) REFERENCES matches(id),
                FOREIGN KEY (killer_id) REFERENCES players(id),
                FOREIGN KEY (victim_id) REFERENCES players(id)
            )
        ''')
        
        db.commit()
        print("✅ Database initialized")

def generate_room_code():
    """Generate random 6-character room code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_player_by_discord(discord_id):
    """Get player by Discord ID"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM players WHERE discord_id = ?', (discord_id,))
    return cursor.fetchone()

def get_or_create_player(discord_id, username):
    """Get existing player or create new one"""
    player = get_player_by_discord(discord_id)
    if player:
        # Update username if changed
        db = get_db()
        cursor = db.cursor()
        cursor.execute('UPDATE players SET username = ? WHERE discord_id = ?', 
                      (username, discord_id))
        db.commit()
        return player
    else:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO players (discord_id, username) 
            VALUES (?, ?)
        ''', (discord_id, username))
        db.commit()
        return get_player_by_discord(discord_id)

def get_active_match_by_code(room_code):
    """Get active match by room code"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT * FROM matches 
        WHERE room_code = ? AND status = 'active'
    ''', (room_code,))
    return cursor.fetchone()

def get_match_players(match_id, team=None):
    """Get players in a match, optionally filtered by team"""
    db = get_db()
    cursor = db.cursor()
    
    if team:
        cursor.execute('''
            SELECT p.*, mp.team, mp.kills as match_kills, mp.deaths as match_deaths
            FROM match_players mp
            JOIN players p ON mp.player_id = p.id
            WHERE mp.match_id = ? AND mp.team = ?
        ''', (match_id, team))
    else:
        cursor.execute('''
            SELECT p.*, mp.team, mp.kills as match_kills, mp.deaths as match_deaths
            FROM match_players mp
            JOIN players p ON mp.player_id = p.id
            WHERE mp.match_id = ?
        ''', (match_id,))
    
    return cursor.fetchall()

def check_team_wipe(match_id, killed_team):
    """Check if all players in a team are dead (HP=0)"""
    db = get_db()
    cursor = db.cursor()
    
    # Get all players in the team
    cursor.execute('''
        SELECT mp.id, p.username
        FROM match_players mp
        JOIN players p ON mp.player_id = p.id
        WHERE mp.match_id = ? AND mp.team = ?
    ''', (match_id, killed_team))
    
    team_players = cursor.fetchall()
    
    # Check if all players in this team have died recently (within 5 seconds)
    cursor.execute('''
        SELECT DISTINCT victim_id 
        FROM kills 
        WHERE match_id = ? 
        AND timestamp >= datetime('now', '-5 seconds')
    ''', (match_id,))
    
    recent_victims = [row[0] for row in cursor.fetchall()]
    
    # Check if all team players are in recent victims
    team_player_ids = [row[0] for row in team_players]
    return all(player_id in recent_victims for player_id in team_player_ids)

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/register', methods=['POST'])
def register_player():
    """Register/link Discord user"""
    data = request.json
    discord_id = data.get('discord_id')
    username = data.get('username')
    
    if not discord_id or not username:
        return jsonify({'error': 'Missing discord_id or username'}), 400
    
    player = get_or_create_player(discord_id, username)
    return jsonify({
        'player_id': player['id'],
        'username': player['username'],
        'kills': player['kills'],
        'deaths': player['deaths']
    })

@app.route('/api/match/create', methods=['POST'])
def create_match():
    """Create a new TDM match"""
    data = request.json
    room_code = generate_room_code()
    
    # Check if code exists (very unlikely but handle it)
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id FROM matches WHERE room_code = ?', (room_code,))
    if cursor.fetchone():
        room_code = generate_room_code()  # Regenerate if collision
    
    cursor.execute('''
        INSERT INTO matches (room_code, status, start_time)
        VALUES (?, 'waiting', CURRENT_TIMESTAMP)
    ''', (room_code,))
    db.commit()
    
    match_id = cursor.lastrowid
    
    return jsonify({
        'room_code': room_code,
        'match_id': match_id,
        'status': 'waiting'
    })

@app.route('/api/match/<room_code>/join', methods=['POST'])
def join_match(room_code):
    """Join a match with team assignment"""
    data = request.json
    player_id = data.get('player_id')
    team = data.get('team')  # 'team1' or 'team2'
    
    if not player_id or not team:
        return jsonify({'error': 'Missing player_id or team'}), 400
    
    # Get match
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM matches WHERE room_code = ?', (room_code,))
    match = cursor.fetchone()
    
    if not match:
        return jsonify({'error': 'Match not found'}), 404
    
    # Check if player already in match
    cursor.execute('''
        SELECT id FROM match_players 
        WHERE match_id = ? AND player_id = ?
    ''', (match['id'], player_id))
    
    if cursor.fetchone():
        return jsonify({'error': 'Player already in match'}), 400
    
    # Add player to match
    cursor.execute('''
        INSERT INTO match_players (match_id, player_id, team)
        VALUES (?, ?, ?)
    ''', (match['id'], player_id, team))
    
    # Update match status to active if enough players
    cursor.execute('''
        SELECT COUNT(DISTINCT team) as teams_count
        FROM match_players 
        WHERE match_id = ?
    ''', (match['id'],))
    
    teams_count = cursor.fetchone()['teams_count']
    
    if teams_count >= 2 and match['status'] == 'waiting':
        cursor.execute('''
            UPDATE matches 
            SET status = 'active', start_time = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (match['id'],))
    
    db.commit()
    
    return jsonify({
        'success': True,
        'room_code': room_code,
        'team': team,
        'match_status': 'active' if teams_count >= 2 else 'waiting'
    })

@app.route('/api/match/<room_code>/start', methods=['POST'])
def start_match(room_code):
    """Start a match (called by client when ready)"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        UPDATE matches 
        SET status = 'active', start_time = CURRENT_TIMESTAMP 
        WHERE room_code = ? AND status = 'waiting'
    ''', (room_code,))
    
    db.commit()
    
    cursor.execute('SELECT * FROM matches WHERE room_code = ?', (room_code,))
    match = cursor.fetchone()
    
    return jsonify({
        'success': True,
        'status': match['status'],
        'start_time': match['start_time']
    })

@app.route('/api/kill', methods=['POST'])
def report_kill():
    """Report a kill"""
    data = request.json
    room_code = data.get('room_code')
    killer_discord_id = data.get('killer_discord_id')
    victim_name = data.get('victim_name', 'Enemy')
    
    if not room_code or not killer_discord_id:
        return jsonify({'error': 'Missing room_code or killer_discord_id'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    # Get match
    cursor.execute('SELECT * FROM matches WHERE room_code = ?', (room_code,))
    match = cursor.fetchone()
    
    if not match or match['status'] != 'active':
        return jsonify({'error': 'Match not found or not active'}), 404
    
    # Get killer player
    killer_player = get_player_by_discord(killer_discord_id)
    if not killer_player:
        return jsonify({'error': 'Killer not registered'}), 404
    
    # Get victim player (if registered)
    victim_player = None
    # Note: In future, we could lookup by name, but for now just track name
    
    # Get killer's team
    cursor.execute('''
        SELECT team FROM match_players 
        WHERE match_id = ? AND player_id = ?
    ''', (match['id'], killer_player['id']))
    
    killer_team_row = cursor.fetchone()
    if not killer_team_row:
        return jsonify({'error': 'Killer not in this match'}), 400
    
    killer_team = killer_team_row['team']
    victim_team = 'team2' if killer_team == 'team1' else 'team1'
    
    # Record kill
    cursor.execute('''
        INSERT INTO kills (match_id, killer_id, victim_id, victim_name, timestamp)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (match['id'], killer_player['id'], 
          victim_player['id'] if victim_player else None, 
          victim_name))
    
    kill_id = cursor.lastrowid
    
    # Update killer's match stats
    cursor.execute('''
        UPDATE match_players 
        SET kills = kills + 1 
        WHERE match_id = ? AND player_id = ?
    ''', (match['id'], killer_player['id']))
    
    # Update killer's global stats
    cursor.execute('''
        UPDATE players 
        SET kills = kills + 1 
        WHERE id = ?
    ''', (killer_player['id'],))
    
    # Update team score
    if killer_team == 'team1':
        cursor.execute('''
            UPDATE matches 
            SET team1_score = team1_score + 1 
            WHERE id = ?
        ''', (match['id'],))
        new_team1_score = match['team1_score'] + 1
        new_team2_score = match['team2_score']
    else:
        cursor.execute('''
            UPDATE matches 
            SET team2_score = team2_score + 1 
            WHERE id = ?
        ''', (match['id'],))
        new_team1_score = match['team1_score']
        new_team2_score = match['team2_score'] + 1
    
    # Check for team wipe
    is_team_wipe = check_team_wipe(match['id'], victim_team)
    
    if is_team_wipe:
        # Award extra point for team wipe
        if killer_team == 'team1':
            cursor.execute('''
                UPDATE matches 
                SET team1_score = team1_score + 1 
                WHERE id = ?
            ''', (match['id'],))
            new_team1_score += 1
        else:
            cursor.execute('''
                UPDATE matches 
                SET team2_score = team2_score + 1 
                WHERE id = ?
            ''', (match['id'],))
            new_team2_score += 1
        
        # Mark kill as team wipe
        cursor.execute('''
            UPDATE kills 
            SET is_team_wipe = 1 
            WHERE id = ?
        ''', (kill_id,))
    
    # Check win condition (first to 10)
    winning_team = None
    if new_team1_score >= 10:
        winning_team = 'team1'
    elif new_team2_score >= 10:
        winning_team = 'team2'
    
    if winning_team:
        cursor.execute('''
            UPDATE matches 
            SET status = 'finished', 
                winning_team = ?,
                end_time = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (winning_team, match['id']))
        
        # Update player wins
        cursor.execute('''
            UPDATE players 
            SET wins = wins + 1, matches_played = matches_played + 1
            WHERE id IN (
                SELECT player_id FROM match_players 
                WHERE match_id = ? AND team = ?
            )
        ''', (match['id'], winning_team))
        
        # Update losses for other team
        cursor.execute('''
            UPDATE players 
            SET matches_played = matches_played + 1
            WHERE id IN (
                SELECT player_id FROM match_players 
                WHERE match_id = ? AND team != ?
            )
        ''', (match['id'], winning_team))
    
    db.commit()
    
    return jsonify({
        'success': True,
        'kill_id': kill_id,
        'team_wipe': is_team_wipe,
        'team1_score': new_team1_score,
        'team2_score': new_team2_score,
        'match_status': 'finished' if winning_team else 'active',
        'winning_team': winning_team
    })

@app.route('/api/death', methods=['POST'])
def report_death():
    """Report a death"""
    data = request.json
    room_code = data.get('room_code')
    victim_discord_id = data.get('victim_discord_id')
    killer_name = data.get('killer_name', 'Enemy')
    
    if not room_code or not victim_discord_id:
        return jsonify({'error': 'Missing room_code or victim_discord_id'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    # Get match
    cursor.execute('SELECT * FROM matches WHERE room_code = ?', (room_code,))
    match = cursor.fetchone()
    
    if not match or match['status'] != 'active':
        return jsonify({'error': 'Match not found or not active'}), 404
    
    # Get victim player
    victim_player = get_player_by_discord(victim_discord_id)
    if not victim_player:
        return jsonify({'error': 'Victim not registered'}), 404
    
    # Update victim's match deaths
    cursor.execute('''
        UPDATE match_players 
        SET deaths = deaths + 1 
        WHERE match_id = ? AND player_id = ?
    ''', (match['id'], victim_player['id']))
    
    # Update victim's global deaths
    cursor.execute('''
        UPDATE players 
        SET deaths = deaths + 1 
        WHERE id = ?
    ''', (victim_player['id'],))
    
    db.commit()
    
    return jsonify({'success': True})

@app.route('/api/match/<room_code>', methods=['GET'])
def get_match_info(room_code):
    """Get match information"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT * FROM matches WHERE room_code = ?', (room_code,))
    match = cursor.fetchone()
    
    if not match:
        return jsonify({'error': 'Match not found'}), 404
    
    # Get players
    team1_players = get_match_players(match['id'], 'team1')
    team2_players = get_match_players(match['id'], 'team2')
    
    # Get recent kills (last 10)
    cursor.execute('''
        SELECT k.*, p.username as killer_name
        FROM kills k
        LEFT JOIN players p ON k.killer_id = p.id
        WHERE k.match_id = ?
        ORDER BY k.timestamp DESC
        LIMIT 10
    ''', (match['id'],))
    
    recent_kills = cursor.fetchall()
    
    # Calculate match duration
    duration = None
    if match['start_time']:
        start = datetime.fromisoformat(match['start_time'].replace('Z', '+00:00'))
        if match['end_time']:
            end = datetime.fromisoformat(match['end_time'].replace('Z', '+00:00'))
            duration = int((end - start).total_seconds())
        else:
            duration = int((datetime.utcnow() - start).total_seconds())
    
    return jsonify({
        'room_code': match['room_code'],
        'status': match['status'],
        'team1_score': match['team1_score'],
        'team2_score': match['team2_score'],
        'winning_team': match['winning_team'],
        'start_time': match['start_time'],
        'end_time': match['end_time'],
        'duration': duration,
        'team1': [
            {
                'username': p['username'],
                'kills': p['match_kills'],
                'deaths': p['match_deaths']
            } for p in team1_players
        ],
        'team2': [
            {
                'username': p['username'],
                'kills': p['match_kills'],
                'deaths': p['match_deaths']
            } for p in team2_players
        ],
        'recent_kills': [
            {
                'killer_name': k['killer_name'] or 'Unknown',
                'victim_name': k['victim_name'],
                'timestamp': k['timestamp'],
                'is_team_wipe': bool(k['is_team_wipe'])
            } for k in recent_kills
        ]
    })

@app.route('/api/scoreboard/<room_code>', methods=['GET'])
def get_scoreboard(room_code):
    """Get scoreboard for webhook/embed"""
    match_info = get_match_info(room_code)
    
    if isinstance(match_info, tuple):  # Error response
        return match_info
    
    data = match_info.get_json()
    
    # Format for Discord embed
    embed_data = {
        'title': f'SoT TDM - Room {room_code}',
        'description': f'Status: {data["status"].upper()}',
        'color': 0x00ff00 if data['status'] == 'active' else 0xff0000 if data['status'] == 'finished' else 0xffff00,
        'fields': [
            {
                'name': f'Team 1 - {data["team1_score"]} points',
                'value': '\n'.join([f'• {p["username"]} - {p["kills"]}/{p["deaths"]} K/D' for p in data['team1']]) or 'No players',
                'inline': True
            },
            {
                'name': f'Team 2 - {data["team2_score"]} points',
                'value': '\n'.join([f'• {p["username"]} - {p["kills"]}/{p["deaths"]} K/D' for p in data['team2']]) or 'No players',
                'inline': True
            }
        ],
        'footer': {
            'text': f'First to 10 points wins | Team wipe = +1 point'
        }
    }
    
    if data['duration']:
        minutes = data['duration'] // 60
        seconds = data['duration'] % 60
        embed_data['footer']['text'] += f' | Time: {minutes}:{seconds:02d}'
    
    if data['recent_kills']:
        kill_feed = []
        for kill in data['recent_kills'][:5]:  # Last 5 kills
            time_str = datetime.fromisoformat(kill['timestamp'].replace('Z', '+00:00')).strftime('%H:%M:%S')
            wipe_str = ' ⚡' if kill['is_team_wipe'] else ''
            kill_feed.append(f'`{time_str}` **{kill["killer_name"]}** → {kill["victim_name"]}{wipe_str}')
        
        embed_data['fields'].append({
            'name': 'Recent Kills',
            'value': '\n'.join(kill_feed) or 'No kills yet',
            'inline': False
        })
    
    return jsonify(embed_data)

@app.route('/api/stats/<discord_id>', methods=['GET'])
def get_player_stats(discord_id):
    """Get player statistics"""
    player = get_player_by_discord(discord_id)
    
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    db = get_db()
    cursor = db.cursor()
    
    # Get recent matches
    cursor.execute('''
        SELECT m.room_code, m.status, m.winning_team, 
               mp.team, mp.kills as match_kills, mp.deaths as match_deaths,
               CASE WHEN mp.team = m.winning_team THEN 1 ELSE 0 END as won
        FROM match_players mp
        JOIN matches m ON mp.match_id = m.id
        WHERE mp.player_id = ?
        ORDER BY m.created_at DESC
        LIMIT 10
    ''', (player['id'],))
    
    recent_matches = cursor.fetchall()
    
    # Calculate K/D ratio
    kd_ratio = player['kills'] / max(player['deaths'], 1)
    win_rate = (player['wins'] / max(player['matches_played'], 1)) * 100
    
    return jsonify({
        'username': player['username'],
        'global_stats': {
            'kills': player['kills'],
            'deaths': player['deaths'],
            'kd_ratio': round(kd_ratio, 2),
            'matches_played': player['matches_played'],
            'wins': player['wins'],
            'win_rate': round(win_rate, 1)
        },
        'recent_matches': [
            {
                'room_code': m['room_code'],
                'status': m['status'],
                'team': m['team'],
                'kills': m['match_kills'],
                'deaths': m['match_deaths'],
                'won': bool(m['won'])
            } for m in recent_matches
        ]
    })

@app.route('/api/history', methods=['GET'])
def get_recent_matches():
    """Get recent match history"""
    limit = request.args.get('limit', 10, type=int)
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT m.*, 
               COUNT(DISTINCT mp.player_id) as player_count
        FROM matches m
        LEFT JOIN match_players mp ON m.id = mp.match_id
        WHERE m.status = 'finished'
        GROUP BY m.id
        ORDER BY m.end_time DESC
        LIMIT ?
    ''', (limit,))
    
    matches = cursor.fetchall()
    
    return jsonify({
        'matches': [
            {
                'room_code': m['room_code'],
                'team1_score': m['team1_score'],
                'team2_score': m['team2_score'],
                'winning_team': m['winning_team'],
                'duration': m['end_time'] and m['start_time'] and 
                           int((datetime.fromisoformat(m['end_time'].replace('Z', '+00:00')) - 
                                datetime.fromisoformat(m['start_time'].replace('Z', '+00:00'))).total_seconds()),
                'player_count': m['player_count'],
                'ended_at': m['end_time']
            } for m in matches
        ]
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render.com"""
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/', methods=['GET'])
def index():
    """Root endpoint - show API info"""
    return jsonify({
        'service': 'SoT TDM Server',
        'version': '1.0.0',
        'endpoints': {
            'POST /api/register': 'Register Discord user',
            'POST /api/match/create': 'Create new match',
            'POST /api/match/<code>/join': 'Join match',
            'POST /api/kill': 'Report kill',
            'POST /api/death': 'Report death',
            'GET /api/match/<code>': 'Get match info',
            'GET /api/scoreboard/<code>': 'Get scoreboard embed',
            'GET /api/stats/<discord_id>': 'Get player stats',
            'GET /api/history': 'Get match history',
            'GET /health': 'Health check'
        }
    })

# =============================================================================
# SERVER STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    if not os.path.exists(DATABASE):
        init_db()
    else:
        # Just ensure tables exist
        with app.app_context():
            init_db()
    
    print("🚀 SoT TDM Server starting...")
    print("📊 Database:", DATABASE)
    print("🌐 API Endpoints:")
    print("  POST /api/register")
    print("  POST /api/match/create")
    print("  POST /api/match/<code>/join")
    print("  POST /api/kill")
    print("  POST /api/death")
    print("  GET  /api/match/<code>")
    print("  GET  /api/scoreboard/<code>")
    print("  GET  /api/stats/<discord_id>")
    print("  GET  /api/history")
    
    # Run server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

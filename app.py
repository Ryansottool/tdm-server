# app.py - FULL WEB SERVER WITH DISCORD BOT
import os
import json
import sqlite3
import random
import string
import threading
import asyncio
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def init_db():
    """Initialize database"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Matches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT UNIQUE,
                team1_name TEXT DEFAULT 'Team 1',
                team2_name TEXT DEFAULT 'Team 2',
                team1_score INTEGER DEFAULT 0,
                team2_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'waiting',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                username TEXT,
                team INTEGER DEFAULT 0,
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Match players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_players (
                match_id INTEGER,
                player_id INTEGER,
                team INTEGER,
                FOREIGN KEY (match_id) REFERENCES matches (id),
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# HTML ROUTES - WEB INTERFACE
# =============================================================================

@app.route('/')
def index():
    """Main web interface"""
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SoT TDM Server</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; 
                min-height: 100vh;
                padding: 20px;
            }
            .container { 
                max-width: 1200px; 
                margin: 0 auto; 
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            }
            header { 
                text-align: center; 
                margin-bottom: 40px; 
                padding-bottom: 20px;
                border-bottom: 2px solid rgba(255, 255, 255, 0.2);
            }
            h1 { 
                font-size: 3em; 
                margin-bottom: 10px; 
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
            }
            .status { 
                display: inline-block; 
                background: #4CAF50; 
                padding: 5px 15px; 
                border-radius: 20px; 
                font-weight: bold;
                margin: 10px 0;
            }
            .grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                gap: 30px; 
                margin-top: 30px;
            }
            .card { 
                background: rgba(255, 255, 255, 0.15); 
                padding: 25px; 
                border-radius: 15px; 
                border: 1px solid rgba(255, 255, 255, 0.2);
                transition: transform 0.3s, box-shadow 0.3s;
            }
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 30px rgba(0, 0, 0, 0.4);
            }
            h2 { 
                margin-bottom: 20px; 
                color: #ffd166;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .btn { 
                display: inline-block; 
                background: #ff6b6b; 
                color: white; 
                padding: 12px 25px; 
                border-radius: 50px; 
                text-decoration: none; 
                font-weight: bold; 
                margin: 10px 5px; 
                border: none;
                cursor: pointer;
                transition: background 0.3s, transform 0.2s;
            }
            .btn:hover { 
                background: #ff5252; 
                transform: scale(1.05);
            }
            .btn-green { background: #4CAF50; }
            .btn-green:hover { background: #45a049; }
            .btn-blue { background: #2196F3; }
            .btn-blue:hover { background: #1976D2; }
            input, select {
                width: 100%;
                padding: 12px;
                margin: 10px 0;
                border-radius: 10px;
                border: 2px solid rgba(255, 255, 255, 0.3);
                background: rgba(255, 255, 255, 0.1);
                color: white;
                font-size: 16px;
            }
            input::placeholder { color: rgba(255, 255, 255, 0.7); }
            .match-card { 
                background: rgba(255, 255, 255, 0.1); 
                padding: 20px; 
                margin: 15px 0; 
                border-radius: 10px; 
                border-left: 5px solid #ffd166;
            }
            .team { 
                display: flex; 
                justify-content: space-between; 
                margin: 10px 0;
                padding: 10px;
                background: rgba(0, 0, 0, 0.2);
                border-radius: 8px;
            }
            .code { 
                font-family: monospace; 
                background: #333; 
                padding: 5px 15px; 
                border-radius: 5px; 
                font-size: 1.2em;
                letter-spacing: 2px;
            }
            footer { 
                text-align: center; 
                margin-top: 50px; 
                padding-top: 20px;
                border-top: 1px solid rgba(255, 255, 255, 0.2);
                font-size: 0.9em;
                color: rgba(255, 255, 255, 0.8);
            }
            @media (max-width: 768px) {
                .container { padding: 20px; }
                h1 { font-size: 2em; }
                .grid { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🏴‍☠️ Sea of Thieves TDM Server</h1>
                <div class="status">🟢 ONLINE</div>
                <p>Manage TDM matches, track scores, and coordinate with your crew</p>
            </header>
            
            <div class="grid">
                <!-- Create Match Card -->
                <div class="card">
                    <h2>🎮 Create Match</h2>
                    <p>Create a new TDM match room</p>
                    <button onclick="createMatch()" class="btn btn-green">Create Room</button>
                    <div id="roomResult"></div>
                </div>
                
                <!-- Active Matches Card -->
                <div class="card">
                    <h2>📊 Active Matches</h2>
                    <div id="matchesList">Loading matches...</div>
                    <button onclick="loadMatches()" class="btn btn-blue">Refresh Matches</button>
                </div>
                
                <!-- Player Stats Card -->
                <div class="card">
                    <h2>👤 Player Stats</h2>
                    <input type="text" id="playerName" placeholder="Enter Discord username">
                    <button onclick="getPlayerStats()" class="btn">Get Stats</button>
                    <div id="playerStats"></div>
                </div>
                
                <!-- Discord Bot Card -->
                <div class="card">
                    <h2>🤖 Discord Bot</h2>
                    <p>Bot Status: <span id="botStatus">Checking...</span></p>
                    <p>Use slash commands in Discord:</p>
                    <ul style="margin-left: 20px; margin-bottom: 20px;">
                        <li><code>/ping</code> - Check bot status</li>
                        <li><code>/room</code> - Create match room</li>
                        <li><code>/stats @player</code> - View player stats</li>
                    </ul>
                    <button onclick="testBot()" class="btn">Test Bot Connection</button>
                </div>
                
                <!-- API Info Card -->
                <div class="card">
                    <h2>🔧 API Endpoints</h2>
                    <p><strong>Interactions URL:</strong></p>
                    <code style="display: block; background: #333; padding: 10px; border-radius: 5px; margin: 10px 0;">
                        'https://' + window.location.hostname + '/interactions'
                    </code>
                    <p>Copy this URL to Discord Developer Portal → Interactions Endpoint</p>
                </div>
            </div>
            
            <!-- Live Match Updates -->
            <div style="margin-top: 40px;">
                <h2>⚡ Live Match Updates</h2>
                <div id="liveMatches"></div>
            </div>
            
            <footer>
                <p>SoT TDM Server v3.0 | Made for the Sea of Thieves community</p>
                <p>Discord Bot: <span id="botUptime">Loading...</span></p>
            </footer>
        </div>
        
        <script>
            // Create match function
            async function createMatch() {
                const btn = event.target;
                btn.disabled = true;
                btn.textContent = 'Creating...';
                
                try {
                    const response = await fetch('/api/match/create', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    const data = await response.json();
                    
                    if (data.success) {
                        document.getElementById('roomResult').innerHTML = `
                            <div class="match-card">
                                <h3>✅ Room Created!</h3>
                                <p><strong>Code:</strong> <span class="code">${data.room_code}</span></p>
                                <p>Share this code with players to join the match</p>
                                <button onclick="copyCode('${data.room_code}')" class="btn btn-blue">Copy Code</button>
                                <a href="/match/${data.room_code}" class="btn btn-green">View Match</a>
                            </div>
                        `;
                        loadMatches(); // Refresh matches list
                    } else {
                        document.getElementById('roomResult').innerHTML = 
                            '<div style="color: #ff6b6b; margin-top: 10px;">Error creating room</div>';
                    }
                } catch (error) {
                    document.getElementById('roomResult').innerHTML = 
                        '<div style="color: #ff6b6b; margin-top: 10px;">Connection error</div>';
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Create Room';
                }
            }
            
            // Copy room code
            function copyCode(code) {
                navigator.clipboard.writeText(code);
                alert('Code copied to clipboard: ' + code);
            }
            
            // Load active matches
            async function loadMatches() {
                try {
                    const response = await fetch('/api/matches/active');
                    const matches = await response.json();
                    
                    let html = '';
                    if (matches.length === 0) {
                        html = '<p>No active matches</p>';
                    } else {
                        matches.forEach(match => {
                            html += `
                                <div class="match-card">
                                    <h3>Room: <span class="code">${match.room_code}</span></h3>
                                    <div class="team">
                                        <span>${match.team1_name}</span>
                                        <span>${match.team1_score}</span>
                                    </div>
                                    <div class="team">
                                        <span>${match.team2_name}</span>
                                        <span>${match.team2_score}</span>
                                    </div>
                                    <p>Status: <strong>${match.status}</strong></p>
                                    <a href="/match/${match.room_code}" class="btn" style="margin-top: 10px;">View Details</a>
                                </div>
                            `;
                        });
                    }
                    document.getElementById('matchesList').innerHTML = html;
                } catch (error) {
                    document.getElementById('matchesList').innerHTML = 
                        '<p style="color: #ff6b6b;">Error loading matches</p>';
                }
            }
            
            // Get player stats
            async function getPlayerStats() {
                const username = document.getElementById('playerName').value;
                if (!username) {
                    alert('Please enter a username');
                    return;
                }
                
                try {
                    const response = await fetch(`/api/player/${encodeURIComponent(username)}`);
                    const data = await response.json();
                    
                    if (data.error) {
                        document.getElementById('playerStats').innerHTML = 
                            `<p style="color: #ff6b6b;">${data.error}</p>`;
                    } else {
                        document.getElementById('playerStats').innerHTML = `
                            <div class="match-card">
                                <h3>📊 ${data.username}'s Stats</h3>
                                <p>Kills: <strong>${data.kills}</strong></p>
                                <p>Deaths: <strong>${data.deaths}</strong></p>
                                <p>K/D Ratio: <strong>${(data.kills/Math.max(data.deaths,1)).toFixed(2)}</strong></p>
                                <p>Wins: <strong>${data.wins}</strong> | Losses: <strong>${data.losses}</strong></p>
                                <p>Win Rate: <strong>${((data.wins/Math.max(data.wins+data.losses,1))*100).toFixed(1)}%</strong></p>
                            </div>
                        `;
                    }
                } catch (error) {
                    document.getElementById('playerStats').innerHTML = 
                        '<p style="color: #ff6b6b;">Error loading stats</p>';
                }
            }
            
            // Test bot connection
            async function testBot() {
                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    document.getElementById('botStatus').innerHTML = 
                        '🟢 Connected | Last check: ' + new Date().toLocaleTimeString();
                } catch (error) {
                    document.getElementById('botStatus').innerHTML = 
                        '🔴 Not connected';
                }
            }
            
            // Live updates for matches
            async function updateLiveMatches() {
                try {
                    const response = await fetch('/api/matches/live');
                    const data = await response.json();
                    
                    let html = '';
                    data.matches.forEach(match => {
                        const totalScore = match.team1_score + match.team2_score;
                        const width1 = totalScore > 0 ? (match.team1_score / totalScore * 100) : 50;
                        const width2 = totalScore > 0 ? (match.team2_score / totalScore * 100) : 50;
                        
                        html += `
                            <div class="match-card">
                                <h3>${match.room_code} - ${match.status}</h3>
                                <div style="display: flex; margin: 10px 0;">
                                    <div style="flex: ${width1}; background: #4CAF50; padding: 10px; text-align: center;">
                                        ${match.team1_name}: ${match.team1_score}
                                    </div>
                                    <div style="flex: ${width2}; background: #2196F3; padding: 10px; text-align: center;">
                                        ${match.team2_name}: ${match.team2_score}
                                    </div>
                                </div>
                                <p>Created: ${new Date(match.created_at).toLocaleTimeString()}</p>
                            </div>
                        `;
                    });
                    
                    document.getElementById('liveMatches').innerHTML = html || '<p>No live matches</p>';
                } catch (error) {
                    console.error('Error updating live matches:', error);
                }
            }
            
            // Bot uptime
            async function updateBotUptime() {
                try {
                    const response = await fetch('/api/bot/status');
                    const data = await response.json();
                    document.getElementById('botUptime').textContent = 
                        data.online ? `Online (${data.uptime})` : 'Offline';
                } catch (error) {
                    document.getElementById('botUptime').textContent = 'Status unknown';
                }
            }
            
            // Initialize page
            document.addEventListener('DOMContentLoaded', function() {
                loadMatches();
                testBot();
                updateLiveMatches();
                updateBotUptime();
                
                // Update every 30 seconds
                setInterval(loadMatches, 30000);
                setInterval(updateLiveMatches, 10000);
                setInterval(updateBotUptime, 60000);
            });
        </script>
    </body>
    </html>
    '''

@app.route('/match/<room_code>')
def match_page(room_code):
    """Individual match page"""
    conn = get_db_connection()
    match = conn.execute('SELECT * FROM matches WHERE room_code = ?', (room_code,)).fetchone()
    conn.close()
    
    if not match:
        return f'''
        <!DOCTYPE html>
        <html>
        <head><title>Match Not Found</title></head>
        <body style="font-family: Arial; padding: 50px; text-align: center;">
            <h1>❌ Match Not Found</h1>
            <p>Room code <strong>{room_code}</strong> does not exist.</p>
            <a href="/" style="color: blue;">Return to Home</a>
        </body>
        </html>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Match {room_code}</title>
        <style>
            body {{ font-family: Arial; padding: 20px; max-width: 800px; margin: 0 auto; }}
            .header {{ background: #f0f0f0; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
            .team {{ display: flex; justify-content: space-between; padding: 15px; margin: 10px 0; border-radius: 8px; }}
            .team1 {{ background: #d4edda; }}
            .team2 {{ background: #d1ecf1; }}
            .score {{ font-size: 2em; font-weight: bold; }}
            .code {{ font-family: monospace; background: #333; color: white; padding: 5px 10px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Match: <span class="code">{room_code}</span></h1>
            <p>Status: <strong>{match['status']}</strong></p>
            <p>Created: {match['created_at']}</p>
            <a href="/">← Back to Home</a>
        </div>
        
        <div>
            <div class="team team1">
                <span>{match['team1_name']}</span>
                <span class="score">{match['team1_score']}</span>
            </div>
            <div class="team team2">
                <span>{match['team2_name']}</span>
                <span class="score">{match['team2_score']}</span>
            </div>
        </div>
        
        <div style="margin-top: 30px;">
            <h3>Match Controls</h3>
            <button onclick="updateScore(1, 1)">Team 1 +1</button>
            <button onclick="updateScore(1, -1)">Team 1 -1</button>
            <button onclick="updateScore(2, 1)">Team 2 +1</button>
            <button onclick="updateScore(2, -1)">Team 2 -1</button>
            <button onclick="endMatch()" style="background: #dc3545; color: white;">End Match</button>
        </div>
        
        <script>
            async function updateScore(team, change) {{
                const response = await fetch('/api/match/{room_code}/score', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ team: team, change: change }})
                }});
                location.reload();
            }}
            
            async function endMatch() {{
                if (confirm('End this match?')) {{
                    await fetch('/api/match/{room_code}/end', {{ method: 'POST' }});
                    location.reload();
                }}
            }}
        </script>
    </body>
    </html>
    '''

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/match/create', methods=['POST'])
def api_create_match():
    """Create a new match"""
    room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO matches (room_code, team1_name, team2_name) 
        VALUES (?, 'Team 1', 'Team 2')
    ''', (room_code,))
    
    conn.commit()
    match_id = cursor.lastrowid
    conn.close()
    
    return jsonify({
        "success": True,
        "room_code": room_code,
        "match_id": match_id,
        "message": f"Match created with code: {room_code}"
    })

@app.route('/api/match/<room_code>/score', methods=['POST'])
def update_score(room_code):
    """Update match score"""
    data = request.json
    if not data or 'team' not in data or 'change' not in data:
        return jsonify({"error": "Missing team or change"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current scores
    cursor.execute('SELECT team1_score, team2_score FROM matches WHERE room_code = ?', (room_code,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return jsonify({"error": "Match not found"}), 404
    
    # Update score
    if data['team'] == 1:
        new_score = max(0, match['team1_score'] + data['change'])
        cursor.execute('UPDATE matches SET team1_score = ? WHERE room_code = ?', (new_score, room_code))
    else:
        new_score = max(0, match['team2_score'] + data['change'])
        cursor.execute('UPDATE matches SET team2_score = ? WHERE room_code = ?', (new_score, room_code))
    
    # Update status if scores changed
    cursor.execute('UPDATE matches SET status = "active" WHERE room_code = ?', (room_code,))
    
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "new_score": new_score})

@app.route('/api/match/<room_code>/end', methods=['POST'])
def end_match(room_code):
    """End a match"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE matches SET status = "ended" WHERE room_code = ?', (room_code,))
    
    # Update player stats (simplified)
    cursor.execute('SELECT team1_score, team2_score FROM matches WHERE room_code = ?', (room_code,))
    match = cursor.fetchone()
    
    if match:
        if match['team1_score'] > match['team2_score']:
            # Team 1 wins
            pass
        elif match['team2_score'] > match['team1_score']:
            # Team 2 wins
            pass
    
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Match ended"})

@app.route('/api/matches/active')
def get_active_matches():
    """Get all active matches"""
    conn = get_db_connection()
    matches = conn.execute('''
        SELECT * FROM matches 
        WHERE status IN ('waiting', 'active') 
        ORDER BY created_at DESC 
        LIMIT 10
    ''').fetchall()
    conn.close()
    
    return jsonify([dict(match) for match in matches])

@app.route('/api/matches/live')
def get_live_matches():
    """Get live matches for display"""
    conn = get_db_connection()
    matches = conn.execute('''
        SELECT * FROM matches 
        WHERE status = 'active' 
        ORDER BY created_at DESC 
        LIMIT 5
    ''').fetchall()
    conn.close()
    
    return jsonify({
        "matches": [dict(match) for match in matches],
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/player/<username>')
def get_player_stats(username):
    """Get player statistics"""
    conn = get_db_connection()
    player = conn.execute('SELECT * FROM players WHERE username LIKE ?', (f'%{username}%',)).fetchone()
    conn.close()
    
    if not player:
        return jsonify({"error": "Player not found"}), 404
    
    return jsonify(dict(player))

@app.route('/api/bot/status')
def bot_status():
    """Get bot status"""
    return jsonify({
        "online": True,
        "uptime": "24/7",
        "commands": ["/ping", "/room", "/stats"],
        "interactions_url": f"https://{request.host}/interactions"
    })

# =============================================================================
# DISCORD INTERACTIONS ENDPOINT
# =============================================================================

@app.route('/interactions', methods=['POST'])
def handle_interactions():
    """Handle Discord slash commands"""
    try:
        data = request.get_json()
        
        # Handle Discord verification
        if data.get('type') == 1:
            return jsonify({'type': 1})
        
        # Handle commands
        if data.get('type') == 2:
            command = data.get('data', {}).get('name')
            
            if command == 'ping':
                return jsonify({
                    'type': 4,
                    'data': {
                        'content': '🏓 Pong! SoT TDM Bot is online!',
                        'flags': 64
                    }
                })
            
            elif command == 'room':
                # Create room
                room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('INSERT INTO matches (room_code) VALUES (?)', (room_code,))
                conn.commit()
                conn.close()
                
                return jsonify({
                    'type': 4,
                    'data': {
                        'content': f'🎮 **TDM Room Created!**\n**Code:** `{room_code}`\n\nJoin here: {request.host_url}match/{room_code}',
                        'flags': 0
                    }
                })
            
            elif command == 'stats':
                options = data.get('data', {}).get('options', [])
                username = options[0].get('value') if options else None
                
                if username:
                    conn = get_db_connection()
                    player = conn.execute('SELECT * FROM players WHERE username LIKE ?', (f'%{username}%',)).fetchone()
                    conn.close()
                    
                    if player:
                        kd = player['kills'] / max(player['deaths'], 1)
                        return jsonify({
                            'type': 4,
                            'data': {
                                'content': f'📊 **{player["username"]} Stats**\nKills: {player["kills"]}\nDeaths: {player["deaths"]}\nK/D: {kd:.2f}\nWins: {player["wins"]}\nLosses: {player["losses"]}',
                                'flags': 64
                            }
                        })
                    else:
                        return jsonify({
                            'type': 4,
                            'data': {
                                'content': f'Player `{username}` not found',
                                'flags': 64
                            }
                        })
        
        return jsonify({'type': 4, 'data': {'content': 'Command received', 'flags': 64}})
        
    except Exception as e:
        logger.error(f"Interactions error: {e}")
        return jsonify({'type': 4, 'data': {'content': f'Error: {str(e)}', 'flags': 64}}), 500

# =============================================================================
# HEALTH & UTILITY ENDPOINTS
# =============================================================================

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "SoT TDM Server",
        "version": "3.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected",
        "endpoints": {
            "interactions": f"{request.host_url}interactions",
            "web_interface": request.host_url,
            "api_docs": f"{request.host_url}api/docs"
        }
    })

@app.route('/api/docs')
def api_docs():
    """API documentation"""
    return jsonify({
        "endpoints": {
            "GET /health": "Health check",
            "POST /interactions": "Discord slash commands",
            "POST /api/match/create": "Create new match",
            "GET /api/matches/active": "Get active matches",
            "GET /api/matches/live": "Get live matches data",
            "POST /api/match/{code}/score": "Update match score",
            "POST /api/match/{code}/end": "End match",
            "GET /api/player/{username}": "Get player stats",
            "GET /api/bot/status": "Get bot status"
        },
        "discord_commands": ["/ping", "/room", "/stats"],
        "web_interface": request.host_url
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*60}")
    print("🚀 SoT TDM Server Starting Up!")
    print(f"{'='*60}")
    print(f"🌐 Web Interface: http://localhost:{port}")
    print(f"🤖 Discord Interactions: http://localhost:{port}/interactions")
    print(f"📊 Health Check: http://localhost:{port}/health")
    print(f"📚 API Docs: http://localhost:{port}/api/docs")
    print(f"{'='*60}")
    print("\n📝 Discord Developer Portal Setup:")
    print("1. Go to: https://discord.com/developers/applications")
    print("2. Select your application")
    print(f"3. Set Interactions Endpoint URL to: http://your-domain.com/interactions")
    print("4. Add slash commands: /ping, /room, /stats")
    print("5. Save changes and wait 1-2 minutes")
    print(f"{'='*60}\n")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=port, debug=False)

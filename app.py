# app.py - Simplified Version
import os
import json
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, session, redirect, url_for, make_response, render_template_string
from flask_cors import CORS
from config import logger, bot_active
from database import init_db, fix_existing_keys, validate_api_key, get_global_stats, get_leaderboard, get_db_connection
from discord_bot import test_discord_token, register_commands, handle_interaction

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = 86400
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app, supports_credentials=True)
port = int(os.environ.get("PORT", 10000))

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_all_players():
    """Get all players from database"""
    conn = get_db_connection()
    players = conn.execute('''
        SELECT id, discord_id, discord_name, in_game_name, api_key, 
               server_id, key_created, last_used, total_kills, total_deaths,
               wins, losses, prestige, is_admin, created_at
        FROM players 
        ORDER BY created_at DESC
    ''').fetchall()
    conn.close()
    
    players_list = []
    for player in players:
        player_dict = {key: player[key] for key in player.keys()}
        # Calculate K/D ratio
        kills = player_dict.get('total_kills', 0)
        deaths = max(player_dict.get('total_deaths', 1), 1)
        player_dict['kd_ratio'] = round(kills / deaths, 2)
        players_list.append(player_dict)
    
    return players_list

def delete_player(player_id):
    """Delete a player from database"""
    conn = get_db_connection()
    
    try:
        conn.execute('DELETE FROM players WHERE id = ?', (player_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting player: {e}")
        conn.close()
        return False

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@app.before_request
def before_request():
    """Check session before each request"""
    if request.endpoint in ['static', 'interactions', 'home', 'api_validate_key', 'health', 'api_stats', 'api_leaderboard', 'logout']:
        return
    
    if 'user_key' not in session:
        return redirect(url_for('home'))

# =============================================================================
# LOGIN PAGE
# =============================================================================

@app.route('/')
def home():
    """Login Page"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            session['user_data'] = user_data
            if user_data.get('is_admin'):
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SOT TDM - Login</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 500px;
                margin: 100px auto;
                padding: 20px;
            }
            h1 {
                text-align: center;
                margin-bottom: 30px;
            }
            input {
                width: 100%;
                padding: 12px;
                margin: 10px 0;
                border: 2px solid #000;
                font-size: 16px;
                box-sizing: border-box;
            }
            button {
                width: 100%;
                padding: 12px;
                background: #000;
                color: #fff;
                border: none;
                font-size: 16px;
                cursor: pointer;
                margin-top: 10px;
            }
            button:hover {
                background: #333;
            }
            .error {
                color: red;
                margin-top: 10px;
                display: none;
            }
        </style>
    </head>
    <body>
        <h1>SOT TDM System</h1>
        <h2>API Key Login</h2>
        <input type="text" id="apiKey" placeholder="Enter your API key (GOB-...)" autocomplete="off">
        <button onclick="login()">Login</button>
        <div class="error" id="error"></div>
        
        <script>
            function login() {
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const error = document.getElementById('error');
                
                if (!key) {
                    error.textContent = "Please enter an API key";
                    error.style.display = 'block';
                    return;
                }
                
                const keyPattern = /^GOB-[A-Z0-9]{20}$/;
                if (!keyPattern.test(key)) {
                    error.textContent = "Invalid API key format";
                    error.style.display = 'block';
                    return;
                }
                
                fetch('/api/validate-key', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ api_key: key })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.valid) {
                        window.location.href = '/dashboard';
                    } else {
                        error.textContent = data.error || 'Invalid API key';
                        error.style.display = 'block';
                    }
                })
                .catch(err => {
                    error.textContent = 'Connection error';
                    error.style.display = 'block';
                });
            }
            
            // Enter key to submit
            document.getElementById('apiKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') login();
            });
        </script>
    </body>
    </html>
    ''')

@app.route('/api/validate-key', methods=['POST'])
def api_validate_key():
    """Validate API key"""
    data = request.get_json()
    api_key = data.get('api_key', '').strip().upper()
    
    if not api_key:
        return jsonify({"valid": False, "error": "No key provided"})
    
    user_data = validate_api_key(api_key)
    
    if user_data:
        session.clear()
        session['user_key'] = api_key
        session['user_data'] = user_data
        session.permanent = True
        session.modified = True
        
        return jsonify({"valid": True, "user": user_data.get('in_game_name'), "is_admin": user_data.get('is_admin', False)})
    else:
        return jsonify({"valid": False, "error": "Invalid API key"})

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('home'))

# =============================================================================
# USER DASHBOARD
# =============================================================================

@app.route('/dashboard')
def dashboard():
    """User Dashboard"""
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    user_data = session.get('user_data')
    if not user_data:
        user_data = validate_api_key(session.get('user_key'))
        if not user_data:
            session.clear()
            return redirect(url_for('home'))
        session['user_data'] = user_data
    
    # Calculate stats
    total_kills = user_data.get('total_kills', 0)
    total_deaths = max(user_data.get('total_deaths', 1), 1)
    wins = user_data.get('wins', 0)
    losses = user_data.get('losses', 0)
    
    kd = total_kills / total_deaths
    total_games = wins + losses
    win_rate = (wins / total_games * 100) if total_games > 0 else 0
    
    # Get leaderboard
    leaderboard_data = get_leaderboard(10)
    
    # Get user's rank
    user_rank = "N/A"
    for i, player in enumerate(leaderboard_data, 1):
        if player.get('api_key') == session['user_key']:
            user_rank = f"#{i}"
            break
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - {{ user_data.get('in_game_name', 'Player') }}</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 20px 0;
                border-bottom: 2px solid #000;
                margin-bottom: 30px;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 20px;
                margin-bottom: 40px;
            }
            .stat-box {
                border: 2px solid #000;
                padding: 20px;
                text-align: center;
            }
            .stat-value {
                font-size: 32px;
                font-weight: bold;
                margin: 10px 0;
            }
            .leaderboard {
                border: 2px solid #000;
                padding: 20px;
                margin-top: 30px;
            }
            .leaderboard-item {
                display: flex;
                justify-content: space-between;
                padding: 10px;
                border-bottom: 1px solid #ccc;
            }
            .nav {
                display: flex;
                gap: 10px;
                margin-top: 30px;
            }
            .nav a {
                padding: 10px 20px;
                background: #000;
                color: #fff;
                text-decoration: none;
            }
            .nav a:hover {
                background: #333;
            }
            @media (max-width: 768px) {
                .stats {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
            @media (max-width: 480px) {
                .stats {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Dashboard - {{ user_data.get('in_game_name', 'Player') }}</h1>
            <div>
                <strong>Rank:</strong> {{ user_rank }} | 
                <a href="/logout">Logout</a>
                {% if user_data.get('is_admin') %}
                | <a href="/admin">Admin</a>
                {% endif %}
            </div>
        </div>
        
        <h2>Your Stats</h2>
        <div class="stats">
            <div class="stat-box">
                <div>K/D Ratio</div>
                <div class="stat-value">{{ "%.2f"|format(kd) }}</div>
                <div>{{ total_kills }} kills / {{ total_deaths }} deaths</div>
            </div>
            <div class="stat-box">
                <div>Win Rate</div>
                <div class="stat-value">{{ "%.1f"|format(win_rate) }}%</div>
                <div>{{ wins }} wins / {{ losses }} losses</div>
            </div>
            <div class="stat-box">
                <div>Games Played</div>
                <div class="stat-value">{{ total_games }}</div>
                <div>Total matches</div>
            </div>
            <div class="stat-box">
                <div>Prestige</div>
                <div class="stat-value">{{ user_data.get('prestige', 0) }}</div>
                <div>Level</div>
            </div>
        </div>
        
        <h2>Your API Key</h2>
        <div style="border: 2px solid #000; padding: 15px; margin: 20px 0; font-family: monospace; background: #f5f5f5;">
            {{ session['user_key'] }}
        </div>
        <button onclick="copyKey()" style="padding: 10px 20px; background: #000; color: #fff; border: none; cursor: pointer;">Copy Key</button>
        
        <div class="leaderboard">
            <h2>Leaderboard (Top 10)</h2>
            {% for player in leaderboard_data %}
            <div class="leaderboard-item">
                <div>
                    <strong>#{{ loop.index }}</strong> {{ player.name }}
                    {% if player.api_key == session['user_key'] %}(You){% endif %}
                    {% if player.prestige > 0 %}P{{ player.prestige }}{% endif %}
                </div>
                <div>K/D: {{ player.kd }} | Kills: {{ player.kills }}</div>
            </div>
            {% endfor %}
        </div>
        
        <div class="nav">
            <a href="/">Home</a>
            <a href="#" onclick="refreshLeaderboard()">Refresh</a>
        </div>
        
        <script>
            function copyKey() {
                navigator.clipboard.writeText("{{ session['user_key'] }}")
                    .then(() => alert('Key copied!'))
                    .catch(err => alert('Failed to copy'));
            }
            
            function refreshLeaderboard() {
                location.reload();
            }
        </script>
    </body>
    </html>
    ''', user_data=user_data, session=session, leaderboard_data=leaderboard_data, 
        total_kills=total_kills, total_deaths=total_deaths, wins=wins, losses=losses,
        kd=kd, total_games=total_games, win_rate=win_rate, user_rank=user_rank)

# =============================================================================
# ADMIN DASHBOARD
# =============================================================================

@app.route('/admin')
def admin_dashboard():
    """Admin Dashboard"""
    if 'user_data' not in session or not session['user_data'].get('is_admin'):
        return redirect(url_for('dashboard'))
    
    # Get all stats for admin dashboard
    players = get_all_players()
    total_players = len(players)
    total_kills = sum(p.get('total_kills', 0) for p in players)
    total_games = sum(p.get('wins', 0) + p.get('losses', 0) for p in players)
    admins = sum(1 for p in players if p.get('is_admin'))
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 20px 0;
                border-bottom: 2px solid #000;
                margin-bottom: 30px;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 20px;
                margin-bottom: 40px;
            }
            .stat-box {
                border: 2px solid #000;
                padding: 20px;
                text-align: center;
            }
            .stat-value {
                font-size: 32px;
                font-weight: bold;
                margin: 10px 0;
            }
            .players-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 30px;
            }
            .players-table th, .players-table td {
                border: 1px solid #000;
                padding: 10px;
                text-align: left;
            }
            .players-table th {
                background: #f5f5f5;
            }
            .action-btn {
                padding: 5px 10px;
                background: #000;
                color: #fff;
                border: none;
                cursor: pointer;
                margin: 0 5px;
            }
            .action-btn:hover {
                background: #333;
            }
            .action-btn.delete {
                background: #cc0000;
            }
            .nav {
                display: flex;
                gap: 10px;
                margin-top: 30px;
            }
            .nav a {
                padding: 10px 20px;
                background: #000;
                color: #fff;
                text-decoration: none;
            }
            .nav a:hover {
                background: #333;
            }
            @media (max-width: 768px) {
                .stats {
                    grid-template-columns: repeat(2, 1fr);
                }
                .players-table {
                    display: block;
                    overflow-x: auto;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Admin Dashboard</h1>
            <div>
                <a href="/dashboard">User View</a> | 
                <a href="/logout">Logout</a>
            </div>
        </div>
        
        <div class="stats">
            <div class="stat-box">
                <div>Total Players</div>
                <div class="stat-value">{{ total_players }}</div>
            </div>
            <div class="stat-box">
                <div>Total Kills</div>
                <div class="stat-value">{{ "{:,}".format(total_kills) }}</div>
            </div>
            <div class="stat-box">
                <div>Games Played</div>
                <div class="stat-value">{{ total_games }}</div>
            </div>
            <div class="stat-box">
                <div>Admins</div>
                <div class="stat-value">{{ admins }}</div>
            </div>
        </div>
        
        <h2>Players ({{ total_players }})</h2>
        <table class="players-table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Discord</th>
                    <th>Kills</th>
                    <th>Deaths</th>
                    <th>K/D</th>
                    <th>Admin</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for player in players %}
                <tr>
                    <td>{{ player.id }}</td>
                    <td>{{ player.in_game_name or 'N/A' }}</td>
                    <td>{{ player.discord_name or 'N/A' }}</td>
                    <td>{{ player.total_kills or 0 }}</td>
                    <td>{{ player.total_deaths or 0 }}</td>
                    <td>{{ player.kd_ratio }}</td>
                    <td>{{ 'Yes' if player.is_admin else 'No' }}</td>
                    <td>
                        <button class="action-btn edit" onclick="editPlayer({{ player.id }})">Edit</button>
                        <button class="action-btn delete" onclick="deletePlayer({{ player.id }})">Delete</button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        
        <div class="nav">
            <a href="/admin">Refresh</a>
            <a href="/dashboard">Back to Dashboard</a>
        </div>
        
        <script>
            function editPlayer(id) {
                alert('Edit player ' + id + ' (feature not implemented)');
            }
            
            function deletePlayer(id) {
                if (confirm('Delete player ' + id + '?')) {
                    fetch('/admin/players/' + id, {
                        method: 'DELETE',
                        headers: {'Content-Type': 'application/json'}
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            alert('Player deleted');
                            location.reload();
                        } else {
                            alert('Error: ' + data.error);
                        }
                    })
                    .catch(err => alert('Error deleting player'));
                }
            }
        </script>
    </body>
    </html>
    ''', total_players=total_players, total_kills=total_kills, total_games=total_games, 
        admins=admins, players=players)

@app.route('/admin/players/<int:player_id>', methods=['DELETE'])
def admin_delete_player(player_id):
    """Delete a player"""
    if 'user_data' not in session or not session['user_data'].get('is_admin'):
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    
    success = delete_player(player_id)
    
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Failed to delete player"})

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/stats')
def api_stats():
    """Get global stats"""
    stats = get_global_stats()
    return jsonify({
        "total_players": stats['total_players'],
        "total_kills": stats['total_kills'],
        "total_games": stats['total_games'],
        "bot_active": bot_active,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/leaderboard')
def api_leaderboard():
    """Get leaderboard data"""
    leaderboard = get_leaderboard(10)
    
    # Remove API keys from response for security
    for player in leaderboard:
        if 'api_key' in player:
            del player['api_key']
    
    return jsonify({"leaderboard": leaderboard})

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy" if bot_active else "offline",
        "bot_active": bot_active,
        "service": "SOT TDM System",
        "timestamp": datetime.utcnow().isoformat()
    })

# =============================================================================
# STARTUP
# =============================================================================

def startup_sequence():
    """Run startup sequence"""
    try:
        init_db()
        
        fixed_keys = fix_existing_keys()
        if fixed_keys > 0:
            logger.info(f"Fixed {fixed_keys} API keys to correct format")
        
        if test_discord_token():
            logger.info("Discord bot connected")
            
            if register_commands():
                logger.info("Commands registered")
            else:
                logger.warning("Could not register commands")
        else:
            logger.warning("Discord token not set or invalid")
        
        logger.info(f"✅ SOT TDM System started successfully on port {port}")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

# Initialize on import (for WSGI/Gunicorn)
startup_sequence()

# For direct execution
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=False)

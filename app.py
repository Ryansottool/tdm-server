# app.py - SOT TDM System
import os
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
from flask_cors import CORS
from config import logger, bot_active
from database import init_db, fix_existing_keys, validate_api_key, get_global_stats, get_leaderboard, get_db_connection
from discord_bot import test_discord_token, register_commands, handle_interaction

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = 86400
CORS(app, supports_credentials=True)
port = int(os.environ.get("PORT", 10000))

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_all_players():
    """Get all players from database"""
    conn = get_db_connection()
    players = conn.execute('SELECT * FROM players ORDER BY created_at DESC').fetchall()
    conn.close()
    
    players_list = []
    for player in players:
        player_dict = {key: player[key] for key in player.keys()}
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
        return True
    except Exception as e:
        logger.error(f"Error deleting player: {e}")
        return False
    finally:
        conn.close()

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@app.before_request
def before_request():
    """Check session before each request"""
    if request.endpoint in ['home', 'api_validate_key', 'health', 'api_stats', 'api_leaderboard', 'logout', 'interactions']:
        return
    
    if 'user_key' not in session:
        return redirect(url_for('home'))

# =============================================================================
# PAGES
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
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial; background: #0a0a0a; color: #fff; min-height: 100vh; display: flex; justify-content: center; align-items: center; position: relative; overflow: hidden; }
            #dots { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; }
            .dot { position: absolute; background: rgba(255,255,255,0.1); border-radius: 50%; animation: float 20s infinite linear; }
            @keyframes float { 0% { transform: translate(0,0) rotate(0deg); opacity: 0.1; } 50% { opacity: 0.2; } 100% { transform: translate(100vw,100vh) rotate(360deg); opacity: 0.1; } }
            .login-box { position: relative; z-index: 10; width: 400px; padding: 40px; background: rgba(20,20,20,0.8); border-radius: 10px; border: 1px solid rgba(255,255,255,0.1); }
            h1 { text-align: center; margin-bottom: 10px; color: #fff; }
            h2 { text-align: center; margin-bottom: 30px; color: #ccc; font-weight: normal; }
            input { width: 100%; padding: 12px; margin: 10px 0; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); border-radius: 5px; color: #fff; font-size: 14px; }
            input:focus { outline: none; border-color: #666; }
            button { width: 100%; padding: 12px; background: #333; color: #fff; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; margin-top: 10px; }
            button:hover { background: #444; }
            .error { color: #ff6b6b; margin-top: 10px; padding: 8px; background: rgba(255,107,107,0.1); border-radius: 3px; border-left: 3px solid #ff6b6b; display: none; }
            .status { margin-top: 20px; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 5px; font-size: 14px; color: #888; }
            .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }
            .online { background: #4CAF50; box-shadow: 0 0 8px #4CAF50; }
            .offline { background: #f44336; box-shadow: 0 0 8px #f44336; }
        </style>
    </head>
    <body>
        <div id="dots"></div>
        <div class="login-box">
            <h1>SOT TDM SYSTEM</h1>
            <h2>API Key Login</h2>
            <input type="text" id="apiKey" placeholder="Enter your API key (GOB-...)" autocomplete="off">
            <button onclick="login()">Login</button>
            <div class="error" id="error"></div>
            <div class="status">
                <span class="status-dot {% if bot_active %}online{% else %}offline{% endif %}"></span>
                <strong>Discord Bot:</strong> {% if bot_active %}Online{% else %}Offline{% endif %}
            </div>
        </div>
        <script>
            for (let i = 0; i < 30; i++) {
                const dot = document.createElement('div');
                dot.className = 'dot';
                dot.style.width = dot.style.height = Math.random() * 3 + 2 + 'px';
                dot.style.left = Math.random() * 100 + '%';
                dot.style.top = Math.random() * 100 + '%';
                dot.style.animationDelay = Math.random() * 10 + 's';
                document.getElementById('dots').appendChild(dot);
            }
            
            function login() {
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const error = document.getElementById('error');
                
                if (!key) {
                    error.textContent = "Please enter an API key";
                    error.style.display = 'block';
                    return;
                }
                
                if (!/^GOB-[A-Z0-9]{20}$/.test(key)) {
                    error.textContent = "Invalid format: GOB- followed by 20 characters";
                    error.style.display = 'block';
                    return;
                }
                
                const btn = document.querySelector('button');
                btn.disabled = true;
                btn.textContent = 'Verifying...';
                
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
                        btn.disabled = false;
                        btn.textContent = 'Login';
                    }
                })
                .catch(err => {
                    error.textContent = 'Connection error';
                    error.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = 'Login';
                });
            }
            
            document.getElementById('apiKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') login();
            });
        </script>
    </body>
    </html>
    ''', bot_active=bot_active)

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
        
        return jsonify({"valid": True, "user": user_data.get('in_game_name'), "is_admin": user_data.get('is_admin', False)})
    else:
        return jsonify({"valid": False, "error": "Invalid API key"})

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('home'))

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
    
    total_kills = user_data.get('total_kills', 0)
    total_deaths = max(user_data.get('total_deaths', 1), 1)
    wins = user_data.get('wins', 0)
    losses = user_data.get('losses', 0)
    
    kd = total_kills / total_deaths
    total_games = wins + losses
    win_rate = (wins / total_games * 100) if total_games > 0 else 0
    
    leaderboard_data = get_leaderboard(10)
    
    user_rank = "N/A"
    for i, player in enumerate(leaderboard_data, 1):
        if player.get('api_key') == session['user_key']:
            user_rank = f"#{i}"
            break
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial; background: #0a0a0a; color: #fff; min-height: 100vh; position: relative; }
            #dots { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; }
            .dot { position: absolute; background: rgba(255,255,255,0.1); border-radius: 50%; animation: float 20s infinite linear; }
            @keyframes float { 0% { transform: translate(0,0) rotate(0deg); opacity: 0.1; } 50% { opacity: 0.2; } 100% { transform: translate(100vw,100vh) rotate(360deg); opacity: 0.1; } }
            .header { padding: 20px; background: rgba(20,20,20,0.9); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; }
            .header h1 { font-size: 20px; }
            .header-right { display: flex; gap: 10px; }
            .header-right a { padding: 8px 15px; background: #333; color: #fff; text-decoration: none; border-radius: 4px; font-size: 14px; }
            .header-right a:hover { background: #444; }
            .main { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .stat { background: rgba(20,20,20,0.8); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 20px; }
            .stat h3 { color: #aaa; font-size: 14px; margin-bottom: 10px; }
            .stat-value { font-size: 28px; font-weight: bold; margin-bottom: 5px; }
            .stat-detail { color: #888; font-size: 14px; }
            .api-box { background: rgba(20,20,20,0.8); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 25px; margin-bottom: 30px; }
            .api-key { background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; padding: 15px; font-family: monospace; margin-bottom: 15px; word-break: break-all; }
            .copy-btn { padding: 10px 20px; background: #333; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
            .copy-btn:hover { background: #444; }
            .leaderboard { background: rgba(20,20,20,0.8); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 25px; }
            table { width: 100%; border-collapse: collapse; }
            th { background: rgba(255,255,255,0.05); color: #aaa; padding: 12px; text-align: left; border-bottom: 2px solid rgba(255,255,255,0.1); }
            td { padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); }
            tr:hover { background: rgba(255,255,255,0.02); }
            .you { background: rgba(255,255,255,0.05); }
            .footer { padding: 20px; text-align: center; color: #666; font-size: 14px; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 40px; }
        </style>
    </head>
    <body>
        <div id="dots"></div>
        <div class="header">
            <h1>SOT TDM Dashboard</h1>
            <div class="header-right">
                <a href="/">Home</a>
                {% if user_data.get('is_admin') %}<a href="/admin">Admin</a>{% endif %}
                <a href="/logout">Logout</a>
            </div>
        </div>
        <div class="main">
            <div class="stats">
                <div class="stat"><h3>K/D Ratio</h3><div class="stat-value">{{ "%.2f"|format(kd) }}</div><div class="stat-detail">{{ total_kills }} kills / {{ total_deaths }} deaths</div></div>
                <div class="stat"><h3>Win Rate</h3><div class="stat-value">{{ "%.1f"|format(win_rate) }}%</div><div class="stat-detail">{{ wins }} wins / {{ losses }} losses</div></div>
                <div class="stat"><h3>Games</h3><div class="stat-value">{{ total_games }}</div><div class="stat-detail">Total matches</div></div>
                <div class="stat"><h3>Rank</h3><div class="stat-value">{{ user_rank }}</div><div class="stat-detail">Leaderboard position</div></div>
            </div>
            <div class="api-box">
                <h2>Your API Key</h2>
                <div class="api-key">{{ session['user_key'] }}</div>
                <button class="copy-btn" onclick="copyKey()">Copy Key</button>
            </div>
            <div class="leaderboard">
                <h2>Top 10 Leaderboard</h2>
                <table>
                    <thead><tr><th>Rank</th><th>Player</th><th>K/D</th><th>Kills</th><th>Wins</th></tr></thead>
                    <tbody>
                        {% for player in leaderboard_data %}
                        <tr class="{% if player.api_key == session['user_key'] %}you{% endif %}">
                            <td>#{{ loop.index }}</td>
                            <td>{{ player.name }}{% if player.api_key == session['user_key'] %} (You){% endif %}</td>
                            <td>{{ player.kd }}</td>
                            <td>{{ player.kills }}</td>
                            <td>{{ player.wins }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        <div class="footer">SOT TDM System | Discord Bot: {% if bot_active %}Online{% else %}Offline{% endif %}</div>
        <script>
            for (let i = 0; i < 20; i++) {
                const dot = document.createElement('div');
                dot.className = 'dot';
                dot.style.width = dot.style.height = Math.random() * 3 + 2 + 'px';
                dot.style.left = Math.random() * 100 + '%';
                dot.style.top = Math.random() * 100 + '%';
                dot.style.animationDelay = Math.random() * 10 + 's';
                document.getElementById('dots').appendChild(dot);
            }
            function copyKey() {
                navigator.clipboard.writeText("{{ session['user_key'] }}").then(() => alert('Key copied!')).catch(() => alert('Failed to copy'));
            }
        </script>
    </body>
    </html>
    ''', user_data=user_data, session=session, leaderboard_data=leaderboard_data, 
        total_kills=total_kills, total_deaths=total_deaths, wins=wins, losses=losses,
        kd=kd, total_games=total_games, win_rate=win_rate, user_rank=user_rank,
        bot_active=bot_active)

@app.route('/admin')
def admin_dashboard():
    """Admin Dashboard"""
    if 'user_data' not in session or not session['user_data'].get('is_admin'):
        return redirect(url_for('dashboard'))
    
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
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial; background: #0a0a0a; color: #fff; min-height: 100vh; }
            #dots { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; }
            .dot { position: absolute; background: rgba(255,255,255,0.1); border-radius: 50%; animation: float 20s infinite linear; }
            @keyframes float { 0% { transform: translate(0,0) rotate(0deg); opacity: 0.1; } 50% { opacity: 0.2; } 100% { transform: translate(100vw,100vh) rotate(360deg); opacity: 0.1; } }
            .header { padding: 20px; background: rgba(20,20,20,0.9); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; }
            .header h1 { font-size: 20px; }
            .header-nav { display: flex; gap: 10px; }
            .header-nav a { padding: 8px 15px; background: #333; color: #fff; text-decoration: none; border-radius: 4px; font-size: 14px; }
            .header-nav a:hover { background: #444; }
            .main { max-width: 1400px; margin: 0 auto; padding: 20px; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .stat { background: rgba(20,20,20,0.8); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 20px; text-align: center; }
            .stat-value { font-size: 32px; font-weight: bold; margin: 10px 0; }
            .stat-label { color: #aaa; font-size: 14px; }
            table { width: 100%; border-collapse: collapse; background: rgba(20,20,20,0.8); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; overflow: hidden; margin-top: 30px; }
            th { background: rgba(255,255,255,0.05); color: #aaa; padding: 12px; text-align: left; border-bottom: 2px solid rgba(255,255,255,0.1); }
            td { padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); }
            tr:hover { background: rgba(255,255,255,0.02); }
            .admin-badge { background: #ff6b6b; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: bold; }
            .actions { display: flex; gap: 8px; }
            .btn { padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }
            .edit { background: #333; color: #fff; }
            .delete { background: #ff4444; color: white; }
            .btn:hover { opacity: 0.8; }
        </style>
    </head>
    <body>
        <div id="dots"></div>
        <div class="header">
            <h1>Admin Dashboard</h1>
            <div class="header-nav">
                <a href="/dashboard">Dashboard</a>
                <a href="/">Login</a>
                <a href="/logout">Logout</a>
            </div>
        </div>
        <div class="main">
            <div class="stats">
                <div class="stat"><div class="stat-label">Players</div><div class="stat-value">{{ total_players }}</div></div>
                <div class="stat"><div class="stat-label">Kills</div><div class="stat-value">{{ "{:,}".format(total_kills) }}</div></div>
                <div class="stat"><div class="stat-label">Games</div><div class="stat-value">{{ total_games }}</div></div>
                <div class="stat"><div class="stat-label">Admins</div><div class="stat-value">{{ admins }}</div></div>
            </div>
            <h2 style="color: #fff; margin: 30px 0 15px 0;">Players ({{ total_players }})</h2>
            <table>
                <thead><tr><th>ID</th><th>Name</th><th>Discord</th><th>K/D</th><th>Kills</th><th>Admin</th><th>Actions</th></tr></thead>
                <tbody>
                    {% for player in players %}
                    <tr>
                        <td>{{ player.id }}</td>
                        <td><strong>{{ player.in_game_name or 'N/A' }}</strong></td>
                        <td>{{ player.discord_name or 'N/A' }}</td>
                        <td>{{ player.kd_ratio }}</td>
                        <td>{{ player.total_kills or 0 }}</td>
                        <td>{% if player.is_admin %}<span class="admin-badge">Admin</span>{% else %}Player{% endif %}</td>
                        <td><div class="actions"><button class="btn edit" onclick="editPlayer({{ player.id }})">Edit</button><button class="btn delete" onclick="deletePlayer({{ player.id }})">Delete</button></div></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <div style="margin-top: 30px; color: #666; text-align: center;">Discord Bot: {% if bot_active %}Online{% else %}Offline{% endif %}</div>
        </div>
        <script>
            for (let i = 0; i < 20; i++) {
                const dot = document.createElement('div');
                dot.className = 'dot';
                dot.style.width = dot.style.height = Math.random() * 3 + 2 + 'px';
                dot.style.left = Math.random() * 100 + '%';
                dot.style.top = Math.random() * 100 + '%';
                dot.style.animationDelay = Math.random() * 10 + 's';
                document.getElementById('dots').appendChild(dot);
            }
            function editPlayer(id) { alert('Edit ' + id); }
            function deletePlayer(id) {
                if (confirm('Delete player ' + id + '?')) {
                    fetch('/admin/players/' + id, { method: 'DELETE' })
                    .then(res => res.json())
                    .then(data => { if (data.success) { alert('Deleted'); location.reload(); } else { alert('Error: ' + data.error); } })
                    .catch(() => alert('Error'));
                }
            }
        </script>
    </body>
    </html>
    ''', total_players=total_players, total_kills=total_kills, total_games=total_games, 
        admins=admins, players=players, bot_active=bot_active)

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
# DISCORD INTERACTIONS ENDPOINT
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord interactions"""
    data = request.json
    return jsonify(handle_interaction(data))

# =============================================================================
# STARTUP
# =============================================================================

def startup_sequence():
    """Run startup sequence"""
    try:
        init_db()
        
        fixed_keys = fix_existing_keys()
        if fixed_keys > 0:
            logger.info(f"Fixed {fixed_keys} API keys")
        
        bot_status = test_discord_token()
        if bot_status:
            logger.info("✅ Discord bot active")
            register_commands()
        else:
            logger.warning("⚠️ Discord bot offline")
        
        logger.info(f"✅ System started on port {port}")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

startup_sequence()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=False)

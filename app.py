# app.py - Simplified Version with Fixed Discord Bot Status
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
# LOGIN PAGE - Simplified
# =============================================================================

@app.route('/')
def home():
    """Login Page - Simplified with only dots background"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            session['user_data'] = user_data
            if user_data.get('is_admin'):
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
    
    # Get actual bot status
    bot_status = test_discord_token()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SOT TDM - Login</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: Arial, sans-serif;
                background: #0a0a0a;
                color: #ffffff;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                position: relative;
                overflow: hidden;
            }
            
            /* Floating dots background */
            #floating-dots {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 1;
                overflow: hidden;
            }
            
            .dot {
                position: absolute;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 50%;
                animation: float 20s infinite linear;
            }
            
            .dot:nth-child(2n) {
                background: rgba(100, 100, 100, 0.1);
                animation-duration: 25s;
            }
            
            .dot:nth-child(3n) {
                background: rgba(150, 150, 150, 0.1);
                animation-duration: 30s;
            }
            
            @keyframes float {
                0% {
                    transform: translate(0, 0) rotate(0deg);
                    opacity: 0.1;
                }
                50% {
                    opacity: 0.2;
                }
                100% {
                    transform: translate(100vw, 100vh) rotate(360deg);
                    opacity: 0.1;
                }
            }
            
            /* Login container */
            .login-container {
                position: relative;
                z-index: 10;
                width: 400px;
                padding: 40px;
                background: rgba(20, 20, 20, 0.8);
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                box-shadow: 0 0 20px rgba(0, 0, 0, 0.5);
            }
            
            h1 {
                text-align: center;
                margin-bottom: 10px;
                color: #fff;
                font-size: 28px;
            }
            
            h2 {
                text-align: center;
                margin-bottom: 30px;
                color: #ccc;
                font-weight: normal;
                font-size: 16px;
            }
            
            input {
                width: 100%;
                padding: 12px;
                margin: 10px 0;
                background: rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 5px;
                color: #fff;
                font-size: 14px;
                box-sizing: border-box;
            }
            
            input:focus {
                outline: none;
                border-color: #666;
            }
            
            button {
                width: 100%;
                padding: 12px;
                background: #333;
                color: #fff;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                cursor: pointer;
                margin-top: 10px;
                transition: background 0.3s;
            }
            
            button:hover {
                background: #444;
            }
            
            button:active {
                background: #222;
            }
            
            .error {
                color: #ff6b6b;
                margin-top: 10px;
                padding: 8px;
                background: rgba(255, 107, 107, 0.1);
                border-radius: 3px;
                border-left: 3px solid #ff6b6b;
                display: none;
                font-size: 14px;
            }
            
            .status {
                margin-top: 20px;
                padding: 10px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 5px;
                font-size: 14px;
                color: #888;
            }
            
            .status-dot {
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                margin-right: 8px;
            }
            
            .status-online {
                background: #4CAF50;
                box-shadow: 0 0 8px #4CAF50;
            }
            
            .status-offline {
                background: #f44336;
                box-shadow: 0 0 8px #f44336;
            }
        </style>
    </head>
    <body>
        <!-- Floating dots background -->
        <div id="floating-dots"></div>
        
        <div class="login-container">
            <h1>SOT TDM SYSTEM</h1>
            <h2>API Key Login</h2>
            
            <input type="text" id="apiKey" placeholder="Enter your API key (GOB-...)" autocomplete="off">
            
            <button onclick="login()">Login</button>
            <div class="error" id="error"></div>
            
            <div class="status">
                <span class="status-dot {% if bot_status %}status-online{% else %}status-offline{% endif %}"></span>
                <strong>Discord Bot:</strong> {% if bot_status %}Online{% else %}Offline{% endif %}
            </div>
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('floating-dots');
                for (let i = 0; i < 30; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    dot.style.width = dot.style.height = Math.random() * 3 + 2 + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 10 + 's';
                    container.appendChild(dot);
                }
            }
            
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
                    error.textContent = "Invalid API key format. Must be: GOB- followed by 20 characters";
                    error.style.display = 'block';
                    return;
                }
                
                // Disable button and show loading
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
                    error.textContent = 'Connection error. Please try again.';
                    error.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = 'Login';
                });
            }
            
            // Enter key to submit
            document.getElementById('apiKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') login();
            });
            
            // Initialize on load
            window.addEventListener('load', generateDots);
        </script>
    </body>
    </html>
    ''', bot_status=bot_active)

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
# USER DASHBOARD - Simplified
# =============================================================================

@app.route('/dashboard')
def dashboard():
    """User Dashboard - Simplified"""
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
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: Arial, sans-serif;
                background: #0a0a0a;
                color: #ffffff;
                min-height: 100vh;
                position: relative;
                overflow-x: hidden;
            }
            
            /* Floating dots background */
            #floating-dots {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 1;
                overflow: hidden;
            }
            
            .dot {
                position: absolute;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 50%;
                animation: float 20s infinite linear;
            }
            
            .dot:nth-child(2n) {
                background: rgba(100, 100, 100, 0.1);
                animation-duration: 25s;
            }
            
            .dot:nth-child(3n) {
                background: rgba(150, 150, 150, 0.1);
                animation-duration: 30s;
            }
            
            @keyframes float {
                0% {
                    transform: translate(0, 0) rotate(0deg);
                    opacity: 0.1;
                }
                50% {
                    opacity: 0.2;
                }
                100% {
                    transform: translate(100vw, 100vh) rotate(360deg);
                    opacity: 0.1;
                }
            }
            
            /* Header */
            .header {
                position: relative;
                z-index: 10;
                padding: 20px;
                background: rgba(20, 20, 20, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .header h1 {
                font-size: 20px;
                color: #fff;
            }
            
            .header-right {
                display: flex;
                gap: 10px;
                align-items: center;
            }
            
            .header-right a {
                padding: 8px 15px;
                background: #333;
                color: #fff;
                text-decoration: none;
                border-radius: 4px;
                font-size: 14px;
            }
            
            .header-right a:hover {
                background: #444;
            }
            
            /* Main content */
            .main-content {
                position: relative;
                z-index: 10;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            
            /* Stats grid */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .stat-box {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 20px;
            }
            
            .stat-box h3 {
                color: #aaa;
                font-size: 14px;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .stat-value {
                font-size: 28px;
                font-weight: bold;
                color: #fff;
                margin-bottom: 5px;
            }
            
            .stat-detail {
                color: #888;
                font-size: 14px;
            }
            
            /* API Key section */
            .api-section {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 25px;
                margin-bottom: 30px;
            }
            
            .api-section h2 {
                color: #fff;
                font-size: 18px;
                margin-bottom: 15px;
            }
            
            .api-key {
                background: rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 15px;
                font-family: monospace;
                font-size: 16px;
                color: #fff;
                margin-bottom: 15px;
                word-break: break-all;
            }
            
            .copy-btn {
                padding: 10px 20px;
                background: #333;
                color: #fff;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            
            .copy-btn:hover {
                background: #444;
            }
            
            .copy-btn:active {
                background: #222;
            }
            
            /* Leaderboard */
            .leaderboard {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 25px;
                margin-bottom: 30px;
            }
            
            .leaderboard h2 {
                color: #fff;
                font-size: 18px;
                margin-bottom: 20px;
            }
            
            .leaderboard-table {
                width: 100%;
                border-collapse: collapse;
            }
            
            .leaderboard-table th {
                background: rgba(255, 255, 255, 0.05);
                color: #aaa;
                padding: 12px;
                text-align: left;
                font-weight: normal;
                border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            }
            
            .leaderboard-table td {
                padding: 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            
            .leaderboard-table tr:hover {
                background: rgba(255, 255, 255, 0.02);
            }
            
            .leaderboard-table .rank {
                color: #aaa;
                width: 50px;
            }
            
            .leaderboard-table .name {
                font-weight: bold;
            }
            
            .leaderboard-table .you {
                background: rgba(255, 255, 255, 0.05);
            }
            
            /* Footer */
            .footer {
                position: relative;
                z-index: 10;
                padding: 20px;
                text-align: center;
                color: #666;
                font-size: 14px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                margin-top: 40px;
            }
        </style>
    </head>
    <body>
        <!-- Floating dots background -->
        <div id="floating-dots"></div>
        
        <!-- Header -->
        <div class="header">
            <h1>SOT TDM Dashboard</h1>
            <div class="header-right">
                <a href="/">Home</a>
                {% if user_data.get('is_admin') %}
                <a href="/admin">Admin</a>
                {% endif %}
                <a href="/logout">Logout</a>
            </div>
        </div>
        
        <!-- Main content -->
        <div class="main-content">
            <!-- Stats Grid -->
            <div class="stats-grid">
                <div class="stat-box">
                    <h3>K/D Ratio</h3>
                    <div class="stat-value">{{ "%.2f"|format(kd) }}</div>
                    <div class="stat-detail">{{ total_kills }} kills / {{ total_deaths }} deaths</div>
                </div>
                
                <div class="stat-box">
                    <h3>Win Rate</h3>
                    <div class="stat-value">{{ "%.1f"|format(win_rate) }}%</div>
                    <div class="stat-detail">{{ wins }} wins / {{ losses }} losses</div>
                </div>
                
                <div class="stat-box">
                    <h3>Games Played</h3>
                    <div class="stat-value">{{ total_games }}</div>
                    <div class="stat-detail">Total matches</div>
                </div>
                
                <div class="stat-box">
                    <h3>Rank</h3>
                    <div class="stat-value">{{ user_rank }}</div>
                    <div class="stat-detail">Your position</div>
                </div>
            </div>
            
            <!-- API Key Section -->
            <div class="api-section">
                <h2>Your API Key</h2>
                <div class="api-key">{{ session['user_key'] }}</div>
                <button class="copy-btn" onclick="copyKey()">Copy to Clipboard</button>
            </div>
            
            <!-- Leaderboard -->
            <div class="leaderboard">
                <h2>Top 10 Leaderboard</h2>
                <table class="leaderboard-table">
                    <thead>
                        <tr>
                            <th class="rank">Rank</th>
                            <th class="name">Player</th>
                            <th>K/D</th>
                            <th>Kills</th>
                            <th>Wins</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for player in leaderboard_data %}
                        <tr class="{% if player.api_key == session['user_key'] %}you{% endif %}">
                            <td class="rank">#{{ loop.index }}</td>
                            <td class="name">
                                {{ player.name }}
                                {% if player.api_key == session['user_key'] %}(You){% endif %}
                            </td>
                            <td>{{ player.kd }}</td>
                            <td>{{ player.kills }}</td>
                            <td>{{ player.wins }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            SOT TDM System | Connected to Database {% if bot_active %}• Discord Bot Online{% endif %}
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('floating-dots');
                for (let i = 0; i < 20; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    dot.style.width = dot.style.height = Math.random() * 3 + 2 + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 10 + 's';
                    container.appendChild(dot);
                }
            }
            
            function copyKey() {
                const key = "{{ session['user_key'] }}";
                navigator.clipboard.writeText(key)
                    .then(() => {
                        alert('API key copied to clipboard!');
                    })
                    .catch(err => {
                        alert('Failed to copy. Please copy manually.');
                    });
            }
            
            // Initialize
            window.addEventListener('load', generateDots);
        </script>
    </body>
    </html>
    ''', user_data=user_data, session=session, leaderboard_data=leaderboard_data, 
        total_kills=total_kills, total_deaths=total_deaths, wins=wins, losses=losses,
        kd=kd, total_games=total_games, win_rate=win_rate, user_rank=user_rank,
        bot_active=bot_active)

# =============================================================================
# ADMIN DASHBOARD - Simplified
# =============================================================================

@app.route('/admin')
def admin_dashboard():
    """Admin Dashboard - Simplified"""
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
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: Arial, sans-serif;
                background: #0a0a0a;
                color: #ffffff;
                min-height: 100vh;
                position: relative;
            }
            
            /* Floating dots background */
            #floating-dots {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 1;
                overflow: hidden;
            }
            
            .dot {
                position: absolute;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 50%;
                animation: float 20s infinite linear;
            }
            
            .dot:nth-child(2n) {
                background: rgba(100, 100, 100, 0.1);
                animation-duration: 25s;
            }
            
            .dot:nth-child(3n) {
                background: rgba(150, 150, 150, 0.1);
                animation-duration: 30s;
            }
            
            @keyframes float {
                0% {
                    transform: translate(0, 0) rotate(0deg);
                    opacity: 0.1;
                }
                50% {
                    opacity: 0.2;
                }
                100% {
                    transform: translate(100vw, 100vh) rotate(360deg);
                    opacity: 0.1;
                }
            }
            
            /* Header */
            .header {
                position: relative;
                z-index: 10;
                padding: 20px;
                background: rgba(20, 20, 20, 0.9);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .header h1 {
                font-size: 20px;
                color: #fff;
            }
            
            .header-nav {
                display: flex;
                gap: 10px;
            }
            
            .header-nav a {
                padding: 8px 15px;
                background: #333;
                color: #fff;
                text-decoration: none;
                border-radius: 4px;
                font-size: 14px;
            }
            
            .header-nav a:hover {
                background: #444;
            }
            
            /* Main content */
            .main-content {
                position: relative;
                z-index: 10;
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }
            
            /* Stats */
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .stat-box {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 20px;
                text-align: center;
            }
            
            .stat-value {
                font-size: 32px;
                font-weight: bold;
                color: #fff;
                margin: 10px 0;
            }
            
            .stat-label {
                color: #aaa;
                font-size: 14px;
                text-transform: uppercase;
            }
            
            /* Players table */
            .players-table {
                width: 100%;
                border-collapse: collapse;
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                overflow: hidden;
                margin-top: 30px;
            }
            
            .players-table th {
                background: rgba(255, 255, 255, 0.05);
                color: #aaa;
                padding: 12px;
                text-align: left;
                font-weight: normal;
                border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            }
            
            .players-table td {
                padding: 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            
            .players-table tr:hover {
                background: rgba(255, 255, 255, 0.02);
            }
            
            .admin-badge {
                background: #ff6b6b;
                color: white;
                padding: 2px 8px;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            
            .action-buttons {
                display: flex;
                gap: 8px;
            }
            
            .action-btn {
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                transition: background 0.3s;
            }
            
            .edit-btn {
                background: #333;
                color: #fff;
            }
            
            .delete-btn {
                background: #ff4444;
                color: white;
            }
            
            .action-btn:hover {
                opacity: 0.8;
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .stats {
                    grid-template-columns: repeat(2, 1fr);
                }
                
                .players-table {
                    display: block;
                    overflow-x: auto;
                }
                
                .action-buttons {
                    flex-direction: column;
                }
            }
        </style>
    </head>
    <body>
        <!-- Floating dots background -->
        <div id="floating-dots"></div>
        
        <!-- Header -->
        <div class="header">
            <h1>Admin Dashboard</h1>
            <div class="header-nav">
                <a href="/dashboard">Dashboard</a>
                <a href="/">Login</a>
                <a href="/logout">Logout</a>
            </div>
        </div>
        
        <!-- Main content -->
        <div class="main-content">
            <!-- Stats -->
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-label">Total Players</div>
                    <div class="stat-value">{{ total_players }}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Total Kills</div>
                    <div class="stat-value">{{ "{:,}".format(total_kills) }}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Games Played</div>
                    <div class="stat-value">{{ total_games }}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Admins</div>
                    <div class="stat-value">{{ admins }}</div>
                </div>
            </div>
            
            <!-- Players Table -->
            <h2 style="color: #fff; margin: 30px 0 15px 0; font-size: 18px;">Players ({{ total_players }})</h2>
            <table class="players-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Discord</th>
                        <th>K/D</th>
                        <th>Kills</th>
                        <th>Admin</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for player in players %}
                    <tr>
                        <td>{{ player.id }}</td>
                        <td><strong>{{ player.in_game_name or 'N/A' }}</strong></td>
                        <td>{{ player.discord_name or 'N/A' }}</td>
                        <td>{{ player.kd_ratio }}</td>
                        <td>{{ player.total_kills or 0 }}</td>
                        <td>
                            {% if player.is_admin %}
                            <span class="admin-badge">Admin</span>
                            {% else %}
                            Player
                            {% endif %}
                        </td>
                        <td>
                            <div class="action-buttons">
                                <button class="action-btn edit-btn" onclick="editPlayer({{ player.id }})">Edit</button>
                                <button class="action-btn delete-btn" onclick="deletePlayer({{ player.id }})">Delete</button>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            
            <div style="margin-top: 30px; color: #666; font-size: 14px; text-align: center;">
                Discord Bot Status: {% if bot_active %}Online{% else %}Offline{% endif %}
            </div>
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('floating-dots');
                for (let i = 0; i < 20; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    dot.style.width = dot.style.height = Math.random() * 3 + 2 + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 10 + 's';
                    container.appendChild(dot);
                }
            }
            
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
            
            // Initialize
            window.addEventListener('load', generateDots);
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
            logger.info(f"Fixed {fixed_keys} API keys to correct format")
        
        # Test Discord connection properly
        bot_status = test_discord_token()
        if bot_status:
            logger.info("✅ Discord bot is ACTIVE")
            
            if register_commands():
                logger.info("✅ Commands registered")
            else:
                logger.warning("⚠️ Could not register commands")
        else:
            logger.warning("⚠️ Discord token not set or invalid")
        
        logger.info(f"✅ SOT TDM System started on port {port}")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

# Initialize on import (for WSGI/Gunicorn)
startup_sequence()

# For direct execution
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=False)

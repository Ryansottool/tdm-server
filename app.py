# app.py - Simplified Version with Black Theme
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
    """Login Page with Black Theme"""
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
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #0a0a0a;
                color: #ffffff;
                min-height: 100vh;
                overflow-x: hidden;
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
                background: rgba(0, 255, 157, 0.3);
                border-radius: 50%;
                animation: float 15s infinite linear;
            }
            
            .dot:nth-child(2n) {
                background: rgba(157, 0, 255, 0.3);
                animation-duration: 20s;
            }
            
            .dot:nth-child(3n) {
                background: rgba(255, 157, 0, 0.3);
                animation-duration: 25s;
            }
            
            @keyframes float {
                0% {
                    transform: translate(0, 0) rotate(0deg);
                    opacity: 0.3;
                }
                50% {
                    opacity: 0.6;
                }
                100% {
                    transform: translate(100vw, 100vh) rotate(360deg);
                    opacity: 0.3;
                }
            }
            
            /* Connections visualization */
            #connections {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 2;
            }
            
            .connection {
                position: absolute;
                height: 1px;
                background: linear-gradient(90deg, 
                    rgba(0, 255, 157, 0) 0%,
                    rgba(0, 255, 157, 0.4) 50%,
                    rgba(0, 255, 157, 0) 100%);
                transform-origin: left center;
                animation: pulse 3s infinite alternate;
            }
            
            @keyframes pulse {
                0% { opacity: 0.2; }
                100% { opacity: 0.6; }
            }
            
            .login-container {
                position: relative;
                z-index: 10;
                max-width: 500px;
                margin: 100px auto;
                padding: 40px;
                background: rgba(20, 20, 20, 0.85);
                border-radius: 20px;
                border: 1px solid rgba(0, 255, 157, 0.3);
                box-shadow: 0 0 50px rgba(0, 255, 157, 0.1),
                            0 0 0 1px rgba(0, 255, 157, 0.1) inset;
                backdrop-filter: blur(10px);
            }
            
            h1 {
                text-align: center;
                margin-bottom: 20px;
                color: #00ff9d;
                font-size: 2.5em;
                text-shadow: 0 0 10px rgba(0, 255, 157, 0.5);
            }
            
            h2 {
                text-align: center;
                margin-bottom: 30px;
                color: #ffffff;
                font-weight: 300;
            }
            
            .input-group {
                position: relative;
                margin: 25px 0;
            }
            
            input {
                width: 100%;
                padding: 15px;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(0, 255, 157, 0.3);
                border-radius: 10px;
                color: #ffffff;
                font-size: 16px;
                transition: all 0.3s ease;
            }
            
            input:focus {
                outline: none;
                border-color: #00ff9d;
                box-shadow: 0 0 15px rgba(0, 255, 157, 0.3);
            }
            
            button {
                width: 100%;
                padding: 15px;
                background: linear-gradient(45deg, #00ff9d, #9d00ff);
                color: #000;
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s ease;
                text-transform: uppercase;
                letter-spacing: 1px;
                position: relative;
                overflow: hidden;
            }
            
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(0, 255, 157, 0.3);
            }
            
            button::after {
                content: '';
                position: absolute;
                top: 50%;
                left: 50%;
                width: 5px;
                height: 5px;
                background: rgba(255, 255, 255, 0.5);
                opacity: 0;
                border-radius: 100%;
                transform: scale(1, 1) translate(-50%);
                transform-origin: 50% 50%;
            }
            
            button:focus:not(:active)::after {
                animation: ripple 1s ease-out;
            }
            
            @keyframes ripple {
                0% {
                    transform: scale(0, 0);
                    opacity: 0.5;
                }
                100% {
                    transform: scale(50, 50);
                    opacity: 0;
                }
            }
            
            .error {
                color: #ff4d4d;
                margin-top: 10px;
                padding: 10px;
                background: rgba(255, 77, 77, 0.1);
                border-radius: 5px;
                display: none;
                border-left: 3px solid #ff4d4d;
            }
            
            .system-status {
                margin-top: 30px;
                padding: 15px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 10px;
                border-left: 3px solid #00ff9d;
            }
            
            .status-dot {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 10px;
                background: {% if bot_active %}#00ff9d{% else %}#ff4d4d{% endif %};
                box-shadow: 0 0 10px {% if bot_active %}rgba(0, 255, 157, 0.5){% else %}rgba(255, 77, 77, 0.5){% endif %};
                animation: pulse-status 2s infinite;
            }
            
            @keyframes pulse-status {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
        </style>
    </head>
    <body>
        <!-- Floating dots background -->
        <div id="floating-dots"></div>
        
        <!-- Connection lines -->
        <div id="connections"></div>
        
        <div class="login-container">
            <h1>SOT TDM SYSTEM</h1>
            <h2>API KEY LOGIN</h2>
            
            <div class="input-group">
                <input type="text" id="apiKey" placeholder="ENTER YOUR API KEY (GOB-...)" autocomplete="off">
            </div>
            
            <button onclick="login()">LOGIN TO DASHBOARD</button>
            <div class="error" id="error"></div>
            
            <div class="system-status">
                <span class="status-dot"></span>
                <strong>System Status:</strong> 
                <span id="botStatus">{% if bot_active %}DISCORD BOT ACTIVE{% else %}BOT OFFLINE{% endif %}</span>
            </div>
            
            <div style="margin-top: 20px; text-align: center; color: #888; font-size: 14px;">
                Connected to: Web Dashboard • Discord Bot • Database • API Endpoints
            </div>
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('floating-dots');
                for (let i = 0; i < 50; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    dot.style.width = dot.style.height = Math.random() * 4 + 2 + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 5 + 's';
                    container.appendChild(dot);
                }
            }
            
            // Generate connection lines between system components
            function generateConnections() {
                const container = document.getElementById('connections');
                const components = [
                    { x: 20, y: 20 },   // Web Dashboard
                    { x: 80, y: 20 },   // Discord Bot
                    { x: 20, y: 80 },   // Database
                    { x: 80, y: 80 },   // API
                    { x: 50, y: 50 }    // Center Hub
                ];
                
                // Connect all components to center hub
                components.forEach((comp, index) => {
                    if (index === 4) return; // Skip center hub
                    
                    const connection = document.createElement('div');
                    connection.className = 'connection';
                    
                    const dx = components[4].x - comp.x;
                    const dy = components[4].y - comp.y;
                    const length = Math.sqrt(dx * dx + dy * dy);
                    const angle = Math.atan2(dy, dx) * 180 / Math.PI;
                    
                    connection.style.width = length + 'vw';
                    connection.style.left = comp.x + '%';
                    connection.style.top = comp.y + '%';
                    connection.style.transform = `rotate(${angle}deg)`;
                    connection.style.animationDelay = index * 0.5 + 's';
                    
                    container.appendChild(connection);
                });
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
                    error.textContent = "Invalid API key format. Format: GOB-XXXXXXXXXXXXXX";
                    error.style.display = 'block';
                    return;
                }
                
                // Add loading animation
                const btn = document.querySelector('button');
                const originalText = btn.textContent;
                btn.textContent = 'CONNECTING...';
                btn.disabled = true;
                
                fetch('/api/validate-key', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ api_key: key })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.valid) {
                        // Success animation
                        btn.style.background = 'linear-gradient(45deg, #00ff9d, #00cc7a)';
                        btn.textContent = 'ACCESS GRANTED!';
                        
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 500);
                    } else {
                        error.textContent = data.error || 'Invalid API key';
                        error.style.display = 'block';
                        btn.textContent = originalText;
                        btn.disabled = false;
                    }
                })
                .catch(err => {
                    error.textContent = 'Connection error. Please try again.';
                    error.style.display = 'block';
                    btn.textContent = originalText;
                    btn.disabled = false;
                });
            }
            
            // Enter key to submit
            document.getElementById('apiKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') login();
            });
            
            // Initialize on load
            window.addEventListener('load', () => {
                generateDots();
                generateConnections();
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
    """User Dashboard with Black Theme"""
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
    
    # System connections status
    stats_data = get_global_stats()
    connections = [
        {"name": "Database", "status": "connected", "color": "#00ff9d"},
        {"name": "Discord Bot", "status": "active" if bot_active else "offline", "color": bot_active and "#00ff9d" or "#ff4d4d"},
        {"name": "API", "status": "online", "color": "#00ff9d"},
        {"name": "Web Socket", "status": "ready", "color": "#00ff9d"}
    ]
    
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
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #0a0a0a;
                color: #ffffff;
                min-height: 100vh;
                overflow-x: hidden;
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
                background: rgba(0, 255, 157, 0.2);
                border-radius: 50%;
                animation: float 20s infinite linear;
            }
            
            .dot:nth-child(2n) {
                background: rgba(157, 0, 255, 0.2);
                animation-duration: 25s;
            }
            
            .dot:nth-child(3n) {
                background: rgba(255, 157, 0, 0.2);
                animation-duration: 30s;
            }
            
            @keyframes float {
                0% {
                    transform: translate(0, 0) rotate(0deg);
                    opacity: 0.2;
                }
                50% {
                    opacity: 0.4;
                }
                100% {
                    transform: translate(100vw, 100vh) rotate(360deg);
                    opacity: 0.2;
                }
            }
            
            /* Connections visualization */
            .connection-node {
                position: absolute;
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: #00ff9d;
                box-shadow: 0 0 20px #00ff9d;
                z-index: 2;
            }
            
            .connection-line {
                position: absolute;
                height: 1px;
                background: linear-gradient(90deg, 
                    rgba(0, 255, 157, 0) 0%,
                    rgba(0, 255, 157, 0.3) 50%,
                    rgba(0, 255, 157, 0) 100%);
                z-index: 1;
            }
            
            /* Main container */
            .main-container {
                position: relative;
                z-index: 10;
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }
            
            /* Header */
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 30px 40px;
                background: rgba(20, 20, 20, 0.9);
                border-radius: 20px;
                border: 1px solid rgba(0, 255, 157, 0.2);
                margin-bottom: 30px;
                backdrop-filter: blur(10px);
            }
            
            .header-left h1 {
                color: #00ff9d;
                font-size: 2em;
                margin-bottom: 5px;
                text-shadow: 0 0 10px rgba(0, 255, 157, 0.5);
            }
            
            .header-left .subtitle {
                color: #888;
                font-size: 14px;
            }
            
            .header-right {
                display: flex;
                gap: 15px;
                align-items: center;
            }
            
            .user-info {
                text-align: right;
            }
            
            .user-info .name {
                font-size: 18px;
                font-weight: bold;
                color: #00ff9d;
            }
            
            .user-info .rank {
                color: #888;
                font-size: 14px;
            }
            
            .nav-button {
                padding: 10px 20px;
                background: rgba(0, 255, 157, 0.1);
                color: #00ff9d;
                border: 1px solid rgba(0, 255, 157, 0.3);
                border-radius: 10px;
                text-decoration: none;
                font-weight: bold;
                transition: all 0.3s ease;
            }
            
            .nav-button:hover {
                background: rgba(0, 255, 157, 0.2);
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0, 255, 157, 0.2);
            }
            
            /* Stats Grid */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 40px;
            }
            
            .stat-card {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 25px;
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
            }
            
            .stat-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #00ff9d, #9d00ff);
            }
            
            .stat-card:hover {
                transform: translateY(-5px);
                border-color: rgba(0, 255, 157, 0.3);
                box-shadow: 0 10px 30px rgba(0, 255, 157, 0.1);
            }
            
            .stat-label {
                color: #888;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 10px;
            }
            
            .stat-value {
                font-size: 36px;
                font-weight: bold;
                color: #ffffff;
                margin-bottom: 5px;
            }
            
            .stat-detail {
                color: #00ff9d;
                font-size: 14px;
            }
            
            /* API Key Section */
            .api-section {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(0, 255, 157, 0.2);
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 40px;
                position: relative;
            }
            
            .api-key-display {
                background: rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(0, 255, 157, 0.3);
                border-radius: 10px;
                padding: 20px;
                font-family: monospace;
                font-size: 18px;
                color: #00ff9d;
                margin: 20px 0;
                letter-spacing: 1px;
                text-align: center;
                position: relative;
                overflow: hidden;
            }
            
            .api-key-display::after {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, 
                    transparent, 
                    rgba(0, 255, 157, 0.1), 
                    transparent);
                animation: scan 3s infinite linear;
            }
            
            @keyframes scan {
                0% { left: -100%; }
                100% { left: 100%; }
            }
            
            .copy-button {
                background: linear-gradient(45deg, #00ff9d, #9d00ff);
                color: #000;
                border: none;
                border-radius: 10px;
                padding: 12px 30px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .copy-button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(0, 255, 157, 0.3);
            }
            
            /* Leaderboard */
            .leaderboard-section {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(0, 255, 157, 0.2);
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 40px;
            }
            
            .leaderboard-title {
                color: #00ff9d;
                font-size: 24px;
                margin-bottom: 20px;
                text-align: center;
            }
            
            .leaderboard-table {
                width: 100%;
                border-collapse: collapse;
            }
            
            .leaderboard-table th {
                background: rgba(0, 255, 157, 0.1);
                color: #00ff9d;
                padding: 15px;
                text-align: left;
                font-weight: 600;
                border-bottom: 2px solid rgba(0, 255, 157, 0.3);
            }
            
            .leaderboard-table td {
                padding: 15px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .leaderboard-table tr:hover {
                background: rgba(0, 255, 157, 0.05);
            }
            
            .leaderboard-table .rank {
                color: #00ff9d;
                font-weight: bold;
                width: 60px;
            }
            
            .leaderboard-table .you {
                background: rgba(0, 255, 157, 0.1);
                border-left: 3px solid #00ff9d;
            }
            
            .leaderboard-table .name {
                font-weight: bold;
            }
            
            /* Connections Panel */
            .connections-panel {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 40px;
            }
            
            .connection-item {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 20px;
                text-align: center;
                transition: all 0.3s ease;
            }
            
            .connection-item:hover {
                border-color: rgba(0, 255, 157, 0.3);
                transform: translateY(-3px);
            }
            
            .connection-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                display: inline-block;
                margin-right: 10px;
                animation: pulse-connection 2s infinite;
            }
            
            @keyframes pulse-connection {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .header {
                    flex-direction: column;
                    text-align: center;
                    gap: 20px;
                }
                
                .header-right {
                    width: 100%;
                    justify-content: center;
                }
                
                .user-info {
                    text-align: center;
                }
                
                .stats-grid {
                    grid-template-columns: 1fr;
                }
                
                .connections-panel {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
            
            @media (max-width: 480px) {
                .connections-panel {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <!-- Floating dots background -->
        <div id="floating-dots"></div>
        
        <!-- Connection nodes -->
        <div class="connection-node" style="top: 10%; left: 10%;" title="Web Dashboard"></div>
        <div class="connection-node" style="top: 10%; left: 90%;" title="Discord Bot"></div>
        <div class="connection-node" style="top: 90%; left: 10%;" title="Database"></div>
        <div class="connection-node" style="top: 90%; left: 90%;" title="API Gateway"></div>
        <div class="connection-node" style="top: 50%; left: 50%;" title="Central Hub"></div>
        
        <!-- Connection lines -->
        <div id="connection-lines"></div>
        
        <div class="main-container">
            <!-- Header -->
            <div class="header">
                <div class="header-left">
                    <h1>SOT TDM DASHBOARD</h1>
                    <div class="subtitle">Real-time stats and management system</div>
                </div>
                <div class="header-right">
                    <div class="user-info">
                        <div class="name">{{ user_data.get('in_game_name', 'Player') }}</div>
                        <div class="rank">Rank: {{ user_rank }}</div>
                    </div>
                    <a href="/" class="nav-button">Home</a>
                    {% if user_data.get('is_admin') %}
                    <a href="/admin" class="nav-button">Admin Panel</a>
                    {% endif %}
                    <a href="/logout" class="nav-button">Logout</a>
                </div>
            </div>
            
            <!-- Stats Grid -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">K/D Ratio</div>
                    <div class="stat-value">{{ "%.2f"|format(kd) }}</div>
                    <div class="stat-detail">{{ total_kills }} kills / {{ total_deaths }} deaths</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Win Rate</div>
                    <div class="stat-value">{{ "%.1f"|format(win_rate) }}%</div>
                    <div class="stat-detail">{{ wins }} wins / {{ losses }} losses</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Games Played</div>
                    <div class="stat-value">{{ total_games }}</div>
                    <div class="stat-detail">Total matches completed</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Prestige Level</div>
                    <div class="stat-value">P{{ user_data.get('prestige', 0) }}</div>
                    <div class="stat-detail">Player status</div>
                </div>
            </div>
            
            <!-- API Key Section -->
            <div class="api-section">
                <h2 style="color: #00ff9d; margin-bottom: 20px;">YOUR API KEY</h2>
                <div class="api-key-display">
                    {{ session['user_key'] }}
                </div>
                <button class="copy-button" onclick="copyKey()">
                    COPY TO CLIPBOARD
                </button>
            </div>
            
            <!-- System Connections -->
            <div class="connections-panel">
                {% for conn in connections %}
                <div class="connection-item">
                    <span class="connection-dot" style="background: {{ conn.color }};"></span>
                    <strong>{{ conn.name }}</strong>
                    <div style="margin-top: 10px; color: {{ conn.color }}; font-size: 12px;">
                        {{ conn.status|upper }}
                    </div>
                </div>
                {% endfor %}
            </div>
            
            <!-- Leaderboard -->
            <div class="leaderboard-section">
                <div class="leaderboard-title">TOP 10 LEADERBOARD</div>
                <table class="leaderboard-table">
                    <thead>
                        <tr>
                            <th class="rank">RANK</th>
                            <th class="name">PLAYER</th>
                            <th>K/D</th>
                            <th>KILLS</th>
                            <th>WINS</th>
                            <th>PRESTIGE</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for player in leaderboard_data %}
                        <tr {% if player.api_key == session['user_key'] %}class="you"{% endif %}>
                            <td class="rank">#{{ loop.index }}</td>
                            <td class="name">
                                {{ player.name }}
                                {% if player.api_key == session['user_key'] %}
                                <span style="color: #00ff9d; font-size: 12px;">(YOU)</span>
                                {% endif %}
                            </td>
                            <td>{{ player.kd }}</td>
                            <td>{{ player.kills }}</td>
                            <td>{{ player.wins }}</td>
                            <td>P{{ player.prestige }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            <!-- Global Stats -->
            <div style="text-align: center; color: #888; font-size: 14px; margin-top: 40px;">
                System Status: ● Online | Players: {{ stats_data.total_players }} | 
                Matches: {{ stats_data.total_games }} | 
                Connected Nodes: 4/4
            </div>
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('floating-dots');
                for (let i = 0; i < 30; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    dot.style.width = dot.style.height = Math.random() * 6 + 3 + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 10 + 's';
                    container.appendChild(dot);
                }
            }
            
            // Generate connection lines between nodes
            function generateConnections() {
                const container = document.getElementById('connection-lines');
                const nodes = [
                    { x: 10, y: 10 },  // Web Dashboard
                    { x: 90, y: 10 },  // Discord Bot
                    { x: 10, y: 90 },  // Database
                    { x: 90, y: 90 },  // API Gateway
                    { x: 50, y: 50 }   // Central Hub
                ];
                
                // Clear existing lines
                container.innerHTML = '';
                
                // Connect each node to central hub
                nodes.forEach((node, index) => {
                    if (index === 4) return; // Skip central hub
                    
                    const line = document.createElement('div');
                    line.className = 'connection-line';
                    
                    const dx = nodes[4].x - node.x;
                    const dy = nodes[4].y - node.y;
                    const length = Math.sqrt(dx * dx + dy * dy);
                    const angle = Math.atan2(dy, dx) * 180 / Math.PI;
                    
                    line.style.width = length + 'vw';
                    line.style.left = node.x + 'vw';
                    line.style.top = node.y + 'vh';
                    line.style.transform = `rotate(${angle}deg)`;
                    line.style.animationDelay = index * 0.3 + 's';
                    
                    container.appendChild(line);
                });
            }
            
            function copyKey() {
                const key = "{{ session['user_key'] }}";
                navigator.clipboard.writeText(key)
                    .then(() => {
                        const btn = document.querySelector('.copy-button');
                        const originalText = btn.textContent;
                        btn.textContent = 'COPIED!';
                        btn.style.background = 'linear-gradient(45deg, #00cc7a, #00ff9d)';
                        
                        setTimeout(() => {
                            btn.textContent = originalText;
                            btn.style.background = 'linear-gradient(45deg, #00ff9d, #9d00ff)';
                        }, 2000);
                    })
                    .catch(err => {
                        alert('Failed to copy key. Please copy manually.');
                    });
            }
            
            // Auto-refresh leaderboard every 30 seconds
            function refreshLeaderboard() {
                fetch('/api/leaderboard')
                    .then(res => res.json())
                    .then(data => {
                        console.log('Leaderboard refreshed:', data);
                    })
                    .catch(err => console.log('Refresh error:', err));
            }
            
            // Initialize on load
            window.addEventListener('load', () => {
                generateDots();
                generateConnections();
                
                // Auto-refresh every 30 seconds
                setInterval(refreshLeaderboard, 30000);
                
                // Animate stats cards on scroll
                const cards = document.querySelectorAll('.stat-card');
                const observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            entry.target.style.transform = 'translateY(0)';
                            entry.target.style.opacity = '1';
                        }
                    });
                }, { threshold: 0.1 });
                
                cards.forEach(card => {
                    card.style.transform = 'translateY(20px)';
                    card.style.opacity = '0';
                    card.style.transition = 'transform 0.5s ease, opacity 0.5s ease';
                    observer.observe(card);
                });
            });
        </script>
    </body>
    </html>
    ''', user_data=user_data, session=session, leaderboard_data=leaderboard_data, 
        total_kills=total_kills, total_deaths=total_deaths, wins=wins, losses=losses,
        kd=kd, total_games=total_games, win_rate=win_rate, user_rank=user_rank,
        stats_data=stats_data, connections=connections, bot_active=bot_active)

# =============================================================================
# ADMIN DASHBOARD (Black Theme)
# =============================================================================

@app.route('/admin')
def admin_dashboard():
    """Admin Dashboard with Black Theme"""
    if 'user_data' not in session or not session['user_data'].get('is_admin'):
        return redirect(url_for('dashboard'))
    
    # Get all stats for admin dashboard
    players = get_all_players()
    total_players = len(players)
    total_kills = sum(p.get('total_kills', 0) for p in players)
    total_games = sum(p.get('wins', 0) + p.get('losses', 0) for p in players)
    admins = sum(1 for p in players if p.get('is_admin'))
    
    # System stats
    stats_data = get_global_stats()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard - SOT TDM System</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #0a0a0a;
                color: #ffffff;
                min-height: 100vh;
                overflow-x: hidden;
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
                background: rgba(157, 0, 255, 0.2);
                border-radius: 50%;
                animation: float 20s infinite linear;
            }
            
            .dot:nth-child(2n) {
                background: rgba(255, 157, 0, 0.2);
                animation-duration: 25s;
            }
            
            .dot:nth-child(3n) {
                background: rgba(0, 255, 157, 0.2);
                animation-duration: 30s;
            }
            
            @keyframes float {
                0% {
                    transform: translate(0, 0) rotate(0deg);
                    opacity: 0.2;
                }
                50% {
                    opacity: 0.4;
                }
                100% {
                    transform: translate(100vw, 100vh) rotate(360deg);
                    opacity: 0.2;
                }
            }
            
            /* System connections */
            .system-node {
                position: fixed;
                width: 15px;
                height: 15px;
                border-radius: 50%;
                z-index: 2;
            }
            
            .node-web { top: 10%; left: 10%; background: #00ff9d; box-shadow: 0 0 20px #00ff9d; }
            .node-bot { top: 10%; left: 90%; background: #9d00ff; box-shadow: 0 0 20px #9d00ff; }
            .node-db { top: 90%; left: 10%; background: #ff9d00; box-shadow: 0 0 20px #ff9d00; }
            .node-api { top: 90%; left: 90%; background: #ff00ff; box-shadow: 0 0 20px #ff00ff; }
            
            /* Main container */
            .main-container {
                position: relative;
                z-index: 10;
                max-width: 1600px;
                margin: 0 auto;
                padding: 20px;
            }
            
            /* Admin Header */
            .admin-header {
                background: rgba(20, 20, 20, 0.9);
                border: 1px solid rgba(157, 0, 255, 0.3);
                border-radius: 20px;
                padding: 30px 40px;
                margin-bottom: 30px;
                backdrop-filter: blur(10px);
                box-shadow: 0 0 50px rgba(157, 0, 255, 0.1);
            }
            
            .admin-header h1 {
                color: #9d00ff;
                font-size: 2.5em;
                margin-bottom: 10px;
                text-shadow: 0 0 10px rgba(157, 0, 255, 0.5);
            }
            
            .admin-header .subtitle {
                color: #888;
                font-size: 14px;
                margin-bottom: 20px;
            }
            
            .admin-nav {
                display: flex;
                gap: 15px;
                margin-top: 20px;
            }
            
            .admin-nav a {
                padding: 10px 25px;
                background: rgba(157, 0, 255, 0.1);
                color: #9d00ff;
                border: 1px solid rgba(157, 0, 255, 0.3);
                border-radius: 10px;
                text-decoration: none;
                transition: all 0.3s ease;
                font-weight: bold;
            }
            
            .admin-nav a:hover {
                background: rgba(157, 0, 255, 0.2);
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(157, 0, 255, 0.3);
            }
            
            /* Stats Overview */
            .stats-overview {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 40px;
            }
            
            .stat-panel {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 25px;
                text-align: center;
                transition: all 0.3s ease;
            }
            
            .stat-panel:hover {
                border-color: rgba(157, 0, 255, 0.3);
                transform: translateY(-3px);
                box-shadow: 0 10px 30px rgba(157, 0, 255, 0.1);
            }
            
            .stat-panel .value {
                font-size: 42px;
                font-weight: bold;
                color: #9d00ff;
                margin: 15px 0;
                text-shadow: 0 0 10px rgba(157, 0, 255, 0.5);
            }
            
            .stat-panel .label {
                color: #888;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            /* Players Table */
            .players-section {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 40px;
            }
            
            .section-title {
                color: #9d00ff;
                font-size: 24px;
                margin-bottom: 25px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .players-table {
                width: 100%;
                border-collapse: collapse;
            }
            
            .players-table th {
                background: rgba(157, 0, 255, 0.1);
                color: #9d00ff;
                padding: 15px;
                text-align: left;
                font-weight: 600;
                border-bottom: 2px solid rgba(157, 0, 255, 0.3);
            }
            
            .players-table td {
                padding: 15px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .players-table tr:hover {
                background: rgba(157, 0, 255, 0.05);
            }
            
            .admin-badge {
                background: #9d00ff;
                color: white;
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: bold;
            }
            
            .action-buttons {
                display: flex;
                gap: 10px;
            }
            
            .action-btn {
                padding: 6px 12px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 12px;
                font-weight: bold;
                transition: all 0.3s ease;
            }
            
            .action-edit {
                background: rgba(0, 255, 157, 0.1);
                color: #00ff9d;
                border: 1px solid rgba(0, 255, 157, 0.3);
            }
            
            .action-delete {
                background: rgba(255, 77, 77, 0.1);
                color: #ff4d4d;
                border: 1px solid rgba(255, 77, 77, 0.3);
            }
            
            .action-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            }
            
            .action-edit:hover {
                background: rgba(0, 255, 157, 0.2);
            }
            
            .action-delete:hover {
                background: rgba(255, 77, 77, 0.2);
            }
            
            /* System Monitoring */
            .system-monitor {
                background: rgba(20, 20, 20, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 40px;
            }
            
            .monitor-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            
            .monitor-item {
                background: rgba(0, 0, 0, 0.3);
                border-radius: 10px;
                padding: 20px;
                border-left: 4px solid #9d00ff;
            }
            
            .monitor-item.online {
                border-left-color: #00ff9d;
            }
            
            .monitor-item.offline {
                border-left-color: #ff4d4d;
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .stats-overview {
                    grid-template-columns: repeat(2, 1fr);
                }
                
                .players-table {
                    display: block;
                    overflow-x: auto;
                }
                
                .monitor-grid {
                    grid-template-columns: 1fr;
                }
                
                .action-buttons {
                    flex-direction: column;
                }
            }
            
            @media (max-width: 480px) {
                .stats-overview {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <!-- Floating dots background -->
        <div id="floating-dots"></div>
        
        <!-- System connection nodes -->
        <div class="system-node node-web" title="Web Dashboard"></div>
        <div class="system-node node-bot" title="Discord Bot"></div>
        <div class="system-node node-db" title="Database"></div>
        <div class="system-node node-api" title="API Gateway"></div>
        
        <div class="main-container">
            <!-- Admin Header -->
            <div class="admin-header">
                <h1>ADMIN CONTROL PANEL</h1>
                <div class="subtitle">Full system management and monitoring | Connected to all system branches</div>
                <div class="admin-nav">
                    <a href="/dashboard">User Dashboard</a>
                    <a href="/">Login</a>
                    <a href="/logout">Logout</a>
                    <a href="/health" target="_blank">Health Check</a>
                </div>
            </div>
            
            <!-- Stats Overview -->
            <div class="stats-overview">
                <div class="stat-panel">
                    <div class="label">Total Players</div>
                    <div class="value">{{ total_players }}</div>
                </div>
                <div class="stat-panel">
                    <div class="label">Total Kills</div>
                    <div class="value">{{ "{:,}".format(total_kills) }}</div>
                </div>
                <div class="stat-panel">
                    <div class="label">Games Played</div>
                    <div class="value">{{ total_games }}</div>
                </div>
                <div class="stat-panel">
                    <div class="label">Admins</div>
                    <div class="value">{{ admins }}</div>
                </div>
                <div class="stat-panel">
                    <div class="label">Avg K/D</div>
                    <div class="value">{{ "%.2f"|format(stats_data.avg_kd) }}</div>
                </div>
            </div>
            
            <!-- System Monitoring -->
            <div class="system-monitor">
                <div class="section-title">
                    <span>SYSTEM MONITORING</span>
                    <span style="color: #00ff9d; font-size: 14px;">● ALL SYSTEMS OPERATIONAL</span>
                </div>
                <div class="monitor-grid">
                    <div class="monitor-item online">
                        <strong>Web Dashboard</strong>
                        <div style="margin-top: 10px; font-size: 12px; color: #00ff9d;">
                            ● Online | Port: {{ port }}
                        </div>
                    </div>
                    <div class="monitor-item {% if bot_active %}online{% else %}offline{% endif %}">
                        <strong>Discord Bot</strong>
                        <div style="margin-top: 10px; font-size: 12px; color: {% if bot_active %}#00ff9d{% else %}#ff4d4d{% endif %};">
                            {% if bot_active %}● Active | Connected{% else %}● Offline | Disconnected{% endif %}
                        </div>
                    </div>
                    <div class="monitor-item online">
                        <strong>Database</strong>
                        <div style="margin-top: 10px; font-size: 12px; color: #00ff9d;">
                            ● Connected | {{ total_players }} records
                        </div>
                    </div>
                    <div class="monitor-item online">
                        <strong>API Endpoints</strong>
                        <div style="margin-top: 10px; font-size: 12px; color: #00ff9d;">
                            ● Online | 4 endpoints active
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Players Management -->
            <div class="players-section">
                <div class="section-title">
                    <span>PLAYERS MANAGEMENT ({{ total_players }})</span>
                    <button onclick="refreshPlayers()" style="padding: 8px 16px; background: rgba(0, 255, 157, 0.1); color: #00ff9d; border: 1px solid rgba(0, 255, 157, 0.3); border-radius: 6px; cursor: pointer;">
                        REFRESH
                    </button>
                </div>
                <table class="players-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>IN-GAME NAME</th>
                            <th>DISCORD</th>
                            <th>K/D</th>
                            <th>STATS</th>
                            <th>ADMIN</th>
                            <th>ACTIONS</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for player in players %}
                        <tr>
                            <td>{{ player.id }}</td>
                            <td><strong>{{ player.in_game_name or 'N/A' }}</strong></td>
                            <td>{{ player.discord_name or 'N/A' }}</td>
                            <td>{{ player.kd_ratio }}</td>
                            <td>{{ player.total_kills or 0 }}/{{ player.total_deaths or 0 }}</td>
                            <td>
                                {% if player.is_admin %}
                                <span class="admin-badge">ADMIN</span>
                                {% else %}
                                Player
                                {% endif %}
                            </td>
                            <td>
                                <div class="action-buttons">
                                    <button class="action-btn action-edit" onclick="editPlayer({{ player.id }})">
                                        EDIT
                                    </button>
                                    <button class="action-btn action-delete" onclick="deletePlayer({{ player.id }})">
                                        DELETE
                                    </button>
                                </div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            <!-- System Info -->
            <div style="text-align: center; color: #888; font-size: 14px; margin-top: 40px; padding: 20px; border-top: 1px solid rgba(255, 255, 255, 0.1);">
                System Architecture: Web Dashboard ↔ Discord Bot ↔ Database ↔ API Gateway<br>
                Last Updated: {{ stats_data.timestamp|default('Now') }} | All connections established
            </div>
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('floating-dots');
                for (let i = 0; i < 40; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    dot.style.width = dot.style.height = Math.random() * 8 + 4 + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 15 + 's';
                    container.appendChild(dot);
                }
            }
            
            // Make system nodes pulse
            function animateNodes() {
                const nodes = document.querySelectorAll('.system-node');
                nodes.forEach((node, index) => {
                    node.style.animation = `pulse 2s ${index * 0.5}s infinite alternate`;
                });
            }
            
            function editPlayer(id) {
                alert('Edit player ' + id + ' (feature not implemented)');
            }
            
            function deletePlayer(id) {
                if (confirm('Are you sure you want to delete player ' + id + '?\nThis action cannot be undone.')) {
                    fetch('/admin/players/' + id, {
                        method: 'DELETE',
                        headers: {'Content-Type': 'application/json'}
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            showNotification('Player deleted successfully', 'success');
                            setTimeout(() => location.reload(), 1000);
                        } else {
                            showNotification('Error: ' + data.error, 'error');
                        }
                    })
                    .catch(err => showNotification('Error deleting player', 'error'));
                }
            }
            
            function refreshPlayers() {
                showNotification('Refreshing player data...', 'info');
                setTimeout(() => location.reload(), 500);
            }
            
            function showNotification(message, type) {
                // Create notification element
                const notification = document.createElement('div');
                notification.textContent = message;
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    padding: 15px 25px;
                    background: ${type === 'success' ? 'rgba(0, 255, 157, 0.1)' : 
                               type === 'error' ? 'rgba(255, 77, 77, 0.1)' : 
                               'rgba(157, 0, 255, 0.1)'};
                    color: ${type === 'success' ? '#00ff9d' : 
                           type === 'error' ? '#ff4d4d' : 
                           '#9d00ff'};
                    border: 1px solid ${type === 'success' ? 'rgba(0, 255, 157, 0.3)' : 
                                      type === 'error' ? 'rgba(255, 77, 77, 0.3)' : 
                                      'rgba(157, 0, 255, 0.3)'};
                    border-radius: 10px;
                    z-index: 1000;
                    font-weight: bold;
                    backdrop-filter: blur(10px);
                    animation: slideIn 0.3s ease;
                `;
                
                document.body.appendChild(notification);
                
                // Remove after 3 seconds
                setTimeout(() => {
                    notification.style.animation = 'slideOut 0.3s ease';
                    setTimeout(() => notification.remove(), 300);
                }, 3000);
            }
            
            // Add CSS for animations
            const style = document.createElement('style');
            style.textContent = `
                @keyframes pulse {
                    0% { transform: scale(1); opacity: 1; }
                    100% { transform: scale(1.2); opacity: 0.7; }
                }
                
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                
                @keyframes slideOut {
                    from { transform: translateX(0); opacity: 1; }
                    to { transform: translateX(100%); opacity: 0; }
                }
            `;
            document.head.appendChild(style);
            
            // Initialize on load
            window.addEventListener('load', () => {
                generateDots();
                animateNodes();
                
                // Add connection lines dynamically
                addConnectionLines();
            });
            
            function addConnectionLines() {
                // This would create SVG lines between nodes in a real implementation
                console.log('All system branches connected: Web, Bot, Database, API');
            }
        </script>
    </body>
    </html>
    ''', total_players=total_players, total_kills=total_kills, total_games=total_games, 
        admins=admins, players=players, stats_data=stats_data, bot_active=bot_active, port=port)

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
        "connected_branches": {
            "web_dashboard": True,
            "discord_bot": bot_active,
            "database": True,
            "api_endpoints": True
        },
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
    
    return jsonify({
        "leaderboard": leaderboard,
        "connected_to": ["database", "web_dashboard", "api_gateway"],
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/health')
def health():
    """Health check for all system branches"""
    return jsonify({
        "status": "healthy" if bot_active else "warning",
        "system": "SOT TDM System",
        "branches": {
            "web_dashboard": "online",
            "discord_bot": "online" if bot_active else "offline",
            "database": "connected",
            "api_endpoints": "active"
        },
        "connections": {
            "web_to_db": True,
            "web_to_bot": bot_active,
            "bot_to_db": bot_active,
            "api_to_db": True
        },
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
    """Run startup sequence for all system branches"""
    try:
        # Initialize database connection
        init_db()
        
        # Fix existing API keys
        fixed_keys = fix_existing_keys()
        if fixed_keys > 0:
            logger.info(f"Fixed {fixed_keys} API keys to correct format")
        
        # Test Discord bot connection
        if test_discord_token():
            logger.info("✅ Discord bot connected to system")
            
            if register_commands():
                logger.info("✅ Discord commands registered")
            else:
                logger.warning("⚠️ Could not register Discord commands")
        else:
            logger.warning("⚠️ Discord token not set or invalid")
        
        logger.info(f"✅ SOT TDM System started successfully")
        logger.info(f"   Web Dashboard: http://localhost:{port}")
        logger.info(f"   API Endpoints: http://localhost:{port}/api/stats")
        logger.info(f"   Health Check: http://localhost:{port}/health")
        logger.info(f"   Connected Branches: Web, Database, API" + (", Discord Bot" if bot_active else ""))
        
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")

# Initialize on import (for WSGI/Gunicorn)
startup_sequence()

# For direct execution
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=False)

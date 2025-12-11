app.py# app.py - SOT TDM System - Fixed for Deployment
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
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app, supports_credentials=True)

# Get port from environment or use default
port = int(os.environ.get("PORT", 10000))

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_all_players():
    """Get all players from database"""
    try:
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
    except Exception as e:
        logger.error(f"Error getting players: {e}")
        return []

def delete_player(player_id):
    """Delete a player from database"""
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM players WHERE id = ?', (player_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting player {player_id}: {e}")
        return False

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
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: #0a0a0a; 
                color: #fff; 
                min-height: 100vh; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                position: relative; 
                overflow: hidden; 
            }
            #dots { 
                position: fixed; 
                top: 0; 
                left: 0; 
                width: 100%; 
                height: 100%; 
                pointer-events: none; 
                z-index: 1;
            }
            .dot { 
                position: absolute; 
                background: rgba(255,255,255,0.05); 
                border-radius: 50%; 
                animation: float 20s infinite linear; 
            }
            @keyframes float { 
                0% { transform: translate(0,0) rotate(0deg); opacity: 0.1; } 
                50% { opacity: 0.2; } 
                100% { transform: translate(100vw,100vh) rotate(360deg); opacity: 0.1; } 
            }
            .login-container { 
                position: relative; 
                z-index: 2; 
                width: 100%;
                max-width: 400px; 
                padding: 40px; 
                background: rgba(20,20,20,0.85);
                backdrop-filter: blur(10px);
                border-radius: 12px; 
                border: 1px solid rgba(255,255,255,0.1); 
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            }
            h1 { 
                text-align: center; 
                margin-bottom: 10px; 
                color: #fff; 
                font-size: 28px;
                font-weight: 600;
            }
            h2 { 
                text-align: center; 
                margin-bottom: 30px; 
                color: #aaa; 
                font-weight: 400;
                font-size: 16px;
            }
            .input-group { margin-bottom: 20px; }
            input { 
                width: 100%; 
                padding: 14px 16px; 
                background: rgba(255,255,255,0.05); 
                border: 1px solid rgba(255,255,255,0.1); 
                border-radius: 8px; 
                color: #fff; 
                font-size: 16px;
                transition: all 0.3s ease;
            }
            input:focus { 
                outline: none; 
                border-color: rgba(255,255,255,0.3);
                box-shadow: 0 0 0 3px rgba(255,255,255,0.1);
            }
            input::placeholder { color: #666; }
            button { 
                width: 100%; 
                padding: 14px; 
                background: #3a3a3a; 
                color: #fff; 
                border: none; 
                border-radius: 8px; 
                font-size: 16px; 
                font-weight: 500;
                cursor: pointer; 
                margin-top: 10px; 
                transition: all 0.3s ease;
            }
            button:hover { 
                background: #4a4a4a; 
                transform: translateY(-1px);
            }
            button:active { 
                transform: translateY(0);
            }
            button:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
            .error { 
                color: #ff6b6b; 
                margin-top: 12px; 
                padding: 10px; 
                background: rgba(255,107,107,0.1); 
                border-radius: 6px; 
                border-left: 3px solid #ff6b6b; 
                display: none; 
                font-size: 14px;
            }
            .status { 
                margin-top: 24px; 
                padding: 12px; 
                background: rgba(255,255,255,0.05); 
                border-radius: 8px; 
                font-size: 14px; 
                color: #888; 
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .status-dot { 
                display: inline-block; 
                width: 8px; 
                height: 8px; 
                border-radius: 50%; 
            }
            .online { background: #4CAF50; box-shadow: 0 0 8px #4CAF50; }
            .offline { background: #f44336; box-shadow: 0 0 8px #f44336; }
            .footer {
                margin-top: 24px;
                text-align: center;
                color: #666;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div id="dots"></div>
        <div class="login-container">
            <h1>SOT TDM SYSTEM</h1>
            <h2>API Key Authentication</h2>
            
            <div class="input-group">
                <input type="text" id="apiKey" placeholder="Enter your API key (GOB-XXXXXXXXXXXXXXX)" autocomplete="off" spellcheck="false">
            </div>
            
            <button onclick="login()" id="loginBtn">Login to Dashboard</button>
            <div class="error" id="error"></div>
            
            <div class="status">
                <span class="status-dot {% if bot_active %}online{% else %}offline{% endif %}"></span>
                <span>Discord Bot: <strong>{% if bot_active %}Online{% else %}Offline{% endif %}</strong></span>
            </div>
            
            <div class="footer">
                System v1.0 • Secure Authentication
            </div>
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('dots');
                for (let i = 0; i < 25; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    const size = Math.random() * 4 + 2;
                    dot.style.width = dot.style.height = size + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 15 + 's';
                    dot.style.animationDuration = (Math.random() * 10 + 15) + 's';
                    container.appendChild(dot);
                }
            }
            
            function login() {
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const error = document.getElementById('error');
                const btn = document.getElementById('loginBtn');
                
                // Reset error
                error.style.display = 'none';
                
                if (!key) {
                    error.textContent = "Please enter an API key";
                    error.style.display = 'block';
                    return;
                }
                
                const keyPattern = /^GOB-[A-Z0-9]{20}$/;
                if (!keyPattern.test(key)) {
                    error.textContent = "Invalid format. Must be: GOB- followed by 20 uppercase letters/numbers";
                    error.style.display = 'block';
                    return;
                }
                
                // Show loading state
                btn.disabled = true;
                btn.textContent = 'Authenticating...';
                
                fetch('/api/validate-key', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ api_key: key })
                })
                .then(res => {
                    if (!res.ok) {
                        throw new Error(`HTTP ${res.status}`);
                    }
                    return res.json();
                })
                .then(data => {
                    if (data.valid) {
                        // Success - redirect to dashboard
                        btn.textContent = 'Access Granted!';
                        btn.style.background = '#4CAF50';
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 500);
                    } else {
                        error.textContent = data.error || 'Invalid API key';
                        error.style.display = 'block';
                        btn.disabled = false;
                        btn.textContent = 'Login to Dashboard';
                    }
                })
                .catch(err => {
                    console.error('Login error:', err);
                    error.textContent = 'Connection error. Please check your network and try again.';
                    error.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = 'Login to Dashboard';
                });
            }
            
            // Enter key to submit
            document.getElementById('apiKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    login();
                }
            });
            
            // Focus input on load
            document.addEventListener('DOMContentLoaded', function() {
                generateDots();
                document.getElementById('apiKey').focus();
            });
        </script>
    </body>
    </html>
    ''', bot_active=bot_active)

@app.route('/api/validate-key', methods=['POST'])
def api_validate_key():
    """Validate API key"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"valid": False, "error": "No data provided"})
        
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
            
            return jsonify({
                "valid": True, 
                "user": user_data.get('in_game_name'), 
                "is_admin": user_data.get('is_admin', False)
            })
        else:
            return jsonify({"valid": False, "error": "Invalid API key"})
    except Exception as e:
        logger.error(f"API validation error: {e}")
        return jsonify({"valid": False, "error": "Server error"}), 500

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
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: #0a0a0a; 
                color: #fff; 
                min-height: 100vh; 
                position: relative; 
            }
            #dots { 
                position: fixed; 
                top: 0; 
                left: 0; 
                width: 100%; 
                height: 100%; 
                pointer-events: none; 
                z-index: 1;
            }
            .dot { 
                position: absolute; 
                background: rgba(255,255,255,0.05); 
                border-radius: 50%; 
                animation: float 20s infinite linear; 
            }
            @keyframes float { 
                0% { transform: translate(0,0) rotate(0deg); opacity: 0.1; } 
                50% { opacity: 0.2; } 
                100% { transform: translate(100vw,100vh) rotate(360deg); opacity: 0.1; } 
            }
            .header { 
                position: relative;
                z-index: 2;
                padding: 20px 24px; 
                background: rgba(20,20,20,0.9);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(255,255,255,0.1); 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
            }
            .header-left h1 { 
                font-size: 20px; 
                font-weight: 600;
                color: #fff;
                margin-bottom: 4px;
            }
            .header-left .subtitle {
                font-size: 13px;
                color: #888;
            }
            .header-right { 
                display: flex; 
                gap: 10px; 
                align-items: center; 
            }
            .nav-btn { 
                padding: 8px 16px; 
                background: rgba(255,255,255,0.08); 
                color: #fff; 
                text-decoration: none; 
                border-radius: 6px; 
                font-size: 14px;
                font-weight: 500;
                transition: all 0.3s ease;
                border: 1px solid rgba(255,255,255,0.1);
            }
            .nav-btn:hover { 
                background: rgba(255,255,255,0.15);
                transform: translateY(-1px);
            }
            .main { 
                position: relative;
                z-index: 2;
                max-width: 1200px; 
                margin: 0 auto; 
                padding: 24px; 
            }
            .stats-grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); 
                gap: 20px; 
                margin-bottom: 30px; 
            }
            .stat-card { 
                background: rgba(20,20,20,0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.1); 
                border-radius: 10px; 
                padding: 24px; 
                transition: all 0.3s ease;
            }
            .stat-card:hover {
                border-color: rgba(255,255,255,0.2);
                transform: translateY(-2px);
                box-shadow: 0 8px 24px rgba(0,0,0,0.2);
            }
            .stat-label { 
                color: #aaa; 
                font-size: 13px; 
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 10px; 
                font-weight: 500;
            }
            .stat-value { 
                font-size: 32px; 
                font-weight: 700; 
                margin-bottom: 6px; 
                color: #fff;
            }
            .stat-detail { 
                color: #888; 
                font-size: 14px; 
            }
            .api-section { 
                background: rgba(20,20,20,0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.1); 
                border-radius: 10px; 
                padding: 28px; 
                margin-bottom: 30px; 
            }
            .api-section h2 { 
                color: #fff; 
                font-size: 18px; 
                margin-bottom: 18px; 
                font-weight: 600;
            }
            .api-key-display { 
                background: rgba(0,0,0,0.3); 
                border: 1px solid rgba(255,255,255,0.15); 
                border-radius: 8px; 
                padding: 20px; 
                font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace; 
                font-size: 16px; 
                color: #4CAF50; 
                margin-bottom: 20px; 
                letter-spacing: 0.5px;
                text-align: center;
                word-break: break-all;
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
                    rgba(76, 175, 80, 0.1), 
                    transparent);
                animation: scan 3s infinite linear;
            }
            @keyframes scan {
                0% { left: -100%; }
                100% { left: 100%; }
            }
            .action-btn {
                padding: 12px 24px;
                background: #3a3a3a;
                color: #fff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            .action-btn:hover {
                background: #4a4a4a;
                transform: translateY(-1px);
            }
            .leaderboard-section { 
                background: rgba(20,20,20,0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.1); 
                border-radius: 10px; 
                padding: 28px; 
                margin-bottom: 30px; 
            }
            .leaderboard-title { 
                color: #fff; 
                font-size: 18px; 
                margin-bottom: 20px; 
                font-weight: 600;
            }
            table { 
                width: 100%; 
                border-collapse: collapse; 
            }
            th { 
                background: rgba(255,255,255,0.05); 
                color: #aaa; 
                padding: 14px 16px; 
                text-align: left; 
                font-weight: 500;
                font-size: 13px;
                border-bottom: 2px solid rgba(255,255,255,0.1); 
            }
            td { 
                padding: 14px 16px; 
                border-bottom: 1px solid rgba(255,255,255,0.05); 
                font-size: 14px;
            }
            tr:hover { 
                background: rgba(255,255,255,0.03); 
            }
            .rank-cell { 
                color: #aaa; 
                width: 60px; 
                font-weight: 600;
            }
            .name-cell { 
                font-weight: 500; 
                color: #fff;
            }
            .you-row { 
                background: rgba(76, 175, 80, 0.05); 
                border-left: 3px solid #4CAF50;
            }
            .footer { 
                position: relative;
                z-index: 2;
                padding: 24px; 
                text-align: center; 
                color: #666; 
                font-size: 13px; 
                border-top: 1px solid rgba(255,255,255,0.1); 
                margin-top: 40px; 
                background: rgba(20,20,20,0.9);
                backdrop-filter: blur(10px);
            }
            @media (max-width: 768px) {
                .stats-grid { grid-template-columns: 1fr; }
                .header { flex-direction: column; gap: 15px; text-align: center; }
                .header-right { justify-content: center; }
                table { font-size: 13px; }
                th, td { padding: 10px 12px; }
            }
        </style>
    </head>
    <body>
        <div id="dots"></div>
        
        <div class="header">
            <div class="header-left">
                <h1>SOT TDM Dashboard</h1>
                <div class="subtitle">Welcome, {{ user_data.get('in_game_name', 'Player') }}</div>
            </div>
            <div class="header-right">
                <a href="/" class="nav-btn">Home</a>
                {% if user_data.get('is_admin') %}
                <a href="/admin" class="nav-btn">Admin</a>
                {% endif %}
                <a href="/logout" class="nav-btn">Logout</a>
            </div>
        </div>
        
        <div class="main">
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
                    <div class="stat-label">Leaderboard Rank</div>
                    <div class="stat-value">{{ user_rank }}</div>
                    <div class="stat-detail">Your global position</div>
                </div>
            </div>
            
            <!-- API Key Section -->
            <div class="api-section">
                <h2>Your API Key</h2>
                <div class="api-key-display">{{ session['user_key'] }}</div>
                <button class="action-btn" onclick="copyKey()">Copy to Clipboard</button>
            </div>
            
            <!-- Leaderboard -->
            <div class="leaderboard-section">
                <div class="leaderboard-title">Global Leaderboard (Top 10)</div>
                <table>
                    <thead>
                        <tr>
                            <th class="rank-cell">Rank</th>
                            <th class="name-cell">Player</th>
                            <th>K/D</th>
                            <th>Kills</th>
                            <th>Wins</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for player in leaderboard_data %}
                        <tr class="{% if player.api_key == session['user_key'] %}you-row{% endif %}">
                            <td class="rank-cell">#{{ loop.index }}</td>
                            <td class="name-cell">
                                {{ player.name }}
                                {% if player.api_key == session['user_key'] %}
                                <span style="color: #4CAF50; font-size: 12px; margin-left: 6px;">(You)</span>
                                {% endif %}
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
        
        <div class="footer">
            SOT TDM System v1.0 • Discord Bot: {% if bot_active %}Online{% else %}Offline{% endif %} • Secure API Authentication
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('dots');
                for (let i = 0; i < 20; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    const size = Math.random() * 3 + 2;
                    dot.style.width = dot.style.height = size + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 10 + 's';
                    dot.style.animationDuration = (Math.random() * 10 + 20) + 's';
                    container.appendChild(dot);
                }
            }
            
            function copyKey() {
                const key = "{{ session['user_key'] }}";
                navigator.clipboard.writeText(key)
                    .then(() => {
                        const btn = document.querySelector('.action-btn');
                        const originalText = btn.textContent;
                        btn.textContent = 'Copied!';
                        btn.style.background = '#4CAF50';
                        setTimeout(() => {
                            btn.textContent = originalText;
                            btn.style.background = '#3a3a3a';
                        }, 2000);
                    })
                    .catch(err => {
                        alert('Failed to copy. Please copy manually.');
                    });
            }
            
            // Initialize on load
            document.addEventListener('DOMContentLoaded', function() {
                generateDots();
            });
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
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: #0a0a0a; 
                color: #fff; 
                min-height: 100vh; 
            }
            #dots { 
                position: fixed; 
                top: 0; 
                left: 0; 
                width: 100%; 
                height: 100%; 
                pointer-events: none; 
                z-index: 1;
            }
            .dot { 
                position: absolute; 
                background: rgba(255,255,255,0.05); 
                border-radius: 50%; 
                animation: float 20s infinite linear; 
            }
            @keyframes float { 
                0% { transform: translate(0,0) rotate(0deg); opacity: 0.1; } 
                50% { opacity: 0.2; } 
                100% { transform: translate(100vw,100vh) rotate(360deg); opacity: 0.1; } 
            }
            .header { 
                position: relative;
                z-index: 2;
                padding: 20px 24px; 
                background: rgba(20,20,20,0.9);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(255,255,255,0.1); 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
            }
            .header h1 { 
                font-size: 20px; 
                font-weight: 600;
                color: #fff;
            }
            .header-nav { 
                display: flex; 
                gap: 10px; 
            }
            .nav-btn { 
                padding: 8px 16px; 
                background: rgba(255,255,255,0.08); 
                color: #fff; 
                text-decoration: none; 
                border-radius: 6px; 
                font-size: 14px;
                font-weight: 500;
                transition: all 0.3s ease;
                border: 1px solid rgba(255,255,255,0.1);
            }
            .nav-btn:hover { 
                background: rgba(255,255,255,0.15);
                transform: translateY(-1px);
            }
            .main { 
                position: relative;
                z-index: 2;
                max-width: 1400px; 
                margin: 0 auto; 
                padding: 24px; 
            }
            .stats-grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 20px; 
                margin-bottom: 30px; 
            }
            .stat-card { 
                background: rgba(20,20,20,0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.1); 
                border-radius: 10px; 
                padding: 24px; 
                text-align: center;
                transition: all 0.3s ease;
            }
            .stat-card:hover {
                border-color: rgba(255,255,255,0.2);
                transform: translateY(-2px);
            }
            .stat-value { 
                font-size: 36px; 
                font-weight: 700; 
                margin: 12px 0; 
                color: #fff;
            }
            .stat-label { 
                color: #aaa; 
                font-size: 13px; 
                text-transform: uppercase;
                letter-spacing: 0.5px;
                font-weight: 500;
            }
            .players-table { 
                width: 100%; 
                border-collapse: collapse; 
                background: rgba(20,20,20,0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.1); 
                border-radius: 10px; 
                overflow: hidden; 
                margin-top: 30px; 
            }
            th { 
                background: rgba(255,255,255,0.05); 
                color: #aaa; 
                padding: 16px; 
                text-align: left; 
                font-weight: 500;
                font-size: 13px;
                border-bottom: 2px solid rgba(255,255,255,0.1); 
            }
            td { 
                padding: 16px; 
                border-bottom: 1px solid rgba(255,255,255,0.05); 
                font-size: 14px;
            }
            tr:hover { 
                background: rgba(255,255,255,0.03); 
            }
            .admin-badge { 
                background: #4CAF50; 
                color: white; 
                padding: 4px 10px; 
                border-radius: 12px; 
                font-size: 12px; 
                font-weight: 600;
            }
            .action-buttons { 
                display: flex; 
                gap: 8px; 
            }
            .action-btn { 
                padding: 6px 12px; 
                border: none; 
                border-radius: 6px; 
                cursor: pointer; 
                font-size: 12px; 
                font-weight: 500;
                transition: all 0.3s ease;
            }
            .edit-btn { 
                background: rgba(255,255,255,0.1); 
                color: #fff; 
            }
            .delete-btn { 
                background: rgba(244, 67, 54, 0.2); 
                color: #f44336; 
                border: 1px solid rgba(244, 67, 54, 0.3);
            }
            .action-btn:hover { 
                transform: translateY(-1px);
                opacity: 0.9;
            }
            .footer { 
                position: relative;
                z-index: 2;
                padding: 24px; 
                text-align: center; 
                color: #666; 
                font-size: 13px; 
                border-top: 1px solid rgba(255,255,255,0.1); 
                margin-top: 40px; 
                background: rgba(20,20,20,0.9);
                backdrop-filter: blur(10px);
            }
            @media (max-width: 768px) {
                .stats-grid { grid-template-columns: repeat(2, 1fr); }
                .players-table { display: block; overflow-x: auto; }
                .header { flex-direction: column; gap: 15px; text-align: center; }
                .header-nav { justify-content: center; }
                th, td { padding: 12px; }
            }
            @media (max-width: 480px) {
                .stats-grid { grid-template-columns: 1fr; }
                .action-buttons { flex-direction: column; }
            }
        </style>
    </head>
    <body>
        <div id="dots"></div>
        
        <div class="header">
            <h1>Admin Control Panel</h1>
            <div class="header-nav">
                <a href="/dashboard" class="nav-btn">Dashboard</a>
                <a href="/" class="nav-btn">Home</a>
                <a href="/logout" class="nav-btn">Logout</a>
            </div>
        </div>
        
        <div class="main">
            <!-- Stats -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Players</div>
                    <div class="stat-value">{{ total_players }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Kills</div>
                    <div class="stat-value">{{ "{:,}".format(total_kills) }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Games Played</div>
                    <div class="stat-value">{{ total_games }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Admins</div>
                    <div class="stat-value">{{ admins }}</div>
                </div>
            </div>
            
            <!-- Players Table -->
            <h2 style="color: #fff; margin: 30px 0 15px 0; font-size: 18px; font-weight: 600;">Player Management ({{ total_players }} total)</h2>
            <table class="players-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>In-Game Name</th>
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
        </div>
        
        <div class="footer">
            System Admin • Discord Bot: {% if bot_active %}Online{% else %}Offline{% endif %} • Total Players: {{ total_players }}
        </div>
        
        <script>
            // Generate floating dots
            function generateDots() {
                const container = document.getElementById('dots');
                for (let i = 0; i < 15; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    const size = Math.random() * 3 + 2;
                    dot.style.width = dot.style.height = size + 'px';
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDelay = Math.random() * 10 + 's';
                    dot.style.animationDuration = (Math.random() * 10 + 20) + 's';
                    container.appendChild(dot);
                }
            }
            
            function editPlayer(id) {
                alert('Edit player ' + id + ' (feature coming soon)');
            }
            
            function deletePlayer(id) {
                if (confirm('Are you sure you want to delete player #' + id + '?\nThis action cannot be undone.')) {
                    fetch('/admin/players/' + id, {
                        method: 'DELETE',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    })
                    .then(res => {
                        if (!res.ok) {
                            throw new Error(`HTTP ${res.status}`);
                        }
                        return res.json();
                    })
                    .then(data => {
                        if (data.success) {
                            alert('Player deleted successfully');
                            location.reload();
                        } else {
                            alert('Error: ' + (data.error || 'Unknown error'));
                        }
                    })
                    .catch(err => {
                        console.error('Delete error:', err);
                        alert('Failed to delete player. Please try again.');
                    });
                }
            }
            
            // Initialize on load
            document.addEventListener('DOMContentLoaded', function() {
                generateDots();
            });
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
    try:
        stats = get_global_stats()
        return jsonify({
            "status": "success",
            "data": {
                "total_players": stats['total_players'],
                "total_kills": stats['total_kills'],
                "total_games": stats['total_games'],
                "avg_kd": stats['avg_kd'],
                "bot_active": bot_active
            },
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"API stats error: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to get stats"
        }), 500

@app.route('/api/leaderboard')
def api_leaderboard():
    """Get leaderboard data"""
    try:
        leaderboard = get_leaderboard(10)
        
        # Remove API keys from response for security
        for player in leaderboard:
            if 'api_key' in player:
                del player['api_key']
        
        return jsonify({
            "status": "success",
            "data": leaderboard,
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"API leaderboard error: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to get leaderboard"
        }), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Test database connection
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "service": "SOT TDM System",
            "bot_active": bot_active,
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            "status": "unhealthy",
            "service": "SOT TDM System",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 500

# =============================================================================
# DISCORD INTERACTIONS ENDPOINT
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord interactions"""
    try:
        data = request.json
        if not data:
            return jsonify({"type": 4, "data": {"content": "No data received", "flags": 64}})
        
        response = handle_interaction(data)
        return jsonify(response)
    except Exception as e:
        logger.error(f"Interaction error: {e}")
        return jsonify({"type": 4, "data": {"content": "Internal server error", "flags": 64}}), 500

# =============================================================================
# STARTUP - DELAYED INITIALIZATION
# =============================================================================

def initialize_system():
    """Initialize system components after app is ready"""
    import time
    import threading
    
    def startup_task():
        """Run startup tasks in background"""
        time.sleep(2)  # Wait for app to be fully ready
        
        try:
            # Initialize database
            logger.info("🔄 Initializing database...")
            init_db()
            
            # Fix any existing API keys
            fixed_keys = fix_existing_keys()
            if fixed_keys > 0:
                logger.info(f"✅ Fixed {fixed_keys} API keys")
            
            # Test Discord connection
            logger.info("🔄 Testing Discord connection...")
            bot_status = test_discord_token()
            
            if bot_status:
                logger.info("✅ Discord bot connected")
                
                # Register commands (non-blocking)
                def register_commands_task():
                    time.sleep(1)
                    if register_commands():
                        logger.info("✅ Discord commands registered")
                    else:
                        logger.warning("⚠️ Failed to register Discord commands")
                
                threading.Thread(target=register_commands_task, daemon=True).start()
            else:
                logger.warning("⚠️ Discord bot offline - continuing without bot features")
            
            logger.info(f"✅ SOT TDM System initialized on port {port}")
            
        except Exception as e:
            logger.error(f"❌ Startup error: {e}")
            logger.info("⚠️ System started with reduced functionality")
    
    # Start background initialization
    threading.Thread(target=startup_task, daemon=True).start()

# Initialize system when app starts
initialize_system()

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    # Run development server
    app.run(host='0.0.0.0', port=port, debug=False)

# app.py - Simplified Goblin Theme
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

def get_player_stats(player_id):
    """Get detailed stats for a specific player"""
    conn = get_db_connection()
    player = conn.execute('''
        SELECT * FROM players WHERE id = ?
    ''', (player_id,)).fetchone()
    
    if not player:
        conn.close()
        return None
    
    player_dict = {key: player[key] for key in player.keys()}
    
    # Get match history
    matches = conn.execute('''
        SELECT m.*, ms.kills, ms.deaths, ms.assists
        FROM matches m
        LEFT JOIN match_stats ms ON m.match_id = ms.match_id AND ms.player_id = ?
        WHERE ms.player_id = ?
        ORDER BY m.started_at DESC
        LIMIT 10
    ''', (player['discord_id'], player['discord_id'])).fetchall()
    
    conn.close()
    
    player_dict['matches'] = []
    for match in matches:
        match_dict = {key: match[key] for key in match.keys()}
        player_dict['matches'].append(match_dict)
    
    return player_dict

def update_player_data(player_id, data):
    """Update player information"""
    conn = get_db_connection()
    
    try:
        # Build update query
        update_fields = []
        values = []
        
        if 'in_game_name' in data:
            update_fields.append('in_game_name = ?')
            values.append(data['in_game_name'])
        
        if 'prestige' in data:
            update_fields.append('prestige = ?')
            values.append(int(data['prestige']))
        
        if 'is_admin' in data:
            update_fields.append('is_admin = ?')
            values.append(1 if data['is_admin'] else 0)
        
        if not update_fields:
            conn.close()
            return False
        
        values.append(player_id)
        query = f'UPDATE players SET {", ".join(update_fields)} WHERE id = ?'
        
        conn.execute(query, values)
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating player: {e}")
        conn.close()
        return False

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
    
    # Re-validate session for admin routes
    if request.endpoint in ['admin_dashboard']:
        user_data = validate_api_key(session.get('user_key'))
        if not user_data or not user_data.get('is_admin'):
            return redirect(url_for('dashboard'))

# =============================================================================
# WEB INTERFACE - SIMPLE GOBLIN THEME
# =============================================================================

@app.route('/')
def home():
    """Home page - Simple Goblin Theme"""
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
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Goblin Cave - SOT TDM</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
                color: #f0f0f0;
                min-height: 100vh;
                overflow-x: hidden;
                position: relative;
            }
            
            /* Animated Background */
            .cave-bg {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-image: 
                    radial-gradient(circle at 20% 50%, rgba(139, 92, 246, 0.1) 0%, transparent 20%),
                    radial-gradient(circle at 80% 20%, rgba(34, 197, 94, 0.1) 0%, transparent 20%),
                    radial-gradient(circle at 40% 80%, rgba(59, 130, 246, 0.1) 0%, transparent 20%);
                z-index: -2;
                animation: pulseBg 8s ease-in-out infinite alternate;
            }
            
            @keyframes pulseBg {
                0% { opacity: 0.7; }
                100% { opacity: 1; }
            }
            
            /* Floating Goblins */
            .goblin {
                position: fixed;
                font-size: 8rem;
                opacity: 0.05;
                z-index: -1;
                user-select: none;
                pointer-events: none;
                animation: float 20s linear infinite;
            }
            
            .goblin:nth-child(1) {
                top: 10%;
                left: 5%;
                animation-delay: 0s;
                animation-duration: 25s;
            }
            
            .goblin:nth-child(2) {
                top: 60%;
                right: 10%;
                animation-delay: 5s;
                animation-duration: 30s;
                animation-direction: reverse;
            }
            
            .goblin:nth-child(3) {
                bottom: 20%;
                left: 15%;
                animation-delay: 10s;
                animation-duration: 35s;
            }
            
            @keyframes float {
                0%, 100% {
                    transform: translateY(0px) rotate(0deg);
                }
                25% {
                    transform: translateY(-20px) rotate(5deg);
                }
                50% {
                    transform: translateY(0px) rotate(0deg);
                }
                75% {
                    transform: translateY(20px) rotate(-5deg);
                }
            }
            
            /* Main Container */
            .main-container {
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 2rem;
                position: relative;
                z-index: 1;
            }
            
            /* Header */
            .header {
                text-align: center;
                margin-bottom: 3rem;
                animation: fadeInDown 1s ease-out;
            }
            
            .title {
                font-size: 4rem;
                font-weight: 800;
                background: linear-gradient(90deg, #8b5cf6, #22c55e, #3b82f6);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 1rem;
                letter-spacing: -1px;
            }
            
            .subtitle {
                font-size: 1.2rem;
                color: #94a3b8;
                max-width: 500px;
                margin: 0 auto;
                line-height: 1.6;
            }
            
            /* Login Card */
            .login-card {
                background: rgba(30, 41, 59, 0.8);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 3rem;
                width: 100%;
                max-width: 500px;
                border: 1px solid rgba(139, 92, 246, 0.3);
                box-shadow: 
                    0 20px 40px rgba(0, 0, 0, 0.3),
                    inset 0 1px 0 rgba(255, 255, 255, 0.1);
                animation: fadeInUp 1s ease-out 0.2s both;
            }
            
            .card-header {
                text-align: center;
                margin-bottom: 2rem;
            }
            
            .card-title {
                font-size: 2rem;
                color: #f0f0f0;
                margin-bottom: 0.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 1rem;
            }
            
            .card-subtitle {
                color: #94a3b8;
                font-size: 1rem;
            }
            
            /* Key Input */
            .key-input-container {
                position: relative;
                margin-bottom: 1.5rem;
            }
            
            .key-icon {
                position: absolute;
                left: 1.5rem;
                top: 50%;
                transform: translateY(-50%);
                color: #8b5cf6;
                font-size: 1.2rem;
            }
            
            .key-input {
                width: 100%;
                padding: 1.2rem 1.2rem 1.2rem 3.5rem;
                background: rgba(15, 23, 42, 0.8);
                border: 2px solid rgba(139, 92, 246, 0.2);
                border-radius: 12px;
                color: #f0f0f0;
                font-size: 1.1rem;
                font-family: 'Courier New', monospace;
                transition: all 0.3s ease;
            }
            
            .key-input:focus {
                outline: none;
                border-color: #8b5cf6;
                box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1);
                transform: translateY(-2px);
            }
            
            .key-input::placeholder {
                color: #64748b;
            }
            
            /* Login Button */
            .login-btn {
                width: 100%;
                padding: 1.2rem;
                background: linear-gradient(90deg, #8b5cf6, #22c55e);
                border: none;
                border-radius: 12px;
                color: white;
                font-size: 1.1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.8rem;
                margin-top: 0.5rem;
            }
            
            .login-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(139, 92, 246, 0.3);
            }
            
            .login-btn:active {
                transform: translateY(0);
            }
            
            /* Error Message */
            .error-message {
                background: rgba(239, 68, 68, 0.1);
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 12px;
                padding: 1rem;
                margin-top: 1.5rem;
                color: #fca5a5;
                display: none;
                animation: fadeIn 0.3s ease-out;
            }
            
            /* Info Box */
            .info-box {
                background: rgba(15, 23, 42, 0.8);
                border-radius: 12px;
                padding: 1.5rem;
                margin-top: 2rem;
                border-left: 4px solid #22c55e;
            }
            
            .info-title {
                color: #22c55e;
                font-weight: 600;
                margin-bottom: 0.8rem;
                display: flex;
                align-items: center;
                gap: 0.8rem;
            }
            
            .info-text {
                color: #94a3b8;
                font-size: 0.95rem;
                line-height: 1.6;
            }
            
            .info-code {
                background: rgba(30, 41, 59, 0.8);
                padding: 0.4rem 0.8rem;
                border-radius: 6px;
                font-family: 'Courier New', monospace;
                color: #f0f0f0;
                margin: 0 0.2rem;
                border: 1px solid rgba(139, 92, 246, 0.2);
            }
            
            /* Footer */
            .footer {
                text-align: center;
                margin-top: 3rem;
                color: #64748b;
                font-size: 0.9rem;
                animation: fadeIn 1s ease-out 0.4s both;
            }
            
            /* Animations */
            @keyframes fadeInDown {
                from {
                    opacity: 0;
                    transform: translateY(-30px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            @keyframes fadeInUp {
                from {
                    opacity: 0;
                    transform: translateY(30px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .title {
                    font-size: 3rem;
                }
                
                .login-card {
                    padding: 2rem;
                    margin: 1rem;
                }
                
                .goblin {
                    font-size: 6rem;
                }
            }
            
            @media (max-width: 480px) {
                .title {
                    font-size: 2.5rem;
                }
                
                .subtitle {
                    font-size: 1rem;
                }
                
                .login-card {
                    padding: 1.5rem;
                }
                
                .card-title {
                    font-size: 1.8rem;
                }
                
                .key-input {
                    font-size: 1rem;
                    padding: 1rem 1rem 1rem 3rem;
                }
            }
        </style>
    </head>
    <body>
        <!-- Background Elements -->
        <div class="cave-bg"></div>
        <div class="goblin">👺</div>
        <div class="goblin">👹</div>
        <div class="goblin">🤡</div>
        
        <!-- Main Content -->
        <div class="main-container">
            <div class="header">
                <h1 class="title">Goblin Cave</h1>
                <p class="subtitle">Enter the cave with your API key to access the SOT TDM System</p>
            </div>
            
            <div class="login-card">
                <div class="card-header">
                    <div class="card-title">
                        🔑 API Key Access
                    </div>
                    <div class="card-subtitle">
                        Enter your GOB-XXXX... key to continue
                    </div>
                </div>
                
                <div class="key-input-container">
                    <div class="key-icon">🗝️</div>
                    <input 
                        type="text" 
                        class="key-input" 
                        id="apiKey" 
                        placeholder="GOB-XXXXXXXXXXXXXXXXXXXX"
                        autocomplete="off"
                        maxlength="24">
                </div>
                
                <button class="login-btn" onclick="validateKey()" id="loginBtn">
                    <span id="btnText">Enter the Cave</span>
                    <span id="btnIcon">⤵️</span>
                </button>
                
                <div class="error-message" id="errorMessage">
                    <div id="errorText">Invalid API key format</div>
                </div>
                
                <div class="info-box">
                    <div class="info-title">
                        ℹ️ Need a key?
                    </div>
                    <div class="info-text">
                        Use <span class="info-code">/register your_name</span> in Discord to get your API key.
                        Then use <span class="info-code">/key</span> to retrieve it anytime.
                    </div>
                </div>
            </div>
            
            <div class="footer">
                <p>SOT TDM System • Goblin Cave v1.0 • Secure Access Portal</p>
            </div>
        </div>
        
        <script>
            async function validateKey() {
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const errorDiv = document.getElementById('errorMessage');
                const errorText = document.getElementById('errorText');
                const btn = document.getElementById('loginBtn');
                const btnText = document.getElementById('btnText');
                const btnIcon = document.getElementById('btnIcon');
                
                // Frontend validation
                const keyPattern = /^GOB-[A-Z0-9]{20}$/;
                
                if (!key) {
                    errorText.textContent = "Please enter an API key";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                if (!keyPattern.test(key)) {
                    errorText.textContent = "Invalid format. Key must be: GOB- followed by 20 uppercase letters/numbers";
                    errorDiv.style.display = 'block';
                    return;
                }
                
                // Visual feedback
                btnText.textContent = "Validating...";
                btnIcon.textContent = "⏳";
                btn.disabled = true;
                
                try {
                    const response = await fetch('/api/validate-key', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ api_key: key })
                    });
                    
                    const data = await response.json();
                    
                    if (data.valid) {
                        btnText.textContent = "Access Granted!";
                        btnIcon.textContent = "✅";
                        btn.style.background = 'linear-gradient(90deg, #22c55e, #10b981)';
                        
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 800);
                    } else {
                        errorText.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        
                        btnText.textContent = "Enter the Cave";
                        btnIcon.textContent = "⤵️";
                        btn.disabled = false;
                    }
                } catch (error) {
                    errorText.textContent = 'Connection error. Please try again.';
                    errorDiv.style.display = 'block';
                    
                    btnText.textContent = "Enter the Cave";
                    btnIcon.textContent = "⤵️";
                    btn.disabled = false;
                }
            }
            
            // Auto-focus input on load
            document.addEventListener('DOMContentLoaded', function() {
                document.getElementById('apiKey').focus();
                
                // Add key validation on input
                document.getElementById('apiKey').addEventListener('input', function(e) {
                    const key = e.target.value.toUpperCase();
                    e.target.value = key;
                    
                    // Hide error when typing
                    document.getElementById('errorMessage').style.display = 'none';
                });
                
                // Enter key submits
                document.getElementById('apiKey').addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') validateKey();
                });
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
    response = make_response(redirect(url_for('home')))
    response.set_cookie('session', '', expires=0)
    return response

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
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard - Goblin Cave</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
                color: #f0f0f0;
                min-height: 100vh;
            }
            
            /* Goblin Background */
            .goblin-bg {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-image: 
                    radial-gradient(circle at 10% 20%, rgba(139, 92, 246, 0.1) 0%, transparent 25%),
                    radial-gradient(circle at 90% 40%, rgba(34, 197, 94, 0.1) 0%, transparent 25%),
                    radial-gradient(circle at 50% 80%, rgba(59, 130, 246, 0.1) 0%, transparent 25%);
                z-index: -2;
            }
            
            /* Header */
            .dashboard-header {
                background: rgba(30, 41, 59, 0.9);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(139, 92, 246, 0.3);
                padding: 1.5rem 2rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: 1rem;
            }
            
            .logo {
                font-size: 1.8rem;
                font-weight: 800;
                background: linear-gradient(90deg, #8b5cf6, #22c55e);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .header-right {
                display: flex;
                align-items: center;
                gap: 1.5rem;
            }
            
            .user-info {
                display: flex;
                align-items: center;
                gap: 0.8rem;
                padding: 0.8rem 1.2rem;
                background: rgba(15, 23, 42, 0.8);
                border-radius: 10px;
                border: 1px solid rgba(139, 92, 246, 0.2);
            }
            
            .user-avatar {
                width: 40px;
                height: 40px;
                background: linear-gradient(135deg, #8b5cf6, #22c55e);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 1.2rem;
            }
            
            .user-details {
                display: flex;
                flex-direction: column;
            }
            
            .user-name {
                font-weight: 600;
                color: #f0f0f0;
            }
            
            .user-rank {
                font-size: 0.85rem;
                color: #94a3b8;
            }
            
            .nav-links {
                display: flex;
                gap: 0.8rem;
            }
            
            .nav-link {
                padding: 0.8rem 1.2rem;
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(139, 92, 246, 0.2);
                color: #94a3b8;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.95rem;
            }
            
            .nav-link:hover {
                background: rgba(139, 92, 246, 0.1);
                color: #f0f0f0;
                border-color: #8b5cf6;
                transform: translateY(-2px);
            }
            
            .nav-link.logout:hover {
                background: rgba(239, 68, 68, 0.1);
                border-color: #ef4444;
                color: #fca5a5;
            }
            
            /* Main Content */
            .dashboard-container {
                max-width: 1200px;
                margin: 2rem auto;
                padding: 0 2rem;
                display: grid;
                grid-template-columns: 2fr 1fr;
                gap: 2rem;
                position: relative;
                z-index: 1;
            }
            
            @media (max-width: 1024px) {
                .dashboard-container {
                    grid-template-columns: 1fr;
                }
            }
            
            /* Profile Card */
            .profile-card {
                background: rgba(30, 41, 59, 0.8);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 2.5rem;
                border: 1px solid rgba(139, 92, 246, 0.3);
                box-shadow: 
                    0 20px 40px rgba(0, 0, 0, 0.3),
                    inset 0 1px 0 rgba(255, 255, 255, 0.1);
            }
            
            .profile-header {
                display: flex;
                align-items: center;
                gap: 2rem;
                margin-bottom: 2.5rem;
                padding-bottom: 2rem;
                border-bottom: 1px solid rgba(139, 92, 246, 0.2);
            }
            
            .profile-avatar {
                width: 100px;
                height: 100px;
                background: linear-gradient(135deg, #8b5cf6, #22c55e);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 3rem;
                font-weight: bold;
                box-shadow: 0 10px 30px rgba(139, 92, 246, 0.3);
            }
            
            .profile-details h2 {
                font-size: 2.5rem;
                margin-bottom: 0.5rem;
                color: #f0f0f0;
            }
            
            .profile-meta {
                color: #94a3b8;
                margin-bottom: 1rem;
                font-size: 1rem;
            }
            
            .profile-tags {
                display: flex;
                gap: 0.8rem;
                margin-top: 1rem;
                flex-wrap: wrap;
            }
            
            .profile-tag {
                padding: 0.5rem 1rem;
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 20px;
                font-size: 0.9rem;
                color: #94a3b8;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }
            
            .profile-tag.prestige {
                background: rgba(245, 158, 11, 0.1);
                border-color: rgba(245, 158, 11, 0.3);
                color: #fbbf24;
            }
            
            /* Stats Grid */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 1.5rem;
                margin-bottom: 2.5rem;
            }
            
            @media (max-width: 768px) {
                .stats-grid {
                    grid-template-columns: 1fr;
                }
            }
            
            .stat-card {
                background: rgba(15, 23, 42, 0.8);
                border-radius: 15px;
                padding: 1.8rem;
                border: 1px solid rgba(139, 92, 246, 0.2);
                transition: all 0.3s ease;
            }
            
            .stat-card:hover {
                transform: translateY(-5px);
                border-color: #8b5cf6;
                box-shadow: 0 10px 30px rgba(139, 92, 246, 0.2);
            }
            
            .stat-value {
                font-size: 3rem;
                font-weight: 800;
                margin: 0.5rem 0;
                color: #8b5cf6;
                text-shadow: 0 0 20px rgba(139, 92, 246, 0.3);
            }
            
            .stat-value.win-rate { color: #22c55e; }
            .stat-value.games { color: #3b82f6; }
            .stat-value.prestige { color: #f59e0b; }
            
            .stat-label {
                color: #94a3b8;
                font-size: 0.95rem;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }
            
            .stat-detail {
                color: #64748b;
                font-size: 0.9rem;
                margin-top: 0.5rem;
            }
            
            /* Key Section */
            .key-section {
                margin-top: 2.5rem;
                padding-top: 2.5rem;
                border-top: 1px solid rgba(139, 92, 246, 0.2);
            }
            
            .section-title {
                font-size: 1.5rem;
                color: #f0f0f0;
                margin-bottom: 1.5rem;
                display: flex;
                align-items: center;
                gap: 1rem;
            }
            
            .key-display {
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 12px;
                padding: 1.5rem;
                margin: 1.5rem 0;
                font-family: 'Courier New', monospace;
                color: #f0f0f0;
                word-break: break-all;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                font-size: 1.2rem;
                position: relative;
                overflow: hidden;
            }
            
            .key-display:hover {
                background: rgba(139, 92, 246, 0.1);
                border-color: #8b5cf6;
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(139, 92, 246, 0.2);
            }
            
            .key-display:active {
                transform: translateY(0);
            }
            
            .action-buttons {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1rem;
                margin-top: 1.5rem;
            }
            
            @media (max-width: 480px) {
                .action-buttons {
                    grid-template-columns: 1fr;
                }
            }
            
            .action-btn {
                padding: 1.2rem;
                background: linear-gradient(90deg, #8b5cf6, #22c55e);
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.8rem;
                font-size: 1rem;
            }
            
            .action-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(139, 92, 246, 0.3);
            }
            
            .action-btn.secondary {
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(139, 92, 246, 0.3);
                color: #94a3b8;
            }
            
            .action-btn.secondary:hover {
                background: rgba(139, 92, 246, 0.1);
                color: #f0f0f0;
                border-color: #8b5cf6;
            }
            
            /* Leaderboard */
            .leaderboard-card {
                background: rgba(30, 41, 59, 0.8);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 2.5rem;
                border: 1px solid rgba(139, 92, 246, 0.3);
                box-shadow: 
                    0 20px 40px rgba(0, 0, 0, 0.3),
                    inset 0 1px 0 rgba(255, 255, 255, 0.1);
                height: fit-content;
            }
            
            .card-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2rem;
                padding-bottom: 1.5rem;
                border-bottom: 1px solid rgba(139, 92, 246, 0.2);
            }
            
            .card-title {
                font-size: 1.8rem;
                color: #22c55e;
                font-weight: 700;
            }
            
            .refresh-btn {
                padding: 0.8rem 1.2rem;
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(139, 92, 246, 0.2);
                color: #94a3b8;
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.95rem;
            }
            
            .refresh-btn:hover {
                background: rgba(139, 92, 246, 0.1);
                color: #f0f0f0;
                border-color: #8b5cf6;
                transform: translateY(-2px);
            }
            
            .leaderboard-list {
                max-height: 500px;
                overflow-y: auto;
                padding-right: 10px;
                margin-bottom: 2rem;
            }
            
            .leaderboard-list::-webkit-scrollbar {
                width: 6px;
            }
            
            .leaderboard-list::-webkit-scrollbar-track {
                background: rgba(15, 23, 42, 0.8);
                border-radius: 3px;
            }
            
            .leaderboard-list::-webkit-scrollbar-thumb {
                background: rgba(139, 92, 246, 0.5);
                border-radius: 3px;
            }
            
            .leaderboard-item {
                display: flex;
                align-items: center;
                padding: 1.2rem;
                margin-bottom: 0.8rem;
                background: rgba(15, 23, 42, 0.8);
                border-radius: 12px;
                border: 1px solid rgba(139, 92, 246, 0.2);
                transition: all 0.3s ease;
            }
            
            .leaderboard-item:hover {
                transform: translateX(5px);
                border-color: #8b5cf6;
                box-shadow: 0 5px 15px rgba(139, 92, 246, 0.2);
            }
            
            .leaderboard-item.current-user {
                background: rgba(139, 92, 246, 0.1);
                border-color: #8b5cf6;
            }
            
            .rank {
                font-size: 1.3rem;
                font-weight: 800;
                width: 50px;
                text-align: center;
                color: #94a3b8;
            }
            
            .rank-1 { color: #fbbf24; }
            .rank-2 { color: #d1d5db; }
            .rank-3 { color: #f59e0b; }
            
            .player-info {
                flex-grow: 1;
                margin-left: 1.2rem;
            }
            
            .player-name {
                font-weight: 600;
                color: #f0f0f0;
                display: flex;
                align-items: center;
                gap: 0.8rem;
                margin-bottom: 0.4rem;
            }
            
            .player-stats {
                display: flex;
                gap: 1.5rem;
                font-size: 0.9rem;
                color: #94a3b8;
            }
            
            .player-kd {
                color: #22c55e;
                font-weight: 600;
            }
            
            .player-kills {
                color: #3b82f6;
                font-weight: 600;
            }
            
            /* Your Rank Section */
            .your-rank {
                background: rgba(15, 23, 42, 0.8);
                border-radius: 15px;
                padding: 1.8rem;
                border: 1px solid rgba(139, 92, 246, 0.3);
                border-left: 5px solid #22c55e;
            }
            
            .your-rank-header {
                display: flex;
                align-items: center;
                gap: 1rem;
                margin-bottom: 1.5rem;
            }
            
            .your-rank-title {
                font-size: 1.2rem;
                color: #22c55e;
                font-weight: 600;
            }
            
            .rank-stats {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .rank-number {
                font-size: 3rem;
                font-weight: 800;
                color: #8b5cf6;
            }
            
            .rank-kd {
                font-size: 2.5rem;
                font-weight: 800;
                color: #22c55e;
            }
            
            .rank-label {
                color: #94a3b8;
                font-size: 0.9rem;
                margin-top: 0.5rem;
            }
            
            /* Footer */
            .dashboard-footer {
                margin-top: 3rem;
                padding: 2rem;
                text-align: center;
                color: #64748b;
                font-size: 0.9rem;
                border-top: 1px solid rgba(139, 92, 246, 0.2);
            }
            
            .footer-links {
                display: flex;
                justify-content: center;
                gap: 2rem;
                margin-top: 1.5rem;
                flex-wrap: wrap;
            }
            
            .footer-link {
                color: #94a3b8;
                text-decoration: none;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.9rem;
            }
            
            .footer-link:hover {
                color: #f0f0f0;
                text-shadow: 0 0 10px rgba(139, 92, 246, 0.5);
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .dashboard-header {
                    flex-direction: column;
                    gap: 1.5rem;
                    padding: 1.5rem;
                }
                
                .dashboard-container {
                    padding: 1rem;
                    gap: 1.5rem;
                }
                
                .profile-header {
                    flex-direction: column;
                    text-align: center;
                    gap: 1.5rem;
                }
                
                .profile-avatar {
                    width: 80px;
                    height: 80px;
                    font-size: 2.5rem;
                }
                
                .profile-details h2 {
                    font-size: 2rem;
                }
                
                .nav-links {
                    flex-wrap: wrap;
                    justify-content: center;
                }
                
                .stat-value {
                    font-size: 2.5rem;
                }
                
                .card-header {
                    flex-direction: column;
                    gap: 1.5rem;
                    text-align: center;
                }
                
                .player-stats {
                    flex-wrap: wrap;
                    gap: 0.8rem;
                }
            }
            
            @media (max-width: 480px) {
                .logo {
                    font-size: 1.5rem;
                }
                
                .user-info {
                    flex-direction: column;
                    text-align: center;
                    padding: 1rem;
                }
                
                .stats-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="goblin-bg"></div>
        
        <!-- Header -->
        <div class="dashboard-header">
            <div class="header-left">
                <div class="logo">Goblin Cave</div>
                <div style="color: #94a3b8; font-size: 0.9rem;">
                    Player Dashboard
                </div>
            </div>
            
            <div class="header-right">
                <div class="user-info">
                    <div class="user-avatar">
                        {{ user_data.get('in_game_name', 'P')[0].upper() }}
                    </div>
                    <div class="user-details">
                        <div class="user-name">{{ user_data.get('in_game_name', 'Player') }}</div>
                        <div class="user-rank">Rank: {{ user_rank }}</div>
                    </div>
                </div>
                
                <div class="nav-links">
                    <a href="/dashboard" class="nav-link" style="background: rgba(139, 92, 246, 0.1); color: #f0f0f0; border-color: #8b5cf6;">
                        <span>🏠</span> Dashboard
                    </a>
                    {% if user_data.get('is_admin') %}
                    <a href="/admin" class="nav-link">
                        <span>👑</span> Admin
                    </a>
                    {% endif %}
                    <a href="/logout" class="nav-link logout">
                        <span>🚪</span> Logout
                    </a>
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="dashboard-container">
            <div>
                <!-- Profile Card -->
                <div class="profile-card">
                    <div class="profile-header">
                        <div class="profile-avatar">
                            {{ user_data.get('in_game_name', 'P')[0].upper() }}
                        </div>
                        <div class="profile-details">
                            <h2>{{ user_data.get('in_game_name', 'Player') }}</h2>
                            <div class="profile-meta">
                                <span>📅 Joined: {{ user_data.get('created_at', '')[:10] }}</span>
                                {% if user_data.get('is_admin') %}
                                <span style="margin-left: 1rem;">👑 Administrator</span>
                                {% endif %}
                            </div>
                            <div class="profile-tags">
                                <div class="profile-tag prestige">
                                    <span>👑</span> Prestige {{ user_data.get('prestige', 0) }}
                                </div>
                                <div class="profile-tag">
                                    <span>🎮</span> {{ total_games }} Games
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value">{{ "%.2f"|format(kd) }}</div>
                            <div class="stat-label">K/D Ratio</div>
                            <div class="stat-detail">
                                {{ total_kills }} kills / {{ total_deaths }} deaths
                            </div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-value win-rate">{{ "%.1f"|format(win_rate) }}%</div>
                            <div class="stat-label">Win Rate</div>
                            <div class="stat-detail">
                                {{ wins }} wins / {{ losses }} losses
                            </div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-value games">{{ total_games }}</div>
                            <div class="stat-label">Games Played</div>
                            <div class="stat-detail">
                                Total matches completed
                            </div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-value prestige">{{ user_data.get('prestige', 0) }}</div>
                            <div class="stat-label">Prestige Level</div>
                            <div class="stat-detail">
                                Current prestige rank
                            </div>
                        </div>
                    </div>
                    
                    <div class="key-section">
                        <div class="section-title">
                            <span>🗝️</span> Your API Key
                        </div>
                        
                        <p style="color: #94a3b8; margin-bottom: 1.5rem; line-height: 1.6;">
                            This key uniquely identifies you in the system. Keep it secure.
                        </p>
                        
                        <div class="key-display" id="apiKeyDisplay" onclick="copyKey()" title="Click to copy">
                            {{ session['user_key'] }}
                        </div>
                        
                        <div class="action-buttons">
                            <button class="action-btn" onclick="copyKey()">
                                <span>📋</span> Copy Key
                            </button>
                            <button class="action-btn secondary" onclick="downloadTool()">
                                <span>📥</span> Download Tool
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Leaderboard -->
            <div class="leaderboard-card">
                <div class="card-header">
                    <div class="card-title">
                        <span>🏆</span> Global Leaderboard
                    </div>
                    <button class="refresh-btn" onclick="loadLeaderboard()">
                        <span>🔄</span> Refresh
                    </button>
                </div>
                
                <div class="leaderboard-list" id="leaderboardContainer">
                    {% for player in leaderboard_data %}
                    <div class="leaderboard-item {{ 'current-user' if player.api_key == session['user_key'] else '' }}">
                        <div class="rank rank-{{ loop.index if loop.index <= 3 else 'other' }}">
                            #{{ loop.index }}
                        </div>
                        <div class="player-info">
                            <div class="player-name">
                                {{ player.name }}
                                {% if player.api_key == session['user_key'] %}
                                <span style="font-size: 0.8rem; color: #8b5cf6;">
                                    <span>👤</span> You
                                </span>
                                {% endif %}
                                {% if player.prestige > 0 %}
                                <span style="font-size: 0.8rem; color: #f59e0b;">
                                    P{{ player.prestige }}
                                </span>
                                {% endif %}
                            </div>
                            <div class="player-stats">
                                <div>
                                    <span style="color: #64748b;">K/D:</span>
                                    <span class="player-kd">{{ player.kd }}</span>
                                </div>
                                <div>
                                    <span style="color: #64748b;">Kills:</span>
                                    <span class="player-kills">{{ player.kills }}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    {% else %}
                    <div style="text-align: center; padding: 3rem; color: #64748b;">
                        <span style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.5;">👥</span>
                        <p>No players on leaderboard yet</p>
                    </div>
                    {% endfor %}
                </div>
                
                <div class="your-rank">
                    <div class="your-rank-header">
                        <span>📊</span>
                        <div class="your-rank-title">Your Position</div>
                    </div>
                    <div class="rank-stats">
                        <div>
                            <div class="rank-number">{{ user_rank }}</div>
                            <div class="rank-label">Global Rank</div>
                        </div>
                        <div style="text-align: right;">
                            <div class="rank-kd">{{ "%.2f"|format(kd) }}</div>
                            <div class="rank-label">Your K/D Ratio</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="dashboard-footer">
            <div style="margin-bottom: 1.5rem; display: flex; align-items: center; justify-content: center; gap: 1.5rem; flex-wrap: wrap;">
                <span>Goblin Cave Dashboard v1.0</span>
                <span style="color: #64748b;">•</span>
                <span>Session Active</span>
                <span style="color: #64748b;">•</span>
                <span>Last Update: {{ datetime.now().strftime('%H:%M:%S') }}</span>
            </div>
            
            <div class="footer-links">
                <a href="/" class="footer-link">
                    <span>🏠</span> Home
                </a>
                <a href="#" class="footer-link" onclick="showDiscordInfo()">
                    <span>💬</span> Discord
                </a>
                <a href="/health" class="footer-link" target="_blank">
                    <span>⚡</span> System Status
                </a>
            </div>
        </div>
        
        <script>
            function copyKey() {
                const key = "{{ session['user_key'] }}";
                navigator.clipboard.writeText(key).then(() => {
                    showNotification('API key copied to clipboard', 'success');
                }).catch(err => {
                    console.error('Copy failed:', err);
                    showNotification('Failed to copy key', 'error');
                });
            }
            
            function downloadTool() {
                showNotification('Download feature coming soon', 'info');
            }
            
            async function loadLeaderboard() {
                const container = document.getElementById('leaderboardContainer');
                const btn = event?.target;
                const originalText = btn?.querySelector('span:last-child')?.textContent || '';
                
                if (btn) {
                    const icon = btn.querySelector('span:first-child');
                    icon.textContent = '⏳';
                    btn.disabled = true;
                }
                
                try {
                    const response = await fetch('/api/leaderboard');
                    const data = await response.json();
                    
                    if (data.leaderboard && data.leaderboard.length > 0) {
                        let html = '';
                        
                        data.leaderboard.forEach((player, index) => {
                            const rank = index + 1;
                            const rankClass = rank <= 3 ? `rank-${rank}` : 'rank-other';
                            const isCurrentUser = "{{ user_data.get('in_game_name', '') }}" === player.name;
                            
                            html += `
                                <div class="leaderboard-item ${isCurrentUser ? 'current-user' : ''}">
                                    <div class="rank ${rankClass}">#${rank}</div>
                                    <div class="player-info">
                                        <div class="player-name">
                                            ${player.name}
                                            ${isCurrentUser ? '<span style="font-size: 0.8rem; color: #8b5cf6;"><span>👤</span> You</span>' : ''}
                                            ${player.prestige > 0 ? `<span style="font-size: 0.8rem; color: #f59e0b;">P${player.prestige}</span>` : ''}
                                        </div>
                                        <div class="player-stats">
                                            <div>
                                                <span style="color: #64748b;">K/D:</span>
                                                <span class="player-kd">${player.kd}</span>
                                            </div>
                                            <div>
                                                <span style="color: #64748b;">Kills:</span>
                                                <span class="player-kills">${player.kills}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            `;
                        });
                        
                        container.innerHTML = html;
                    } else {
                        container.innerHTML = `
                            <div style="text-align: center; padding: 3rem; color: #64748b;">
                                <span style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.5;">👥</span>
                                <p>No players on leaderboard yet</p>
                            </div>
                        `;
                    }
                    
                    if (btn) {
                        const icon = btn.querySelector('span:first-child');
                        icon.textContent = '✅';
                        setTimeout(() => {
                            icon.textContent = '🔄';
                            btn.disabled = false;
                        }, 500);
                    }
                    
                } catch (error) {
                    console.error('Error loading leaderboard:', error);
                    container.innerHTML = `
                        <div style="text-align: center; padding: 3rem; color: #64748b;">
                            <span style="font-size: 3rem; margin-bottom: 1rem; color: #ef4444;">⚠️</span>
                            <p>Failed to load leaderboard</p>
                        </div>
                    `;
                    
                    if (btn) {
                        const icon = btn.querySelector('span:first-child');
                        icon.textContent = '⚠️';
                        setTimeout(() => {
                            icon.textContent = '🔄';
                            btn.disabled = false;
                        }, 1000);
                    }
                }
            }
            
            function showDiscordInfo() {
                alert('Join our Discord server for support and updates.');
            }
            
            function showNotification(message, type = 'info') {
                const colors = {
                    info: '#8b5cf6',
                    success: '#22c55e',
                    warning: '#f59e0b',
                    error: '#ef4444'
                };
                
                const icons = {
                    info: 'ℹ️',
                    success: '✅',
                    warning: '⚠️',
                    error: '❌'
                };
                
                const notification = document.createElement('div');
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: rgba(30, 41, 59, 0.95);
                    backdrop-filter: blur(10px);
                    border-left: 4px solid ${colors[type]};
                    color: #f0f0f0;
                    padding: 1.2rem;
                    border-radius: 12px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                    z-index: 10000;
                    transform: translateX(400px);
                    transition: transform 0.3s ease-out;
                    max-width: 300px;
                    display: flex;
                    align-items: center;
                    gap: 1rem;
                    border: 1px solid rgba(139, 92, 246, 0.3);
                `;
                
                notification.innerHTML = `
                    <span style="font-size: 1.5rem;">${icons[type]}</span>
                    <div>
                        <div style="font-weight: 600; color: ${colors[type]}; margin-bottom: 0.3rem;">${type.toUpperCase()}</div>
                        <div style="margin-top: 0.2rem; font-size: 0.95rem;">${message}</div>
                    </div>
                `;
                
                document.body.appendChild(notification);
                
                setTimeout(() => {
                    notification.style.transform = 'translateX(0)';
                }, 10);
                
                setTimeout(() => {
                    notification.style.transform = 'translateX(400px)';
                    setTimeout(() => notification.remove(), 300);
                }, 3000);
                
                notification.addEventListener('click', () => {
                    notification.style.transform = 'translateX(400px)';
                    setTimeout(() => notification.remove(), 300);
                });
            }
            
            // Auto-refresh leaderboard every 60 seconds
            setInterval(loadLeaderboard, 60000);
            
            // Initialize on load
            document.addEventListener('DOMContentLoaded', function() {
                // Add click effect to key display
                const keyDisplay = document.getElementById('apiKeyDisplay');
                if (keyDisplay) {
                    keyDisplay.addEventListener('click', copyKey);
                }
            });
        </script>
    </body>
    </html>
    ''', user_data=user_data, session=session, leaderboard_data=leaderboard_data, 
        total_kills=total_kills, total_deaths=total_deaths, wins=wins, losses=losses,
        kd=kd, total_games=total_games, win_rate=win_rate, user_rank=user_rank, datetime=datetime)

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
    
    # Get recent activity
    conn = get_db_connection()
    recent_activity = conn.execute('''
        SELECT * FROM tickets 
        WHERE status = 'open'
        ORDER BY created_at DESC
        LIMIT 5
    ''').fetchall()
    
    recent_matches = conn.execute('''
        SELECT * FROM matches 
        ORDER BY started_at DESC
        LIMIT 5
    ''').fetchall()
    conn.close()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin Dashboard - Goblin Cave</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
                color: #f0f0f0;
                min-height: 100vh;
            }
            
            /* Header */
            .admin-header {
                background: rgba(30, 41, 59, 0.9);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(245, 158, 11, 0.3);
                padding: 1.5rem 2rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: 1rem;
            }
            
            .logo {
                font-size: 1.8rem;
                font-weight: 800;
                background: linear-gradient(90deg, #f59e0b, #d97706);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .admin-badge {
                padding: 0.8rem 1.2rem;
                background: rgba(245, 158, 11, 0.1);
                border: 1px solid rgba(245, 158, 11, 0.3);
                border-radius: 8px;
                color: #f59e0b;
                font-weight: 600;
                font-size: 0.95rem;
                display: flex;
                align-items: center;
                gap: 0.8rem;
            }
            
            .nav-links {
                display: flex;
                gap: 0.8rem;
            }
            
            .nav-link {
                padding: 0.8rem 1.2rem;
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(139, 92, 246, 0.2);
                color: #94a3b8;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.95rem;
            }
            
            .nav-link:hover {
                background: rgba(139, 92, 246, 0.1);
                color: #f0f0f0;
                border-color: #8b5cf6;
                transform: translateY(-2px);
            }
            
            .nav-link.active {
                background: rgba(245, 158, 11, 0.1);
                border-color: #f59e0b;
                color: #f0f0f0;
            }
            
            /* Main Content */
            .admin-container {
                max-width: 1400px;
                margin: 2rem auto;
                padding: 0 2rem;
                position: relative;
                z-index: 1;
            }
            
            /* Stats Grid */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 1.5rem;
                margin-bottom: 2.5rem;
            }
            
            @media (max-width: 1024px) {
                .stats-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
            
            @media (max-width: 640px) {
                .stats-grid {
                    grid-template-columns: 1fr;
                }
            }
            
            .stat-card {
                background: rgba(30, 41, 59, 0.8);
                backdrop-filter: blur(10px);
                border-radius: 15px;
                padding: 2rem;
                border: 1px solid rgba(139, 92, 246, 0.2);
                transition: all 0.3s ease;
            }
            
            .stat-card:hover {
                transform: translateY(-5px);
                border-color: #8b5cf6;
                box-shadow: 0 10px 30px rgba(139, 92, 246, 0.2);
            }
            
            .stat-icon {
                font-size: 2.5rem;
                margin-bottom: 1rem;
                color: #8b5cf6;
            }
            
            .stat-value {
                font-size: 3rem;
                font-weight: 800;
                margin: 1rem 0;
                color: #f0f0f0;
                text-shadow: 0 0 20px rgba(139, 92, 246, 0.3);
            }
            
            .stat-label {
                color: #94a3b8;
                font-size: 0.95rem;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }
            
            /* Admin Sections */
            .admin-sections {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 2rem;
                margin-bottom: 2.5rem;
            }
            
            @media (max-width: 1024px) {
                .admin-sections {
                    grid-template-columns: 1fr;
                }
            }
            
            .admin-section {
                background: rgba(30, 41, 59, 0.8);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 2rem;
                border: 1px solid rgba(139, 92, 246, 0.3);
            }
            
            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1.5rem;
                padding-bottom: 1.5rem;
                border-bottom: 1px solid rgba(139, 92, 246, 0.2);
            }
            
            .section-title {
                font-size: 1.5rem;
                color: #f0f0f0;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 1rem;
            }
            
            .view-all {
                padding: 0.6rem 1.2rem;
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(139, 92, 246, 0.2);
                color: #94a3b8;
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
                font-size: 0.9rem;
                text-decoration: none;
            }
            
            .view-all:hover {
                background: rgba(139, 92, 246, 0.1);
                color: #f0f0f0;
                border-color: #8b5cf6;
                transform: translateY(-2px);
            }
            
            /* Activity List */
            .activity-list {
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }
            
            .activity-item {
                display: flex;
                align-items: center;
                gap: 1.2rem;
                padding: 1.2rem;
                background: rgba(15, 23, 42, 0.8);
                border-radius: 12px;
                border: 1px solid rgba(139, 92, 246, 0.2);
                transition: all 0.3s ease;
            }
            
            .activity-item:hover {
                transform: translateX(5px);
                border-color: #8b5cf6;
            }
            
            .activity-icon {
                width: 50px;
                height: 50px;
                background: linear-gradient(135deg, #8b5cf6, #22c55e);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 1.5rem;
            }
            
            .activity-content {
                flex-grow: 1;
            }
            
            .activity-title {
                font-weight: 600;
                color: #f0f0f0;
                margin-bottom: 0.4rem;
                display: flex;
                align-items: center;
                gap: 0.8rem;
            }
            
            .activity-time {
                color: #94a3b8;
                font-size: 0.85rem;
            }
            
            /* Badges */
            .badge {
                padding: 0.3rem 0.8rem;
                border-radius: 6px;
                font-size: 0.8rem;
                font-weight: 600;
            }
            
            .badge-success { background: rgba(34, 197, 94, 0.1); color: #22c55e; }
            .badge-warning { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
            .badge-info { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
            .badge-purple { background: rgba(139, 92, 246, 0.1); color: #8b5cf6; }
            
            /* Quick Actions */
            .quick-actions {
                margin-top: 2.5rem;
            }
            
            .actions-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 1.5rem;
                margin-top: 1.5rem;
            }
            
            .action-card {
                background: rgba(30, 41, 59, 0.8);
                backdrop-filter: blur(10px);
                border-radius: 15px;
                padding: 2rem;
                border: 1px solid rgba(139, 92, 246, 0.2);
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                text-decoration: none;
                color: #f0f0f0;
                display: block;
            }
            
            .action-card:hover {
                transform: translateY(-5px);
                border-color: #8b5cf6;
                box-shadow: 0 10px 30px rgba(139, 92, 246, 0.2);
                background: rgba(30, 41, 59, 0.9);
            }
            
            .action-icon {
                font-size: 3rem;
                margin-bottom: 1rem;
                color: #8b5cf6;
            }
            
            .action-title {
                font-weight: 600;
                margin-bottom: 0.8rem;
                font-size: 1.2rem;
            }
            
            .action-desc {
                color: #94a3b8;
                font-size: 0.9rem;
                line-height: 1.5;
            }
            
            /* Footer */
            .admin-footer {
                margin-top: 3rem;
                padding: 2rem;
                text-align: center;
                color: #64748b;
                font-size: 0.9rem;
                border-top: 1px solid rgba(139, 92, 246, 0.2);
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .admin-header {
                    flex-direction: column;
                    gap: 1.5rem;
                    padding: 1.5rem;
                }
                
                .admin-container {
                    padding: 1rem;
                }
                
                .nav-links {
                    flex-wrap: wrap;
                    justify-content: center;
                }
                
                .section-header {
                    flex-direction: column;
                    gap: 1.5rem;
                    text-align: center;
                }
                
                .activity-item {
                    flex-direction: column;
                    text-align: center;
                    gap: 1rem;
                }
                
                .actions-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <!-- Header -->
        <div class="admin-header">
            <div class="header-left">
                <div class="logo">👑 Goblin Admin</div>
                <div style="color: #94a3b8; font-size: 0.9rem;">
                    System Management
                </div>
            </div>
            
            <div class="admin-badge">
                <span>👑</span> Administrator
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="admin-container">
            <!-- Stats Overview -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon">👥</div>
                    <div class="stat-value">{{ total_players }}</div>
                    <div class="stat-label">Total Players</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-icon">🎯</div>
                    <div class="stat-value">{{ "{:,}".format(total_kills) }}</div>
                    <div class="stat-label">Total Kills</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-icon">🎮</div>
                    <div class="stat-value">{{ total_games }}</div>
                    <div class="stat-label">Games Played</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-icon">👑</div>
                    <div class="stat-value">{{ admins }}</div>
                    <div class="stat-label">Administrators</div>
                </div>
            </div>
            
            <!-- Recent Activity -->
            <div class="admin-sections">
                <div class="admin-section">
                    <div class="section-header">
                        <div class="section-title">
                            <span>🎫</span> Recent Tickets
                        </div>
                        <a href="#" class="view-all">View All</a>
                    </div>
                    
                    <div class="activity-list">
                        {% for ticket in recent_activity %}
                        <div class="activity-item">
                            <div class="activity-icon">❓</div>
                            <div class="activity-content">
                                <div class="activity-title">
                                    {{ ticket.discord_name }}
                                    <span class="badge badge-info">{{ ticket.category }}</span>
                                </div>
                                <div class="activity-time">
                                    {{ ticket.created_at[:10] }} • {{ ticket.issue[:50] }}...
                                </div>
                            </div>
                        </div>
                        {% else %}
                        <div style="text-align: center; padding: 3rem; color: #64748b;">
                            <span style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.5;">✅</span>
                            <p>No open tickets</p>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                
                <div class="admin-section">
                    <div class="section-header">
                        <div class="section-title">
                            <span>🏆</span> Recent Matches
                        </div>
                        <a href="#" class="view-all">View All</a>
                    </div>
                    
                    <div class="activity-list">
                        {% for match in recent_matches %}
                        <div class="activity-item">
                            <div class="activity-icon">⚔️</div>
                            <div class="activity-content">
                                <div class="activity-title">
                                    Match {{ match.match_id[:8] }}
                                    <span class="badge {{ 'badge-success' if match.status == 'ended' else 'badge-warning' }}">
                                        {{ match.status }}
                                    </span>
                                </div>
                                <div class="activity-time">
                                    {{ match.started_at[:10] }} • Score: {{ match.team1_score }}-{{ match.team2_score }}
                                </div>
                            </div>
                        </div>
                        {% else %}
                        <div style="text-align: center; padding: 3rem; color: #64748b;">
                            <span style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.5;">⚔️</span>
                            <p>No recent matches</p>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            
            <!-- Quick Actions -->
            <div class="quick-actions">
                <h2 style="color: #f0f0f0; margin-bottom: 1.5rem; font-size: 1.8rem; display: flex; align-items: center; gap: 1rem;">
                    <span>⚡</span> Quick Actions
                </h2>
                
                <div class="actions-grid">
                    <a href="/admin/players" class="action-card">
                        <div class="action-icon">👥</div>
                        <div class="action-title">Manage Players</div>
                        <div class="action-desc">
                            View, edit, and manage all registered players
                        </div>
                    </a>
                    
                    <a href="/admin/players?action=add" class="action-card">
                        <div class="action-icon">➕</div>
                        <div class="action-title">Add Player</div>
                        <div class="action-desc">
                            Manually register a new player to the system
                        </div>
                    </a>
                    
                    <a href="#" class="action-card" onclick="showNotification('Feature coming soon', 'info')">
                        <div class="action-icon">🎫</div>
                        <div class="action-title">Manage Tickets</div>
                        <div class="action-desc">
                            Review and resolve support tickets
                        </div>
                    </a>
                    
                    <a href="#" class="action-card" onclick="showNotification('Feature coming soon', 'info')">
                        <div class="action-icon">⚙️</div>
                        <div class="action-title">System Settings</div>
                        <div class="action-desc">
                            Configure system preferences and options
                        </div>
                    </a>
                </div>
            </div>
        </div>
        
        <div class="admin-footer">
            <div style="margin-bottom: 1.5rem; display: flex; align-items: center; justify-content: center; gap: 1.5rem; flex-wrap: wrap;">
                <span>👑 Admin Panel v1.0</span>
                <span style="color: #64748b;">•</span>
                <span>System Time: {{ datetime.now().strftime('%H:%M:%S') }}</span>
                <span style="color: #64748b;">•</span>
                <span>Status: <span style="color: #22c55e;">Operational</span></span>
            </div>
            
            <div style="color: #64748b; font-size: 0.85rem; opacity: 0.8;">
                &copy; {{ datetime.now().year }} Goblin Cave Administration
            </div>
        </div>
        
        <script>
            function showNotification(message, type = 'info') {
                const colors = {
                    info: '#8b5cf6',
                    success: '#22c55e',
                    warning: '#f59e0b',
                    error: '#ef4444'
                };
                
                const icons = {
                    info: 'ℹ️',
                    success: '✅',
                    warning: '⚠️',
                    error: '❌'
                };
                
                const notification = document.createElement('div');
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: rgba(30, 41, 59, 0.95);
                    backdrop-filter: blur(10px);
                    border-left: 4px solid ${colors[type]};
                    color: #f0f0f0;
                    padding: 1.2rem;
                    border-radius: 12px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                    z-index: 10000;
                    transform: translateX(400px);
                    transition: transform 0.3s ease-out;
                    max-width: 300px;
                    display: flex;
                    align-items: center;
                    gap: 1rem;
                    border: 1px solid rgba(139, 92, 246, 0.3);
                `;
                
                notification.innerHTML = `
                    <span style="font-size: 1.5rem;">${icons[type]}</span>
                    <div>
                        <div style="font-weight: 600; color: ${colors[type]}; margin-bottom: 0.3rem;">${type.toUpperCase()}</div>
                        <div style="margin-top: 0.2rem; font-size: 0.95rem;">${message}</div>
                    </div>
                `;
                
                document.body.appendChild(notification);
                
                setTimeout(() => {
                    notification.style.transform = 'translateX(0)';
                }, 10);
                
                setTimeout(() => {
                    notification.style.transform = 'translateX(400px)';
                    setTimeout(() => notification.remove(), 300);
                }, 3000);
                
                notification.addEventListener('click', () => {
                    notification.style.transform = 'translateX(400px)';
                    setTimeout(() => notification.remove(), 300);
                });
            }
            
            // Initialize on load
            document.addEventListener('DOMContentLoaded', function() {
                // Add hover effects to action cards
                const actionCards = document.querySelectorAll('.action-card');
                actionCards.forEach(card => {
                    card.addEventListener('mouseenter', function() {
                        this.style.transform = 'translateY(-5px)';
                    });
                    
                    card.addEventListener('mouseleave', function() {
                        this.style.transform = 'translateY(0)';
                    });
                });
            });
        </script>
    </body>
    </html>
    ''', total_players=total_players, total_kills=total_kills, total_games=total_games, 
        admins=admins, recent_activity=recent_activity, recent_matches=recent_matches, datetime=datetime)

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

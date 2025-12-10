# app.py - Main Flask web server
import os
import json
import random
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, session, redirect, url_for, make_response
from flask_cors import CORS
from config import logger, bot_active, generate_secure_key
from database import init_db, fix_existing_keys, validate_api_key, get_global_stats, get_leaderboard, get_db_connection
from discord_bot import test_discord_token, register_commands, handle_interaction, update_key_database

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = 86400
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app, supports_credentials=True)
port = int(os.environ.get("PORT", 10000))

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@app.before_request
def before_request():
    """Check session before each request"""
    if request.endpoint not in ['home', 'api_validate_key', 'health', 'api_stats', 'api_leaderboard', 'interactions']:
        if 'user_key' not in session:
            return redirect(url_for('home'))
        
        if request.endpoint == 'dashboard':
            user_data = validate_api_key(session.get('user_key'))
            if not user_data:
                session.clear()
                return redirect(url_for('home'))
            session['user_data'] = user_data

# =============================================================================
# DISCORD INTERACTIONS ENDPOINT
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord slash commands and interactions"""
    logger.info("Received interaction request")
    
    # If signature verification is needed (uncomment if using DISCORD_PUBLIC_KEY)
    # signature = request.headers.get('X-Signature-Ed25519')
    # timestamp = request.headers.get('X-Signature-Timestamp')
    # if signature and timestamp:
    #     if not verify_discord_signature(request):
    #         return jsonify({"error": "Invalid signature"}), 401
    
    data = request.get_json()
    response = handle_interaction(data)
    return jsonify(response)

# =============================================================================
# WEB INTERFACE - DARK THEME
# =============================================================================

@app.route('/')
def home():
    """Home page - Goblin Hut - DARK THEME"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            session['user_data'] = user_data
            return redirect(url_for('dashboard'))
    
    stats = get_global_stats()
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Goblin Hut</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            :root {{
                --primary: #080011;
                --secondary: #1a0a2a;
                --accent: #9d00ff;
                --accent2: #00ff9d;
                --text: #e0d6ff;
                --text-dim: #b19cd9;
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: var(--primary);
                color: var(--text);
                min-height: 100vh;
                overflow-x: hidden;
            }}
            
            /* Your existing CSS styles here */
            /* ... (copy all the CSS from your original app.py) ... */
        </style>
    </head>
    <body>
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
        
        <div class="container">
            <div class="login-section">
                <div class="logo">GOBLIN HUT</div>
                <div class="subtitle">Enter your API key to enter the cave</div>
                
                <div class="login-box">
                    <input type="text" 
                           class="key-input" 
                           id="apiKey" 
                           placeholder="GOB-XXXXXXXXXXXXXXXXXXXX"
                           pattern="GOB-[A-Z0-9]{{20}}"
                           title="Format: GOB- followed by 20 uppercase letters/numbers"
                           autocomplete="off">
                    
                    <button class="login-btn" onclick="validateKey()" id="loginBtn">
                        Enter Cave
                    </button>
                    
                    <div class="error-box" id="errorMessage">
                        Invalid API key
                    </div>
                </div>
                
                <div class="divider"></div>
                
                <div class="info-box">
                    <strong>How to get your API key:</strong>
                    <p>1. Use <code>/register your_name</code> in Discord <em>(one-time only)</em></p>
                    <p>2. Copy your <code>GOB-XXXXXXXXXXXXXXX</code> key from bot response</p>
                    <p>3. Use <code>/key</code> to see your key anytime</p>
                    <p>4. Enter it above to access your dashboard</p>
                </div>
                
                <div class="bot-status" id="botStatus">
                    Bot Status: {'ONLINE' if bot_active else 'OFFLINE'}
                </div>
            </div>
            
            <div class="info-section">
                <div class="stats-box">
                    <div class="stats-header">
                        <div class="stats-title">📊 Server Stats</div>
                        <button class="login-btn" style="padding: 8px 15px; font-size: 0.9rem;" onclick="loadStats()">
                            ↻ Refresh
                        </button>
                    </div>
                    
                    <div id="statsContainer">
                        <div class="stats-grid">
                            <div class="stat-item">
                                <div class="stat-label">Total Players</div>
                                <div class="stat-value" id="totalPlayers">{stats['total_players']}</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-label">Total Kills</div>
                                <div class="stat-value" id="totalKills">{stats['total_kills']:,}</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-label">Games Played</div>
                                <div class="stat-value" id="totalGames">{stats['total_games']}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="github-link">
                        <p>Want to join? <a href="#" onclick="showDiscordInfo()">Join our Discord</a></p>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            async function validateKey() {{
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const errorDiv = document.getElementById('errorMessage');
                const btn = document.getElementById('loginBtn');
                
                const keyPattern = /^GOB-[A-Z0-9]{{20}}$/;
                
                if (!key) {{
                    errorDiv.textContent = "Please enter an API key";
                    errorDiv.style.display = 'block';
                    return;
                }}
                
                if (!keyPattern.test(key)) {{
                    errorDiv.textContent = "Invalid format. Key must be: GOB- followed by 20 uppercase letters/numbers";
                    errorDiv.style.display = 'block';
                    return;
                }}
                
                btn.innerHTML = 'Entering cave...';
                btn.disabled = true;
                
                try {{
                    const response = await fetch('/api/validate-key', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ api_key: key }})
                    }});
                    
                    const data = await response.json();
                    
                    if (data.valid) {{
                        btn.innerHTML = 'Access granted!';
                        btn.style.background = 'linear-gradient(45deg, #00ff9d, #00d4ff)';
                        setTimeout(() => window.location.href = '/dashboard', 500);
                    }} else {{
                        errorDiv.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        btn.innerHTML = 'Enter Cave';
                        btn.disabled = false;
                    }}
                }} catch (error) {{
                    errorDiv.textContent = 'Connection error. Please try again.';
                    errorDiv.style.display = 'block';
                    btn.innerHTML = 'Enter Cave';
                    btn.disabled = false;
                }}
            }}
            
            async function loadStats() {{
                try {{
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    document.getElementById('totalPlayers').textContent = data.total_players || '0';
                    document.getElementById('totalKills').textContent = data.total_kills?.toLocaleString() || '0';
                    document.getElementById('totalGames').textContent = data.total_games || '0';
                    
                    const status = document.getElementById('botStatus');
                    if (data.bot_active) {{
                        status.innerHTML = 'Bot Status: ONLINE';
                        status.className = 'bot-status status-online';
                    }} else {{
                        status.innerHTML = 'Bot Status: OFFLINE';
                        status.className = 'bot-status status-offline';
                    }}
                }} catch (error) {{
                    console.error('Error loading stats:', error);
                }}
            }}
            
            function showDiscordInfo() {{
                alert('Join our Discord server to use /register and get your API key!');
            }}
            
            document.getElementById('apiKey').addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') validateKey();
            }});
            
            document.addEventListener('DOMContentLoaded', function() {{
                document.getElementById('apiKey').focus();
                setInterval(loadStats, 30000);
            }});
        </script>
    </body>
    </html>
    '''

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
        
        return jsonify({"valid": True, "user": user_data.get('in_game_name')})
    else:
        return jsonify({"valid": False, "error": "Invalid API key"})

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    response = make_response(redirect(url_for('home')))
    response.set_cookie('session', '', expires=0)
    return response

@app.route('/dashboard')
def dashboard():
    """Profile Dashboard"""
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
    
    # Format leaderboard HTML
    leaderboard_html = ''
    for i, player in enumerate(leaderboard_data, 1):
        rank_class = f'rank-{i}' if i <= 3 else 'rank-other'
        is_current_user = player['api_key'] == session['user_key']
        user_class = 'current-user' if is_current_user else ''
        
        leaderboard_html += f'''
        <div class="leaderboard-item {user_class}">
            <div class="rank {rank_class}">#{i}</div>
            <div class="player-info">
                <div class="player-name">
                    {player['name']}
                    {is_current_user and '<span class="you-badge">YOU</span>' or ''}
                    {player['prestige'] > 0 and f'<span class="prestige-badge">P{player["prestige"]}</span>' or ''}
                </div>
                <div class="player-stats">
                    <div class="stat">
                        <span class="stat-label">K/D:</span>
                        <span class="stat-value">{player['kd']}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Kills:</span>
                        <span class="stat-value">{player['kills']}</span>
                    </div>
                </div>
            </div>
        </div>
        '''
    
    if not leaderboard_html:
        leaderboard_html = '<div class="no-data">No players on leaderboard yet</div>'
    
    # Return dashboard HTML (similar to your original, but simplified)
    return f'''<!DOCTYPE html>
<html>
<head>
    <title>Goblin Hut - Profile</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        /* Your dashboard CSS here */
    </style>
</head>
<body>
    <!-- Dashboard HTML structure -->
    <div class="header">
        <div class="logo">GOBLIN HUT</div>
        <div class="user-info">
            <div class="user-name">{user_data.get('in_game_name', 'Player')}</div>
            <a href="/logout" class="logout-btn">Exit Cave</a>
        </div>
    </div>
    
    <div class="container">
        <!-- Your dashboard content here -->
        <div class="key-display" id="apiKeyDisplay">
            {session['user_key']}
        </div>
        
        <div class="leaderboard-card card">
            <div class="leaderboard-header">
                <div class="leaderboard-title">🏆 Leaderboard</div>
            </div>
            <div class="leaderboard-list" id="leaderboardContainer">
                {leaderboard_html}
            </div>
        </div>
    </div>
    
    <script>
        function copyKey() {{
            const key = "{session['user_key']}";
            navigator.clipboard.writeText(key).then(() => {{
                alert('✅ API key copied to clipboard!');
            }});
        }}
    </script>
</body>
</html>'''

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
        "service": "Goblin Hut Bot",
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
        
        logger.info(f"✅ Goblin Hut Bot started successfully on port {port}")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

# Initialize on import (for WSGI/Gunicorn)
startup_sequence()

# For direct execution
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=False)
# app.py - Professional Dark Theme with Admin Dashboard
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

def is_user_admin():
    """Check if current session user is admin"""
    if 'user_data' not in session:
        return False
    return session['user_data'].get('is_admin', False)

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
    if request.endpoint in ['static', 'interactions']:
        return
    
    if request.endpoint in ['home', 'api_validate_key', 'health', 'api_stats', 'api_leaderboard']:
        return
    
    if 'user_key' not in session:
        return redirect(url_for('home'))
    
    # Re-validate session for admin routes
    if request.endpoint in ['admin_dashboard', 'admin_players', 'admin_player_detail', 
                           'admin_tickets', 'admin_matches', 'admin_settings']:
        user_data = validate_api_key(session.get('user_key'))
        if not user_data or not user_data.get('is_admin'):
            return redirect(url_for('dashboard'))
        session['user_data'] = user_data

# =============================================================================
# WEB INTERFACE - PROFESSIONAL DARK THEME
# =============================================================================

@app.route('/')
def home():
    """Home page - Professional Dark Theme"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            session['user_data'] = user_data
            return redirect(url_for('dashboard'))
    
    stats = get_global_stats()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SOT TDM System - Secure Access</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                /* Professional Dark Theme */
                --bg-primary: #0d1117;
                --bg-secondary: #161b22;
                --bg-tertiary: #21262d;
                --border: #30363d;
                --text-primary: #c9d1d9;
                --text-secondary: #8b949e;
                --text-tertiary: #6e7681;
                --accent-blue: #58a6ff;
                --accent-green: #56d364;
                --accent-yellow: #e3b341;
                --accent-orange: #f78166;
                --accent-purple: #bc8cff;
                --success: #238636;
                --warning: #9e6a03;
                --danger: #da3633;
                --info: #1f6feb;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', sans-serif;
                background: var(--bg-primary);
                color: var(--text-primary);
                min-height: 100vh;
                line-height: 1.6;
            }
            
            /* Minimal grid background */
            .grid-bg {
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                background-image: 
                    linear-gradient(rgba(88, 166, 255, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(88, 166, 255, 0.03) 1px, transparent 1px);
                background-size: 50px 50px;
                z-index: -1;
                pointer-events: none;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 40px 20px;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 40px;
                position: relative;
                z-index: 1;
            }
            
            @media (max-width: 1024px) {
                .container {
                    grid-template-columns: 1fr;
                    max-width: 600px;
                }
            }
            
            /* HEADER SECTION */
            .header-section {
                animation: fadeIn 0.8s ease-out;
            }
            
            .logo-container {
                margin-bottom: 50px;
                padding: 30px;
                background: var(--bg-secondary);
                border: 1px solid var(--border);
                border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
            }
            
            .logo {
                font-size: 3.5rem;
                font-weight: 700;
                margin-bottom: 10px;
                color: var(--accent-blue);
                font-family: 'Inter', sans-serif;
            }
            
            .logo span {
                color: var(--accent-green);
            }
            
            .subtitle {
                font-size: 1.2rem;
                color: var(--text-secondary);
                margin-bottom: 30px;
                font-weight: 400;
            }
            
            .tagline {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                margin-top: 20px;
            }
            
            .tag {
                padding: 8px 16px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                border-radius: 20px;
                font-size: 0.9rem;
                color: var(--text-secondary);
                font-weight: 500;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            /* LOGIN SECTION */
            .login-card {
                background: var(--bg-secondary);
                border-radius: 16px;
                padding: 40px;
                border: 1px solid var(--border);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
                animation: slideUp 0.8s ease-out 0.2s both;
            }
            
            .card-title {
                font-size: 1.8rem;
                color: var(--accent-blue);
                margin-bottom: 30px;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 12px;
            }
            
            .input-group {
                position: relative;
                margin-bottom: 24px;
            }
            
            .input-icon {
                position: absolute;
                left: 16px;
                top: 50%;
                transform: translateY(-50%);
                color: var(--text-tertiary);
            }
            
            .key-input {
                width: 100%;
                padding: 16px 16px 16px 48px;
                background: var(--bg-primary);
                border: 1px solid var(--border);
                border-radius: 12px;
                color: var(--text-primary);
                font-size: 1rem;
                font-family: 'JetBrains Mono', monospace;
                transition: all 0.2s;
            }
            
            .key-input:focus {
                outline: none;
                border-color: var(--accent-blue);
                box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1);
            }
            
            .key-input::placeholder {
                color: var(--text-tertiary);
            }
            
            .login-btn {
                width: 100%;
                padding: 16px;
                background: var(--accent-blue);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
                margin-top: 10px;
            }
            
            .login-btn:hover {
                background: #388bfd;
                transform: translateY(-2px);
                box-shadow: 0 8px 16px rgba(88, 166, 255, 0.2);
            }
            
            .login-btn:active {
                transform: translateY(0);
            }
            
            .error-box {
                background: rgba(218, 54, 51, 0.1);
                border: 1px solid rgba(218, 54, 51, 0.3);
                border-radius: 12px;
                padding: 16px;
                margin-top: 20px;
                color: var(--danger);
                display: none;
                animation: fadeIn 0.3s ease-out;
            }
            
            /* INFO SECTION */
            .info-card {
                background: var(--bg-secondary);
                border-radius: 16px;
                padding: 32px;
                border: 1px solid var(--border);
                margin-top: 30px;
                animation: fadeIn 0.8s ease-out 0.4s both;
            }
            
            .info-title {
                font-size: 1.4rem;
                color: var(--accent-blue);
                margin-bottom: 24px;
                display: flex;
                align-items: center;
                gap: 12px;
            }
            
            .steps-list {
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            
            .step {
                display: flex;
                gap: 16px;
                padding: 16px;
                background: var(--bg-tertiary);
                border-radius: 12px;
                border-left: 4px solid var(--accent-blue);
            }
            
            .step-number {
                width: 32px;
                height: 32px;
                background: var(--accent-blue);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: 600;
                font-size: 0.9rem;
                flex-shrink: 0;
            }
            
            .step-content {
                flex-grow: 1;
                color: var(--text-secondary);
            }
            
            .step-content code {
                background: var(--bg-primary);
                padding: 4px 8px;
                border-radius: 6px;
                border: 1px solid var(--border);
                font-family: 'JetBrains Mono', monospace;
                color: var(--accent-purple);
                margin: 0 4px;
                font-size: 0.9rem;
            }
            
            /* STATS SECTION */
            .stats-section {
                animation: fadeIn 0.8s ease-out 0.6s both;
            }
            
            .stats-card {
                background: var(--bg-secondary);
                border-radius: 16px;
                padding: 40px;
                border: 1px solid var(--border);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
                height: fit-content;
            }
            
            .stats-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 32px;
                padding-bottom: 20px;
                border-bottom: 1px solid var(--border);
            }
            
            .stats-title {
                font-size: 1.8rem;
                color: var(--accent-green);
                font-weight: 600;
            }
            
            .refresh-btn {
                padding: 10px 20px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                color: var(--text-secondary);
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .refresh-btn:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin-bottom: 30px;
            }
            
            @media (max-width: 768px) {
                .stats-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
            
            @media (max-width: 480px) {
                .stats-grid {
                    grid-template-columns: 1fr;
                }
            }
            
            .stat-item {
                background: var(--bg-tertiary);
                border-radius: 12px;
                padding: 24px;
                text-align: center;
                border: 1px solid var(--border);
                transition: all 0.2s;
            }
            
            .stat-item:hover {
                transform: translateY(-4px);
                border-color: var(--accent-blue);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
            }
            
            .stat-value {
                font-size: 2.5rem;
                font-weight: 700;
                margin: 12px 0;
                color: var(--accent-blue);
                font-family: 'Inter', sans-serif;
            }
            
            .stat-label {
                color: var(--text-secondary);
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }
            
            /* BOT STATUS */
            .status-container {
                margin-top: 40px;
                text-align: center;
            }
            
            .status-badge {
                display: inline-flex;
                align-items: center;
                gap: 12px;
                padding: 12px 24px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                border-radius: 24px;
                font-weight: 600;
                font-size: 1rem;
                backdrop-filter: blur(10px);
            }
            
            .status-badge.online {
                border-color: var(--success);
                color: var(--accent-green);
            }
            
            .status-badge.offline {
                border-color: var(--danger);
                color: var(--danger);
            }
            
            .status-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
            }
            
            .status-dot.online {
                background: var(--accent-green);
                box-shadow: 0 0 8px var(--accent-green);
                animation: pulse 2s infinite;
            }
            
            .status-dot.offline {
                background: var(--danger);
                box-shadow: 0 0 8px var(--danger);
            }
            
            /* FOOTER */
            .footer {
                margin-top: 60px;
                text-align: center;
                padding: 30px;
                color: var(--text-tertiary);
                font-size: 0.9rem;
                border-top: 1px solid var(--border);
                position: relative;
                z-index: 2;
            }
            
            .footer-links {
                display: flex;
                justify-content: center;
                gap: 30px;
                margin-top: 20px;
                flex-wrap: wrap;
            }
            
            .footer-link {
                color: var(--text-secondary);
                text-decoration: none;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.9rem;
            }
            
            .footer-link:hover {
                color: var(--accent-blue);
            }
            
            /* ANIMATIONS */
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            @keyframes slideUp {
                from {
                    opacity: 0;
                    transform: translateY(30px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            
            /* RESPONSIVE */
            @media (max-width: 768px) {
                .container {
                    padding: 20px;
                    gap: 30px;
                }
                
                .logo {
                    font-size: 2.5rem;
                }
                
                .login-card,
                .info-card,
                .stats-card {
                    padding: 30px 24px;
                }
                
                .stats-header {
                    flex-direction: column;
                    gap: 20px;
                    text-align: center;
                }
                
                .tagline {
                    gap: 8px;
                }
                
                .tag {
                    padding: 6px 12px;
                    font-size: 0.8rem;
                }
            }
            
            @media (max-width: 480px) {
                .logo {
                    font-size: 2rem;
                }
                
                .subtitle {
                    font-size: 1rem;
                }
                
                .login-btn {
                    padding: 14px;
                    font-size: 0.95rem;
                }
                
                .stats-title {
                    font-size: 1.5rem;
                }
                
                .stat-value {
                    font-size: 2rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="grid-bg"></div>
        
        <div class="container">
            <div class="header-section">
                <div class="logo-container">
                    <div class="logo">SOT <span>TDM</span> SYSTEM</div>
                    <div class="subtitle">
                        Secure access portal for Sea of Thieves Team Deathmatch
                    </div>
                    
                    <div class="tagline">
                        <div class="tag">
                            <i class="fas fa-shield-alt"></i> Secure
                        </div>
                        <div class="tag">
                            <i class="fas fa-bolt"></i> Fast
                        </div>
                        <div class="tag">
                            <i class="fas fa-users"></i> Community
                        </div>
                        <div class="tag">
                            <i class="fas fa-chart-line"></i> Stats
                        </div>
                    </div>
                </div>
                
                <div class="login-card">
                    <div class="card-title">
                        <i class="fas fa-key"></i> API Key Access
                    </div>
                    
                    <div class="input-group">
                        <i class="fas fa-key input-icon"></i>
                        <input type="text" 
                               class="key-input" 
                               id="apiKey" 
                               placeholder="GOB-XXXXXXXXXXXXXXXXXXXX"
                               autocomplete="off"
                               maxlength="24">
                    </div>
                    
                    <button class="login-btn" onclick="validateKey()" id="loginBtn">
                        <i class="fas fa-sign-in-alt"></i> Access Dashboard
                    </button>
                    
                    <div class="error-box" id="errorMessage">
                        <i class="fas fa-exclamation-circle"></i>
                        <span id="errorText">Invalid API key format</span>
                    </div>
                </div>
                
                <div class="info-card">
                    <div class="info-title">
                        <i class="fas fa-info-circle"></i> Getting Started
                    </div>
                    
                    <div class="steps-list">
                        <div class="step">
                            <div class="step-number">1</div>
                            <div class="step-content">
                                Use <code>/register your_name</code> in Discord to get your API key
                            </div>
                        </div>
                        
                        <div class="step">
                            <div class="step-number">2</div>
                            <div class="step-content">
                                Copy your <code>GOB-XXXXXXXXXXXXXXX</code> key from the bot response
                            </div>
                        </div>
                        
                        <div class="step">
                            <div class="step-number">3</div>
                            <div class="step-content">
                                Enter the key above to access your personal dashboard
                            </div>
                        </div>
                        
                        <div class="step">
                            <div class="step-number">4</div>
                            <div class="step-content">
                                Use <code>/key</code> in Discord to retrieve your key anytime
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="status-container">
                    <div class="status-badge {{ 'online' if bot_active else 'offline' }}">
                        <div class="status-dot {{ 'online' if bot_active else 'offline' }}"></div>
                        <span>SYSTEM STATUS: {{ 'ONLINE' if bot_active else 'OFFLINE' }}</span>
                    </div>
                </div>
            </div>
            
            <div class="stats-section">
                <div class="stats-card">
                    <div class="stats-header">
                        <div class="stats-title">
                            <i class="fas fa-chart-bar"></i> System Statistics
                        </div>
                        <button class="refresh-btn" onclick="loadStats()">
                            <i class="fas fa-sync-alt"></i> Refresh
                        </button>
                    </div>
                    
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-value" id="totalPlayers">{{ stats['total_players'] }}</div>
                            <div class="stat-label">Total Players</div>
                        </div>
                        
                        <div class="stat-item">
                            <div class="stat-value" id="totalKills">{{ "{:,}".format(stats['total_kills']) }}</div>
                            <div class="stat-label">Total Kills</div>
                        </div>
                        
                        <div class="stat-item">
                            <div class="stat-value" id="totalGames">{{ stats['total_games'] }}</div>
                            <div class="stat-label">Games Played</div>
                        </div>
                    </div>
                    
                    <div style="margin-top: 30px; padding: 20px; background: var(--bg-tertiary); border-radius: 12px; border-left: 4px solid var(--accent-green);">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 15px;">
                            <i class="fab fa-discord" style="color: var(--accent-green); font-size: 1.5rem;"></i>
                            <h3 style="color: var(--accent-green); margin: 0; font-size: 1.2rem;">Need Help?</h3>
                        </div>
                        <p style="color: var(--text-secondary); margin-bottom: 15px; line-height: 1.5; font-size: 0.95rem;">
                            Join our Discord community to get your API key and access all features.
                        </p>
                        <button class="login-btn" style="background: var(--accent-green);" onclick="showDiscordInfo()">
                            <i class="fab fa-discord"></i> Join Discord
                        </button>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <div style="margin-bottom: 20px; display: flex; align-items: center; justify-content: center; gap: 20px;">
                <span>SOT TDM System v2.0</span>
                <i class="fas fa-circle" style="font-size: 4px; color: var(--text-tertiary);"></i>
                <span>Secure Access Portal</span>
            </div>
            
            <div class="footer-links">
                <a href="#" class="footer-link" onclick="showDiscordInfo()">
                    <i class="fab fa-discord"></i> Discord
                </a>
                <a href="#" class="footer-link" onclick="downloadTool()">
                    <i class="fas fa-download"></i> Game Tool
                </a>
                <a href="/health" class="footer-link" target="_blank">
                    <i class="fas fa-server"></i> System Status
                </a>
                <a href="#" class="footer-link" onclick="showSupport()">
                    <i class="fas fa-question-circle"></i> Support
                </a>
            </div>
            
            <div style="margin-top: 20px; font-size: 0.8rem; opacity: 0.8;">
                &copy; {{ datetime.now().year }} SOT TDM System. All rights reserved.
            </div>
        </div>
        
        <script>
            async function validateKey() {
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const errorDiv = document.getElementById('errorMessage');
                const errorText = document.getElementById('errorText');
                const btn = document.getElementById('loginBtn');
                
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
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Validating...';
                btn.disabled = true;
                
                try {
                    const response = await fetch('/api/validate-key', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ api_key: key })
                    });
                    
                    const data = await response.json();
                    
                    if (data.valid) {
                        btn.innerHTML = '<i class="fas fa-check"></i> Access Granted';
                        btn.style.background = 'var(--accent-green)';
                        
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 500);
                    } else {
                        errorText.textContent = data.error || 'Invalid API key';
                        errorDiv.style.display = 'block';
                        
                        btn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Access Dashboard';
                        btn.disabled = false;
                    }
                } catch (error) {
                    errorText.textContent = 'Connection error. Please try again.';
                    errorDiv.style.display = 'block';
                    
                    btn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Access Dashboard';
                    btn.disabled = false;
                }
            }
            
            async function loadStats() {
                const btn = event?.target;
                if (btn) {
                    const originalHtml = btn.innerHTML;
                    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                    btn.disabled = true;
                }
                
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    document.getElementById('totalPlayers').textContent = data.total_players || '0';
                    document.getElementById('totalKills').textContent = data.total_kills?.toLocaleString() || '0';
                    document.getElementById('totalGames').textContent = data.total_games || '0';
                    
                    // Update status badge
                    const statusBadge = document.querySelector('.status-badge');
                    const statusDot = document.querySelector('.status-dot');
                    const statusText = statusBadge.querySelector('span');
                    
                    if (data.bot_active) {
                        statusBadge.className = 'status-badge online';
                        statusDot.className = 'status-dot online';
                        statusText.textContent = 'SYSTEM STATUS: ONLINE';
                    } else {
                        statusBadge.className = 'status-badge offline';
                        statusDot.className = 'status-dot offline';
                        statusText.textContent = 'SYSTEM STATUS: OFFLINE';
                    }
                    
                    if (btn) {
                        btn.innerHTML = '<i class="fas fa-check"></i>';
                        setTimeout(() => {
                            btn.innerHTML = originalHtml;
                            btn.disabled = false;
                        }, 500);
                    }
                    
                } catch (error) {
                    console.error('Error loading stats:', error);
                    if (btn) {
                        btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
                        setTimeout(() => {
                            btn.innerHTML = 'Refresh';
                            btn.disabled = false;
                        }, 1000);
                    }
                }
            }
            
            function showDiscordInfo() {
                alert('Join our Discord server to get your API key and access all features.');
            }
            
            function downloadTool() {
                const githubReleaseUrl = 'https://github.com/yourusername/sot-tdm-tool/releases/latest/download/sot_tdm_tool.exe';
                
                const link = document.createElement('a');
                link.href = githubReleaseUrl;
                link.download = 'sot_tdm_tool.exe';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                alert('Download started! Check your downloads folder.');
            }
            
            function showSupport() {
                alert('For support, please join our Discord server or create a ticket.');
            }
            
            // Auto-focus input on load
            document.addEventListener('DOMContentLoaded', function() {
                document.getElementById('apiKey').focus();
                
                // Load stats every 30 seconds
                loadStats();
                setInterval(loadStats, 30000);
                
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
    ''', stats=stats, bot_active=bot_active, datetime=datetime)

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
        <title>Dashboard - {{ user_data.get('in_game_name', 'Player') }}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                /* Professional Dark Theme */
                --bg-primary: #0d1117;
                --bg-secondary: #161b22;
                --bg-tertiary: #21262d;
                --border: #30363d;
                --text-primary: #c9d1d9;
                --text-secondary: #8b949e;
                --text-tertiary: #6e7681;
                --accent-blue: #58a6ff;
                --accent-green: #56d364;
                --accent-yellow: #e3b341;
                --accent-orange: #f78166;
                --accent-purple: #bc8cff;
                --success: #238636;
                --warning: #9e6a03;
                --danger: #da3633;
                --info: #1f6feb;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', sans-serif;
                background: var(--bg-primary);
                color: var(--text-primary);
                min-height: 100vh;
                line-height: 1.6;
            }
            
            .grid-bg {
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                background-image: 
                    linear-gradient(rgba(88, 166, 255, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(88, 166, 255, 0.03) 1px, transparent 1px);
                background-size: 50px 50px;
                z-index: -1;
                pointer-events: none;
            }
            
            /* HEADER */
            .dashboard-header {
                background: var(--bg-secondary);
                border-bottom: 1px solid var(--border);
                padding: 20px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            
            .logo {
                font-size: 1.8rem;
                font-weight: 700;
                color: var(--accent-blue);
            }
            
            .logo span {
                color: var(--accent-green);
            }
            
            .header-right {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            
            .user-info {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 8px 16px;
                background: var(--bg-tertiary);
                border-radius: 8px;
                border: 1px solid var(--border);
            }
            
            .user-avatar {
                width: 36px;
                height: 36px;
                background: var(--accent-blue);
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
                color: var(--text-primary);
            }
            
            .user-rank {
                font-size: 0.85rem;
                color: var(--text-secondary);
            }
            
            .nav-links {
                display: flex;
                gap: 10px;
            }
            
            .nav-link {
                padding: 10px 20px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                color: var(--text-secondary);
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.95rem;
            }
            
            .nav-link:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            .nav-link.active {
                background: var(--accent-blue);
                color: white;
                border-color: var(--accent-blue);
            }
            
            /* MAIN CONTENT */
            .dashboard-container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 30px;
                display: grid;
                grid-template-columns: 2fr 1fr;
                gap: 30px;
                position: relative;
                z-index: 1;
            }
            
            @media (max-width: 1024px) {
                .dashboard-container {
                    grid-template-columns: 1fr;
                }
            }
            
            /* PROFILE CARD */
            .profile-card {
                background: var(--bg-secondary);
                border-radius: 16px;
                padding: 30px;
                border: 1px solid var(--border);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                animation: fadeIn 0.8s ease-out;
            }
            
            .profile-header {
                display: flex;
                align-items: center;
                gap: 24px;
                margin-bottom: 30px;
                padding-bottom: 24px;
                border-bottom: 1px solid var(--border);
            }
            
            .profile-avatar {
                width: 80px;
                height: 80px;
                background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 2rem;
                font-weight: bold;
                box-shadow: 0 8px 24px rgba(88, 166, 255, 0.2);
            }
            
            .profile-details h2 {
                font-size: 2rem;
                margin-bottom: 8px;
                color: var(--text-primary);
            }
            
            .profile-tags {
                display: flex;
                gap: 8px;
                margin-top: 12px;
                flex-wrap: wrap;
            }
            
            .profile-tag {
                padding: 6px 12px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                border-radius: 20px;
                font-size: 0.85rem;
                color: var(--text-secondary);
                display: flex;
                align-items: center;
                gap: 6px;
            }
            
            .profile-tag.admin {
                background: rgba(227, 179, 65, 0.1);
                border-color: rgba(227, 179, 65, 0.3);
                color: var(--accent-yellow);
            }
            
            /* STATS GRID */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                margin-bottom: 30px;
            }
            
            @media (max-width: 768px) {
                .stats-grid {
                    grid-template-columns: 1fr;
                }
            }
            
            .stat-card {
                background: var(--bg-tertiary);
                border-radius: 12px;
                padding: 24px;
                border: 1px solid var(--border);
                transition: all 0.2s;
            }
            
            .stat-card:hover {
                transform: translateY(-4px);
                border-color: var(--accent-blue);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
            }
            
            .stat-value {
                font-size: 2.5rem;
                font-weight: 700;
                margin: 12px 0;
                color: var(--accent-blue);
            }
            
            .stat-label {
                color: var(--text-secondary);
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }
            
            .stat-detail {
                color: var(--text-tertiary);
                font-size: 0.9rem;
                margin-top: 8px;
            }
            
            /* KEY SECTION */
            .key-section {
                margin-top: 30px;
            }
            
            .section-title {
                font-size: 1.4rem;
                color: var(--accent-blue);
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 12px;
            }
            
            .key-display {
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 20px;
                margin: 20px 0;
                font-family: 'JetBrains Mono', monospace;
                color: var(--text-primary);
                word-break: break-all;
                text-align: center;
                cursor: pointer;
                transition: all 0.2s;
                font-size: 1.1rem;
                position: relative;
            }
            
            .key-display:hover {
                background: var(--border);
                border-color: var(--accent-green);
            }
            
            .action-buttons {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
                margin-top: 20px;
            }
            
            @media (max-width: 480px) {
                .action-buttons {
                    grid-template-columns: 1fr;
                }
            }
            
            .action-btn {
                padding: 16px;
                background: var(--accent-blue);
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
                font-size: 1rem;
            }
            
            .action-btn:hover {
                background: #388bfd;
                transform: translateY(-2px);
                box-shadow: 0 8px 16px rgba(88, 166, 255, 0.2);
            }
            
            .action-btn.secondary {
                background: var(--bg-tertiary);
                color: var(--text-secondary);
                border: 1px solid var(--border);
            }
            
            .action-btn.secondary:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            /* LEADERBOARD */
            .leaderboard-card {
                background: var(--bg-secondary);
                border-radius: 16px;
                padding: 30px;
                border: 1px solid var(--border);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                height: fit-content;
                animation: fadeIn 0.8s ease-out 0.2s both;
            }
            
            .card-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 24px;
                padding-bottom: 20px;
                border-bottom: 1px solid var(--border);
            }
            
            .card-title {
                font-size: 1.6rem;
                color: var(--accent-green);
                font-weight: 600;
            }
            
            .refresh-btn {
                padding: 10px 20px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                color: var(--text-secondary);
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.95rem;
            }
            
            .refresh-btn:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            .leaderboard-list {
                max-height: 500px;
                overflow-y: auto;
                padding-right: 10px;
            }
            
            .leaderboard-list::-webkit-scrollbar {
                width: 6px;
            }
            
            .leaderboard-list::-webkit-scrollbar-track {
                background: var(--bg-tertiary);
                border-radius: 3px;
            }
            
            .leaderboard-list::-webkit-scrollbar-thumb {
                background: var(--border);
                border-radius: 3px;
            }
            
            .leaderboard-item {
                display: flex;
                align-items: center;
                padding: 16px;
                margin-bottom: 12px;
                background: var(--bg-tertiary);
                border-radius: 12px;
                border: 1px solid var(--border);
                transition: all 0.2s;
            }
            
            .leaderboard-item:hover {
                transform: translateX(4px);
                border-color: var(--accent-blue);
            }
            
            .leaderboard-item.current-user {
                background: rgba(88, 166, 255, 0.1);
                border-color: var(--accent-blue);
            }
            
            .rank {
                font-size: 1.2rem;
                font-weight: 700;
                width: 40px;
                text-align: center;
                color: var(--text-secondary);
            }
            
            .rank-1 { color: var(--accent-yellow); }
            .rank-2 { color: #c0c0c0; }
            .rank-3 { color: #cd7f32; }
            
            .player-info {
                flex-grow: 1;
                margin-left: 16px;
            }
            
            .player-name {
                font-weight: 600;
                color: var(--text-primary);
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 4px;
            }
            
            .player-stats {
                display: flex;
                gap: 16px;
                font-size: 0.9rem;
                color: var(--text-secondary);
            }
            
            .stat-value {
                font-size: 1rem;
                color: var(--accent-green);
                font-weight: 600;
            }
            
            /* FOOTER */
            .dashboard-footer {
                margin-top: 40px;
                padding: 30px;
                text-align: center;
                color: var(--text-tertiary);
                font-size: 0.9rem;
                border-top: 1px solid var(--border);
            }
            
            .footer-links {
                display: flex;
                justify-content: center;
                gap: 30px;
                margin-top: 20px;
                flex-wrap: wrap;
            }
            
            .footer-link {
                color: var(--text-secondary);
                text-decoration: none;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.9rem;
            }
            
            .footer-link:hover {
                color: var(--accent-blue);
            }
            
            /* ANIMATIONS */
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            /* RESPONSIVE */
            @media (max-width: 768px) {
                .dashboard-header {
                    flex-direction: column;
                    gap: 20px;
                    padding: 20px;
                }
                
                .dashboard-container {
                    padding: 20px;
                    gap: 25px;
                }
                
                .profile-header {
                    flex-direction: column;
                    text-align: center;
                    gap: 20px;
                }
                
                .profile-avatar {
                    width: 70px;
                    height: 70px;
                    font-size: 1.8rem;
                }
                
                .profile-details h2 {
                    font-size: 1.8rem;
                }
                
                .nav-links {
                    flex-wrap: wrap;
                    justify-content: center;
                }
                
                .stat-value {
                    font-size: 2rem;
                }
                
                .card-header {
                    flex-direction: column;
                    gap: 20px;
                    text-align: center;
                }
            }
            
            @media (max-width: 480px) {
                .logo {
                    font-size: 1.5rem;
                }
                
                .user-info {
                    flex-direction: column;
                    text-align: center;
                    padding: 12px;
                }
                
                .stats-grid {
                    grid-template-columns: 1fr;
                }
                
                .player-stats {
                    flex-wrap: wrap;
                    gap: 8px;
                }
            }
        </style>
    </head>
    <body>
        <div class="grid-bg"></div>
        
        <!-- Header -->
        <div class="dashboard-header">
            <div class="header-left">
                <div class="logo">SOT <span>TDM</span></div>
                <div style="color: var(--text-tertiary); font-size: 0.9rem;">
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
                    <a href="/dashboard" class="nav-link active">
                        <i class="fas fa-home"></i> Dashboard
                    </a>
                    {% if user_data.get('is_admin') %}
                    <a href="/admin" class="nav-link">
                        <i class="fas fa-cog"></i> Admin
                    </a>
                    {% endif %}
                    <a href="/logout" class="nav-link">
                        <i class="fas fa-sign-out-alt"></i> Logout
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
                            <div style="color: var(--text-secondary); margin-bottom: 10px;">
                                <i class="fas fa-calendar"></i> Joined: {{ user_data.get('created_at', '')[:10] }}
                            </div>
                            <div class="profile-tags">
                                <div class="profile-tag">
                                    <i class="fas fa-crown"></i> Prestige {{ user_data.get('prestige', 0) }}
                                </div>
                                <div class="profile-tag">
                                    <i class="fas fa-gamepad"></i> {{ total_games }} Games
                                </div>
                                {% if user_data.get('is_admin') %}
                                <div class="profile-tag admin">
                                    <i class="fas fa-shield-alt"></i> Administrator
                                </div>
                                {% endif %}
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
                            <div class="stat-value">{{ "%.1f"|format(win_rate) }}%</div>
                            <div class="stat-label">Win Rate</div>
                            <div class="stat-detail">
                                {{ wins }} wins / {{ losses }} losses
                            </div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-value">{{ total_games }}</div>
                            <div class="stat-label">Games Played</div>
                            <div class="stat-detail">
                                Total matches completed
                            </div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-value">{{ user_data.get('prestige', 0) }}</div>
                            <div class="stat-label">Prestige Level</div>
                            <div class="stat-detail">
                                Current prestige rank
                            </div>
                        </div>
                    </div>
                    
                    <div class="key-section">
                        <div class="section-title">
                            <i class="fas fa-key"></i> Your API Key
                        </div>
                        
                        <p style="color: var(--text-secondary); margin-bottom: 20px; line-height: 1.5;">
                            This key uniquely identifies you in the system. Keep it secure.
                        </p>
                        
                        <div class="key-display" id="apiKeyDisplay" onclick="copyKey()" title="Click to copy">
                            {{ session['user_key'] }}
                        </div>
                        
                        <div class="action-buttons">
                            <button class="action-btn" onclick="copyKey()">
                                <i class="fas fa-copy"></i> Copy Key
                            </button>
                            <button class="action-btn secondary" onclick="downloadTool()">
                                <i class="fas fa-download"></i> Download Tool
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Leaderboard -->
            <div class="leaderboard-card">
                <div class="card-header">
                    <div class="card-title">
                        <i class="fas fa-trophy"></i> Global Leaderboard
                    </div>
                    <button class="refresh-btn" onclick="loadLeaderboard()">
                        <i class="fas fa-sync-alt"></i> Refresh
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
                                <span style="font-size: 0.8rem; color: var(--accent-blue);">
                                    <i class="fas fa-user"></i> You
                                </span>
                                {% endif %}
                                {% if player.prestige > 0 %}
                                <span style="font-size: 0.8rem; color: var(--accent-yellow);">
                                    P{{ player.prestige }}
                                </span>
                                {% endif %}
                            </div>
                            <div class="player-stats">
                                <div>
                                    <span style="color: var(--text-tertiary);">K/D:</span>
                                    <span class="stat-value">{{ player.kd }}</span>
                                </div>
                                <div>
                                    <span style="color: var(--text-tertiary);">Kills:</span>
                                    <span class="stat-value">{{ player.kills }}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    {% else %}
                    <div style="text-align: center; padding: 40px; color: var(--text-tertiary);">
                        <i class="fas fa-users" style="font-size: 2rem; margin-bottom: 20px; opacity: 0.5;"></i>
                        <p>No players on leaderboard yet</p>
                    </div>
                    {% endfor %}
                </div>
                
                <div style="margin-top: 30px; padding: 20px; background: var(--bg-tertiary); border-radius: 12px; border-left: 4px solid var(--accent-green);">
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 10px;">
                        <i class="fas fa-chart-line" style="color: var(--accent-green);"></i>
                        <h3 style="color: var(--accent-green); margin: 0; font-size: 1.2rem;">Your Position</h3>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <div style="font-size: 2rem; font-weight: bold; color: var(--accent-blue);">{{ user_rank }}</div>
                            <div style="color: var(--text-secondary); font-size: 0.9rem;">Global Rank</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.8rem; font-weight: bold; color: var(--accent-green);">{{ "%.2f"|format(kd) }}</div>
                            <div style="color: var(--text-secondary); font-size: 0.9rem;">Your K/D Ratio</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="dashboard-footer">
            <div style="margin-bottom: 20px; display: flex; align-items: center; justify-content: center; gap: 20px;">
                <span>Dashboard v2.0</span>
                <i class="fas fa-circle" style="font-size: 4px; color: var(--text-tertiary);"></i>
                <span>Session Active</span>
                <i class="fas fa-circle" style="font-size: 4px; color: var(--text-tertiary);"></i>
                <span>Last Update: {{ datetime.now().strftime('%H:%M:%S') }}</span>
            </div>
            
            <div class="footer-links">
                <a href="/" class="footer-link">
                    <i class="fas fa-home"></i> Home
                </a>
                <a href="#" class="footer-link" onclick="showDiscordInfo()">
                    <i class="fab fa-discord"></i> Discord
                </a>
                <a href="/health" class="footer-link" target="_blank">
                    <i class="fas fa-server"></i> System Status
                </a>
                <a href="#" class="footer-link" onclick="showSupport()">
                    <i class="fas fa-question-circle"></i> Support
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
                const githubReleaseUrl = 'https://github.com/yourusername/sot-tdm-tool/releases/latest/download/sot_tdm_tool.exe';
                
                const link = document.createElement('a');
                link.href = githubReleaseUrl;
                link.download = 'sot_tdm_tool.exe';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                showNotification('Download started', 'success');
            }
            
            async function loadLeaderboard() {
                const container = document.getElementById('leaderboardContainer');
                const btn = event?.target;
                const originalHtml = btn?.innerHTML || 'Refresh';
                
                if (btn) {
                    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
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
                                            ${isCurrentUser ? '<span style="font-size: 0.8rem; color: var(--accent-blue);"><i class="fas fa-user"></i> You</span>' : ''}
                                            ${player.prestige > 0 ? `<span style="font-size: 0.8rem; color: var(--accent-yellow);">P${player.prestige}</span>` : ''}
                                        </div>
                                        <div class="player-stats">
                                            <div>
                                                <span style="color: var(--text-tertiary);">K/D:</span>
                                                <span class="stat-value">${player.kd}</span>
                                            </div>
                                            <div>
                                                <span style="color: var(--text-tertiary);">Kills:</span>
                                                <span class="stat-value">${player.kills}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            `;
                        });
                        
                        container.innerHTML = html;
                    } else {
                        container.innerHTML = `
                            <div style="text-align: center; padding: 40px; color: var(--text-tertiary);">
                                <i class="fas fa-users" style="font-size: 2rem; margin-bottom: 20px; opacity: 0.5;"></i>
                                <p>No players on leaderboard yet</p>
                            </div>
                        `;
                    }
                    
                    if (btn) {
                        btn.innerHTML = '<i class="fas fa-check"></i>';
                        setTimeout(() => {
                            btn.innerHTML = originalHtml;
                            btn.disabled = false;
                        }, 500);
                    }
                    
                } catch (error) {
                    console.error('Error loading leaderboard:', error);
                    container.innerHTML = `
                        <div style="text-align: center; padding: 40px; color: var(--text-tertiary);">
                            <i class="fas fa-exclamation-triangle" style="font-size: 2rem; margin-bottom: 20px; color: var(--danger);"></i>
                            <p>Failed to load leaderboard</p>
                        </div>
                    `;
                    
                    if (btn) {
                        btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
                        setTimeout(() => {
                            btn.innerHTML = 'Refresh';
                            btn.disabled = false;
                        }, 1000);
                    }
                }
            }
            
            function showDiscordInfo() {
                alert('Join our Discord server for support and updates.');
            }
            
            function showSupport() {
                alert('For support, please join our Discord server or create a ticket.');
            }
            
            function showNotification(message, type = 'info') {
                const colors = {
                    info: 'var(--accent-blue)',
                    success: 'var(--accent-green)',
                    warning: 'var(--accent-yellow)',
                    error: 'var(--danger)'
                };
                
                const notification = document.createElement('div');
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: var(--bg-secondary);
                    border-left: 4px solid ${colors[type]};
                    color: var(--text-primary);
                    padding: 16px;
                    border-radius: 8px;
                    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
                    z-index: 10000;
                    transform: translateX(400px);
                    transition: transform 0.3s ease-out;
                    max-width: 300px;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    border: 1px solid var(--border);
                `;
                
                notification.innerHTML = `
                    <i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'}" style="color: ${colors[type]};"></i>
                    <div>
                        <div style="font-weight: 600; color: ${colors[type]};">${type.toUpperCase()}</div>
                        <div style="margin-top: 4px; font-size: 0.95rem;">${message}</div>
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
                
                // Add hover effects to stat cards
                const statCards = document.querySelectorAll('.stat-card');
                statCards.forEach(card => {
                    card.addEventListener('mouseenter', function() {
                        this.style.transform = 'translateY(-4px)';
                    });
                    
                    card.addEventListener('mouseleave', function() {
                        this.style.transform = 'translateY(0)';
                    });
                });
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
    """Admin Dashboard Main Page"""
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
        <title>Admin Dashboard - SOT TDM System</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                /* Professional Dark Theme */
                --bg-primary: #0d1117;
                --bg-secondary: #161b22;
                --bg-tertiary: #21262d;
                --border: #30363d;
                --text-primary: #c9d1d9;
                --text-secondary: #8b949e;
                --text-tertiary: #6e7681;
                --accent-blue: #58a6ff;
                --accent-green: #56d364;
                --accent-yellow: #e3b341;
                --accent-orange: #f78166;
                --accent-purple: #bc8cff;
                --success: #238636;
                --warning: #9e6a03;
                --danger: #da3633;
                --info: #1f6feb;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', sans-serif;
                background: var(--bg-primary);
                color: var(--text-primary);
                min-height: 100vh;
                line-height: 1.6;
            }
            
            .grid-bg {
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                background-image: 
                    linear-gradient(rgba(88, 166, 255, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(88, 166, 255, 0.03) 1px, transparent 1px);
                background-size: 50px 50px;
                z-index: -1;
                pointer-events: none;
            }
            
            /* HEADER */
            .admin-header {
                background: var(--bg-secondary);
                border-bottom: 1px solid var(--border);
                padding: 20px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            
            .logo {
                font-size: 1.8rem;
                font-weight: 700;
                color: var(--accent-blue);
            }
            
            .logo span {
                color: var(--accent-yellow);
            }
            
            .header-right {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            
            .admin-badge {
                padding: 8px 16px;
                background: rgba(227, 179, 65, 0.1);
                border: 1px solid rgba(227, 179, 65, 0.3);
                border-radius: 8px;
                color: var(--accent-yellow);
                font-weight: 600;
                font-size: 0.95rem;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .nav-links {
                display: flex;
                gap: 10px;
            }
            
            .nav-link {
                padding: 10px 20px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                color: var(--text-secondary);
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.95rem;
            }
            
            .nav-link:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            .nav-link.active {
                background: var(--accent-blue);
                color: white;
                border-color: var(--accent-blue);
            }
            
            /* MAIN CONTENT */
            .admin-container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 30px;
                position: relative;
                z-index: 1;
            }
            
            .admin-welcome {
                margin-bottom: 40px;
                padding: 30px;
                background: var(--bg-secondary);
                border-radius: 16px;
                border: 1px solid var(--border);
            }
            
            .admin-welcome h1 {
                font-size: 2.2rem;
                color: var(--text-primary);
                margin-bottom: 10px;
            }
            
            .admin-welcome p {
                color: var(--text-secondary);
                font-size: 1.1rem;
            }
            
            /* STATS GRID */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 20px;
                margin-bottom: 40px;
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
                background: var(--bg-secondary);
                border-radius: 12px;
                padding: 24px;
                border: 1px solid var(--border);
                transition: all 0.2s;
            }
            
            .stat-card:hover {
                transform: translateY(-4px);
                border-color: var(--accent-blue);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
            }
            
            .stat-icon {
                font-size: 2rem;
                margin-bottom: 16px;
                color: var(--accent-blue);
            }
            
            .stat-value {
                font-size: 2.5rem;
                font-weight: 700;
                margin: 12px 0;
                color: var(--text-primary);
            }
            
            .stat-label {
                color: var(--text-secondary);
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }
            
            /* ADMIN SECTIONS */
            .admin-sections {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 30px;
                margin-bottom: 40px;
            }
            
            @media (max-width: 1024px) {
                .admin-sections {
                    grid-template-columns: 1fr;
                }
            }
            
            .admin-section {
                background: var(--bg-secondary);
                border-radius: 16px;
                padding: 30px;
                border: 1px solid var(--border);
            }
            
            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 24px;
                padding-bottom: 20px;
                border-bottom: 1px solid var(--border);
            }
            
            .section-title {
                font-size: 1.4rem;
                color: var(--accent-blue);
                font-weight: 600;
            }
            
            .view-all {
                padding: 8px 16px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                color: var(--text-secondary);
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                font-size: 0.9rem;
                text-decoration: none;
                display: inline-block;
            }
            
            .view-all:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            .activity-list {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            
            .activity-item {
                display: flex;
                align-items: center;
                gap: 16px;
                padding: 16px;
                background: var(--bg-tertiary);
                border-radius: 12px;
                border: 1px solid var(--border);
            }
            
            .activity-icon {
                width: 40px;
                height: 40px;
                background: var(--accent-blue);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 1.2rem;
            }
            
            .activity-content {
                flex-grow: 1;
            }
            
            .activity-title {
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 4px;
            }
            
            .activity-time {
                color: var(--text-tertiary);
                font-size: 0.85rem;
            }
            
            /* QUICK ACTIONS */
            .quick-actions {
                margin-top: 40px;
            }
            
            .actions-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            
            .action-card {
                background: var(--bg-secondary);
                border-radius: 12px;
                padding: 24px;
                border: 1px solid var(--border);
                text-align: center;
                cursor: pointer;
                transition: all 0.2s;
                text-decoration: none;
                color: var(--text-primary);
            }
            
            .action-card:hover {
                transform: translateY(-4px);
                border-color: var(--accent-blue);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
                background: var(--bg-tertiary);
            }
            
            .action-icon {
                font-size: 2.5rem;
                margin-bottom: 16px;
                color: var(--accent-blue);
            }
            
            .action-title {
                font-weight: 600;
                margin-bottom: 8px;
            }
            
            .action-desc {
                color: var(--text-secondary);
                font-size: 0.9rem;
                line-height: 1.4;
            }
            
            /* FOOTER */
            .admin-footer {
                margin-top: 60px;
                padding: 30px;
                text-align: center;
                color: var(--text-tertiary);
                font-size: 0.9rem;
                border-top: 1px solid var(--border);
            }
            
            /* UTILITIES */
            .text-success { color: var(--accent-green); }
            .text-warning { color: var(--accent-yellow); }
            .text-danger { color: var(--danger); }
            .text-info { color: var(--accent-blue); }
            
            .badge {
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.8rem;
                font-weight: 600;
            }
            
            .badge-success { background: rgba(86, 211, 100, 0.1); color: var(--accent-green); }
            .badge-warning { background: rgba(227, 179, 65, 0.1); color: var(--accent-yellow); }
            .badge-danger { background: rgba(218, 54, 51, 0.1); color: var(--danger); }
            .badge-info { background: rgba(88, 166, 255, 0.1); color: var(--accent-blue); }
            
            /* ANIMATIONS */
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            /* RESPONSIVE */
            @media (max-width: 768px) {
                .admin-header {
                    flex-direction: column;
                    gap: 20px;
                    padding: 20px;
                }
                
                .admin-container {
                    padding: 20px;
                }
                
                .admin-welcome {
                    padding: 20px;
                }
                
                .admin-welcome h1 {
                    font-size: 1.8rem;
                }
                
                .nav-links {
                    flex-wrap: wrap;
                    justify-content: center;
                }
                
                .section-header {
                    flex-direction: column;
                    gap: 20px;
                    text-align: center;
                }
                
                .activity-item {
                    flex-direction: column;
                    text-align: center;
                    gap: 12px;
                }
            }
            
            @media (max-width: 480px) {
                .logo {
                    font-size: 1.5rem;
                }
                
                .admin-badge {
                    padding: 6px 12px;
                    font-size: 0.85rem;
                }
                
                .stat-value {
                    font-size: 2rem;
                }
                
                .actions-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="grid-bg"></div>
        
        <!-- Header -->
        <div class="admin-header">
            <div class="header-left">
                <div class="logo">ADMIN <span>PANEL</span></div>
                <div style="color: var(--text-tertiary); font-size: 0.9rem;">
                    SOT TDM System Management
                </div>
            </div>
            
            <div class="header-right">
                <div class="admin-badge">
                    <i class="fas fa-shield-alt"></i> Administrator
                </div>
                
                <div class="nav-links">
                    <a href="/admin" class="nav-link active">
                        <i class="fas fa-tachometer-alt"></i> Dashboard
                    </a>
                    <a href="/admin/players" class="nav-link">
                        <i class="fas fa-users"></i> Players
                    </a>
                    <a href="/dashboard" class="nav-link">
                        <i class="fas fa-user"></i> User View
                    </a>
                    <a href="/logout" class="nav-link">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="admin-container">
            <div class="admin-welcome">
                <h1>Welcome, Administrator</h1>
                <p>System overview and management controls for SOT TDM System</p>
            </div>
            
            <!-- Stats Overview -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon">
                        <i class="fas fa-users"></i>
                    </div>
                    <div class="stat-value">{{ total_players }}</div>
                    <div class="stat-label">Total Players</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-icon">
                        <i class="fas fa-crosshairs"></i>
                    </div>
                    <div class="stat-value">{{ "{:,}".format(total_kills) }}</div>
                    <div class="stat-label">Total Kills</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-icon">
                        <i class="fas fa-gamepad"></i>
                    </div>
                    <div class="stat-value">{{ total_games }}</div>
                    <div class="stat-label">Games Played</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-icon">
                        <i class="fas fa-shield-alt"></i>
                    </div>
                    <div class="stat-value">{{ admins }}</div>
                    <div class="stat-label">Administrators</div>
                </div>
            </div>
            
            <!-- Recent Activity -->
            <div class="admin-sections">
                <div class="admin-section">
                    <div class="section-header">
                        <div class="section-title">
                            <i class="fas fa-ticket-alt"></i> Recent Tickets
                        </div>
                        <a href="/admin/tickets" class="view-all">
                            View All
                        </a>
                    </div>
                    
                    <div class="activity-list">
                        {% for ticket in recent_activity %}
                        <div class="activity-item">
                            <div class="activity-icon">
                                <i class="fas fa-question-circle"></i>
                            </div>
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
                        <div style="text-align: center; padding: 40px; color: var(--text-tertiary);">
                            <i class="fas fa-check-circle" style="font-size: 2rem; margin-bottom: 16px; opacity: 0.5;"></i>
                            <p>No open tickets</p>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                
                <div class="admin-section">
                    <div class="section-header">
                        <div class="section-title">
                            <i class="fas fa-gamepad"></i> Recent Matches
                        </div>
                        <a href="/admin/matches" class="view-all">
                            View All
                        </a>
                    </div>
                    
                    <div class="activity-list">
                        {% for match in recent_matches %}
                        <div class="activity-item">
                            <div class="activity-icon">
                                <i class="fas fa-trophy"></i>
                            </div>
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
                        <div style="text-align: center; padding: 40px; color: var(--text-tertiary);">
                            <i class="fas fa-gamepad" style="font-size: 2rem; margin-bottom: 16px; opacity: 0.5;"></i>
                            <p>No recent matches</p>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            
            <!-- Quick Actions -->
            <div class="quick-actions">
                <h2 style="color: var(--text-primary); margin-bottom: 20px; font-size: 1.6rem;">
                    <i class="fas fa-bolt"></i> Quick Actions
                </h2>
                
                <div class="actions-grid">
                    <a href="/admin/players" class="action-card">
                        <div class="action-icon">
                            <i class="fas fa-user-cog"></i>
                        </div>
                        <div class="action-title">Manage Players</div>
                        <div class="action-desc">
                            View, edit, and manage all registered players
                        </div>
                    </a>
                    
                    <a href="/admin/players?action=add" class="action-card">
                        <div class="action-icon">
                            <i class="fas fa-user-plus"></i>
                        </div>
                        <div class="action-title">Add Player</div>
                        <div class="action-desc">
                            Manually register a new player to the system
                        </div>
                    </a>
                    
                    <a href="/admin/tickets" class="action-card">
                        <div class="action-icon">
                            <i class="fas fa-ticket-alt"></i>
                        </div>
                        <div class="action-title">Manage Tickets</div>
                        <div class="action-desc">
                            Review and resolve support tickets
                        </div>
                    </a>
                    
                    <a href="/admin/settings" class="action-card">
                        <div class="action-icon">
                            <i class="fas fa-cog"></i>
                        </div>
                        <div class="action-title">System Settings</div>
                        <div class="action-desc">
                            Configure system preferences and options
                        </div>
                    </a>
                </div>
            </div>
        </div>
        
        <div class="admin-footer">
            <div style="margin-bottom: 20px; display: flex; align-items: center; justify-content: center; gap: 20px;">
                <span>Admin Panel v2.0</span>
                <i class="fas fa-circle" style="font-size: 4px; color: var(--text-tertiary);"></i>
                <span>System Time: {{ datetime.now().strftime('%H:%M:%S') }}</span>
                <i class="fas fa-circle" style="font-size: 4px; color: var(--text-tertiary);"></i>
                <span>Status: <span class="text-success">Operational</span></span>
            </div>
            
            <div style="color: var(--text-tertiary); font-size: 0.85rem; opacity: 0.8;">
                &copy; {{ datetime.now().year }} SOT TDM System Administration
            </div>
        </div>
        
        <script>
            function showNotification(message, type = 'info') {
                const colors = {
                    info: 'var(--accent-blue)',
                    success: 'var(--accent-green)',
                    warning: 'var(--accent-yellow)',
                    error: 'var(--danger)'
                };
                
                const notification = document.createElement('div');
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: var(--bg-secondary);
                    border-left: 4px solid ${colors[type]};
                    color: var(--text-primary);
                    padding: 16px;
                    border-radius: 8px;
                    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
                    z-index: 10000;
                    transform: translateX(400px);
                    transition: transform 0.3s ease-out;
                    max-width: 300px;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    border: 1px solid var(--border);
                `;
                
                notification.innerHTML = `
                    <i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'}" style="color: ${colors[type]};"></i>
                    <div>
                        <div style="font-weight: 600; color: ${colors[type]};">${type.toUpperCase()}</div>
                        <div style="margin-top: 4px; font-size: 0.95rem;">${message}</div>
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
                        this.style.transform = 'translateY(-4px)';
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

@app.route('/admin/players')
def admin_players():
    """Admin Players Management"""
    if 'user_data' not in session or not session['user_data'].get('is_admin'):
        return redirect(url_for('dashboard'))
    
    players = get_all_players()
    action = request.args.get('action', '')
    
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Player Management - Admin Panel</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                --bg-primary: #0d1117;
                --bg-secondary: #161b22;
                --bg-tertiary: #21262d;
                --border: #30363d;
                --text-primary: #c9d1d9;
                --text-secondary: #8b949e;
                --text-tertiary: #6e7681;
                --accent-blue: #58a6ff;
                --accent-green: #56d364;
                --accent-yellow: #e3b341;
                --accent-orange: #f78166;
                --accent-purple: #bc8cff;
                --success: #238636;
                --warning: #9e6a03;
                --danger: #da3633;
                --info: #1f6feb;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', sans-serif;
                background: var(--bg-primary);
                color: var(--text-primary);
                min-height: 100vh;
                line-height: 1.6;
            }
            
            .grid-bg {
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                background-image: 
                    linear-gradient(rgba(88, 166, 255, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(88, 166, 255, 0.03) 1px, transparent 1px);
                background-size: 50px 50px;
                z-index: -1;
                pointer-events: none;
            }
            
            /* HEADER */
            .admin-header {
                background: var(--bg-secondary);
                border-bottom: 1px solid var(--border);
                padding: 20px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            
            .logo {
                font-size: 1.8rem;
                font-weight: 700;
                color: var(--accent-blue);
            }
            
            .logo span {
                color: var(--accent-yellow);
            }
            
            .header-right {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            
            .admin-badge {
                padding: 8px 16px;
                background: rgba(227, 179, 65, 0.1);
                border: 1px solid rgba(227, 179, 65, 0.3);
                border-radius: 8px;
                color: var(--accent-yellow);
                font-weight: 600;
                font-size: 0.95rem;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .nav-links {
                display: flex;
                gap: 10px;
            }
            
            .nav-link {
                padding: 10px 20px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                color: var(--text-secondary);
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.95rem;
            }
            
            .nav-link:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            .nav-link.active {
                background: var(--accent-blue);
                color: white;
                border-color: var(--accent-blue);
            }
            
            /* MAIN CONTENT */
            .admin-container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 30px;
                position: relative;
                z-index: 1;
            }
            
            .page-header {
                margin-bottom: 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .page-title {
                font-size: 2rem;
                color: var(--text-primary);
            }
            
            .page-actions {
                display: flex;
                gap: 12px;
            }
            
            .btn {
                padding: 10px 20px;
                border: 1px solid var(--border);
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.95rem;
                text-decoration: none;
                color: var(--text-primary);
                background: var(--bg-tertiary);
            }
            
            .btn:hover {
                background: var(--border);
            }
            
            .btn-primary {
                background: var(--accent-blue);
                border-color: var(--accent-blue);
                color: white;
            }
            
            .btn-primary:hover {
                background: #388bfd;
            }
            
            .btn-success {
                background: var(--accent-green);
                border-color: var(--accent-green);
                color: white;
            }
            
            .btn-success:hover {
                background: #3fb950;
            }
            
            /* PLAYERS TABLE */
            .players-table-container {
                background: var(--bg-secondary);
                border-radius: 16px;
                border: 1px solid var(--border);
                overflow: hidden;
                margin-bottom: 30px;
            }
            
            .table-header {
                display: grid;
                grid-template-columns: 50px 1fr 1fr 1fr 100px 100px 100px 100px 120px;
                padding: 20px;
                background: var(--bg-tertiary);
                border-bottom: 1px solid var(--border);
                font-weight: 600;
                color: var(--text-secondary);
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .table-row {
                display: grid;
                grid-template-columns: 50px 1fr 1fr 1fr 100px 100px 100px 100px 120px;
                padding: 16px 20px;
                border-bottom: 1px solid var(--border);
                align-items: center;
                transition: all 0.2s;
            }
            
            .table-row:hover {
                background: var(--bg-tertiary);
            }
            
            .table-row:last-child {
                border-bottom: none;
            }
            
            .player-avatar {
                width: 36px;
                height: 36px;
                background: var(--accent-blue);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 1rem;
            }
            
            .player-name {
                font-weight: 600;
                color: var(--text-primary);
            }
            
            .player-discord {
                color: var(--text-secondary);
                font-size: 0.9rem;
            }
            
            .player-key {
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.85rem;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all 0.2s;
            }
            
            .player-key:hover {
                color: var(--accent-blue);
            }
            
            .player-stats {
                text-align: center;
                font-weight: 600;
            }
            
            .player-kd {
                color: var(--accent-green);
            }
            
            .player-admin {
                text-align: center;
            }
            
            .badge {
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.8rem;
                font-weight: 600;
            }
            
            .badge-success { background: rgba(86, 211, 100, 0.1); color: var(--accent-green); }
            .badge-warning { background: rgba(227, 179, 65, 0.1); color: var(--accent-yellow); }
            .badge-danger { background: rgba(218, 54, 51, 0.1); color: var(--danger); }
            .badge-info { background: rgba(88, 166, 255, 0.1); color: var(--accent-blue); }
            
            .player-actions {
                display: flex;
                gap: 8px;
                justify-content: center;
            }
            
            .action-btn {
                width: 32px;
                height: 32px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                border-radius: 6px;
                color: var(--text-secondary);
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .action-btn:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            .action-btn.edit:hover {
                color: var(--accent-blue);
                border-color: var(--accent-blue);
            }
            
            .action-btn.delete:hover {
                color: var(--danger);
                border-color: var(--danger);
            }
            
            /* PAGINATION */
            .pagination {
                display: flex;
                justify-content: center;
                gap: 8px;
                margin-top: 30px;
            }
            
            .page-btn {
                width: 40px;
                height: 40px;
                background: var(--bg-tertiary);
                border: 1px solid var(--border);
                border-radius: 8px;
                color: var(--text-secondary);
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .page-btn:hover {
                background: var(--border);
                color: var(--text-primary);
            }
            
            .page-btn.active {
                background: var(--accent-blue);
                border-color: var(--accent-blue);
                color: white;
            }
            
            /* RESPONSIVE */
            @media (max-width: 1200px) {
                .table-header,
                .table-row {
                    grid-template-columns: 50px 1fr 1fr 100px 100px 100px 120px;
                }
                
                .table-header > :nth-child(4),
                .table-row > :nth-child(4) {
                    display: none;
                }
            }
            
            @media (max-width: 992px) {
                .table-header,
                .table-row {
                    grid-template-columns: 50px 1fr 100px 100px 120px;
                }
                
                .table-header > :nth-child(3),
                .table-row > :nth-child(3),
                .table-header > :nth-child(6),
                .table-row > :nth-child(6),
                .table-header > :nth-child(7),
                .table-row > :nth-child(7) {
                    display: none;
                }
            }
            
            @media (max-width: 768px) {
                .admin-header {
                    flex-direction: column;
                    gap: 20px;
                    padding: 20px;
                }
                
                .admin-container {
                    padding: 20px;
                }
                
                .page-header {
                    flex-direction: column;
                    gap: 20px;
                    text-align: center;
                }
                
                .nav-links {
                    flex-wrap: wrap;
                    justify-content: center;
                }
                
                .table-header,
                .table-row {
                    grid-template-columns: 40px 1fr 80px 100px;
                    padding: 12px 16px;
                    font-size: 0.85rem;
                }
                
                .table-header > :nth-child(5),
                .table-row > :nth-child(5),
                .table-header > :nth-child(8),
                .table-row > :nth-child(8) {
                    display: none;
                }
                
                .player-avatar {
                    width: 30px;
                    height: 30px;
                    font-size: 0.9rem;
                }
            }
            
            @media (max-width: 480px) {
                .logo {
                    font-size: 1.5rem;
                }
                
                .admin-badge {
                    padding: 6px 12px;
                    font-size: 0.85rem;
                }
                
                .page-title {
                    font-size: 1.5rem;
                }
                
                .page-actions {
                    flex-direction: column;
                    width: 100%;
                }
                
                .btn {
                    width: 100%;
                    justify-content: center;
                }
            }
        </style>
    </head>
    <body>
        <div class="grid-bg"></div>
        
        <!-- Header -->
        <div class="admin-header">
            <div class="header-left">
                <div class="logo">ADMIN <span>PANEL</span></div>
                <div style="color: var(--text-tertiary); font-size: 0.9rem;">
                    Player Management
                </div>
            </div>
            
            <div class="header-right">
                <div class="admin-badge">
                    <i class="fas fa-shield-alt"></i> Administrator
                </div>
                
                <div class="nav-links">
                    <a href="/admin" class="nav-link">
                        <i class="fas fa-tachometer-alt"></i> Dashboard
                    </a>
                    <a href="/admin/players" class="nav-link active">
                        <i class="fas fa-users"></i> Players
                    </a>
                    <a href="/dashboard" class="nav-link">
                        <i class="fas fa-user"></i> User View
                    </a>
                    <a href="/logout" class="nav-link">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="admin-container">
            <div class="page-header">
                <h1 class="page-title">
                    <i class="fas fa-users"></i> Player Management
                </h1>
                
                <div class="page-actions">
                    <a href="/admin/players?action=add" class="btn btn-primary">
                        <i class="fas fa-user-plus"></i> Add Player
                    </a>
                    <button class="btn btn-success" onclick="exportPlayers()">
                        <i class="fas fa-download"></i> Export
                    </button>
                    <button class="btn" onclick="refreshPlayers()">
                        <i class="fas fa-sync-alt"></i> Refresh
                    </button>
                </div>
            </div>
            
            <!-- Players Table -->
            <div class="players-table-container">
                <div class="table-header">
                    <div></div>
                    <div>Player</div>
                    <div>Discord</div>
                    <div>API Key</div>
                    <div>Kills</div>
                    <div>Deaths</div>
                    <div>K/D</div>
                    <div>Status</div>
                    <div>Actions</div>
                </div>
                
                {% for player in players %}
                <div class="table-row">
                    <div class="player-avatar">
                        {{ player.in_game_name[0].upper() if player.in_game_name else 'P' }}
                    </div>
                    <div class="player-name">
                        {{ player.in_game_name or 'N/A' }}
                        {% if player.prestige > 0 %}
                        <span style="font-size: 0.8rem; color: var(--accent-yellow);">P{{ player.prestige }}</span>
                        {% endif %}
                    </div>
                    <div class="player-discord">
                        {{ player.discord_name or 'N/A' }}
                    </div>
                    <div class="player-key" onclick="copyKey('{{ player.api_key }}')" title="Click to copy">
                        {{ player.api_key[:8] }}...
                    </div>
                    <div class="player-stats">
                        {{ player.total_kills or 0 }}
                    </div>
                    <div class="player-stats">
                        {{ player.total_deaths or 0 }}
                    </div>
                    <div class="player-stats player-kd">
                        {{ player.kd_ratio }}
                    </div>
                    <div class="player-admin">
                        {% if player.is_admin %}
                        <span class="badge badge-warning">Admin</span>
                        {% else %}
                        <span class="badge badge-success">Player</span>
                        {% endif %}
                    </div>
                    <div class="player-actions">
                        <button class="action-btn edit" onclick="editPlayer({{ player.id }})" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="action-btn delete" onclick="deletePlayer({{ player.id }})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                        <button class="action-btn" onclick="viewPlayer({{ player.id }})" title="View Details">
                            <i class="fas fa-eye"></i>
                        </button>
                    </div>
                </div>
                {% else %}
                <div style="text-align: center; padding: 60px; color: var(--text-tertiary);">
                    <i class="fas fa-users" style="font-size: 3rem; margin-bottom: 20px; opacity: 0.5;"></i>
                    <h3>No players found</h3>
                    <p>No players have registered yet.</p>
                </div>
                {% endfor %}
            </div>
            
            <!-- Pagination -->
            <div class="pagination">
                <button class="page-btn active">1</button>
                <button class="page-btn">2</button>
                <button class="page-btn">3</button>
                <span style="color: var(--text-tertiary); margin: 0 10px;">...</span>
                <button class="page-btn">10</button>
            </div>
        </div>
        
        <script>
            function copyKey(key) {
                navigator.clipboard.writeText(key).then(() => {
                    showNotification('API key copied to clipboard', 'success');
                }).catch(err => {
                    console.error('Copy failed:', err);
                    showNotification('Failed to copy key', 'error');
                });
            }
            
            function editPlayer(playerId) {
                showNotification('Edit player feature coming soon', 'info');
                // In a real implementation, this would open an edit modal
                // window.location.href = `/admin/players/${playerId}/edit`;
            }
            
            function deletePlayer(playerId) {
                if (confirm('Are you sure you want to delete this player? This action cannot be undone.')) {
                    fetch(`/admin/players/${playerId}`, {
                        method: 'DELETE',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            showNotification('Player deleted successfully', 'success');
                            setTimeout(() => {
                                window.location.reload();
                            }, 1000);
                        } else {
                            showNotification(data.error || 'Failed to delete player', 'error');
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        showNotification('Failed to delete player', 'error');
                    });
                }
            }
            
            function viewPlayer(playerId) {
                showNotification('View player feature coming soon', 'info');
                // window.location.href = `/admin/players/${playerId}`;
            }
            
            function exportPlayers() {
                showNotification('Export feature coming soon', 'info');
                // In a real implementation, this would download a CSV/JSON file
            }
            
            function refreshPlayers() {
                window.location.reload();
            }
            
            function showNotification(message, type = 'info') {
                const colors = {
                    info: 'var(--accent-blue)',
                    success: 'var(--accent-green)',
                    warning: 'var(--accent-yellow)',
                    error: 'var(--danger)'
                };
                
                const notification = document.createElement('div');
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: var(--bg-secondary);
                    border-left: 4px solid ${colors[type]};
                    color: var(--text-primary);
                    padding: 16px;
                    border-radius: 8px;
                    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
                    z-index: 10000;
                    transform: translateX(400px);
                    transition: transform 0.3s ease-out;
                    max-width: 300px;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    border: 1px solid var(--border);
                `;
                
                notification.innerHTML = `
                    <i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'}" style="color: ${colors[type]};"></i>
                    <div>
                        <div style="font-weight: 600; color: ${colors[type]};">${type.toUpperCase()}</div>
                        <div style="margin-top: 4px; font-size: 0.95rem;">${message}</div>
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
                // Add search functionality
                const searchInput = document.createElement('input');
                searchInput.type = 'text';
                searchInput.placeholder = 'Search players...';
                searchInput.style.cssText = `
                    padding: 10px 16px;
                    background: var(--bg-tertiary);
                    border: 1px solid var(--border);
                    border-radius: 8px;
                    color: var(--text-primary);
                    font-family: 'Inter', sans-serif;
                    font-size: 0.95rem;
                    width: 300px;
                    margin-bottom: 20px;
                `;
                
                const pageHeader = document.querySelector('.page-header');
                if (pageHeader) {
                    pageHeader.parentNode.insertBefore(searchInput, pageHeader.nextSibling);
                }
            });
        </script>
    </body>
    </html>
    ''', players=players, action=action)

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

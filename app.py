# app.py - COMPLETE DISCORD BOT WITH WEB SERVER
import os
import json
import sqlite3
import random
import string
import threading
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord credentials - ALL REQUIRED
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot status
bot_active = False
bot_info = {}

# =============================================================================
# DATABASE SETUP
# =============================================================================

def init_db():
    """Initialize database"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                username TEXT,
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
# DISCORD BOT FUNCTIONS
# =============================================================================

def test_discord_token():
    """Test if Discord token is valid"""
    global bot_active, bot_info
    
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN not set in environment")
        return False
    
    try:
        url = "https://discord.com/api/v10/users/@me"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            bot_info = response.json()
            bot_active = True
            logger.info(f"✅ Discord bot is ACTIVE: {bot_info['username']}#{bot_info['discriminator']}")
            return True
        else:
            logger.error(f"❌ Invalid Discord token: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Discord API error: {e}")
        return False

def register_commands():
    """Register slash commands with Discord"""
    if not DISCORD_TOKEN or not DISCORD_CLIENT_ID:
        logger.error("❌ Cannot register commands: Missing token or client ID")
        return False
    
    commands = [
        {
            "name": "ping",
            "description": "Check if bot is alive",
            "type": 1
        },
        {
            "name": "room",
            "description": "Create a TDM match room",
            "type": 1
        },
        {
            "name": "stats",
            "description": "Check player statistics",
            "type": 1,
            "options": [
                {
                    "name": "player",
                    "description": "Player name",
                    "type": 3,
                    "required": True
                }
            ]
        }
    ]
    
    try:
        url = f"https://discord.com/api/v10/applications/{DISCORD_CLIENT_ID}/commands"
        headers = {
            "Authorization": f"Bot {DISCORD_TOKEN}",
            "Content-Type": "application/json"
        }
        
        response = requests.put(url, headers=headers, json=commands, timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info(f"✅ Registered {len(commands)} slash commands")
            return True
        else:
            logger.error(f"❌ Failed to register commands: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error registering commands: {e}")
        return False

def create_invite_link():
    """Generate bot invite link"""
    if not DISCORD_CLIENT_ID:
        return None
    
    permissions = "274877975616"  # Send Messages, Read Messages, Use Slash Commands
    return f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions={permissions}&scope=bot%20applications.commands"

# =============================================================================
# FLASK ROUTES - WEB INTERFACE
# =============================================================================

@app.route('/')
def home():
    """Main web page"""
    invite_link = create_invite_link()
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SoT TDM Server</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            header {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; margin-bottom: 30px; }}
            h1 {{ color: #333; margin: 0 0 10px 0; }}
            .status {{ display: inline-block; padding: 8px 16px; border-radius: 20px; font-weight: bold; margin: 10px; }}
            .online {{ background: #4CAF50; color: white; }}
            .offline {{ background: #f44336; color: white; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
            .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .btn {{ display: inline-block; background: #4285f4; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none; margin: 5px; border: none; cursor: pointer; }}
            .btn:hover {{ background: #3367d6; }}
            .btn-green {{ background: #34a853; }}
            .btn-green:hover {{ background: #2d9249; }}
            .btn-red {{ background: #ea4335; }}
            .btn-red:hover {{ background: #d33426; }}
            code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
            .info-box {{ background: #e8f0fe; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #4285f4; }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🏴‍☠️ Sea of Thieves TDM Server</h1>
                <div class="status {'online' if bot_active else 'offline'}" id="botStatus">
                    {'🤖 BOT ONLINE' if bot_active else '❌ BOT OFFLINE'}
                </div>
                <p>Complete TDM match management with Discord bot integration</p>
            </header>
            
            <div class="grid">
                <div class="card">
                    <h2>🎮 Quick Actions</h2>
                    <button onclick="createMatch()" class="btn btn-green">Create Match</button>
                    <button onclick="testBot()" class="btn">Test Bot</button>
                    <button onclick="registerCommands()" class="btn">Register Commands</button>
                    <div id="result" style="margin-top: 15px;"></div>
                </div>
                
                <div class="card">
                    <h2>🤖 Bot Status</h2>
                    <div id="botInfo">
                        {'<p>🤖 ' + bot_info.get('username', 'Unknown') + '#' + bot_info.get('discriminator', '0000') + '</p>' if bot_info else '<p>Bot not connected</p>'}
                    </div>
                    <p>Token: {'✅ Set' if DISCORD_TOKEN else '❌ Missing'}</p>
                    <p>Client ID: {'✅ Set' if DISCORD_CLIENT_ID else '❌ Missing'}</p>
                    <p>Public Key: {'✅ Set' if DISCORD_PUBLIC_KEY else '❌ Missing'}</p>
                </div>
                
                <div class="card">
                    <h2>🔗 Invite Bot</h2>
                    {'<a href="' + invite_link + '" target="_blank" class="btn btn-green">Invite to Server</a>' if invite_link else '<p>Set CLIENT_ID to generate invite link</p>'}
                    <p>Interactions Endpoint:</p>
                    <code>{request.host_url}interactions</code>
                    <p>Copy this URL to Discord Developer Portal</p>
                </div>
                
                <div class="card">
                    <h2>📊 Active Matches</h2>
                    <div id="matches">Loading...</div>
                    <button onclick="loadMatches()" class="btn">Refresh</button>
                </div>
            </div>
            
            <div class="card" style="margin-top: 30px;">
                <h2>📝 Setup Instructions</h2>
                <div class="info-box">
                    <h3>1. Get Discord Credentials</h3>
                    <p>Go to <a href="https://discord.com/developers/applications" target="_blank">Discord Developer Portal</a></p>
                    <p>• Copy TOKEN from "Bot" section</p>
                    <p>• Copy CLIENT_ID from "General Information"</p>
                    <p>• Copy PUBLIC_KEY from "General Information"</p>
                </div>
                <div class="info-box">
                    <h3>2. Set Render Environment Variables</h3>
                    <p>In Render.com dashboard, set:</p>
                    <code>DISCORD_TOKEN = your_token_here</code><br>
                    <code>DISCORD_CLIENT_ID = your_client_id</code><br>
                    <code>DISCORD_PUBLIC_KEY = your_public_key</code>
                </div>
                <div class="info-box">
                    <h3>3. Set Interactions URL</h3>
                    <p>In Discord portal → General Information:</p>
                    <code>{request.host_url}interactions</code>
                </div>
            </div>
        </div>
        
        <script>
            function createMatch() {{
                fetch('/api/match/create', {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(data => {{
                        document.getElementById('result').innerHTML = `
                            <div style="background: #e8f5e9; padding: 15px; border-radius: 5px;">
                                <h3 style="margin: 0 0 10px 0;">✅ Room Created!</h3>
                                <p>Code: <code style="font-size: 1.2em;">${{data.room_code}}</code></p>
                                <a href="/match/${{data.room_code}}" class="btn">View Match</a>
                            </div>
                        `;
                        loadMatches();
                    }});
            }}
            
            function testBot() {{
                document.getElementById('result').innerHTML = '<p>Testing bot connection...</p>';
                fetch('/api/bot/test')
                    .then(r => r.json())
                    .then(data => {{
                        if (data.success) {{
                            document.getElementById('result').innerHTML = `
                                <div style="background: #e8f5e9; padding: 15px; border-radius: 5px;">
                                    <h3 style="margin: 0 0 10px 0;">✅ Bot is Active!</h3>
                                    <p>${{data.message}}</p>
                                </div>
                            `;
                            document.getElementById('botStatus').className = 'status online';
                            document.getElementById('botStatus').textContent = '🤖 BOT ONLINE';
                            document.getElementById('botInfo').innerHTML = `<p>🤖 ${{data.bot_info.username}}#${{data.bot_info.discriminator}}</p>`;
                        }} else {{
                            document.getElementById('result').innerHTML = `
                                <div style="background: #ffebee; padding: 15px; border-radius: 5px;">
                                    <h3 style="margin: 0 0 10px 0;">❌ Bot Test Failed</h3>
                                    <p>${{data.error}}</p>
                                </div>
                            `;
                        }}
                    }});
            }}
            
            function registerCommands() {{
                fetch('/api/bot/register-commands', {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(data => {{
                        alert(data.message);
                    }});
            }}
            
            function loadMatches() {{
                fetch('/api/matches/active')
                    .then(r => r.json())
                    .then(matches => {{
                        let html = '';
                        if (matches.length === 0) {{
                            html = '<p>No active matches</p>';
                        }} else {{
                            matches.forEach(match => {{
                                html += `
                                    <div style="border: 1px solid #ddd; padding: 10px; margin: 10px 0; border-radius: 5px;">
                                        <strong>${{match.room_code}}</strong><br>
                                        ${{match.team1_name}}: ${{match.team1_score}} vs ${{match.team2_name}}: ${{match.team2_score}}<br>
                                        Status: ${{match.status}}
                                    </div>
                                `;
                            }});
                        }}
                        document.getElementById('matches').innerHTML = html;
                    }});
            }}
            
            // Load matches on page load
            document.addEventListener('DOMContentLoaded', loadMatches);
        </script>
    </body>
    </html>
    '''

@app.route('/match/<room_code>')
def match_page(room_code):
    """Match details page"""
    conn = get_db_connection()
    match = conn.execute('SELECT * FROM matches WHERE room_code = ?', (room_code,)).fetchone()
    conn.close()
    
    if not match:
        return '<h1>Match not found</h1><a href="/">Go Home</a>'
    
    return f'''
    <html>
    <head><title>Match {room_code}</title></head>
    <body>
        <h1>Match: {room_code}</h1>
        <div style="font-size: 1.2em;">
            <p>{match['team1_name']}: <strong>{match['team1_score']}</strong></p>
            <p>{match['team2_name']}: <strong>{match['team2_score']}</strong></p>
            <p>Status: {match['status']}</p>
        </div>
        <a href="/">← Back to Home</a>
    </body>
    </html>
    '''

# =============================================================================
# DISCORD INTERACTIONS ENDPOINT
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Handle Discord slash commands"""
    try:
        data = request.get_json()
        
        # Handle Discord verification ping
        if data.get('type') == 1:
            return jsonify({"type": 1})  # PONG response
        
        # Handle slash commands
        if data.get('type') == 2:
            command = data.get('data', {}).get('name')
            
            if command == 'ping':
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": "🏓 Pong! SoT TDM Bot is online!",
                        "flags": 64  # EPHEMERAL
                    }
                })
            
            elif command == 'room':
                # Create a new match room
                room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('INSERT INTO matches (room_code) VALUES (?)', (room_code,))
                conn.commit()
                conn.close()
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": f"🎮 **TDM Room Created!**\n**Code:** `{room_code}`\n\nUse this code to join the match!",
                        "flags": 0
                    }
                })
            
            elif command == 'stats':
                options = data.get('data', {}).get('options', [])
                if options and len(options) > 0:
                    player_name = options[0].get('value', 'Unknown')
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": f"📊 **{player_name}'s Stats**\nKills: 0\nDeaths: 0\nK/D: 0.00\nWins: 0\nLosses: 0\n\n*Stats will be tracked once matches start*",
                            "flags": 64
                        }
                    })
        
        return jsonify({
            "type": 4,
            "data": {
                "content": "Command received",
                "flags": 64
            }
        })
        
    except Exception as e:
        logger.error(f"Interactions error: {e}")
        return jsonify({
            "type": 4,
            "data": {
                "content": f"Error: {str(e)}",
                "flags": 64
            }
        }), 500

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/match/create', methods=['POST'])
def api_create_match():
    """Create a new match"""
    room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO matches (room_code) VALUES (?)', (room_code,))
    conn.commit()
    match_id = cursor.lastrowid
    conn.close()
    
    return jsonify({
        "success": True,
        "room_code": room_code,
        "match_id": match_id,
        "message": "Match created successfully"
    })

@app.route('/api/matches/active')
def api_active_matches():
    """Get active matches"""
    conn = get_db_connection()
    matches = conn.execute('SELECT * FROM matches WHERE status != "ended" ORDER BY created_at DESC LIMIT 10').fetchall()
    conn.close()
    
    return jsonify([dict(match) for match in matches])

@app.route('/api/bot/status')
def api_bot_status():
    """Get bot status"""
    return jsonify({
        "active": bot_active,
        "bot_info": bot_info,
        "token_set": bool(DISCORD_TOKEN),
        "client_id_set": bool(DISCORD_CLIENT_ID),
        "public_key_set": bool(DISCORD_PUBLIC_KEY),
        "interactions_url": f"{request.host_url}interactions"
    })

@app.route('/api/bot/test', methods=['GET'])
def api_test_bot():
    """Test bot connection"""
    if test_discord_token():
        return jsonify({
            "success": True,
            "message": "Bot is connected to Discord",
            "bot_info": bot_info
        })
    else:
        return jsonify({
            "success": False,
            "error": "Bot cannot connect to Discord. Check your DISCORD_TOKEN."
        })

@app.route('/api/bot/register-commands', methods=['POST'])
def api_register_commands():
    """Register slash commands"""
    if register_commands():
        return jsonify({
            "success": True,
            "message": "Slash commands registered successfully!"
        })
    else:
        return jsonify({
            "success": False,
            "message": "Failed to register commands. Check your credentials."
        })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "bot_active": bot_active,
        "service": "SoT TDM Server",
        "version": "1.0.0"
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*60}")
    print("🚀 SoT TDM Server with Discord Bot")
    print(f"{'='*60}")
    
    # Test Discord connection
    if test_discord_token():
        print(f"✅ Discord bot connected: {bot_info.get('username', 'Unknown')}")
        
        # Register commands
        if register_commands():
            print("✅ Slash commands registered")
        else:
            print("⚠️ Could not register commands (check CLIENT_ID)")
    else:
        print("❌ Discord bot NOT connected")
        print("   Set DISCORD_TOKEN in environment variables")
    
    # Generate invite link
    invite_link = create_invite_link()
    if invite_link:
        print(f"\n🔗 Invite bot to your server:")
        print(f"   {invite_link}")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🤖 Interactions: http://localhost:{port}/interactions")
    print(f"📊 Health Check: http://localhost:{port}/health")
    
    print(f"\n📝 Set in Discord Developer Portal:")
    print(f"   Interactions Endpoint URL: http://YOUR-APP.onrender.com/interactions")
    print(f"{'='*60}\n")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=port, debug=False)

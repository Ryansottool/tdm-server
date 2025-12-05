# app.py - WITH DISCORD BOT (DISABLED UNTIL TOKEN IS SET)
import os
import json
import sqlite3
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from datetime import datetime
import threading

app = Flask(__name__)
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord bot - will be imported when token is available
discord_bot = None

# =============================================================================
# SIMPLE DATABASE SETUP
# =============================================================================

def init_db():
    """Initialize database"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Create simple tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT UNIQUE,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Database initialized")

# =============================================================================
# BASIC API ENDPOINTS
# =============================================================================

@app.route('/')
def home():
    """Home page"""
    return jsonify({
        "status": "online",
        "service": "SoT TDM Server",
        "version": "2.0.0",
        "features": ["API", "Database", "Discord Bot Ready"],
        "endpoints": {
            "GET /": "This page",
            "GET /health": "Health check",
            "POST /api/register": "Register player",
            "POST /api/match/create": "Create match",
            "GET /api/match/<code>": "Get match info"
        }
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "discord_bot": "ready" if os.environ.get('DISCORD_TOKEN') else "disabled"
    })

@app.route('/api/register', methods=['POST'])
def register_player():
    """Register a player"""
    data = request.json
    if not data or 'discord_id' not in data or 'username' not in data:
        return jsonify({"error": "Missing discord_id or username"}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Check if player exists
    cursor.execute('SELECT * FROM players WHERE discord_id = ?', (data['discord_id'],))
    player = cursor.fetchone()
    
    if player:
        # Update username if changed
        cursor.execute('UPDATE players SET username = ? WHERE discord_id = ?', 
                      (data['username'], data['discord_id']))
    else:
        # Create new player
        cursor.execute('INSERT INTO players (discord_id, username) VALUES (?, ?)',
                      (data['discord_id'], data['username']))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "message": f"Player {data['username']} registered"
    })

@app.route('/api/match/create', methods=['POST'])
def create_match():
    """Create a new match"""
    import random
    import string
    
    # Generate random room code
    room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO matches (room_code, status) 
        VALUES (?, 'waiting')
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

@app.route('/api/match/<room_code>', methods=['GET'])
def get_match(room_code):
    """Get match information"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM matches WHERE room_code = ?', (room_code,))
    match = cursor.fetchone()
    
    if not match:
        return jsonify({"error": "Match not found"}), 404
    
    # Convert to dict
    match_dict = {
        'room_code': match[1],
        'team1_score': match[2],
        'team2_score': match[3],
        'status': match[4],
        'created_at': match[5]
    }
    
    conn.close()
    
    return jsonify(match_dict)

# =============================================================================
# DISCORD BOT SETUP (WILL START WHEN TOKEN IS AVAILABLE)
# =============================================================================

def start_discord_bot():
    """Start Discord bot if token is available"""
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        print("⚠️ DISCORD_TOKEN not set. Bot disabled.")
        return
    
    try:
        import discord
        from discord.ext import commands
        
        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix='!', intents=intents)
        
        @bot.event
        async def on_ready():
            print(f"✅ Discord bot logged in as {bot.user}")
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="SoT TDM Matches"
                )
            )
        
        @bot.tree.command(name="ping", description="Check if bot is alive")
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message("🏓 Pong! Bot is online.")
        
        @bot.tree.command(name="room", description="Create a TDM room")
        async def create_room(interaction: discord.Interaction):
            await interaction.response.defer()
            
            # Create match via API
            import requests
            response = requests.post(
                f"http://localhost:{port}/api/match/create",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                await interaction.followup.send(
                    f"🎮 **New TDM Room Created!**\n"
                    f"**Code:** `{data['room_code']}`\n"
                    f"Share this code with your team to join!"
                )
            else:
                await interaction.followup.send("❌ Failed to create room")
        
        print("🤖 Starting Discord bot...")
        bot.run(token)
        
    except Exception as e:
        print(f"❌ Discord bot failed: {e}")

# =============================================================================
# APPLICATION STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"🚀 SoT TDM Server starting on port {port}...")
    print(f"📊 Database: {DATABASE}")
    
    # Start Discord bot in background thread if token exists
    token = os.environ.get('DISCORD_TOKEN')
    if token:
        print("🤖 Discord bot token found, starting bot...")
        bot_thread = threading.Thread(target=start_discord_bot, daemon=True)
        bot_thread.start()
    else:
        print("⚠️ Discord bot disabled (set DISCORD_TOKEN to enable)")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=port, debug=False)

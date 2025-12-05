# app.py - DISCORD BOT WITH INTERACTIONS ENDPOINT
import os
import json
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import threading
import discord
from discord.ext import commands
import asyncio

app = Flask(__name__)
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# =============================================================================
# SIMPLE DATABASE SETUP
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
# DISCORD BOT COMMANDS
# =============================================================================

@bot.event
async def on_ready():
    """When bot is ready"""
    print(f"✅ Discord bot logged in as {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="SoT TDM Matches"
        )
    )
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

@bot.tree.command(name="ping", description="Check if bot is alive")
async def ping(interaction: discord.Interaction):
    """Ping command"""
    await interaction.response.send_message("🏓 Pong! Bot is online.")

@bot.tree.command(name="room", description="Create a TDM room")
async def create_room(interaction: discord.Interaction):
    """Create room command"""
    await interaction.response.defer()
    
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
    conn.close()
    
    await interaction.followup.send(
        f"🎮 **New TDM Room Created!**\n"
        f"**Code:** `{room_code}`\n"
        f"Share this code with your team to join!"
    )

# =============================================================================
# DISCORD INTERACTIONS ENDPOINT (CRITICAL FOR RENDER.COM)
# =============================================================================

@app.route('/interactions', methods=['POST'])
def interactions():
    """Discord Interactions Endpoint - REQUIRED FOR RENDER.COM"""
    # Verify the request is from Discord (in production, you should verify the signature)
    # For simplicity in testing, we'll skip verification
    
    # Parse the interaction
    interaction_data = request.json
    
    if not interaction_data:
        return jsonify({"error": "No data provided"}), 400
    
    # Get interaction type
    interaction_type = interaction_data.get('type', 0)
    
    # Handle Ping (Discord verification)
    if interaction_type == 1:
        return jsonify({
            "type": 1  # PONG response
        })
    
    # Handle Application Commands
    elif interaction_type == 2:
        # Get command name
        data = interaction_data.get('data', {})
        command_name = data.get('name', '')
        
        # Create minimal response
        return jsonify({
            "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
            "data": {
                "content": f"Command received: {command_name}",
                "flags": 64  # EPHEMERAL
            }
        })
    
    # Default response
    return jsonify({"error": "Unknown interaction type"}), 400

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
        "features": ["API", "Database", "Discord Bot"],
        "endpoints": {
            "GET /": "This page",
            "POST /interactions": "Discord Interactions Endpoint",
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
        "bot_status": "ready" if os.environ.get('DISCORD_TOKEN') else "disabled"
    })

@app.route('/api/register', methods=['POST'])
def register_player():
    """Register a player"""
    data = request.json
    if not data or 'discord_id' not in data or 'username' not in data:
        return jsonify({"error": "Missing discord_id or username"}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM players WHERE discord_id = ?', (data['discord_id'],))
    player = cursor.fetchone()
    
    if player:
        cursor.execute('UPDATE players SET username = ? WHERE discord_id = ?', 
                      (data['username'], data['discord_id']))
    else:
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
# DISCORD BOT STARTUP
# =============================================================================

def start_bot():
    """Start Discord bot in a separate thread"""
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        print("⚠️ DISCORD_TOKEN not set. Bot disabled.")
        return
    
    try:
        print("🤖 Starting Discord bot...")
        # Run bot in current thread
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
    print(f"🌐 Interactions Endpoint: https://your-app.onrender.com/interactions")
    
    # Start Discord bot in background thread
    token = os.environ.get('DISCORD_TOKEN')
    if token:
        print("🤖 Discord bot token found, starting bot...")
        bot_thread = threading.Thread(target=start_bot, daemon=True)
        bot_thread.start()
    else:
        print("⚠️ Discord bot disabled (set DISCORD_TOKEN to enable)")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

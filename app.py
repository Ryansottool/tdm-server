# app.py - ENHANCED DISCORD BOT WITH REGISTRATION & KEY SYSTEM
import os
import json
import sqlite3
import random
import string
import threading
import time
import hashlib
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from datetime import datetime, timedelta
import logging
from uuid import uuid4

app = Flask(__name__)
CORS(app)
DATABASE = 'sot_tdm.db'
port = int(os.environ.get("PORT", 10000))

# Discord credentials
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot status
bot_active = False
bot_info = {}
ping_responses = [
    "🏓 Pong! Goblin is UP and watching!",
    "⚡ Still alive, newgen. What do you want?",
    "👁️ I see you... yes, I'm online.",
    "⚓ Captain's log: Bot operational. Stop bothering me.",
    "🎮 Stop pinging and go play some TDM.",
    "💀 Not dead yet, surprisingly.",
    "🔫 Pew pew! I'm here. Happy?",
    "🏴‍☠️ Yar har! The bot sails smoothly!",
    "🌊 Sea worthy and ready, landlubber.",
    "💰 Got gold? No? Then stop pinging."
]

# =============================================================================
# DATABASE SETUP
# =============================================================================

def init_db():
    """Initialize database with enhanced tables"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Players table with API keys
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                discord_name TEXT,
                in_game_name TEXT,
                api_key TEXT UNIQUE,
                key_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                total_kills INTEGER DEFAULT 0,
                total_deaths INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                prestige INTEGER DEFAULT 0,
                credits INTEGER DEFAULT 1000,
                title TEXT DEFAULT 'Deckhand',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Matches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_code TEXT UNIQUE,
                team1_players TEXT,  -- JSON array of player IDs
                team2_players TEXT,
                team1_score INTEGER DEFAULT 0,
                team2_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'waiting',
                map TEXT DEFAULT 'Arena',
                duration INTEGER DEFAULT 0,
                winner INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Match history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                player_id INTEGER,
                team INTEGER,
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                damage_done INTEGER DEFAULT 0,
                score INTEGER DEFAULT 0,
                FOREIGN KEY (match_id) REFERENCES matches (id),
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
        ''')
        
        # Items shop
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                price INTEGER,
                item_type TEXT,  -- title, cosmetic, boost, etc.
                rarity TEXT DEFAULT 'common',
                available BOOLEAN DEFAULT 1
            )
        ''')
        
        # Insert default shop items
        default_items = [
            ('Golden Sailor', 'Shiny golden title', 5000, 'title', 'rare'),
            ('Kraken Slayer', 'Defeated the kraken', 10000, 'title', 'epic'),
            ('Ghost Captain', 'Legendary ghost title', 25000, 'title', 'legendary'),
            ('Double XP (1hr)', 'Earn double XP for 1 hour', 2000, 'boost', 'common'),
            ('Golden Blunderbuss Skin', 'Golden weapon cosmetic', 7500, 'cosmetic', 'rare'),
            ('Pirate Legend Flag', 'Show your legend status', 15000, 'cosmetic', 'epic')
        ]
        
        for item in default_items:
            cursor.execute('''
                INSERT OR IGNORE INTO shop_items (name, description, price, item_type, rarity)
                VALUES (?, ?, ?, ?, ?)
            ''', item)
        
        conn.commit()
        conn.close()
        logger.info("✅ Enhanced database initialized")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# KEY & AUTH FUNCTIONS
# =============================================================================

def generate_api_key(discord_id, discord_name):
    """Generate unique API key for player"""
    timestamp = str(int(time.time()))
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    raw_key = f"{discord_id}:{discord_name}:{timestamp}:{random_str}"
    
    # Create hash-based key
    api_key = hashlib.sha256(raw_key.encode()).hexdigest()[:32]
    
    # Format as SOT-XXXX-XXXX-XXXX-XXXX
    formatted_key = f"SOT-{api_key[:4]}-{api_key[4:8]}-{api_key[8:12]}-{api_key[12:16]}"
    
    return formatted_key

def validate_api_key(api_key):
    """Validate API key and return player info"""
    if not api_key or not api_key.startswith("SOT-"):
        return None
    
    conn = get_db_connection()
    player = conn.execute(
        'SELECT * FROM players WHERE api_key = ? AND status = "active"',
        (api_key,)
    ).fetchone()
    conn.close()
    
    if player:
        # Update last used timestamp
        conn = get_db_connection()
        conn.execute(
            'UPDATE players SET last_used = CURRENT_TIMESTAMP WHERE id = ?',
            (player['id'],)
        )
        conn.commit()
        conn.close()
    
    return player

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
            "description": "Check if the goblin is watching",
            "type": 1
        },
        {
            "name": "register",
            "description": "Register and get your API key",
            "type": 1,
            "options": [
                {
                    "name": "ingame_name",
                    "description": "Your in-game name",
                    "type": 3,
                    "required": True
                }
            ]
        },
        {
            "name": "profile",
            "description": "View your profile and API key",
            "type": 1
        },
        {
            "name": "leaderboard",
            "description": "View top players",
            "type": 1
        },
        {
            "name": "shop",
            "description": "View available items",
            "type": 1
        },
        {
            "name": "buy",
            "description": "Purchase an item from shop",
            "type": 1,
            "options": [
                {
                    "name": "item",
                    "description": "Item name to buy",
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
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>🏴‍☠️ SoT TDM Registry - The Goblin's Den</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Pirata+One&family=Seaweed+Script&family=Cinzel:wght@400;700&display=swap');
            
            :root {
                --gold: #FFD700;
                --dark-gold: #B8860B;
                --sea-blue: #1E3A8A;
                --deep-blue: #0F172A;
                --blood-red: #8B0000;
                --parchment: #F5E6CA;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                background: linear-gradient(rgba(0, 0, 0, 0.8), rgba(0, 0, 0, 0.9)), 
                            url('https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=1920');
                background-size: cover;
                background-attachment: fixed;
                color: var(--parchment);
                font-family: 'Cinzel', serif;
                min-height: 100vh;
                position: relative;
                overflow-x: hidden;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
                position: relative;
                z-index: 1;
            }
            
            /* Animated ship in background */
            .ship {
                position: fixed;
                bottom: -100px;
                right: -200px;
                width: 500px;
                height: 300px;
                background: url('https://cdn-icons-png.flaticon.com/512/1995/1995516.png') no-repeat center;
                background-size: contain;
                opacity: 0.1;
                animation: sail 60s linear infinite;
                z-index: 0;
            }
            
            @keyframes sail {
                0% { transform: translateX(0) translateY(0) rotate(5deg); }
                50% { transform: translateX(-100px) translateY(-50px) rotate(-5deg); }
                100% { transform: translateX(-200px) translateY(0) rotate(5deg); }
            }
            
            /* Header with pirate theme */
            header {
                text-align: center;
                padding: 40px 20px;
                margin-bottom: 40px;
                border-bottom: 3px solid var(--gold);
                position: relative;
                background: rgba(15, 23, 42, 0.8);
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(10px);
            }
            
            h1 {
                font-family: 'Pirata One', cursive;
                font-size: 4.5rem;
                color: var(--gold);
                text-shadow: 3px 3px 0 var(--blood-red),
                             6px 6px 0 rgba(0, 0, 0, 0.5);
                margin-bottom: 10px;
                letter-spacing: 3px;
            }
            
            .subtitle {
                font-family: 'Seaweed Script', cursive;
                font-size: 1.8rem;
                color: #87CEEB;
                margin-bottom: 20px;
            }
            
            .status-badge {
                display: inline-block;
                padding: 12px 24px;
                background: linear-gradient(45deg, var(--blood-red), #8B0000);
                color: white;
                border-radius: 30px;
                font-weight: bold;
                font-size: 1.2rem;
                border: 2px solid var(--gold);
                box-shadow: 0 0 20px rgba(255, 215, 0, 0.3);
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { box-shadow: 0 0 20px rgba(255, 215, 0, 0.3); }
                50% { box-shadow: 0 0 40px rgba(255, 215, 0, 0.6); }
            }
            
            /* Main grid layout */
            .main-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 30px;
                margin-bottom: 40px;
            }
            
            @media (max-width: 1024px) {
                .main-grid {
                    grid-template-columns: 1fr;
                }
            }
            
            /* Card styles */
            .card {
                background: rgba(15, 23, 42, 0.85);
                border-radius: 15px;
                padding: 30px;
                border: 2px solid var(--dark-gold);
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
                backdrop-filter: blur(5px);
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
            }
            
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 35px rgba(255, 215, 0, 0.2);
                border-color: var(--gold);
            }
            
            .card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: linear-gradient(90deg, var(--gold), var(--blood-red));
            }
            
            .card h2 {
                font-family: 'Pirata One', cursive;
                color: var(--gold);
                font-size: 2.2rem;
                margin-bottom: 20px;
                border-bottom: 2px solid rgba(255, 215, 0, 0.3);
                padding-bottom: 10px;
            }
            
            /* Button styles */
            .btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 14px 28px;
                background: linear-gradient(45deg, var(--sea-blue), #1E40AF);
                color: white;
                border: none;
                border-radius: 10px;
                font-family: 'Cinzel', serif;
                font-weight: bold;
                font-size: 1.1rem;
                cursor: pointer;
                transition: all 0.3s ease;
                text-decoration: none;
                margin: 8px;
                min-width: 180px;
                box-shadow: 0 5px 15px rgba(30, 58, 138, 0.4);
            }
            
            .btn:hover {
                transform: translateY(-3px);
                box-shadow: 0 8px 20px rgba(30, 58, 138, 0.6);
                background: linear-gradient(45deg, #1E40AF, #1D4ED8);
            }
            
            .btn-gold {
                background: linear-gradient(45deg, var(--dark-gold), var(--gold));
                box-shadow: 0 5px 15px rgba(184, 134, 11, 0.4);
            }
            
            .btn-gold:hover {
                background: linear-gradient(45deg, var(--gold), #FFED4E);
                box-shadow: 0 8px 20px rgba(255, 215, 0, 0.6);
            }
            
            .btn-red {
                background: linear-gradient(45deg, var(--blood-red), #DC2626);
                box-shadow: 0 5px 15px rgba(139, 0, 0, 0.4);
            }
            
            .btn-red:hover {
                background: linear-gradient(45deg, #DC2626, #EF4444);
                box-shadow: 0 8px 20px rgba(220, 38, 38, 0.6);
            }
            
            /* API Key display */
            .key-display {
                background: rgba(0, 0, 0, 0.5);
                border: 2px dashed var(--gold);
                border-radius: 10px;
                padding: 20px;
                margin: 20px 0;
                font-family: monospace;
                font-size: 1.3rem;
                color: #4ADE80;
                text-align: center;
                letter-spacing: 2px;
                position: relative;
                overflow: hidden;
            }
            
            .key-display::before {
                content: 'SECRET KEY';
                position: absolute;
                top: 5px;
                left: 10px;
                font-size: 0.8rem;
                color: var(--gold);
                opacity: 0.7;
            }
            
            /* Leaderboard */
            .leaderboard {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }
            
            .leaderboard th {
                background: linear-gradient(45deg, var(--sea-blue), var(--deep-blue));
                color: var(--gold);
                padding: 15px;
                text-align: left;
                font-size: 1.1rem;
                border-bottom: 3px solid var(--gold);
            }
            
            .leaderboard td {
                padding: 12px 15px;
                border-bottom: 1px solid rgba(255, 215, 0, 0.2);
            }
            
            .leaderboard tr:hover {
                background: rgba(255, 215, 0, 0.1);
            }
            
            .rank-1 { color: var(--gold); font-weight: bold; }
            .rank-2 { color: #C0C0C0; }
            .rank-3 { color: #CD7F32; }
            
            /* Footer */
            footer {
                text-align: center;
                padding: 30px;
                margin-top: 50px;
                border-top: 2px solid var(--dark-gold);
                color: #87CEEB;
                font-size: 0.9rem;
            }
            
            .goblin-eye {
                display: inline-block;
                width: 40px;
                height: 40px;
                background: radial-gradient(circle, #00FF00, #008800);
                border-radius: 50%;
                margin: 0 10px;
                animation: blink 4s infinite;
                box-shadow: 0 0 20px #00FF00;
                vertical-align: middle;
            }
            
            @keyframes blink {
                0%, 45%, 55%, 100% { transform: scale(1); }
                50% { transform: scale(0.1); }
            }
            
            /* Modal */
            .modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.9);
                z-index: 1000;
                align-items: center;
                justify-content: center;
            }
            
            .modal-content {
                background: linear-gradient(45deg, #0F172A, #1E293B);
                padding: 40px;
                border-radius: 20px;
                border: 3px solid var(--gold);
                max-width: 600px;
                width: 90%;
                position: relative;
                box-shadow: 0 0 50px rgba(255, 215, 0, 0.3);
            }
            
            .close-modal {
                position: absolute;
                top: 15px;
                right: 20px;
                color: var(--gold);
                font-size: 2rem;
                cursor: pointer;
            }
            
            /* Badges and icons */
            .badge {
                display: inline-block;
                padding: 5px 10px;
                border-radius: 12px;
                font-size: 0.8rem;
                font-weight: bold;
                margin: 0 5px;
            }
            
            .badge-legend { background: linear-gradient(45deg, #8B5CF6, #7C3AED); color: white; }
            .badge-veteran { background: linear-gradient(45deg, var(--gold), #F59E0B); color: black; }
            .badge-new { background: linear-gradient(45deg, #10B981, #059669); color: white; }
            
            /* Scrollbar */
            ::-webkit-scrollbar {
                width: 12px;
            }
            
            ::-webkit-scrollbar-track {
                background: rgba(15, 23, 42, 0.8);
            }
            
            ::-webkit-scrollbar-thumb {
                background: linear-gradient(var(--gold), var(--dark-gold));
                border-radius: 6px;
            }
            
            /* Treasure chest animation */
            .treasure-chest {
                position: fixed;
                bottom: 20px;
                left: 20px;
                width: 60px;
                height: 60px;
                background: url('https://cdn-icons-png.flaticon.com/512/3208/3208720.png') no-repeat center;
                background-size: contain;
                cursor: pointer;
                animation: bounce 2s infinite;
                filter: drop-shadow(0 0 10px var(--gold));
                z-index: 100;
            }
            
            @keyframes bounce {
                0%, 100% { transform: translateY(0); }
                50% { transform: translateY(-10px); }
            }
        </style>
    </head>
    <body>
        <!-- Animated ship -->
        <div class="ship"></div>
        
        <!-- Treasure chest -->
        <div class="treasure-chest" onclick="showSurprise()"></div>
        
        <div class="container">
            <header>
                <h1>THE GOBLIN'S REGISTRY</h1>
                <div class="subtitle">Where Pirates Get Their Keys</div>
                <div class="status-badge" id="statusBadge">
                    <span class="goblin-eye"></span>
                    THE GOBLIN IS WATCHING
                    <span class="goblin-eye"></span>
                </div>
            </header>
            
            <div class="main-grid">
                <!-- Left Column -->
                <div class="card">
                    <h2>🔑 KEY MANAGEMENT</h2>
                    <p style="margin-bottom: 20px; line-height: 1.6;">
                        Every pirate needs a key to unlock their destiny. Register with the Discord bot 
                        using <code>/register</code> to get your unique API key. Guard it like treasure!
                    </p>
                    
                    <div style="text-align: center;">
                        <button class="btn btn-gold" onclick="checkMyKey()">
                            🔍 CHECK MY KEY
                        </button>
                        <button class="btn" onclick="generateTestKey()">
                            ⚡ TEST KEY GEN
                        </button>
                        <button class="btn btn-red" onclick="showKeyVault()">
                            🗝️ KEY VAULT
                        </button>
                    </div>
                    
                    <div id="keyResult" style="margin-top: 20px;"></div>
                    
                    <div class="key-display" id="sampleKey" onclick="copyKey(this)">
                        SOT-XXXX-XXXX-XXXX-XXXX
                        <div style="font-size: 0.8rem; color: #94A3B8; margin-top: 10px;">
                            Click to copy | Keep it secret!
                        </div>
                    </div>
                </div>
                
                <!-- Right Column -->
                <div class="card">
                    <h2>🏆 PIRATE LEADERBOARD</h2>
                    <div id="leaderboard">
                        <table class="leaderboard">
                            <thead>
                                <tr>
                                    <th>Rank</th>
                                    <th>Pirate</th>
                                    <th>Title</th>
                                    <th>K/D</th>
                                    <th>Gold</th>
                                </tr>
                            </thead>
                            <tbody id="leaderboardBody">
                                <!-- Filled by JavaScript -->
                            </tbody>
                        </table>
                    </div>
                    <button class="btn" onclick="refreshLeaderboard()" style="margin-top: 15px;">
                        🔄 REFRESH
                    </button>
                </div>
            </div>
            
            <!-- Second Row -->
            <div class="main-grid" style="margin-top: 30px;">
                <!-- Discord Bot Card -->
                <div class="card">
                    <h2>🤖 DISCORD GOBLIN</h2>
                    <p style="margin-bottom: 15px;">
                        Our watchful goblin bot lives in Discord. Invite it to your server 
                        and use these commands:
                    </p>
                    
                    <div style="background: rgba(0, 0, 0, 0.3); padding: 15px; border-radius: 10px; margin: 15px 0;">
                        <code style="color: #60A5FA; display: block; margin: 5px 0;">/ping</code>
                        <small style="color: #94A3B8;">The goblin responds with attitude</small>
                        
                        <code style="color: #60A5FA; display: block; margin: 10px 0;">/register [ingame_name]</code>
                        <small style="color: #94A3B8;">Get your API key</small>
                        
                        <code style="color: #60A5FA; display: block; margin: 10px 0;">/profile</code>
                        <small style="color: #94A3B8;">View your stats and key</small>
                        
                        <code style="color: #60A5FA; display: block; margin: 10px 0;">/shop</code>
                        <small style="color: #94A3B8;">Spend your gold</small>
                    </div>
                    
                    <button class="btn btn-gold" onclick="inviteBot()">
                        🏴‍☠️ INVITE GOBLIN BOT
                    </button>
                    <button class="btn" onclick="testPing()">
                        🏓 TEST /PING
                    </button>
                    
                    <div id="botStatus" style="margin-top: 15px; padding: 10px; background: rgba(0,0,0,0.3); border-radius: 5px;">
                        Bot status: <span id="botStatusText">Checking...</span>
                    </div>
                </div>
                
                <!-- API Documentation -->
                <div class="card">
                    <h2>📜 API DOCS</h2>
                    <p>Use your API key to access these endpoints:</p>
                    
                    <div style="margin: 20px 0;">
                        <div style="background: #1E293B; padding: 12px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #10B981;">
                            <code>GET /api/profile?key=YOUR_KEY</code>
                            <div style="font-size: 0.9rem; color: #94A3B8;">Get your profile data</div>
                        </div>
                        
                        <div style="background: #1E293B; padding: 12px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #F59E0B;">
                            <code>POST /api/match/report</code>
                            <div style="font-size: 0.9rem; color: #94A3B8;">Report match results (requires key)</div>
                        </div>
                        
                        <div style="background: #1E293B; padding: 12px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #8B5CF6;">
                            <code>GET /api/leaderboard</code>
                            <div style="font-size: 0.9rem; color: #94A3B8;">Global leaderboard</div>
                        </div>
                    </div>
                    
                    <button class="btn" onclick="testAPI()">
                        🧪 TEST API
                    </button>
                </div>
            </div>
            
            <!-- Stats Row -->
            <div class="card" style="margin-top: 30px;">
                <h2>📊 LIVE STATISTICS</h2>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 20px;">
                    <div style="text-align: center; padding: 20px; background: rgba(30, 41, 59, 0.5); border-radius: 10px;">
                        <div style="font-size: 2.5rem; color: var(--gold); font-weight: bold;" id="totalPlayers">0</div>
                        <div>Registered Pirates</div>
                    </div>
                    <div style="text-align: center; padding: 20px; background: rgba(30, 41, 59, 0.5); border-radius: 10px;">
                        <div style="font-size: 2.5rem; color: #10B981; font-weight: bold;" id="totalMatches">0</div>
                        <div>Fights Settled</div>
                    </div>
                    <div style="text-align: center; padding: 20px; background: rgba(30, 41, 59, 0.5); border-radius: 10px;">
                        <div style="font-size: 2.5rem; color: #EF4444; font-weight: bold;" id="totalKills">0</div>
                        <div>Total Kills</div>
                    </div>
                    <div style="text-align: center; padding: 20px; background: rgba(30, 41, 59, 0.5); border-radius: 10px;">
                        <div style="font-size: 2.5rem; color: #8B5CF6; font-weight: bold;" id="totalGold">0</div>
                        <div>Gold in Circulation</div>
                    </div>
                </div>
            </div>
            
            <footer>
                <p>⚓ The Goblin's Registry v2.0 | "He watches, he knows, he judges."</p>
                <p style="margin-top: 10px; font-size: 0.8rem; color: #64748B;">
                    This site is protected by ancient pirate magic. Misuse will summon the kraken.
                </p>
                <p style="margin-top: 5px;">
                    <span class="badge badge-legend">LEGEND</span>
                    <span class="badge badge-veteran">VETERAN</span>
                    <span class="badge badge-new">NEW BLOOD</span>
                </p>
            </footer>
        </div>
        
        <!-- Modal -->
        <div class="modal" id="keyModal">
            <div class="modal-content">
                <span class="close-modal" onclick="closeModal()">&times;</span>
                <h2 style="color: var(--gold);">🗝️ SECRET KEY VAULT</h2>
                <div id="modalContent">
                    <p>Loading your treasures...</p>
                </div>
            </div>
        </div>
        
        <script>
            // Initialize
            document.addEventListener('DOMContentLoaded', function() {
                loadStats();
                loadLeaderboard();
                checkBotStatus();
                
                // Add typing effect to sample key
                const keyElement = document.getElementById('sampleKey');
                const realKey = 'SOT-' + Math.random().toString(36).substr(2, 4).toUpperCase() + 
                              '-' + Math.random().toString(36).substr(2, 4).toUpperCase() + 
                              '-' + Math.random().toString(36).substr(2, 4).toUpperCase() + 
                              '-' + Math.random().toString(36).substr(2, 4).toUpperCase();
                
                let i = 0;
                const typeKey = setInterval(() => {
                    if (i <= realKey.length) {
                        keyElement.textContent = realKey.substring(0, i) + 
                            (i < realKey.length ? '|' : '') + 
                            '\nClick to copy | Keep it secret!';
                        i++;
                    } else {
                        clearInterval(typeKey);
                    }
                }, 50);
            });
            
            function loadStats() {
                fetch('/api/stats')
                    .then(r => r.json())
                    .then(data => {
                        document.getElementById('totalPlayers').textContent = data.total_players || '0';
                        document.getElementById('totalMatches').textContent = data.total_matches || '0';
                        document.getElementById('totalKills').textContent = data.total_kills || '0';
                        document.getElementById('totalGold').textContent = (data.total_gold || '0') + 'G';
                    });
            }
            
            function loadLeaderboard() {
                fetch('/api/leaderboard')
                    .then(r => r.json())
                    .then(data => {
                        const tbody = document.getElementById('leaderboardBody');
                        tbody.innerHTML = '';
                        
                        data.players.forEach((player, index) => {
                            const row = document.createElement('tr');
                            row.className = `rank-${index + 1}`;
                            
                            let rankIcon = '⚓';
                            if (index === 0) rankIcon = '👑';
                            if (index === 1) rankIcon = '🥈';
                            if (index === 2) rankIcon = '🥉';
                            
                            const kd = player.total_deaths > 0 ? 
                                (player.total_kills / player.total_deaths).toFixed(2) : 
                                player.total_kills.toFixed(0);
                            
                            row.innerHTML = `
                                <td>${rankIcon} ${index + 1}</td>
                                <td><strong>${player.in_game_name || player.discord_name}</strong></td>
                                <td><span class="badge badge-${player.prestige > 100 ? 'legend' : player.prestige > 50 ? 'veteran' : 'new'}">
                                    ${player.title || 'Deckhand'}
                                </span></td>
                                <td>${kd}</td>
                                <td>${player.credits}G</td>
                            `;
                            tbody.appendChild(row);
                        });
                    });
            }
            
            function checkBotStatus() {
                fetch('/api/bot/status')
                    .then(r => r.json())
                    .then(data => {
                        const statusText = document.getElementById('botStatusText');
                        if (data.active) {
                            statusText.innerHTML = '<span style="color: #10B981;">🟢 ONLINE - Goblin is watching</span>';
                        } else {
                            statusText.innerHTML = '<span style="color: #EF4444;">🔴 OFFLINE - Goblin is sleeping</span>';
                        }
                    });
            }
            
            function checkMyKey() {
                const key = prompt('Enter your API key (or leave blank for demo):');
                if (key === null) return;
                
                if (!key) {
                    // Demo mode
                    document.getElementById('keyResult').innerHTML = `
                        <div style="background: linear-gradient(45deg, #1E293B, #0F172A); padding: 20px; border-radius: 10px; border-left: 4px solid var(--gold);">
                            <h3 style="color: var(--gold); margin-bottom: 10px;">DEMO MODE</h3>
                            <p>In production, this would fetch your profile using your real API key.</p>
                            <p>Get your key from the Discord bot using <code>/register</code></p>
                            <div style="margin-top: 15px;">
                                <button class="btn" onclick="generateTestKey()">Generate Test Key</button>
                            </div>
                        </div>
                    `;
                    return;
                }
                
                fetch('/api/profile?key=' + encodeURIComponent(key))
                    .then(r => r.json())
                    .then(data => {
                        if (data.error) {
                            alert('Invalid key: ' + data.error);
                        } else {
                            document.getElementById('keyResult').innerHTML = `
                                <div style="background: linear-gradient(45deg, #064E3B, #065F46); padding: 20px; border-radius: 10px; border-left: 4px solid #10B981;">
                                    <h3 style="color: #10B981; margin-bottom: 10px;">✅ KEY VALID</h3>
                                    <p>Welcome back, <strong>${data.in_game_name}</strong>!</p>
                                    <p>Title: <span class="badge badge-legend">${data.title}</span></p>
                                    <p>Gold: <strong>${data.credits}G</strong></p>
                                    <p>K/D: <strong>${(data.total_kills / Math.max(data.total_deaths, 1)).toFixed(2)}</strong></p>
                                </div>
                            `;
                        }
                    });
            }
            
            function generateTestKey() {
                const chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
                let key = 'SOT-';
                for (let i = 0; i < 12; i++) {
                    if (i > 0 && i % 4 === 0) key += '-';
                    key += chars[Math.floor(Math.random() * chars.length)];
                }
                
                document.getElementById('keyResult').innerHTML = `
                    <div style="background: linear-gradient(45deg, #7C3AED, #8B5CF6); padding: 20px; border-radius: 10px;">
                        <h3 style="color: white; margin-bottom: 10px;">🎮 TEST KEY GENERATED</h3>
                        <div class="key-display" onclick="copyKey(this)" style="cursor: pointer;">
                            ${key}
                        </div>
                        <p style="margin-top: 10px; color: #94A3B8; font-size: 0.9rem;">
                            ⚠️ This is a demo key. Get your real key from Discord bot.
                        </p>
                    </div>
                `;
            }
            
            function showKeyVault() {
                const modal = document.getElementById('keyModal');
                const content = document.getElementById('modalContent');
                
                content.innerHTML = `
                    <div style="text-align: center;">
                        <div style="font-size: 4rem; margin: 20px;">🗝️🔐</div>
                        <p>The Key Vault is protected by ancient magic.</p>
                        <p>To access your keys, use the Discord bot:</p>
                        <code style="display: block; background: #1E293B; padding: 10px; border-radius: 5px; margin: 15px 0; color: #60A5FA;">
                            /profile
                        </code>
                        <p>This will show your API key in a secure, ephemeral message.</p>
                        <button class="btn btn-gold" onclick="inviteBot()" style="margin-top: 20px;">
                            Get Key from Discord Bot
                        </button>
                    </div>
                `;
                
                modal.style.display = 'flex';
            }
            
            function copyKey(element) {
                const text = element.textContent.split('\n')[0].trim();
                navigator.clipboard.writeText(text);
                
                const original = element.innerHTML;
                element.innerHTML = '✅ COPIED TO CLIPBOARD!';
                element.style.background = 'linear-gradient(45deg, #065F46, #047857)';
                
                setTimeout(() => {
                    element.innerHTML = original;
                    element.style.background = '';
                }, 2000);
            }
            
            function refreshLeaderboard() {
                loadLeaderboard();
                document.getElementById('leaderboardBody').style.opacity = '0.5';
                setTimeout(() => {
                    document.getElementById('leaderboardBody').style.opacity = '1';
                }, 500);
            }
            
            function inviteBot() {
                fetch('/api/bot/invite')
                    .then(r => r.json())
                    .then(data => {
                        if (data.url) {
                            window.open(data.url, '_blank');
                        } else {
                            alert('Bot invite link not available. Set DISCORD_CLIENT_ID in environment.');
                        }
                    });
            }
            
            function testPing() {
                const responses = [
                    "🏓 Pong! Goblin is UP and watching!",
                    "⚡ Still alive, newgen. What do you want?",
                    "👁️ I see you... yes, I'm online.",
                    "⚓ Captain's log: Bot operational. Stop bothering me.",
                    "🎮 Stop pinging and go play some TDM.",
                    "💀 Not dead yet, surprisingly.",
                    "🔫 Pew pew! I'm here. Happy?",
                    "🏴‍☠️ Yar har! The bot sails smoothly!",
                    "🌊 Sea worthy and ready, landlubber.",
                    "💰 Got gold? No? Then stop pinging."
                ];
                
                const response = responses[Math.floor(Math.random() * responses.length)];
                alert(response);
            }
            
            function testAPI() {
                fetch('/api/test')
                    .then(r => r.json())
                    .then(data => {
                        alert(`API Test: ${data.message}\nStatus: ${data.status}`);
                    });
            }
            
            function showSurprise() {
                const surprises = [
                    "🏆 You found hidden treasure! +1000G",
                    "🎭 The goblin winks at you.",
                    "⚔️ A skeleton appears then disappears!",
                    "🗺️ You found a secret map piece!",
                    "💎 Shiny! But it's just fool's gold.",
                    "👻 A ghostly 'Yarrr' echoes...",
                    "🔮 The crystal ball shows your future victories!",
                    "🎪 Circus music plays... then stops.",
                    "🌪️ A sudden storm! Then calm.",
                    "🐙 Tentacles! Just kidding."
                ];
                
                const surprise = surprises[Math.floor(Math.random() * surprises.length)];
                
                document.getElementById('keyResult').innerHTML = `
                    <div style="background: linear-gradient(45deg, #7C2D12, #9A3412); padding: 20px; border-radius: 10px; border: 2px solid var(--gold); animation: pulse 0.5s 3;">
                        <h3 style="color: var(--gold); margin-bottom: 10px;">🎉 SURPRISE!</h3>
                        <p style="font-size: 1.2rem;">${surprise}</p>
                        <div style="font-size: 0.9rem; color: #FBBF24; margin-top: 10px;">
                            The goblin appreciates your curiosity.
                        </div>
                    </div>
                `;
                
                // Make chest bounce
                const chest = document.querySelector('.treasure-chest');
                chest.style.animation = 'none';
                setTimeout(() => {
                    chest.style.animation = 'bounce 2s infinite';
                }, 10);
            }
            
            function closeModal() {
                document.getElementById('keyModal').style.display = 'none';
            }
            
            // Close modal on outside click
            window.onclick = function(event) {
                const modal = document.getElementById('keyModal');
                if (event.target === modal) {
                    closeModal();
                }
            }
        </script>
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
            user_id = data.get('member', {}).get('user', {}).get('id')
            user_name = data.get('member', {}).get('user', {}).get('global_name', 'Unknown')
            
            if command == 'ping':
                # Random ping response
                response = random.choice(ping_responses)
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": response,
                        "flags": 64  # EPHEMERAL
                    }
                })
            
            elif command == 'register':
                options = data.get('data', {}).get('options', [])
                if options and len(options) > 0:
                    in_game_name = options[0].get('value', 'Unknown')
                    
                    conn = get_db_connection()
                    
                    # Check if already registered
                    existing = conn.execute(
                        'SELECT * FROM players WHERE discord_id = ?',
                        (user_id,)
                    ).fetchone()
                    
                    if existing:
                        conn.close()
                        return jsonify({
                            "type": 4,
                            "data": {
                                "content": f"⚓ You're already registered, {in_game_name}!\nUse `/profile` to see your API key.",
                                "flags": 64
                            }
                        })
                    
                    # Generate API key
                    api_key = generate_api_key(user_id, user_name)
                    
                    # Register new player
                    conn.execute('''
                        INSERT INTO players 
                        (discord_id, discord_name, in_game_name, api_key, credits)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, user_name, in_game_name, api_key, 1000))
                    
                    conn.commit()
                    conn.close()
                    
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": (
                                f"🎉 **Welcome aboard, {in_game_name}!**\n\n"
                                f"**Your API Key:** `{api_key}`\n"
                                f"**Keep this secret!** Use it to access the web API.\n\n"
                                f"🔗 Visit: {request.host_url}\n"
                                f"📊 Use `/profile` to see your stats\n"
                                f"💰 Start with: **1000G**\n\n"
                                f"⚓ *The goblin is now watching you...*"
                            ),
                            "flags": 64  # EPHEMERAL - only user can see
                        }
                    })
            
            elif command == 'profile':
                conn = get_db_connection()
                player = conn.execute(
                    'SELECT * FROM players WHERE discord_id = ?',
                    (user_id,)
                ).fetchone()
                conn.close()
                
                if not player:
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": "❌ You're not registered! Use `/register [ingame_name]` first.",
                            "flags": 64
                        }
                    })
                
                kd = player['total_deaths'] > 0 and player['total_kills'] / player['total_deaths'] or player['total_kills']
                win_rate = (player['wins'] + player['losses']) > 0 and (player['wins'] / (player['wins'] + player['losses']) * 100) or 0
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": (
                            f"🏴‍☠️ **{player['in_game_name']}'s Profile**\n\n"
                            f"**Title:** {player['title']}\n"
                            f"**Prestige:** {player['prestige']}\n"
                            f"**Gold:** {player['credits']}G\n\n"
                            f"📊 **Stats:**\n"
                            f"• Kills: {player['total_kills']}\n"
                            f"• Deaths: {player['total_deaths']}\n"
                            f"• K/D: {kd:.2f}\n"
                            f"• Wins: {player['wins']}\n"
                            f"• Losses: {player['losses']}\n"
                            f"• Win Rate: {win_rate:.1f}%\n\n"
                            f"🔑 **API Key:**\n`{player['api_key']}`\n\n"
                            f"🔗 **Web Dashboard:**\n{request.host_url}\n\n"
                            f"*Use your key wisely, pirate.*"
                        ),
                        "flags": 64
                    }
                })
            
            elif command == 'leaderboard':
                conn = get_db_connection()
                players = conn.execute('''
                    SELECT in_game_name, title, total_kills, total_deaths, credits, prestige
                    FROM players 
                    WHERE status = 'active'
                    ORDER BY total_kills DESC, prestige DESC
                    LIMIT 10
                ''').fetchall()
                conn.close()
                
                leaderboard_text = "🏆 **TOP PIRATES** 🏆\n\n"
                for i, player in enumerate(players):
                    kd = player['total_deaths'] > 0 and player['total_kills'] / player['total_deaths'] or player['total_kills']
                    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][i] if i < 10 else f"{i+1}."
                    leaderboard_text += f"{medal} **{player['in_game_name']}** - {player['title']}\n"
                    leaderboard_text += f"   K/D: {kd:.2f} | Gold: {player['credits']}G\n\n"
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": leaderboard_text,
                        "flags": 0
                    }
                })
            
            elif command == 'shop':
                conn = get_db_connection()
                items = conn.execute('''
                    SELECT name, description, price, rarity
                    FROM shop_items 
                    WHERE available = 1
                    ORDER BY price ASC
                ''').fetchall()
                conn.close()
                
                shop_text = "🏪 **THE GOblIN'S MARKET** 🏪\n\n"
                for item in items:
                    price_color = {
                        'common': '🟢',
                        'rare': '🔵', 
                        'epic': '🟣',
                        'legendary': '🟠'
                    }.get(item['rarity'], '⚪')
                    
                    shop_text += f"{price_color} **{item['name']}**\n"
                    shop_text += f"   {item['description']}\n"
                    shop_text += f"   Price: **{item['price']}G**\n\n"
                
                shop_text += f"Use `/buy [item_name]` to purchase!\n"
                shop_text += f"Check your gold with `/profile`"
                
                return jsonify({
                    "type": 4,
                    "data": {
                        "content": shop_text,
                        "flags": 0
                    }
                })
            
            elif command == 'buy':
                options = data.get('data', {}).get('options', [])
                if options and len(options) > 0:
                    item_name = options[0].get('value', '')
                    
                    conn = get_db_connection()
                    
                    # Get player
                    player = conn.execute(
                        'SELECT * FROM players WHERE discord_id = ?',
                        (user_id,)
                    ).fetchone()
                    
                    if not player:
                        conn.close()
                        return jsonify({
                            "type": 4,
                            "data": {
                                "content": "❌ You need to register first! Use `/register`",
                                "flags": 64
                            }
                        })
                    
                    # Get item
                    item = conn.execute(
                        'SELECT * FROM shop_items WHERE name = ? AND available = 1',
                        (item_name,)
                    ).fetchone()
                    
                    if not item:
                        conn.close()
                        return jsonify({
                            "type": 4,
                            "data": {
                                "content": f"❌ Item '{item_name}' not found! Check `/shop`",
                                "flags": 64
                            }
                        })
                    
                    # Check if player has enough gold
                    if player['credits'] < item['price']:
                        conn.close()
                        return jsonify({
                            "type": 4,
                            "data": {
                                "content": f"❌ Not enough gold! You have {player['credits']}G, need {item['price']}G",
                                "flags": 64
                            }
                        })
                    
                    # Process purchase
                    new_credits = player['credits'] - item['price']
                    
                    # Update player credits
                    conn.execute(
                        'UPDATE players SET credits = ? WHERE id = ?',
                        (new_credits, player['id'])
                    )
                    
                    # Handle item type
                    if item['item_type'] == 'title':
                        conn.execute(
                            'UPDATE players SET title = ? WHERE id = ?',
                            (item['name'], player['id'])
                        )
                        message = f"🎉 You are now known as **{item['name']}**!"
                    else:
                        message = f"🎁 Purchased **{item['name']}**! Check your inventory."
                    
                    conn.commit()
                    conn.close()
                    
                    return jsonify({
                        "type": 4,
                        "data": {
                            "content": (
                                f"✅ Purchase successful!\n\n"
                                f"{message}\n"
                                f"Remaining gold: **{new_credits}G**\n\n"
                                f"*The goblin happily takes your gold.*"
                            ),
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
                "content": f"⚓ Yarrr! There be an error: {str(e)[:100]}",
                "flags": 64
            }
        }), 500

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/profile')
def api_profile():
    """Get profile using API key"""
    api_key = request.args.get('key')
    if not api_key:
        return jsonify({"error": "API key required"}), 401
    
    player = validate_api_key(api_key)
    if not player:
        return jsonify({"error": "Invalid API key"}), 401
    
    return jsonify(dict(player))

@app.route('/api/stats')
def api_stats():
    """Get global statistics"""
    conn = get_db_connection()
    
    total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
    total_matches = conn.execute('SELECT COUNT(*) as count FROM matches').fetchone()['count']
    total_kills = conn.execute('SELECT SUM(total_kills) as sum FROM players').fetchone()['sum'] or 0
    total_gold = conn.execute('SELECT SUM(credits) as sum FROM players').fetchone()['sum'] or 0
    
    conn.close()
    
    return jsonify({
        "total_players": total_players,
        "total_matches": total_matches,
        "total_kills": total_kills,
        "total_gold": total_gold,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/leaderboard')
def api_leaderboard():
    """Get leaderboard"""
    conn = get_db_connection()
    players = conn.execute('''
        SELECT discord_name, in_game_name, title, total_kills, total_deaths, credits, prestige
        FROM players 
        WHERE status = 'active'
        ORDER BY total_kills DESC, prestige DESC
        LIMIT 20
    ''').fetchall()
    conn.close()
    
    return jsonify({
        "players": [dict(p) for p in players],
        "updated": datetime.utcnow().isoformat()
    })

@app.route('/api/bot/status')
def api_bot_status():
    """Get bot status"""
    return jsonify({
        "active": bot_active,
        "bot_info": bot_info,
        "interactions_url": f"{request.host_url}interactions",
        "web_interface": request.host_url
    })

@app.route('/api/bot/invite')
def api_bot_invite():
    """Get bot invite link"""
    invite_url = create_invite_link()
    return jsonify({
        "url": invite_url,
        "client_id": DISCORD_CLIENT_ID
    })

@app.route('/api/test')
def api_test():
    """Test endpoint"""
    return jsonify({
        "status": "operational",
        "message": "The Goblin's Registry API is working!",
        "timestamp": datetime.utcnow().isoformat(),
        "goblin_says": random.choice(ping_responses)
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "service": "SoT Goblin Registry",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "goblin_watching": bot_active
    })

# =============================================================================
# STARTUP
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print(f"\n{'='*70}")
    print("🏴‍☠️  THE GOBLIN'S REGISTRY - Enhanced Edition")
    print(f"{'='*70}")
    
    # Test Discord connection
    if test_discord_token():
        print(f"✅ Discord goblin connected: {bot_info.get('username', 'Unknown')}")
        
        # Register commands
        if register_commands():
            print("✅ Slash commands registered with Discord")
        else:
            print("⚠️ Could not register commands")
    else:
        print("❌ Discord goblin NOT connected")
        print("   Set DISCORD_TOKEN, DISCORD_CLIENT_ID in environment")
    
    # Show invite link
    invite_link = create_invite_link()
    if invite_link:
        print(f"\n🔗 Invite the goblin to your server:")
        print(f"   {invite_link}")
    
    print(f"\n🌐 Web Interface: http://localhost:{port}")
    print(f"🤖 Interactions: http://localhost:{port}/interactions")
    print(f"📊 Health Check: http://localhost:{port}/health")
    
    print(f"\n🎮 Available Discord Commands:")
    print(f"   /ping       - Check if the goblin is watching")
    print(f"   /register   - Get your API key")
    print(f"   /profile    - View your profile and key")
    print(f"   /leaderboard- See top pirates")
    print(f"   /shop       - Browse items")
    print(f"   /buy        - Purchase items")
    
    print(f"\n⚓ The goblin is watching...")
    print(f"{'='*70}\n")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=port, debug=False)# app.py - COMPLETE DISCORD BOT WITH WEB SERVER
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

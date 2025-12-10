# database.py - Database setup and management
import sqlite3
from config import DATABASE, logger
import threading
from datetime import datetime

# Thread-local storage for database connections
local_storage = threading.local()

def get_db_connection():
    """Get database connection with thread safety"""
    if not hasattr(local_storage, 'conn'):
        local_storage.conn = sqlite3.connect(DATABASE)
        local_storage.conn.row_factory = sqlite3.Row
    return local_storage.conn

def close_db_connection():
    """Close database connection for current thread"""
    if hasattr(local_storage, 'conn'):
        local_storage.conn.close()
        delattr(local_storage, 'conn')

def init_db():
    """Initialize database tables"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE,
                discord_name TEXT,
                discord_avatar TEXT,
                in_game_name TEXT,
                api_key TEXT UNIQUE CHECK(LENGTH(api_key) = 24),
                server_id TEXT,
                key_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                total_kills INTEGER DEFAULT 0,
                total_deaths INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                prestige INTEGER DEFAULT 0,
                is_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tickets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE,
                discord_id TEXT,
                discord_name TEXT,
                issue TEXT,
                category TEXT DEFAULT 'Other',
                channel_id TEXT,
                status TEXT DEFAULT 'open',
                assigned_to TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            )
        ''')
        
        # Matches table for score tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT UNIQUE,
                team1_players TEXT,
                team2_players TEXT,
                team1_score INTEGER DEFAULT 0,
                team2_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'ongoing',
                winner TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP
            )
        ''')
        
        # Player stats per match
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT,
                player_id TEXT,
                player_name TEXT,
                team INTEGER,
                kills INTEGER DEFAULT 0,
                deaths INTEGER DEFAULT 0,
                assists INTEGER DEFAULT 0
            )
        ''')
        
        # Admin channels table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE,
                guild_id TEXT,
                created_by_id TEXT,
                created_by_name TEXT,
                channel_type TEXT DEFAULT 'admin-chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False

def validate_api_key(api_key):
    """Validate API key with proper format and length checking"""
    from config import logger
    import re
    
    if not api_key:
        return None
    
    api_key = api_key.strip().upper()
    pattern = r'^GOB-[A-Z0-9]{20}$'
    
    if not re.match(pattern, api_key):
        return None
    
    try:
        conn = get_db_connection()
        player = conn.execute(
            'SELECT * FROM players WHERE api_key = ?',
            (api_key,)
        ).fetchone()
        
        if player:
            conn.execute(
                'UPDATE players SET last_used = CURRENT_TIMESTAMP WHERE id = ?',
                (player['id'],)
            )
            conn.commit()
            
            player_dict = {key: player[key] for key in player.keys()}
            logger.info(f"API key validated for user: {player_dict.get('in_game_name')}")
            return player_dict
        return None
        
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        return None

def fix_existing_keys():
    """Fix existing keys to correct format"""
    from config import generate_secure_key, logger
    
    try:
        conn = get_db_connection()
        players = conn.execute('SELECT id, api_key FROM players').fetchall()
        
        fixed_count = 0
        for player in players:
            old_key = player['api_key']
            if old_key and (not old_key.startswith('GOB-') or len(old_key) != 24):
                new_key = generate_secure_key()
                conn.execute('UPDATE players SET api_key = ? WHERE id = ?', 
                           (new_key, player['id']))
                fixed_count += 1
        
        if fixed_count > 0:
            conn.commit()
            logger.info(f"Fixed {fixed_count} API keys")
        
        return fixed_count
        
    except Exception as e:
        logger.error(f"Error fixing keys: {e}")
        return 0

def get_global_stats():
    """Get global statistics"""
    try:
        conn = get_db_connection()
        
        total_players = conn.execute('SELECT COUNT(*) as count FROM players').fetchone()['count']
        total_kills = conn.execute('SELECT SUM(total_kills) as sum FROM players').fetchone()['sum'] or 0
        total_deaths = conn.execute('SELECT SUM(total_deaths) as sum FROM players').fetchone()['sum'] or 1
        total_wins = conn.execute('SELECT SUM(wins) as sum FROM players').fetchone()['sum'] or 0
        total_losses = conn.execute('SELECT SUM(losses) as sum FROM players').fetchone()['sum'] or 0
        
        conn.close()
        
        return {
            'total_players': total_players,
            'total_kills': total_kills,
            'total_deaths': total_deaths,
            'total_wins': total_wins,
            'total_losses': total_losses,
            'total_games': total_wins + total_losses,
            'avg_kd': total_kills / total_deaths if total_deaths > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting global stats: {e}")
        return {
            'total_players': 0,
            'total_kills': 0,
            'total_deaths': 1,
            'total_wins': 0,
            'total_losses': 0,
            'total_games': 0,
            'avg_kd': 0
        }

def get_leaderboard(limit=10):
    """Get leaderboard data"""
    try:
        conn = get_db_connection()
        
        top_players = conn.execute('''
            SELECT discord_name, in_game_name, total_kills, total_deaths, 
                   CAST(total_kills AS FLOAT) / MAX(total_deaths, 1) as kd_ratio,
                   wins, losses, prestige, api_key
            FROM players 
            WHERE total_kills >= 1
            ORDER BY kd_ratio DESC, total_kills DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        
        conn.close()
        
        leaderboard = []
        for i, player in enumerate(top_players, 1):
            leaderboard.append({
                "rank": i,
                "name": player['in_game_name'] or player['discord_name'],
                "kills": player['total_kills'],
                "deaths": player['total_deaths'],
                "kd": round(player['kd_ratio'], 2),
                "wins": player['wins'],
                "losses": player['losses'],
                "prestige": player['prestige'],
                "api_key": player['api_key']
            })
        
        return leaderboard
        
    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}")
        return []
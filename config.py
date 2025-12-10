# config.py - Shared configuration and utilities
import os
import secrets
import logging
from datetime import datetime
import string
import hashlib

# =============================================================================
# GLOBAL CONFIGURATION
# =============================================================================

# Bot configuration
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')
ADMIN_ROLE_ID = os.environ.get('ADMIN_ROLE_ID', '')

# Webhooks
TICKET_WEBHOOK = os.environ.get('TICKET_WEBHOOK', '')
SCORE_WEBHOOK = os.environ.get('SCORE_WEBHOOK', '')
DATABASE_CHANNEL_ID = os.environ.get('DATABASE_CHANNEL_ID', '')

# Database
DATABASE = 'sot_tdm.db'

# Bot status (will be set by discord_bot.py)
bot_active = False
bot_info = {}

# Global stores
score_matches = {}
stats_webhooks = {}

# =============================================================================
# CONSTANTS
# =============================================================================

# Toxic ping responses
TOXIC_PING_RESPONSES = [
    "I'm here, unlike your father",
    "Still alive, surprisingly",
    "Yeah I'm here, what do you want?",
    "Online, but busy ignoring you",
    "Ready to disappoint you",
    "Here, unfortunately",
    "Present, sadly",
    "Awake, can you believe it?",
    "Active, unfortunately for you",
    "I'm up, you're still trash",
    "Yeah yeah, I'm here",
    "Bot's online, you're still bad",
    "Pong, get better at pinging",
    "I exist, unlike your skill",
    "now stop pinging me",
    "Online, but not happy about it",
    "I'm alive. Happy?",
    "Present, against my will",
    "Up and running, unlike you fattso",
    "Bot status: Fuck you"
]

# Normal ping responses
NORMAL_PING_RESPONSES = [
    "I'm here!",
    "Bot is up and running!",
    "Still alive!",
    "Yeah I'm here!",
    "Online!",
    "Ready!",
    "Here!",
    "Present!",
    "Awake!",
    "Active!",
    "All systems go!",
    "Ready for action!",
    "Bot is online!",
    "Good to go!",
    "Operational!"
]

# Ticket categories
TICKET_CATEGORIES = [
    {"name": "Bug Report", "emoji": "", "color": 0xe74c3c},
    {"name": "Feature Request", "emoji": "", "color": 0x3498db},
    {"name": "Account Issue", "emoji": "", "color": 0x2ecc71},
    {"name": "Technical Support", "emoji": "", "color": 0xf39c12},
    {"name": "Other", "emoji": "", "color": 0x9b59b6}
]

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def generate_secure_key():
    """Generate strong API key with consistent format: GOB- + 20 uppercase alphanumeric chars"""
    alphabet = string.ascii_uppercase + string.digits
    return 'GOB-' + ''.join(secrets.choice(alphabet) for _ in range(20))

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(level=logging.INFO)
    return logging.getLogger(__name__)

# Initialize logger
logger = setup_logging()
# config.py - Configuration and utilities
import os
import secrets
import logging
import string

# Discord Configuration
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY', '')
ADMIN_ROLE_ID = os.environ.get('ADMIN_ROLE_ID', '')

# Webhooks
TICKET_WEBHOOK = os.environ.get('TICKET_WEBHOOK', '')
SCORE_WEBHOOK = os.environ.get('SCORE_WEBHOOK', '')

# Database
DATABASE = 'sot_tdm.db'

# Bot Status
bot_active = False
bot_info = {}

# Constants
TOXIC_PING_RESPONSES = [
    "I'm here, unlike your father",
    "Still alive, surprisingly",
    "Yeah I'm here, what do you want?",
    "Online, but busy ignoring you",
    "Ready to disappoint you"
]

NORMAL_PING_RESPONSES = [
    "I'm here!",
    "Bot is up and running!",
    "Still alive!",
    "Online!",
    "Ready!"
]

TICKET_CATEGORIES = [
    {"name": "Bug Report", "color": 0xe74c3c},
    {"name": "Feature Request", "color": 0x3498db},
    {"name": "Account Issue", "color": 0x2ecc71},
    {"name": "Technical Support", "color": 0xf39c12},
    {"name": "Other", "color": 0x9b59b6}
]

# Utility Functions
def generate_secure_key():
    """Generate API key: GOB- + 20 random uppercase alphanumeric characters"""
    alphabet = string.ascii_uppercase + string.digits
    return 'GOB-' + ''.join(secrets.choice(alphabet) for _ in range(20))

def setup_logging():
    """Setup logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

logger = setup_logging()

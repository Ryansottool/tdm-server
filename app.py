# app.py - Main Flask web server with DARK THEME
import os
import json
import random
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, session, redirect, url_for, make_response
from flask_cors import CORS
from config import logger, bot_active, generate_secure_key, TICKET_CATEGORIES
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
    data = request.get_json()
    response = handle_interaction(data)
    return jsonify(response)

# =============================================================================
# WEB INTERFACE - DARK THEME ENHANCED
# =============================================================================

@app.route('/')
def home():
    """Home page - Goblin Hut - ULTRA DARK THEME"""
    if 'user_key' in session:
        user_data = validate_api_key(session['user_key'])
        if user_data:
            session['user_data'] = user_data
            return redirect(url_for('dashboard'))
    
    stats = get_global_stats()
    
    return f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Goblin Hut - Dark Realm</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Exo+2:wght@300;400;500;600;700&family=Source+Code+Pro:wght@300;400;500&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {{
                /* Deep Dark Cyberpunk Theme */
                --void-black: #0a0a0f;
                --abyss-black: #12121a;
                --midnight: #1a1a2e;
                --nebula: #16213e;
                --stardust: #0f3460;
                --cyber-purple: #9d00ff;
                --neon-purple: #b300ff;
                --matrix-green: #00ff9d;
                --cyber-green: #00cc7a;
                --cyber-pink: #ff00ff;
                --electric-blue: #00d4ff;
                --plasma: #ff6b6b;
                --hologram: #e0d6ff;
                --hologram-dim: #a099cc;
                
                /* Glow Effects */
                --glow-purple: 0 0 30px rgba(157, 0, 255, 0.7);
                --glow-green: 0 0 30px rgba(0, 255, 157, 0.7);
                --glow-blue: 0 0 30px rgba(0, 212, 255, 0.7);
                --glow-pink: 0 0 30px rgba(255, 0, 255, 0.7);
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Exo 2', sans-serif;
                background: linear-gradient(135deg, var(--void-black) 0%, var(--abyss-black) 50%, var(--midnight) 100%);
                color: var(--hologram);
                min-height: 100vh;
                overflow-x: hidden;
                position: relative;
                line-height: 1.6;
            }}
            
            /* Matrix-style background particles */
            #particles-js {{
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                z-index: 0;
                opacity: 0.3;
            }}
            
            /* Grid lines overlay */
            .grid-overlay {{
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                background-image: 
                    linear-gradient(rgba(157, 0, 255, 0.05) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(157, 0, 255, 0.05) 1px, transparent 1px);
                background-size: 50px 50px;
                z-index: 1;
                pointer-events: none;
            }}
            
            /* Animated scan line */
            .scan-line {{
                position: fixed;
                width: 100%;
                height: 2px;
                background: linear-gradient(90deg, transparent, var(--matrix-green), transparent);
                top: 50%;
                left: 0;
                z-index: 2;
                opacity: 0.3;
                animation: scan 4s linear infinite;
                filter: blur(1px);
            }}
            
            @keyframes scan {{
                0% {{ top: 0%; opacity: 0; }}
                5% {{ opacity: 1; }}
                95% {{ opacity: 1; }}
                100% {{ top: 100%; opacity: 0; }}
            }}
            
            .glitch-text {{
                position: relative;
                font-family: 'Orbitron', sans-serif;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
            
            .glitch-text::before,
            .glitch-text::after {{
                content: attr(data-text);
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                clip: rect(0, 900px, 0, 0);
            }}
            
            .glitch-text::before {{
                left: 2px;
                text-shadow: -2px 0 var(--cyber-pink);
                animation: glitch-1 2s infinite linear alternate-reverse;
            }}
            
            .glitch-text::after {{
                left: -2px;
                text-shadow: -2px 0 var(--electric-blue);
                animation: glitch-2 3s infinite linear alternate-reverse;
            }}
            
            @keyframes glitch-1 {{
                0% {{ clip: rect(42px, 9999px, 44px, 0); }}
                5% {{ clip: rect(12px, 9999px, 59px, 0); }}
                10% {{ clip: rect(48px, 9999px, 29px, 0); }}
                15% {{ clip: rect(42px, 9999px, 73px, 0); }}
                20% {{ clip: rect(63px, 9999px, 27px, 0); }}
                25% {{ clip: rect(34px, 9999px, 55px, 0); }}
                30% {{ clip: rect(86px, 9999px, 73px, 0); }}
                35% {{ clip: rect(20px, 9999px, 20px, 0); }}
                40% {{ clip: rect(26px, 9999px, 60px, 0); }}
                45% {{ clip: rect(25px, 9999px, 66px, 0); }}
                50% {{ clip: rect(57px, 9999px, 98px, 0); }}
                55% {{ clip: rect(5px, 9999px, 46px, 0); }}
                60% {{ clip: rect(82px, 9999px, 31px, 0); }}
                65% {{ clip: rect(54px, 9999px, 27px, 0); }}
                70% {{ clip: rect(28px, 9999px, 99px, 0); }}
                75% {{ clip: rect(45px, 9999px, 69px, 0); }}
                80% {{ clip: rect(23px, 9999px, 85px, 0); }}
                85% {{ clip: rect(54px, 9999px, 84px, 0); }}
                90% {{ clip: rect(45px, 9999px, 47px, 0); }}
                95% {{ clip: rect(37px, 9999px, 20px, 0); }}
                100% {{ clip: rect(4px, 9999px, 91px, 0); }}
            }}
            
            @keyframes glitch-2 {{
                0% {{ clip: rect(65px, 9999px, 100px, 0); }}
                5% {{ clip: rect(52px, 9999px, 74px, 0); }}
                10% {{ clip: rect(79px, 9999px, 85px, 0); }}
                15% {{ clip: rect(75px, 9999px, 5px, 0); }}
                20% {{ clip: rect(67px, 9999px, 61px, 0); }}
                25% {{ clip: rect(14px, 9999px, 79px, 0); }}
                30% {{ clip: rect(1px, 9999px, 66px, 0); }}
                35% {{ clip: rect(86px, 9999px, 30px, 0); }}
                40% {{ clip: rect(23px, 9999px, 98px, 0); }}
                45% {{ clip: rect(85px, 9999px, 72px, 0); }}
                50% {{ clip: rect(71px, 9999px, 75px, 0); }}
                55% {{ clip: rect(2px, 9999px, 48px, 0); }}
                60% {{ clip: rect(30px, 9999px, 16px, 0); }}
                65% {{ clip: rect(59px, 9999px, 50px, 0); }}
                70% {{ clip: rect(41px, 9999px, 62px, 0); }}
                75% {{ clip: rect(2px, 9999px, 82px, 0); }}
                80% {{ clip: rect(47px, 9999px, 73px, 0); }}
                85% {{ clip: rect(3px, 9999px, 27px, 0); }}
                90% {{ clip: rect(40px, 9999px, 86px, 0); }}
                95% {{ clip: rect(45px, 9999px, 72px, 0); }}
                100% {{ clip: rect(23px, 9999px, 49px, 0); }}
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 30px;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 40px;
                position: relative;
                z-index: 3;
            }}
            
            @media (max-width: 1100px) {{
                .container {{
                    grid-template-columns: 1fr;
                    max-width: 600px;
                }}
            }}
            
            /* HEADER SECTION */
            .header-section {{
                animation: fadeInUp 1s ease-out;
            }}
            
            .logo-container {{
                margin-bottom: 40px;
                position: relative;
                overflow: hidden;
                border-radius: 20px;
                padding: 30px;
                background: linear-gradient(145deg, rgba(26, 26, 46, 0.8), rgba(10, 10, 15, 0.9));
                border: 1px solid rgba(157, 0, 255, 0.3);
                box-shadow: var(--glow-purple), inset 0 0 30px rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(20px);
            }}
            
            .logo {{
                font-family: 'Orbitron', sans-serif;
                font-size: 4.5rem;
                font-weight: 900;
                background: linear-gradient(45deg, var(--cyber-purple), var(--cyber-pink), var(--electric-blue));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                text-align: center;
                letter-spacing: 3px;
                text-shadow: 0 0 30px rgba(157, 0, 255, 0.5);
                position: relative;
                margin-bottom: 15px;
            }}
            
            .logo::after {{
                content: '';
                position: absolute;
                bottom: -10px;
                left: 25%;
                width: 50%;
                height: 3px;
                background: linear-gradient(90deg, transparent, var(--matrix-green), transparent);
                filter: blur(2px);
            }}
            
            .subtitle {{
                font-size: 1.4rem;
                text-align: center;
                color: var(--hologram-dim);
                font-weight: 300;
                letter-spacing: 1px;
                margin-bottom: 20px;
                font-family: 'Source Code Pro', monospace;
            }}
            
            .tagline {{
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-top: 20px;
                flex-wrap: wrap;
            }}
            
            .tag {{
                padding: 8px 20px;
                background: rgba(0, 255, 157, 0.1);
                border: 1px solid rgba(0, 255, 157, 0.3);
                border-radius: 30px;
                font-size: 0.9rem;
                color: var(--matrix-green);
                font-weight: 500;
                backdrop-filter: blur(10px);
                transition: all 0.3s;
            }}
            
            .tag:hover {{
                background: rgba(0, 255, 157, 0.2);
                transform: translateY(-3px);
                box-shadow: var(--glow-green);
            }}
            
            /* LOGIN SECTION */
            .login-container {{
                background: linear-gradient(145deg, rgba(26, 26, 46, 0.9), rgba(18, 18, 26, 0.95));
                border-radius: 25px;
                padding: 40px;
                border: 1px solid rgba(157, 0, 255, 0.4);
                box-shadow: var(--glow-purple), inset 0 0 40px rgba(0, 0, 0, 0.6);
                backdrop-filter: blur(25px);
                animation: slideUp 0.8s ease-out 0.2s both;
                position: relative;
                overflow: hidden;
            }}
            
            .login-container::before {{
                content: '';
                position: absolute;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: conic-gradient(
                    transparent, 
                    rgba(157, 0, 255, 0.1), 
                    transparent 30%
                );
                animation: rotate 10s linear infinite;
                z-index: -1;
            }}
            
            @keyframes rotate {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            
            .login-title {{
                font-family: 'Orbitron', sans-serif;
                font-size: 1.8rem;
                color: var(--matrix-green);
                margin-bottom: 30px;
                text-align: center;
                letter-spacing: 2px;
                text-shadow: 0 0 15px rgba(0, 255, 157, 0.5);
            }}
            
            .key-input-group {{
                position: relative;
                margin-bottom: 30px;
            }}
            
            .key-input {{
                width: 100%;
                padding: 20px 20px 20px 50px;
                background: rgba(10, 10, 15, 0.8);
                border: 2px solid rgba(157, 0, 255, 0.5);
                border-radius: 15px;
                color: var(--hologram);
                font-size: 1.1rem;
                font-family: 'Source Code Pro', monospace;
                letter-spacing: 1px;
                transition: all 0.3s;
                backdrop-filter: blur(10px);
            }}
            
            .key-input:focus {{
                outline: none;
                border-color: var(--matrix-green);
                box-shadow: var(--glow-green);
                transform: translateY(-2px);
            }}
            
            .key-input::placeholder {{
                color: rgba(160, 153, 204, 0.5);
                font-weight: 300;
            }}
            
            .input-icon {{
                position: absolute;
                left: 20px;
                top: 50%;
                transform: translateY(-50%);
                color: var(--cyber-purple);
                font-size: 1.2rem;
            }}
            
            .login-btn {{
                width: 100%;
                padding: 20px;
                background: linear-gradient(45deg, var(--cyber-purple), var(--neon-purple));
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 1.2rem;
                font-weight: 700;
                font-family: 'Orbitron', sans-serif;
                letter-spacing: 2px;
                cursor: pointer;
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(157, 0, 255, 0.4);
                margin-bottom: 20px;
            }}
            
            .login-btn:hover {{
                transform: translateY(-5px);
                box-shadow: 0 15px 40px rgba(157, 0, 255, 0.6);
                background: linear-gradient(45deg, var(--neon-purple), var(--cyber-pink));
            }}
            
            .login-btn:active {{
                transform: translateY(-2px);
            }}
            
            .login-btn::after {{
                content: '';
                position: absolute;
                top: -50%;
                left: -60%;
                width: 40%;
                height: 200%;
                background: rgba(255, 255, 255, 0.1);
                transform: rotate(30deg);
                transition: all 0.5s;
            }}
            
            .login-btn:hover::after {{
                left: 120%;
            }}
            
            .error-box {{
                background: rgba(255, 107, 107, 0.1);
                border: 1px solid rgba(255, 107, 107, 0.3);
                border-radius: 12px;
                padding: 20px;
                margin-top: 20px;
                color: var(--plasma);
                display: none;
                animation: shake 0.5s;
                backdrop-filter: blur(10px);
                font-family: 'Source Code Pro', monospace;
            }}
            
            @keyframes shake {{
                0%, 100% {{ transform: translateX(0); }}
                25% {{ transform: translateX(-10px); }}
                75% {{ transform: translateX(10px); }}
            }}
            
            /* INFO BOX */
            .info-container {{
                background: linear-gradient(145deg, rgba(26, 26, 46, 0.9), rgba(18, 18, 26, 0.95));
                border-radius: 25px;
                padding: 35px;
                border: 1px solid rgba(0, 212, 255, 0.4);
                box-shadow: var(--glow-blue), inset 0 0 40px rgba(0, 0, 0, 0.6);
                backdrop-filter: blur(25px);
                margin-top: 40px;
                animation: fadeIn 1s ease-out 0.4s both;
            }}
            
            .info-title {{
                font-family: 'Orbitron', sans-serif;
                font-size: 1.6rem;
                color: var(--electric-blue);
                margin-bottom: 25px;
                display: flex;
                align-items: center;
                gap: 15px;
            }}
            
            .info-title i {{
                font-size: 1.8rem;
            }}
            
            .info-steps {{
                display: flex;
                flex-direction: column;
                gap: 20px;
            }}
            
            .info-step {{
                display: flex;
                align-items: center;
                gap: 15px;
                padding: 15px;
                background: rgba(10, 10, 15, 0.6);
                border-radius: 12px;
                border-left: 4px solid var(--cyber-purple);
                transition: all 0.3s;
            }}
            
            .info-step:hover {{
                background: rgba(157, 0, 255, 0.1);
                transform: translateX(5px);
                border-left-color: var(--matrix-green);
            }}
            
            .step-number {{
                width: 36px;
                height: 36px;
                background: linear-gradient(45deg, var(--cyber-purple), var(--neon-purple));
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-family: 'Orbitron', sans-serif;
                font-size: 1.1rem;
                flex-shrink: 0;
            }}
            
            .step-text {{
                flex-grow: 1;
                color: var(--hologram-dim);
                font-size: 1rem;
            }}
            
            .step-text code {{
                background: rgba(0, 0, 0, 0.6);
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid rgba(157, 0, 255, 0.3);
                font-family: 'Source Code Pro', monospace;
                color: var(--cyber-purple);
                margin: 0 5px;
            }}
            
            /* STATS SECTION */
            .stats-section {{
                animation: fadeInRight 1s ease-out;
            }}
            
            .stats-container {{
                background: linear-gradient(145deg, rgba(26, 26, 46, 0.9), rgba(18, 18, 26, 0.95));
                border-radius: 25px;
                padding: 40px;
                border: 1px solid rgba(255, 0, 255, 0.4);
                box-shadow: var(--glow-pink), inset 0 0 40px rgba(0, 0, 0, 0.6);
                backdrop-filter: blur(25px);
                height: fit-content;
            }}
            
            .stats-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 35px;
                padding-bottom: 20px;
                border-bottom: 2px solid rgba(255, 0, 255, 0.3);
            }}
            
            .stats-title {{
                font-family: 'Orbitron', sans-serif;
                font-size: 2rem;
                background: linear-gradient(45deg, var(--cyber-pink), var(--electric-blue));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                letter-spacing: 2px;
            }}
            
            .refresh-btn {{
                padding: 12px 25px;
                background: linear-gradient(45deg, var(--cyber-pink), var(--plasma));
                color: white;
                border: none;
                border-radius: 10px;
                font-family: 'Exo 2', sans-serif;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                display: flex;
                align-items: center;
                gap: 10px;
                box-shadow: 0 5px 20px rgba(255, 0, 255, 0.3);
            }}
            
            .refresh-btn:hover {{
                transform: translateY(-3px) rotate(15deg);
                box-shadow: 0 10px 25px rgba(255, 0, 255, 0.5);
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin-bottom: 30px;
            }}
            
            @media (max-width: 768px) {{
                .stats-grid {{
                    grid-template-columns: repeat(2, 1fr);
                }}
            }}
            
            @media (max-width: 480px) {{
                .stats-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
            
            .stat-card {{
                background: linear-gradient(145deg, rgba(10, 10, 15, 0.8), rgba(26, 26, 46, 0.9));
                border-radius: 18px;
                padding: 25px;
                text-align: center;
                border: 1px solid rgba(0, 212, 255, 0.3);
                transition: all 0.3s;
                position: relative;
                overflow: hidden;
                backdrop-filter: blur(10px);
            }}
            
            .stat-card:hover {{
                transform: translateY(-10px);
                border-color: var(--electric-blue);
                box-shadow: var(--glow-blue);
            }}
            
            .stat-icon {{
                font-size: 2.5rem;
                margin-bottom: 15px;
                color: var(--electric-blue);
                filter: drop-shadow(0 0 10px rgba(0, 212, 255, 0.5));
            }}
            
            .stat-value {{
                font-size: 2.8rem;
                font-weight: 900;
                font-family: 'Orbitron', sans-serif;
                margin: 10px 0;
                background: linear-gradient(45deg, var(--electric-blue), var(--matrix-green));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                text-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
            }}
            
            .stat-label {{
                color: var(--hologram-dim);
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 2px;
                font-weight: 600;
            }}
            
            /* BOT STATUS */
            .bot-status-container {{
                margin-top: 40px;
                text-align: center;
            }}
            
            .bot-status {{
                display: inline-flex;
                align-items: center;
                gap: 15px;
                padding: 15px 40px;
                background: linear-gradient(145deg, rgba(26, 26, 46, 0.9), rgba(18, 18, 26, 0.95));
                border-radius: 50px;
                border: 2px solid;
                font-family: 'Orbitron', sans-serif;
                font-weight: 600;
                font-size: 1.1rem;
                letter-spacing: 1px;
                backdrop-filter: blur(20px);
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                animation: pulse 2s infinite;
            }}
            
            .bot-status.online {{
                border-color: var(--matrix-green);
                color: var(--matrix-green);
                box-shadow: 0 10px 30px rgba(0, 255, 157, 0.2);
            }}
            
            .bot-status.offline {{
                border-color: var(--plasma);
                color: var(--plasma);
                box-shadow: 0 10px 30px rgba(255, 107, 107, 0.2);
            }}
            
            @keyframes pulse {{
                0%, 100% {{ 
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                    transform: scale(1);
                }}
                50% {{ 
                    box-shadow: 0 15px 40px rgba(0, 255, 157, 0.3);
                    transform: scale(1.03);
                }}
            }}
            
            .status-indicator {{
                width: 12px;
                height: 12px;
                border-radius: 50%;
                animation: blink 1.5s infinite;
            }}
            
            .status-indicator.online {{
                background: var(--matrix-green);
                box-shadow: 0 0 10px var(--matrix-green);
            }}
            
            .status-indicator.offline {{
                background: var(--plasma);
                box-shadow: 0 0 10px var(--plasma);
            }}
            
            @keyframes blink {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.3; }}
            }}
            
            /* FOOTER */
            .footer {{
                margin-top: 60px;
                text-align: center;
                padding: 30px;
                color: var(--hologram-dim);
                font-size: 0.9rem;
                border-top: 1px solid rgba(157, 0, 255, 0.2);
                position: relative;
                z-index: 3;
            }}
            
            .footer-links {{
                display: flex;
                justify-content: center;
                gap: 30px;
                margin-top: 20px;
                flex-wrap: wrap;
            }}
            
            .footer-link {{
                color: var(--hologram-dim);
                text-decoration: none;
                transition: all 0.3s;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .footer-link:hover {{
                color: var(--matrix-green);
                transform: translateY(-3px);
            }}
            
            /* ANIMATIONS */
            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}
            
            @keyframes fadeInUp {{
                from {{ 
                    opacity: 0;
                    transform: translateY(30px);
                }}
                to {{ 
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            @keyframes fadeInRight {{
                from {{ 
                    opacity: 0;
                    transform: translateX(30px);
                }}
                to {{ 
                    opacity: 1;
                    transform: translateX(0);
                }}
            }}
            
            @keyframes slideUp {{
                from {{ 
                    opacity: 0;
                    transform: translateY(40px);
                }}
                to {{ 
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            /* RESPONSIVE */
            @media (max-width: 768px) {{
                .container {{
                    padding: 20px;
                    gap: 30px;
                }}
                
                .logo {{
                    font-size: 3.5rem;
                }}
                
                .login-container, 
                .info-container, 
                .stats-container {{
                    padding: 30px 25px;
                }}
                
                .stats-header {{
                    flex-direction: column;
                    gap: 20px;
                    text-align: center;
                }}
                
                .tagline {{
                    gap: 10px;
                }}
                
                .tag {{
                    padding: 6px 15px;
                    font-size: 0.8rem;
                }}
            }}
            
            @media (max-width: 480px) {{
                .logo {{
                    font-size: 2.8rem;
                }}
                
                .subtitle {{
                    font-size: 1.1rem;
                }}
                
                .login-btn {{
                    padding: 18px;
                    font-size: 1.1rem;
                }}
                
                .stats-title {{
                    font-size: 1.6rem;
                }}
                
                .stat-value {{
                    font-size: 2.2rem;
                }}
            }}
        </style>
    </head>
    <body>
        <!-- Matrix Background -->
        <div id="particles-js"></div>
        <div class="grid-overlay"></div>
        <div class="scan-line"></div>
        
        <div class="container">
            <div class="header-section">
                <div class="logo-container">
                    <div class="logo glitch-text" data-text="GOBLIN HUT">GOBLIN HUT</div>
                    <div class="subtitle">ENTER THE DARK REALM</div>
                    <div class="tagline">
                        <div class="tag"><i class="fas fa-shield-alt"></i> Secure</div>
                        <div class="tag"><i class="fas fa-bolt"></i> Fast</div>
                        <div class="tag"><i class="fas fa-user-secret"></i> Private</div>
                        <div class="tag"><i class="fas fa-gamepad"></i> Gaming</div>
                    </div>
                </div>
                
                <div class="login-container">
                    <div class="login-title">
                        <i class="fas fa-key"></i> ENTER API KEY
                    </div>
                    
                    <div class="key-input-group">
                        <i class="fas fa-key input-icon"></i>
                        <input type="text" 
                               class="key-input" 
                               id="apiKey" 
                               placeholder="GOB-XXXXXXXXXXXXXXXXXXXX"
                               autocomplete="off"
                               maxlength="24">
                    </div>
                    
                    <button class="login-btn" onclick="validateKey()" id="loginBtn">
                        <i class="fas fa-dungeon"></i> ENTER DARK REALM
                    </button>
                    
                    <div class="error-box" id="errorMessage">
                        <i class="fas fa-exclamation-triangle"></i> 
                        <span id="errorText">Invalid API key format</span>
                    </div>
                </div>
                
                <div class="info-container">
                    <div class="info-title">
                        <i class="fas fa-terminal"></i> ACCESS INSTRUCTIONS
                    </div>
                    
                    <div class="info-steps">
                        <div class="info-step">
                            <div class="step-number">1</div>
                            <div class="step-text">
                                Use <code>/register your_name</code> in Discord <em>(one-time only)</em>
                            </div>
                        </div>
                        
                        <div class="info-step">
                            <div class="step-number">2</div>
                            <div class="step-text">
                                Copy your <code>GOB-XXXXXXXXXXXXXXX</code> key from bot response
                            </div>
                        </div>
                        
                        <div class="info-step">
                            <div class="step-number">3</div>
                            <div class="step-text">
                                Use <code>/key</code> command to retrieve your key anytime
                            </div>
                        </div>
                        
                        <div class="info-step">
                            <div class="step-number">4</div>
                            <div class="step-text">
                                Enter the key above to access your personal dashboard
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="bot-status-container">
                    <div class="bot-status {'online' if bot_active else 'offline'}">
                        <div class="status-indicator {'online' if bot_active else 'offline'}"></div>
                        <span>BOT STATUS: {'ONLINE' if bot_active else 'OFFLINE'}</span>
                    </div>
                </div>
            </div>
            
            <div class="stats-section">
                <div class="stats-container">
                    <div class="stats-header">
                        <div class="stats-title">
                            <i class="fas fa-chart-network"></i> REALM STATISTICS
                        </div>
                        <button class="refresh-btn" onclick="loadStats()">
                            <i class="fas fa-sync-alt"></i> REFRESH
                        </button>
                    </div>
                    
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-icon">
                                <i class="fas fa-users"></i>
                            </div>
                            <div class="stat-value" id="totalPlayers">{stats['total_players']}</div>
                            <div class="stat-label">Total Players</div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-icon">
                                <i class="fas fa-crosshairs"></i>
                            </div>
                            <div class="stat-value" id="totalKills">{stats['total_kills']:,}</div>
                            <div class="stat-label">Total Kills</div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-icon">
                                <i class="fas fa-trophy"></i>
                            </div>
                            <div class="stat-value" id="totalGames">{stats['total_games']}</div>
                            <div class="stat-label">Games Played</div>
                        </div>
                    </div>
                    
                    <div style="margin-top: 30px; padding: 20px; background: rgba(10, 10, 15, 0.6); border-radius: 15px; border-left: 4px solid var(--matrix-green);">
                        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 15px;">
                            <i class="fas fa-robot" style="color: var(--matrix-green); font-size: 1.5rem;"></i>
                            <h3 style="color: var(--matrix-green); margin: 0; font-family: 'Orbitron', sans-serif;">Need Help?</h3>
                        </div>
                        <p style="color: var(--hologram-dim); margin-bottom: 15px; line-height: 1.6;">
                            Join our Discord community to get your API key and access exclusive features.
                        </p>
                        <button class="login-btn" style="background: linear-gradient(45deg, var(--matrix-green), var(--cyber-green));" onclick="showDiscordInfo()">
                            <i class="fab fa-discord"></i> JOIN DISCORD
                        </button>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <div style="margin-bottom: 20px;">
                <i class="fas fa-code" style="color: var(--cyber-purple); margin-right: 10px;"></i>
                <span>GOBLIN HUT SYSTEM v2.0</span>
                <i class="fas fa-heart" style="color: var(--plasma); margin: 0 10px;"></i>
                <span>DARK REALM EDITION</span>
            </div>
            
            <div class="footer-links">
                <a href="#" class="footer-link" onclick="showDiscordInfo()">
                    <i class="fab fa-discord"></i> Discord
                </a>
                <a href="#" class="footer-link" onclick="downloadTool()">
                    <i class="fas fa-download"></i> Download Tool
                </a>
                <a href="/health" class="footer-link" target="_blank">
                    <i class="fas fa-heartbeat"></i> Health Status
                </a>
                <a href="#" class="footer-link" onclick="toggleTheme()">
                    <i class="fas fa-palette"></i> Theme
                </a>
            </div>
            
            <div style="margin-top: 20px; font-size: 0.8rem; opacity: 0.7;">
                &copy; {datetime.now().year} Goblin Hut System. All rights reserved.
            </div>
        </div>
        
        <!-- Particles.js Script -->
        <script src="https://cdn.jsdelivr.net/particles.js/2.0.0/particles.min.js"></script>
        <script>
            // Initialize particles background
            particlesJS('particles-js', {{
                particles: {{
                    number: {{
                        value: 80,
                        density: {{
                            enable: true,
                            value_area: 800
                        }}
                    }},
                    color: {{
                        value: ["#9d00ff", "#00ff9d", "#ff00ff", "#00d4ff"]
                    }},
                    shape: {{
                        type: "circle",
                        stroke: {{
                            width: 0,
                            color: "#000000"
                        }}
                    }},
                    opacity: {{
                        value: 0.5,
                        random: true,
                        anim: {{
                            enable: true,
                            speed: 1,
                            opacity_min: 0.1,
                            sync: false
                        }}
                    }},
                    size: {{
                        value: 3,
                        random: true,
                        anim: {{
                            enable: true,
                            speed: 2,
                            size_min: 0.1,
                            sync: false
                        }}
                    }},
                    line_linked: {{
                        enable: true,
                        distance: 150,
                        color: "#9d00ff",
                        opacity: 0.2,
                        width: 1
                    }},
                    move: {{
                        enable: true,
                        speed: 1,
                        direction: "none",
                        random: true,
                        straight: false,
                        out_mode: "out",
                        bounce: false,
                        attract: {{
                            enable: false,
                            rotateX: 600,
                            rotateY: 1200
                        }}
                    }}
                }},
                interactivity: {{
                    detect_on: "canvas",
                    events: {{
                        onhover: {{
                            enable: true,
                            mode: "grab"
                        }},
                        onclick: {{
                            enable: true,
                            mode: "push"
                        }},
                        resize: true
                    }},
                    modes: {{
                        grab: {{
                            distance: 140,
                            line_linked: {{
                                opacity: 0.5
                            }}
                        }},
                        push: {{
                            particles_nb: 4
                        }}
                    }}
                }},
                retina_detect: true
            }});
            
            async function validateKey() {{
                const key = document.getElementById('apiKey').value.trim().toUpperCase();
                const errorDiv = document.getElementById('errorMessage');
                const errorText = document.getElementById('errorText');
                const btn = document.getElementById('loginBtn');
                
                // Frontend validation
                const keyPattern = /^GOB-[A-Z0-9]{{20}}$/;
                
                if (!key) {{
                    errorText.textContent = "Please enter an API key";
                    errorDiv.style.display = 'block';
                    shakeElement(errorDiv);
                    return;
                }}
                
                if (!keyPattern.test(key)) {{
                    errorText.textContent = "Invalid format. Key must be: GOB- followed by 20 uppercase letters/numbers";
                    errorDiv.style.display = 'block';
                    shakeElement(errorDiv);
                    return;
                }}
                
                // Visual feedback
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ACCESSING REALM...';
                btn.disabled = true;
                btn.style.opacity = '0.8';
                
                try {{
                    const response = await fetch('/api/validate-key', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ api_key: key }})
                    }});
                    
                    const data = await response.json();
                    
                    if (data.valid) {{
                        // Success animation
                        btn.innerHTML = '<i class="fas fa-check"></i> ACCESS GRANTED!';
                        btn.style.background = 'linear-gradient(45deg, #00ff9d, #00cc7a)';
                        btn.style.boxShadow = '0 15px 40px rgba(0, 255, 157, 0.6)';
                        
                        // Confetti effect
                        createConfetti();
                        
                        // Redirect after delay
                        setTimeout(() => {{
                            window.location.href = '/dashboard';
                        }}, 1000);
                    }} else {{
                        errorText.textContent = data.error || 'Invalid API key. Please check and try again.';
                        errorDiv.style.display = 'block';
                        shakeElement(errorDiv);
                        
                        btn.innerHTML = '<i class="fas fa-dungeon"></i> ENTER DARK REALM';
                        btn.disabled = false;
                        btn.style.opacity = '1';
                    }}
                }} catch (error) {{
                    errorText.textContent = 'Connection error. Please check your connection and try again.';
                    errorDiv.style.display = 'block';
                    shakeElement(errorDiv);
                    
                    btn.innerHTML = '<i class="fas fa-dungeon"></i> ENTER DARK REALM';
                    btn.disabled = false;
                    btn.style.opacity = '1';
                }}
            }}
            
            async function loadStats() {{
                const btn = event?.target;
                if (btn) {{
                    const originalHtml = btn.innerHTML;
                    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                    btn.disabled = true;
                }}
                
                try {{
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    document.getElementById('totalPlayers').textContent = data.total_players || '0';
                    document.getElementById('totalKills').textContent = data.total_kills?.toLocaleString() || '0';
                    document.getElementById('totalGames').textContent = data.total_games || '0';
                    
                    // Update bot status
                    const botStatus = document.querySelector('.bot-status');
                    const statusIndicator = document.querySelector('.status-indicator');
                    const statusText = botStatus.querySelector('span');
                    
                    if (data.bot_active) {{
                        botStatus.className = 'bot-status online';
                        statusIndicator.className = 'status-indicator online';
                        statusText.textContent = 'BOT STATUS: ONLINE';
                    }} else {{
                        botStatus.className = 'bot-status offline';
                        statusIndicator.className = 'status-indicator offline';
                        statusText.textContent = 'BOT STATUS: OFFLINE';
                    }}
                    
                    // Success animation
                    if (btn) {{
                        btn.innerHTML = '<i class="fas fa-check"></i>';
                        setTimeout(() => {{
                            btn.innerHTML = originalHtml;
                            btn.disabled = false;
                        }}, 500);
                    }}
                    
                }} catch (error) {{
                    console.error('Error loading stats:', error);
                    if (btn) {{
                        btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
                        setTimeout(() => {{
                            btn.innerHTML = 'REFRESH';
                            btn.disabled = false;
                        }}, 1000);
                    }}
                }}
            }}
            
            function showDiscordInfo() {{
                // Create modal
                const modal = document.createElement('div');
                modal.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0, 0, 0, 0.9);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 10000;
                    animation: fadeIn 0.3s ease-out;
                    backdrop-filter: blur(10px);
                `;
                
                modal.innerHTML = `
                    <div style="
                        background: linear-gradient(145deg, rgba(26, 26, 46, 0.95), rgba(10, 10, 15, 0.98));
                        border-radius: 25px;
                        padding: 40px;
                        max-width: 500px;
                        width: 90%;
                        border: 2px solid rgba(157, 0, 255, 0.5);
                        box-shadow: 0 0 50px rgba(157, 0, 255, 0.5);
                        position: relative;
                        animation: slideUp 0.5s ease-out;
                    ">
                        <button onclick="this.parentElement.parentElement.remove()" style="
                            position: absolute;
                            top: 20px;
                            right: 20px;
                            background: transparent;
                            border: none;
                            color: var(--plasma);
                            font-size: 1.5rem;
                            cursor: pointer;
                        ">
                            <i class="fas fa-times"></i>
                        </button>
                        
                        <div style="text-align: center; margin-bottom: 30px;">
                            <i class="fab fa-discord" style="font-size: 3rem; color: #7289da; margin-bottom: 20px;"></i>
                            <h2 style="color: var(--matrix-green); font-family: 'Orbitron', sans-serif; margin-bottom: 15px;">JOIN OUR DISCORD</h2>
                            <p style="color: var(--hologram-dim); line-height: 1.6;">
                                To get your API key and access all features, join our Discord server and use the <code>/register</code> command.
                            </p>
                        </div>
                        
                        <div style="background: rgba(10, 10, 15, 0.8); padding: 20px; border-radius: 15px; margin: 20px 0; border-left: 4px solid var(--matrix-green);">
                            <h4 style="color: var(--electric-blue); margin-bottom: 10px; display: flex; align-items: center; gap: 10px;">
                                <i class="fas fa-info-circle"></i> Steps to Get Started:
                            </h4>
                            <ol style="color: var(--hologram-dim); padding-left: 20px; line-height: 1.8;">
                                <li>Join our Discord server</li>
                                <li>Use <code>/register your_name</code> in any channel</li>
                                <li>Copy your unique API key from the bot response</li>
                                <li>Return here and enter your key above</li>
                            </ol>
                        </div>
                        
                        <button onclick="window.open('https://discord.gg/example', '_blank')" style="
                            width: 100%;
                            padding: 18px;
                            background: linear-gradient(45deg, #7289da, #5865f2);
                            color: white;
                            border: none;
                            border-radius: 15px;
                            font-size: 1.2rem;
                            font-weight: bold;
                            cursor: pointer;
                            transition: all 0.3s;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            gap: 15px;
                            margin-top: 20px;
                        ">
                            <i class="fab fa-discord"></i> JOIN DISCORD SERVER
                        </button>
                    </div>
                `;
                
                document.body.appendChild(modal);
                
                // Close on ESC
                const closeModal = (e) => {{
                    if (e.key === 'Escape') modal.remove();
                }};
                document.addEventListener('keydown', closeModal);
                modal.addEventListener('click', (e) => {{
                    if (e.target === modal) modal.remove();
                }});
            }}
            
            function downloadTool() {{
                const githubReleaseUrl = 'https://github.com/yourusername/goblin-hut-tool/releases/latest/download/goblin_hut_tool.exe';
                
                const link = document.createElement('a');
                link.href = githubReleaseUrl;
                link.download = 'goblin_hut_tool.exe';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                // Show notification
                showNotification('Download started! Check your downloads folder.', 'success');
            }}
            
            function toggleTheme() {{
                showNotification('Theme customization coming soon!', 'info');
            }}
            
            function shakeElement(element) {{
                element.classList.remove('shake');
                void element.offsetWidth; // Trigger reflow
                element.classList.add('shake');
            }}
            
            function createConfetti() {{
                const colors = ['#9d00ff', '#00ff9d', '#ff00ff', '#00d4ff', '#ff6b6b'];
                
                for (let i = 0; i < 100; i++) {{
                    const confetti = document.createElement('div');
                    confetti.style.cssText = `
                        position: fixed;
                        width: 10px;
                        height: 10px;
                        background: ${{colors[Math.floor(Math.random() * colors.length)]}};
                        top: -20px;
                        left: ${{Math.random() * 100}}%;
                        border-radius: ${{Math.random() > 0.5 ? '50%' : '0'}};
                        z-index: 1000;
                        pointer-events: none;
                    `;
                    
                    document.body.appendChild(confetti);
                    
                    // Animation
                    const animation = confetti.animate([
                        {{ transform: 'translateY(0) rotate(0deg)', opacity: 1 }},
                        {{ transform: `translateY(${{window.innerHeight + 100}}px) rotate(${{Math.random() * 360}}deg)`, opacity: 0 }}
                    ], {{
                        duration: 1000 + Math.random() * 2000,
                        easing: 'cubic-bezier(0.215, 0.61, 0.355, 1)'
                    }});
                    
                    animation.onfinish = () => confetti.remove();
                }}
            }}
            
            function showNotification(message, type = 'info') {{
                const notification = document.createElement('div');
                const colors = {{
                    info: '#00d4ff',
                    success: '#00ff9d',
                    warning: '#ffa500',
                    error: '#ff6b6b'
                }};
                
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: rgba(26, 26, 46, 0.95);
                    border-left: 4px solid ${{colors[type]}};
                    color: var(--hologram);
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                    z-index: 10000;
                    transform: translateX(400px);
                    transition: transform 0.3s ease-out;
                    backdrop-filter: blur(10px);
                    max-width: 300px;
                    display: flex;
                    align-items: center;
                    gap: 15px;
                `;
                
                notification.innerHTML = `
                    <i class="fas fa-${{type === 'success' ? 'check-circle' : 'info-circle'}}" style="color: ${{colors[type]}}; font-size: 1.2rem;"></i>
                    <div>
                        <strong style="color: ${{colors[type]}};">${{type.toUpperCase()}}</strong>
                        <div style="margin-top: 5px;">${{message}}</div>
                    </div>
                `;
                
                document.body.appendChild(notification);
                
                // Slide in
                setTimeout(() => {{
                    notification.style.transform = 'translateX(0)';
                }}, 10);
                
                // Auto remove after 5 seconds
                setTimeout(() => {{
                    notification.style.transform = 'translateX(400px)';
                    setTimeout(() => notification.remove(), 300);
                }}, 5000);
                
                // Click to dismiss
                notification.addEventListener('click', () => {{
                    notification.style.transform = 'translateX(400px)';
                    setTimeout(() => notification.remove(), 300);
                }});
            }}
            
            // Auto-focus input on load
            document.addEventListener('DOMContentLoaded', function() {{
                document.getElementById('apiKey').focus();
                
                // Load stats every 30 seconds
                loadStats();
                setInterval(loadStats, 30000);
                
                // Add key validation on input
                document.getElementById('apiKey').addEventListener('input', function(e) {{
                    const key = e.target.value.toUpperCase();
                    e.target.value = key;
                    
                    // Hide error when typing
                    document.getElementById('errorMessage').style.display = 'none';
                }});
                
                // Enter key submits
                document.getElementById('apiKey').addEventListener('keypress', function(e) {{
                    if (e.key === 'Enter') validateKey();
                }});
                
                // Add some random glitch effects to the title
                setInterval(() => {{
                    if (Math.random() < 0.1) {{
                        document.querySelector('.glitch-text').classList.add('glitching');
                        setTimeout(() => {{
                            document.querySelector('.glitch-text').classList.remove('glitching');
                        }}, 200);
                    }}
                }}, 3000);
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

# =============================================================================
# DASHBOARD - DARK THEME ENHANCED
# =============================================================================

@app.route('/dashboard')
def dashboard():
    """Profile Dashboard - DARK REALM EDITION"""
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
    
    # Format dates
    created_at = user_data.get('created_at', datetime.now())
    last_used = user_data.get('last_used', datetime.now())
    
    # Get leaderboard
    leaderboard_data = get_leaderboard(10)
    
    # Get recent matches (placeholder - you'll need to implement this)
    recent_matches = []
    
    # Get user's rank
    user_rank = "N/A"
    for i, player in enumerate(leaderboard_data, 1):
        if player.get('api_key') == session['user_key']:
            user_rank = f"#{i}"
            break
    
    # Format leaderboard HTML
    leaderboard_html = ''
    for i, player in enumerate(leaderboard_data, 1):
        rank_class = f'rank-{i}' if i <= 3 else 'rank-other'
        is_current_user = player.get('api_key') == session['user_key']
        user_class = 'current-user' if is_current_user else ''
        
        leaderboard_html += f'''
        <div class="leaderboard-item {user_class}" data-rank="{i}">
            <div class="rank {rank_class}">#{i}</div>
            <div class="player-avatar">
                <div class="avatar-placeholder">{player['name'][0].upper()}</div>
            </div>
            <div class="player-info">
                <div class="player-name">
                    <span class="name">{player['name']}</span>
                    {is_current_user and '<span class="you-badge"><i class="fas fa-user"></i> YOU</span>' or ''}
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
                    <div class="stat">
                        <span class="stat-label">Wins:</span>
                        <span class="stat-value">{player['wins']}</span>
                    </div>
                </div>
            </div>
            <div class="player-action">
                <button class="view-btn" onclick="viewPlayer('{player['name']}')">
                    <i class="fas fa-eye"></i>
                </button>
            </div>
        </div>
        '''
    
    if not leaderboard_html:
        leaderboard_html = '''
        <div class="no-data">
            <i class="fas fa-users-slash"></i>
            <h3>No players on leaderboard yet</h3>
            <p>Be the first to register and play!</p>
        </div>
        '''
    
    # Format recent matches HTML
    matches_html = ''
    if recent_matches:
        for match in recent_matches:
            matches_html += f'''
            <div class="match-card">
                <div class="match-header">
                    <span class="match-id">{match.get('id', 'N/A')}</span>
                    <span class="match-status {match.get('status', 'ended')}">{match.get('status', 'ended').upper()}</span>
                </div>
                <div class="match-teams">
                    <div class="team team1">
                        <div class="team-name">Team 1</div>
                        <div class="team-score">{match.get('team1_score', 0)}</div>
                    </div>
                    <div class="vs">VS</div>
                    <div class="team team2">
                        <div class="team-name">Team 2</div>
                        <div class="team-score">{match.get('team2_score', 0)}</div>
                    </div>
                </div>
                <div class="match-footer">
                    <span class="match-date">{match.get('date', 'N/A')}</span>
                    <button class="match-details-btn">
                        <i class="fas fa-chart-bar"></i> Details
                    </button>
                </div>
            </div>
            '''
    else:
        matches_html = '''
        <div class="no-data">
            <i class="fas fa-gamepad"></i>
            <h3>No recent matches</h3>
            <p>Play some games to see your match history here</p>
        </div>
        '''
    
    # Build the dashboard HTML with DARK REALM theme
    dashboard_html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dark Realm - {user_data.get('in_game_name', 'Player')}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Exo+2:wght@300;400;500;600;700&family=Source+Code+Pro:wght@300;400;500&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {{
                /* Deep Dark Cyberpunk Theme */
                --void-black: #0a0a0f;
                --abyss-black: #12121a;
                --midnight: #1a1a2e;
                --nebula: #16213e;
                --stardust: #0f3460;
                --cyber-purple: #9d00ff;
                --neon-purple: #b300ff;
                --matrix-green: #00ff9d;
                --cyber-green: #00cc7a;
                --cyber-pink: #ff00ff;
                --electric-blue: #00d4ff;
                --plasma: #ff6b6b;
                --hologram: #e0d6ff;
                --hologram-dim: #a099cc;
                
                /* Glow Effects */
                --glow-purple: 0 0 30px rgba(157, 0, 255, 0.7);
                --glow-green: 0 0 30px rgba(0, 255, 157, 0.7);
                --glow-blue: 0 0 30px rgba(0, 212, 255, 0.7);
                --glow-pink: 0 0 30px rgba(255, 0, 255, 0.7);
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Exo 2', sans-serif;
                background: linear-gradient(135deg, var(--void-black) 0%, var(--abyss-black) 50%, var(--midnight) 100%);
                color: var(--hologram);
                min-height: 100vh;
                overflow-x: hidden;
            }}
            
            /* Background Effects */
            #particles-js {{
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                z-index: 0;
                opacity: 0.3;
            }}
            
            .grid-overlay {{
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                background-image: 
                    linear-gradient(rgba(157, 0, 255, 0.05) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(157, 0, 255, 0.05) 1px, transparent 1px);
                background-size: 50px 50px;
                z-index: 1;
                pointer-events: none;
            }}
            
            /* HEADER */
            .dashboard-header {{
                background: linear-gradient(90deg, rgba(26, 26, 46, 0.95), rgba(10, 10, 15, 0.98));
                backdrop-filter: blur(20px);
                border-bottom: 2px solid rgba(157, 0, 255, 0.4);
                padding: 20px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 1000;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
            }}
            
            .header-left {{
                display: flex;
                align-items: center;
                gap: 20px;
            }}
            
            .logo {{
                font-family: 'Orbitron', sans-serif;
                font-size: 2.5rem;
                font-weight: 900;
                background: linear-gradient(45deg, var(--cyber-purple), var(--cyber-pink), var(--electric-blue));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                letter-spacing: 2px;
                text-shadow: 0 0 20px rgba(157, 0, 255, 0.3);
            }}
            
            .header-right {{
                display: flex;
                align-items: center;
                gap: 30px;
            }}
            
            .user-profile {{
                display: flex;
                align-items: center;
                gap: 15px;
                padding: 10px 20px;
                background: rgba(10, 10, 15, 0.8);
                border-radius: 50px;
                border: 1px solid rgba(157, 0, 255, 0.3);
                backdrop-filter: blur(10px);
            }}
            
            .user-avatar {{
                width: 45px;
                height: 45px;
                background: linear-gradient(45deg, var(--cyber-purple), var(--neon-purple));
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5rem;
                font-weight: bold;
                color: white;
                box-shadow: 0 0 15px rgba(157, 0, 255, 0.5);
            }}
            
            .user-info {{
                display: flex;
                flex-direction: column;
            }}
            
            .user-name {{
                font-size: 1.2rem;
                font-weight: 600;
                color: var(--matrix-green);
                font-family: 'Orbitron', sans-serif;
                letter-spacing: 1px;
            }}
            
            .user-rank {{
                font-size: 0.9rem;
                color: var(--hologram-dim);
            }}
            
            .logout-btn {{
                padding: 12px 30px;
                background: linear-gradient(45deg, var(--plasma), #ff416c);
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: bold;
                cursor: pointer;
                text-decoration: none;
                transition: all 0.3s;
                box-shadow: 0 5px 20px rgba(255, 107, 107, 0.3);
                font-family: 'Exo 2', sans-serif;
                letter-spacing: 1px;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            .logout-btn:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 25px rgba(255, 107, 107, 0.4);
                background: linear-gradient(45deg, #ff416c, #ff4b2b);
            }}
            
            /* MAIN CONTAINER */
            .dashboard-container {{
                max-width: 1600px;
                margin: 0 auto;
                padding: 30px;
                display: grid;
                grid-template-columns: 2fr 1fr;
                gap: 30px;
                position: relative;
                z-index: 2;
            }}
            
            @media (max-width: 1200px) {{
                .dashboard-container {{
                    grid-template-columns: 1fr;
                }}
            }}
            
            /* SIDEBAR */
            .sidebar {{
                display: flex;
                flex-direction: column;
                gap: 20px;
            }}
            
            /* PROFILE CARD */
            .profile-card {{
                background: linear-gradient(145deg, rgba(26, 26, 46, 0.9), rgba(18, 18, 26, 0.95));
                border-radius: 25px;
                padding: 30px;
                border: 1px solid rgba(157, 0, 255, 0.4);
                box-shadow: var(--glow-purple), inset 0 0 40px rgba(0, 0, 0, 0.6);
                backdrop-filter: blur(25px);
                animation: slideUp 0.8s ease-out;
            }}
            
            .profile-header {{
                display: flex;
                align-items: center;
                gap: 25px;
                margin-bottom: 30px;
                padding-bottom: 25px;
                border-bottom: 2px solid rgba(157, 0, 255, 0.3);
            }}
            
            .profile-avatar {{
                width: 120px;
                height: 120px;
                background: linear-gradient(45deg, var(--cyber-purple), var(--neon-purple));
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 3.5rem;
                color: white;
                box-shadow: 0 0 30px rgba(157, 0, 255, 0.5);
                position: relative;
                overflow: hidden;
            }}
            
            .profile-avatar::before {{
                content: '';
                position: absolute;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: conic-gradient(
                    transparent, 
                    rgba(255, 255, 255, 0.1), 
                    transparent 30%
                );
                animation: rotate 10s linear infinite;
            }}
            
            .profile-info h2 {{
                font-size: 2.8rem;
                margin-bottom: 10px;
                background: linear-gradient(45deg, var(--matrix-green), var(--electric-blue));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                text-shadow: 0 0 20px rgba(0, 255, 157, 0.3);
                font-family: 'Orbitron', sans-serif;
            }}
            
            .profile-tags {{
                display: flex;
                gap: 10px;
                margin-top: 10px;
                flex-wrap: wrap;
            }}
            
            .profile-tag {{
                padding: 6px 15px;
                background: rgba(157, 0, 255, 0.1);
                border: 1px solid rgba(157, 0, 255, 0.3);
                border-radius: 20px;
                font-size: 0.9rem;
                color: var(--cyber-purple);
                backdrop-filter: blur(10px);
            }}
            
            /* STATS GRID */
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                margin-bottom: 30px;
            }}
            
            @media (max-width: 768px) {{
                .stats-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
            
            .stat-card {{
                background: linear-gradient(145deg, rgba(10, 10, 15, 0.8), rgba(26, 26, 46, 0.9));
                border-radius: 18px;
                padding: 25px;
                text-align: center;
                border: 1px solid rgba(0, 212, 255, 0.3);
                transition: all 0.3s;
                backdrop-filter: blur(10px);
            }}
            
            .stat-card:hover {{
                transform: translateY(-10px);
                border-color: var(--electric-blue);
                box-shadow: var(--glow-blue);
            }}
            
            .stat-value {{
                font-size: 3rem;
                font-weight: 900;
                font-family: 'Orbitron', sans-serif;
                margin: 10px 0;
                background: linear-gradient(45deg, var(--electric-blue), var(--matrix-green));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                text-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
            }}
            
            .stat-label {{
                color: var(--hologram-dim);
                font-size: 1rem;
                text-transform: uppercase;
                letter-spacing: 2px;
                font-weight: 600;
            }}
            
            /* KEY SECTION */
            .key-section {{
                margin-top: 30px;
            }}
            
            .section-title {{
                font-family: 'Orbitron', sans-serif;
                font-size: 1.6rem;
                color: var(--matrix-green);
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 15px;
            }}
            
            .key-display {{
                background: rgba(10, 10, 15, 0.8);
                border: 2px solid rgba(157, 0, 255, 0.4);
                border-radius: 15px;
                padding: 25px;
                margin: 20px 0;
                font-family: 'Source Code Pro', monospace;
                color: transparent;
                text-align: center;
                cursor: pointer;
                word-break: break-all;
                transition: all 0.3s;
                backdrop-filter: blur(10px);
                position: relative;
                overflow: hidden;
                font-size: 1.2rem;
                letter-spacing: 1px;
            }}
            
            .key-display::before {{
                content: '🔒 HOVER TO REVEAL';
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                color: var(--hologram-dim);
                font-size: 1.2rem;
                opacity: 1;
                transition: opacity 0.3s;
            }}
            
            .key-display:hover {{
                color: var(--matrix-green);
                text-shadow: 0 0 15px rgba(0, 255, 157, 0.5);
                border-color: rgba(0, 255, 157, 0.6);
                box-shadow: 0 0 30px rgba(0, 255, 157, 0.3);
            }}
            
            .key-display:hover::before {{
                opacity: 0;
            }}
            
            .action-buttons {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
                margin-top: 20px;
            }}
            
            @media (max-width: 768px) {{
                .action-buttons {{
                    grid-template-columns: 1fr;
                }}
            }}
            
            .action-btn {{
                padding: 18px;
                background: linear-gradient(45deg, var(--cyber-purple), var(--neon-purple));
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                box-shadow: 0 5px 15px rgba(157, 0, 255, 0.3);
                font-family: 'Exo 2', sans-serif;
                font-size: 1.1rem;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 15px;
            }}
            
            .action-btn:hover {{
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(157, 0, 255, 0.5);
            }}
            
            .action-btn.download {{
                background: linear-gradient(45deg, var(--matrix-green), var(--cyber-green));
            }}
            
            .action-btn.download:hover {{
                box-shadow: 0 10px 25px rgba(0, 255, 157, 0.5);
            }}
            
            /* LEADERBOARD CARD */
            .leaderboard-card {{
                background: linear-gradient(145deg, rgba(26, 26, 46, 0.9), rgba(18, 18, 26, 0.95));
                border-radius: 25px;
                padding: 30px;
                border: 1px solid rgba(255, 0, 255, 0.4);
                box-shadow: var(--glow-pink), inset 0 0 40px rgba(0, 0, 0, 0.6);
                backdrop-filter: blur(25px);
                height: fit-content;
                animation: slideUp 0.8s ease-out 0.2s both;
            }}
            
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 25px;
                padding-bottom: 20px;
                border-bottom: 2px solid rgba(255, 0, 255, 0.3);
            }}
            
            .card-title {{
                font-family: 'Orbitron', sans-serif;
                font-size: 2rem;
                background: linear-gradient(45deg, var(--cyber-pink), var(--electric-blue));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                letter-spacing: 2px;
            }}
            
            .refresh-btn {{
                padding: 10px 20px;
                background: linear-gradient(45deg, var(--cyber-pink), var(--plasma));
                color: white;
                border: none;
                border-radius: 10px;
                font-family: 'Exo 2', sans-serif;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                display: flex;
                align-items: center;
                gap: 10px;
                box-shadow: 0 5px 20px rgba(255, 0, 255, 0.3);
            }}
            
            .refresh-btn:hover {{
                transform: translateY(-3px) rotate(15deg);
                box-shadow: 0 10px 25px rgba(255, 0, 255, 0.5);
            }}
            
            .leaderboard-list {{
                max-height: 600px;
                overflow-y: auto;
                padding-right: 10px;
            }}
            
            .leaderboard-list::-webkit-scrollbar {{
                width: 8px;
            }}
            
            .leaderboard-list::-webkit-scrollbar-track {{
                background: rgba(10, 10, 15, 0.3);
                border-radius: 4px;
            }}
            
            .leaderboard-list::-webkit-scrollbar-thumb {{
                background: linear-gradient(var(--cyber-purple), var(--neon-purple));
                border-radius: 4px;
            }}
            
            .leaderboard-item {{
                display: flex;
                align-items: center;
                padding: 15px;
                margin-bottom: 12px;
                background: rgba(10, 10, 15, 0.6);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: all 0.3s;
                backdrop-filter: blur(5px);
                animation: fadeIn 0.5s ease-out;
            }}
            
            .leaderboard-item:hover {{
                transform: translateX(10px);
                border-color: rgba(157, 0, 255, 0.3);
                background: rgba(157, 0, 255, 0.1);
                box-shadow: 0 5px 15px rgba(157, 0, 255, 0.2);
            }}
            
            .leaderboard-item.current-user {{
                background: rgba(157, 0, 255, 0.2);
                border-color: rgba(157, 0, 255, 0.5);
                box-shadow: 0 0 15px rgba(157, 0, 255, 0.3);
            }}
            
            .rank {{
                font-size: 1.8rem;
                font-weight: bold;
                width: 50px;
                text-align: center;
                margin-right: 15px;
                font-family: 'Orbitron', sans-serif;
            }}
            
            .rank-1 {{ color: #ffd700; text-shadow: 0 0 15px #ffd700; }}
            .rank-2 {{ color: #c0c0c0; text-shadow: 0 0 15px #c0c0c0; }}
            .rank-3 {{ color: #cd7f32; text-shadow: 0 0 15px #cd7f32; }}
            .rank-other {{ color: var(--matrix-green); }}
            
            .player-avatar {{
                margin-right: 15px;
            }}
            
            .avatar-placeholder {{
                width: 40px;
                height: 40px;
                background: linear-gradient(45deg, var(--electric-blue), var(--matrix-green));
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 1.2rem;
                box-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
            }}
            
            .player-info {{
                flex-grow: 1;
            }}
            
            .player-name {{
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 5px;
            }}
            
            .player-name .name {{
                font-weight: bold;
                color: var(--hologram);
                font-size: 1.1rem;
            }}
            
            .you-badge {{
                background: linear-gradient(45deg, var(--matrix-green), var(--cyber-green));
                color: black;
                padding: 3px 10px;
                border-radius: 12px;
                font-size: 0.8rem;
                font-weight: bold;
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            
            .prestige-badge {{
                background: linear-gradient(45deg, #ffd700, #ffa500);
                color: black;
                padding: 3px 10px;
                border-radius: 12px;
                font-size: 0.9rem;
                font-weight: bold;
            }}
            
            .player-stats {{
                display: flex;
                gap: 20px;
                font-size: 0.9rem;
                color: var(--hologram-dim);
            }}
            
            .stat-value {{
                color: var(--matrix-green);
                font-weight: bold;
                font-size: 1rem;
            }}
            
            .player-action {{
                opacity: 0;
                transition: opacity 0.3s;
            }}
            
            .leaderboard-item:hover .player-action {{
                opacity: 1;
            }}
            
            .view-btn {{
                background: rgba(157, 0, 255, 0.2);
                border: 1px solid rgba(157, 0, 255, 0.4);
                color: var(--cyber-purple);
                border-radius: 8px;
                padding: 8px 12px;
                cursor: pointer;
                transition: all 0.3s;
            }}
            
            .view-btn:hover {{
                background: rgba(157, 0, 255, 0.4);
                transform: scale(1.1);
            }}
            
            .no-data {{
                text-align: center;
                padding: 60px 20px;
                color: var(--hologram-dim);
                font-size: 1.1rem;
            }}
            
            .no-data i {{
                font-size: 3rem;
                color: var(--cyber-purple);
                margin-bottom: 20px;
                opacity: 0.5;
            }}
            
            /* MATCH HISTORY */
            .matches-section {{
                margin-top: 30px;
            }}
            
            .matches-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }}
            
            .match-card {{
                background: linear-gradient(145deg, rgba(10, 10, 15, 0.8), rgba(26, 26, 46, 0.9));
                border-radius: 15px;
                padding: 20px;
                border: 1px solid rgba(0, 212, 255, 0.3);
                transition: all 0.3s;
                backdrop-filter: blur(10px);
            }}
            
            .match-card:hover {{
                transform: translateY(-5px);
                border-color: var(--electric-blue);
                box-shadow: var(--glow-blue);
            }}
            
            /* FOOTER */
            .dashboard-footer {{
                margin-top: 60px;
                text-align: center;
                padding: 30px;
                color: var(--hologram-dim);
                font-size: 0.9rem;
                border-top: 1px solid rgba(157, 0, 255, 0.2);
                position: relative;
                z-index: 3;
            }}
            
            .footer-links {{
                display: flex;
                justify-content: center;
                gap: 30px;
                margin-top: 20px;
                flex-wrap: wrap;
            }}
            
            .footer-link {{
                color: var(--hologram-dim);
                text-decoration: none;
                transition: all 0.3s;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .footer-link:hover {{
                color: var(--matrix-green);
                transform: translateY(-3px);
            }}
            
            /* ANIMATIONS */
            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}
            
            @keyframes slideUp {{
                from {{ 
                    opacity: 0;
                    transform: translateY(40px);
                }}
                to {{ 
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            @keyframes rotate {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            
            /* RESPONSIVE */
            @media (max-width: 768px) {{
                .dashboard-header {{
                    flex-direction: column;
                    gap: 20px;
                    padding: 20px;
                }}
                
                .dashboard-container {{
                    padding: 20px;
                    gap: 25px;
                }}
                
                .profile-header {{
                    flex-direction: column;
                    text-align: center;
                }}
                
                .profile-avatar {{
                    width: 100px;
                    height: 100px;
                    font-size: 2.5rem;
                }}
                
                .profile-info h2 {{
                    font-size: 2.2rem;
                }}
                
                .stat-value {{
                    font-size: 2.5rem;
                }}
                
                .card-header {{
                    flex-direction: column;
                    gap: 20px;
                    text-align: center;
                }}
                
                .matches-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
            
            @media (max-width: 480px) {{
                .logo {{
                    font-size: 2rem;
                }}
                
                .user-profile {{
                    flex-direction: column;
                    text-align: center;
                    padding: 15px;
                }}
                
                .action-buttons {{
                    grid-template-columns: 1fr;
                }}
                
                .player-stats {{
                    flex-wrap: wrap;
                    gap: 10px;
                }}
            }}
        </style>
    </head>
    <body>
        <!-- Background Effects -->
        <div id="particles-js"></div>
        <div class="grid-overlay"></div>
        
        <!-- Header -->
        <div class="dashboard-header">
            <div class="header-left">
                <div class="logo">GOBLIN HUT</div>
                <div style="color: var(--hologram-dim); font-size: 0.9rem;">
                    <i class="fas fa-map-marker-alt"></i> DARK REALM
                </div>
            </div>
            
            <div class="header-right">
                <div class="user-profile">
                    <div class="user-avatar">
                        {user_data.get('in_game_name', 'P')[0].upper()}
                    </div>
                    <div class="user-info">
                        <div class="user-name">{user_data.get('in_game_name', 'Player')}</div>
                        <div class="user-rank">Rank: {user_rank}</div>
                    </div>
                </div>
                
                <a href="/logout" class="logout-btn">
                    <i class="fas fa-sign-out-alt"></i> EXIT REALM
                </a>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="dashboard-container">
            <div class="sidebar">
                <!-- Profile Card -->
                <div class="profile-card">
                    <div class="profile-header">
                        <div class="profile-avatar">
                            {user_data.get('in_game_name', 'P')[0].upper()}
                        </div>
                        <div class="profile-info">
                            <h2>{user_data.get('in_game_name', 'Player')}</h2>
                            <div style="color: var(--hologram-dim); margin-bottom: 10px;">
                                <i class="fas fa-calendar"></i> Joined: {created_at[:10] if isinstance(created_at, str) else created_at.strftime('%Y-%m-%d')}
                            </div>
                            <div class="profile-tags">
                                <div class="profile-tag">
                                    <i class="fas fa-crown"></i> Prestige {user_data.get('prestige', 0)}
                                </div>
                                <div class="profile-tag">
                                    <i class="fas fa-gamepad"></i> {total_games} Games
                                </div>
                                {user_data.get('is_admin') and '<div class="profile-tag" style="background: rgba(255, 215, 0, 0.1); border-color: rgba(255, 215, 0, 0.3); color: #ffd700;"><i class="fas fa-shield-alt"></i> Admin</div>' or ''}
                            </div>
                        </div>
                    </div>
                    
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value">{kd:.2f}</div>
                            <div class="stat-label">K/D Ratio</div>
                            <div style="color: var(--hologram-dim); font-size: 0.9rem; margin-top: 5px;">
                                {total_kills} kills / {total_deaths} deaths
                            </div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-value">{win_rate:.1f}%</div>
                            <div class="stat-label">Win Rate</div>
                            <div style="color: var(--hologram-dim); font-size: 0.9rem; margin-top: 5px;">
                                {wins} wins / {losses} losses
                            </div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-value">{total_games}</div>
                            <div class="stat-label">Total Games</div>
                            <div style="color: var(--hologram-dim); font-size: 0.9rem; margin-top: 5px;">
                                Matches played
                            </div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-value">{user_data.get('prestige', 0)}</div>
                            <div class="stat-label">Prestige</div>
                            <div style="color: var(--hologram-dim); font-size: 0.9rem; margin-top: 5px;">
                                Current level
                            </div>
                        </div>
                    </div>
                    
                    <div class="key-section">
                        <div class="section-title">
                            <i class="fas fa-key"></i> YOUR API KEY
                        </div>
                        
                        <p style="color: var(--hologram-dim); margin-bottom: 20px; line-height: 1.6;">
                            This key is your identity in the Goblin Hut system. 
                            <strong style="color: var(--plasma);">Never share it with anyone.</strong>
                        </p>
                        
                        <div class="key-display" id="apiKeyDisplay">
                            {session['user_key']}
                        </div>
                        
                        <div class="action-buttons">
                            <button class="action-btn" onclick="copyKey()">
                                <i class="fas fa-copy"></i> COPY KEY
                            </button>
                            <button class="action-btn download" onclick="downloadTool()">
                                <i class="fas fa-download"></i> DOWNLOAD TOOL
                            </button>
                        </div>
                    </div>
                </div>
                
                <!-- Match History (Optional) -->
                <div class="matches-section">
                    <div class="section-title">
                        <i class="fas fa-history"></i> RECENT MATCHES
                    </div>
                    <div class="matches-grid" id="matchesContainer">
                        {matches_html}
                    </div>
                </div>
            </div>
            
            <!-- Leaderboard -->
            <div class="leaderboard-card">
                <div class="card-header">
                    <div class="card-title">
                        <i class="fas fa-trophy"></i> LEADERBOARD
                    </div>
                    <button class="refresh-btn" onclick="loadLeaderboard()">
                        <i class="fas fa-sync-alt"></i> REFRESH
                    </button>
                </div>
                
                <div class="leaderboard-list" id="leaderboardContainer">
                    {leaderboard_html}
                </div>
                
                <div style="margin-top: 30px; padding: 20px; background: rgba(10, 10, 15, 0.6); border-radius: 15px; border-left: 4px solid var(--matrix-green);">
                    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                        <i class="fas fa-info-circle" style="color: var(--matrix-green); font-size: 1.5rem;"></i>
                        <h3 style="color: var(--matrix-green); margin: 0; font-family: 'Orbitron', sans-serif;">Your Position</h3>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <div style="font-size: 2.5rem; font-weight: bold; color: var(--electric-blue);">{user_rank}</div>
                            <div style="color: var(--hologram-dim); font-size: 0.9rem;">Global Rank</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.8rem; font-weight: bold; color: var(--matrix-green);">{kd:.2f}</div>
                            <div style="color: var(--hologram-dim); font-size: 0.9rem;">Your K/D Ratio</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="dashboard-footer">
            <div style="margin-bottom: 20px;">
                <i class="fas fa-code" style="color: var(--cyber-purple); margin-right: 10px;"></i>
                <span>GOBLIN HUT DASHBOARD v2.0</span>
                <i class="fas fa-heart" style="color: var(--plasma); margin: 0 10px;"></i>
                <span>DARK REALM EDITION</span>
            </div>
            
            <div class="footer-links">
                <a href="/" class="footer-link">
                    <i class="fas fa-home"></i> Home
                </a>
                <a href="#" class="footer-link" onclick="showDiscordInfo()">
                    <i class="fab fa-discord"></i> Discord
                </a>
                <a href="/health" class="footer-link" target="_blank">
                    <i class="fas fa-heartbeat"></i> System Status
                </a>
                <a href="#" class="footer-link" onclick="showSupport()">
                    <i class="fas fa-question-circle"></i> Support
                </a>
            </div>
            
            <div style="margin-top: 20px; font-size: 0.8rem; opacity: 0.7;">
                Session active • Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>
        
        <!-- Particles.js Script -->
        <script src="https://cdn.jsdelivr.net/particles.js/2.0.0/particles.min.js"></script>
        <script>
            // Initialize particles background
            particlesJS('particles-js', {{
                particles: {{
                    number: {{
                        value: 60,
                        density: {{
                            enable: true,
                            value_area: 800
                        }}
                    }},
                    color: {{
                        value: ["#9d00ff", "#00ff9d", "#ff00ff", "#00d4ff"]
                    }},
                    shape: {{
                        type: "circle",
                        stroke: {{
                            width: 0,
                            color: "#000000"
                        }}
                    }},
                    opacity: {{
                        value: 0.5,
                        random: true,
                        anim: {{
                            enable: true,
                            speed: 1,
                            opacity_min: 0.1,
                            sync: false
                        }}
                    }},
                    size: {{
                        value: 3,
                        random: true,
                        anim: {{
                            enable: true,
                            speed: 2,
                            size_min: 0.1,
                            sync: false
                        }}
                    }},
                    line_linked: {{
                        enable: true,
                        distance: 150,
                        color: "#9d00ff",
                        opacity: 0.2,
                        width: 1
                    }},
                    move: {{
                        enable: true,
                        speed: 1,
                        direction: "none",
                        random: true,
                        straight: false,
                        out_mode: "out",
                        bounce: false,
                        attract: {{
                            enable: false,
                            rotateX: 600,
                            rotateY: 1200
                        }}
                    }}
                }},
                interactivity: {{
                    detect_on: "canvas",
                    events: {{
                        onhover: {{
                            enable: true,
                            mode: "grab"
                        }},
                        onclick: {{
                            enable: true,
                            mode: "push"
                        }},
                        resize: true
                    }},
                    modes: {{
                        grab: {{
                            distance: 140,
                            line_linked: {{
                                opacity: 0.5
                            }}
                        }},
                        push: {{
                            particles_nb: 4
                        }}
                    }}
                }},
                retina_detect: true
            }});
            
            function copyKey() {{
                const key = "{session['user_key']}";
                navigator.clipboard.writeText(key).then(() => {{
                    showNotification('✅ API key copied to clipboard!', 'success');
                }}).catch(err => {{
                    console.error('Copy failed:', err);
                    showNotification('❌ Failed to copy key. Please try again.', 'error');
                }});
            }}
            
            function downloadTool() {{
                const githubReleaseUrl = 'https://github.com/yourusername/goblin-hut-tool/releases/latest/download/goblin_hut_tool.exe';
                
                const link = document.createElement('a');
                link.href = githubReleaseUrl;
                link.download = 'goblin_hut_tool.exe';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                showNotification('📥 Download started! Check your downloads folder.', 'success');
            }}
            
            async function loadLeaderboard() {{
                const container = document.getElementById('leaderboardContainer');
                const btn = event?.target;
                const originalHtml = btn?.innerHTML || 'REFRESH';
                
                if (btn) {{
                    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                    btn.disabled = true;
                }}
                
                try {{
                    const response = await fetch('/api/leaderboard');
                    const data = await response.json();
                    
                    if (data.leaderboard && data.leaderboard.length > 0) {{
                        let html = '';
                        
                        data.leaderboard.forEach((player, index) => {{
                            const rank = index + 1;
                            const rankClass = rank <= 3 ? `rank-${{rank}}` : 'rank-other';
                            const isCurrentUser = "{user_data.get('in_game_name', '')}" === player.name || "{session['user_key']}".includes(player.api_key || '');
                            const userClass = isCurrentUser ? 'current-user' : '';
                            
                            html += `
                                <div class="leaderboard-item ${{userClass}}" data-rank="${{rank}}">
                                    <div class="rank ${{rankClass}}">#${{rank}}</div>
                                    <div class="player-avatar">
                                        <div class="avatar-placeholder">${{player.name.charAt(0).toUpperCase()}}</div>
                                    </div>
                                    <div class="player-info">
                                        <div class="player-name">
                                            <span class="name">${{player.name}}</span>
                                            ${{isCurrentUser ? '<span class="you-badge"><i class="fas fa-user"></i> YOU</span>' : ''}}
                                            ${{player.prestige > 0 ? `<span class="prestige-badge">P${{player.prestige}}</span>` : ''}}
                                        </div>
                                        <div class="player-stats">
                                            <div class="stat">
                                                <span class="stat-label">K/D:</span>
                                                <span class="stat-value">${{player.kd}}</span>
                                            </div>
                                            <div class="stat">
                                                <span class="stat-label">Kills:</span>
                                                <span class="stat-value">${{player.kills}}</span>
                                            </div>
                                            <div class="stat">
                                                <span class="stat-label">Wins:</span>
                                                <span class="stat-value">${{player.wins}}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="player-action">
                                        <button class="view-btn" onclick="viewPlayer('${{player.name}}')">
                                            <i class="fas fa-eye"></i>
                                        </button>
                                    </div>
                                </div>
                            `;
                        }});
                        
                        container.innerHTML = html;
                    }} else {{
                        container.innerHTML = `
                            <div class="no-data">
                                <i class="fas fa-users-slash"></i>
                                <h3>No players on leaderboard yet</h3>
                                <p>Be the first to register and play!</p>
                            </div>
                        `;
                    }}
                    
                    if (btn) {{
                        btn.innerHTML = '<i class="fas fa-check"></i>';
                        setTimeout(() => {{
                            btn.innerHTML = originalHtml;
                            btn.disabled = false;
                        }}, 500);
                    }}
                    
                }} catch (error) {{
                    console.error('Error loading leaderboard:', error);
                    container.innerHTML = `
                        <div class="no-data">
                            <i class="fas fa-exclamation-triangle"></i>
                            <h3>Failed to load leaderboard</h3>
                            <p>Please try again later</p>
                        </div>
                    `;
                    
                    if (btn) {{
                        btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
                        setTimeout(() => {{
                            btn.innerHTML = 'REFRESH';
                            btn.disabled = false;
                        }}, 1000);
                    }}
                }}
            }}
            
            function viewPlayer(playerName) {{
                showNotification(`Viewing profile of ${{playerName}}`, 'info');
                // In a real implementation, this would open a player profile modal
            }}
            
            function showDiscordInfo() {{
                // Create modal similar to home page
                showNotification('Join our Discord for support and updates!', 'info');
            }}
            
            function showSupport() {{
                showNotification('Support features coming soon!', 'info');
            }}
            
            function showNotification(message, type = 'info') {{
                const colors = {{
                    info: '#00d4ff',
                    success: '#00ff9d',
                    warning: '#ffa500',
                    error: '#ff6b6b'
                }};
                
                const notification = document.createElement('div');
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: rgba(26, 26, 46, 0.95);
                    border-left: 4px solid ${{colors[type]}};
                    color: var(--hologram);
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                    z-index: 10000;
                    transform: translateX(400px);
                    transition: transform 0.3s ease-out;
                    backdrop-filter: blur(10px);
                    max-width: 300px;
                    display: flex;
                    align-items: center;
                    gap: 15px;
                `;
                
                notification.innerHTML = `
                    <i class="fas fa-${{type === 'success' ? 'check-circle' : 'info-circle'}}" style="color: ${{colors[type]}}; font-size: 1.2rem;"></i>
                    <div>
                        <strong style="color: ${{colors[type]}};">${{type.toUpperCase()}}</strong>
                        <div style="margin-top: 5px;">${{message}}</div>
                    </div>
                `;
                
                document.body.appendChild(notification);
                
                setTimeout(() => {{
                    notification.style.transform = 'translateX(0)';
                }}, 10);
                
                setTimeout(() => {{
                    notification.style.transform = 'translateX(400px)';
                    setTimeout(() => notification.remove(), 300);
                }}, 5000);
                
                notification.addEventListener('click', () => {{
                    notification.style.transform = 'translateX(400px)';
                    setTimeout(() => notification.remove(), 300);
                }});
            }}
            
            // Auto-refresh leaderboard every 60 seconds
            setInterval(loadLeaderboard, 60000);
            
            // Initialize on load
            document.addEventListener('DOMContentLoaded', function() {{
                // Add hover effect for key display
                const keyDisplay = document.getElementById('apiKeyDisplay');
                if (keyDisplay) {{
                    keyDisplay.addEventListener('mouseenter', function() {{
                        this.style.textShadow = '0 0 20px rgba(0, 255, 157, 0.8)';
                    }});
                    
                    keyDisplay.addEventListener('mouseleave', function() {{
                        this.style.textShadow = 'none';
                    }});
                    
                    // Click to copy
                    keyDisplay.addEventListener('click', copyKey);
                }}
                
                // Add some interactive effects
                const statCards = document.querySelectorAll('.stat-card');
                statCards.forEach(card => {{
                    card.addEventListener('mouseenter', function() {{
                        this.style.transform = 'translateY(-10px) scale(1.05)';
                    }});
                    
                    card.addEventListener('mouseleave', function() {{
                        this.style.transform = 'translateY(0) scale(1)';
                    }});
                }});
                
                // Add pulse animation to user avatar
                const userAvatar = document.querySelector('.user-avatar');
                if (userAvatar) {{
                    setInterval(() => {{
                        userAvatar.style.boxShadow = '0 0 20px rgba(157, 0, 255, 0.7)';
                        setTimeout(() => {{
                            userAvatar.style.boxShadow = '0 0 15px rgba(157, 0, 255, 0.5)';
                        }}, 1000);
                    }}, 3000);
                }}
            }});
        </script>
    </body>
    </html>
    '''
    
    return dashboard_html

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

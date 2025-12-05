# discord_bot.py - SoT TDM Discord Bot
import os
import json
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
from datetime import datetime
import typing

# Configuration
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
SERVER_URL = os.environ.get('SERVER_URL', 'http://localhost:5000')
if not DISCORD_TOKEN:
    print("❌ Error: DISCORD_TOKEN environment variable required")
    exit(1)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def api_request(method, endpoint, data=None):
    """Make API request to render server"""
    url = f"{SERVER_URL}{endpoint}"
    
    async with aiohttp.ClientSession() as session:
        try:
            if method == 'GET':
                async with session.get(url) as response:
                    return await response.json()
            elif method == 'POST':
                async with session.post(url, json=data) as response:
                    return await response.json()
        except Exception as e:
            print(f"❌ API request failed: {e}")
            return None

async def send_scoreboard_embed(channel, room_code):
    """Send scoreboard embed to channel"""
    data = await api_request('GET', f'/api/scoreboard/{room_code}')
    
    if not data or 'error' in data:
        embed = discord.Embed(
            title="Error",
            description=f"Could not fetch scoreboard for room {room_code}",
            color=0xff0000
        )
        await channel.send(embed=embed)
        return
    
    embed = discord.Embed(
        title=data.get('title', f'SoT TDM - Room {room_code}'),
        description=data.get('description', ''),
        color=data.get('color', 0x00ff00),
        timestamp=datetime.utcnow()
    )
    
    for field in data.get('fields', []):
        embed.add_field(
            name=field['name'],
            value=field['value'],
            inline=field.get('inline', False)
        )
    
    if 'footer' in data:
        embed.set_footer(text=data['footer']['text'])
    
    await channel.send(embed=embed)

# =============================================================================
# SLASH COMMANDS
# =============================================================================

@bot.tree.command(name="register", description="Register your Discord for SoT TDM")
async def register(interaction: discord.Interaction):
    """Register Discord user with TDM system"""
    await interaction.response.defer(thinking=True)
    
    data = {
        'discord_id': str(interaction.user.id),
        'username': interaction.user.name
    }
    
    result = await api_request('POST', '/api/register', data)
    
    if result and 'error' not in result:
        embed = discord.Embed(
            title="✅ Registration Successful",
            description=f"Registered **{interaction.user.name}** for SoT TDM",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Player ID", value=result['player_id'], inline=False)
        embed.add_field(name="Stats", value=f"Kills: {result['kills']} | Deaths: {result['deaths']}", inline=False)
        embed.set_footer(text="Use /stats to see your progress")
    else:
        embed = discord.Embed(
            title="❌ Registration Failed",
            description=result.get('error', 'Unknown error'),
            color=0xff0000
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="scoreboard", description="Show TDM scoreboard for a room")
@app_commands.describe(room_code="Room code (e.g., ABC123)")
async def scoreboard(interaction: discord.Interaction, room_code: str):
    """Display live scoreboard for a match"""
    await interaction.response.defer(thinking=True)
    await send_scoreboard_embed(interaction.channel, room_code.upper())
    await interaction.followup.send("Scoreboard updated!")

@bot.tree.command(name="stats", description="Show your TDM statistics")
@app_commands.describe(player="Optional: Another player to check (mention)")
async def stats(interaction: discord.Interaction, player: typing.Optional[discord.Member] = None):
    """Show player statistics"""
    await interaction.response.defer(thinking=True)
    
    target = player or interaction.user
    discord_id = str(target.id)
    
    result = await api_request('GET', f'/api/stats/{discord_id}')
    
    if not result or 'error' in result:
        embed = discord.Embed(
            title="❌ Player Not Found",
            description=f"{target.mention} is not registered. Use `/register` first.",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed)
        return
    
    stats_data = result['global_stats']
    
    embed = discord.Embed(
        title=f"📊 TDM Stats - {result['username']}",
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    
    # Global stats
    embed.add_field(name="Kills", value=stats_data['kills'], inline=True)
    embed.add_field(name="Deaths", value=stats_data['deaths'], inline=True)
    embed.add_field(name="K/D Ratio", value=stats_data['kd_ratio'], inline=True)
    embed.add_field(name="Matches", value=stats_data['matches_played'], inline=True)
    embed.add_field(name="Wins", value=stats_data['wins'], inline=True)
    embed.add_field(name="Win Rate", value=f"{stats_data['win_rate']}%", inline=True)
    
    # Recent matches
    if result['recent_matches']:
        matches_text = []
        for match in result['recent_matches'][:5]:  # Last 5 matches
            status = "✅" if match['won'] else "❌"
            matches_text.append(f"{status} {match['room_code']} - {match['kills']}/{match['deaths']} K/D")
        
        embed.add_field(
            name="Recent Matches",
            value="\n".join(matches_text) or "No matches played",
            inline=False
        )
    
    embed.set_thumbnail(url=target.avatar.url if target.avatar else None)
    embed.set_footer(text=f"Player ID: {discord_id}")
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="history", description="Show recent TDM matches")
async def history(interaction: discord.Interaction):
    """Show recent match history"""
    await interaction.response.defer(thinking=True)
    
    result = await api_request('GET', '/api/history')
    
    if not result or 'error' in result:
        embed = discord.Embed(
            title="❌ Error",
            description="Could not fetch match history",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="📜 Recent TDM Matches",
        color=0x00ff00,
        timestamp=datetime.utcnow()
    )
    
    if result['matches']:
        for match in result['matches'][:5]:  # Last 5 matches
            winner = f"**{match['winning_team'].upper()}**" if match['winning_team'] else "Draw"
            duration = f"{match['duration'] // 60}:{match['duration'] % 60:02d}" if match['duration'] else "N/A"
            
            embed.add_field(
                name=f"Room {match['room_code']}",
                value=f"Score: **{match['team1_score']}** - **{match['team2_score']}**\n"
                      f"Winner: {winner}\n"
                      f"Duration: {duration}\n"
                      f"Players: {match['player_count']}",
                inline=True
            )
    else:
        embed.description = "No matches played yet"
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    """Show help message"""
    embed = discord.Embed(
        title="🎯 SoT TDM Bot Commands",
        description="Team Deathmatch tracking for Sea of Thieves",
        color=0x00ff00
    )
    
    commands_list = [
        ("`/register`", "Register your Discord for TDM tracking"),
        ("`/scoreboard <code>`", "Show live scoreboard for a room"),
        ("`/stats [player]`", "Show player statistics"),
        ("`/history`", "Show recent match history"),
        ("`/help`", "Show this help message")
    ]
    
    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="🔗 Client Setup",
        value="1. Download SoT HUD Client\n"
              "2. Enter room code to join match\n"
              "3. Kills/deaths auto-report to server\n"
              "4. View scoreboards here with `/scoreboard`",
        inline=False
    )
    
    embed.set_footer(text="First to 10 points wins | Team wipe = +1 point")
    
    await interaction.response.send_message(embed=embed)

# =============================================================================
# BOT EVENTS
# =============================================================================

@bot.event
async def on_ready():
    """Bot startup"""
    print(f"✅ Discord bot logged in as {bot.user}")
    print(f"🔗 Server URL: {SERVER_URL}")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

# =============================================================================
# BOT STARTUP
# =============================================================================

if __name__ == "__main__":
    print("🤖 Starting Discord bot...")
    bot.run(DISCORD_TOKEN)
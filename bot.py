import os
import discord
import yt_dlp
import asyncio
import re
import subprocess
import unicodedata
import sys
import locale
import time
import shutil
import json
import pytz
import logging
import urllib.request
import spotipy
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pathlib import Path
from discord.ext import tasks
from collections import deque
from datetime import datetime
from pytz import timezone
from scripts.commandlogger import CommandLogger
from scripts.downloadprogress import DownloadProgress
from scripts.constants import RED, GREEN, BLUE, RESET
from scripts.musicbot import MusicBot, PlaylistHandler, AfterPlayingHandler, SpotifyHandler
from scripts.play_next import play_next
from scripts.ui_components import NowPlayingView
from scripts.process_queue import process_queue
from scripts.clear_queue import clear_queue
from scripts.format_size import format_size
from scripts.duration import get_audio_duration
from scripts.url_identifier import is_url, is_playlist_url, is_radio_stream
from scripts.handle_playlist import PlaylistHandler
from scripts.after_playing_coro import AfterPlayingHandler
from scripts.handle_spotify import SpotifyHandler
from scripts.config import load_config, YTDL_OPTIONS, FFMPEG_OPTIONS
from scripts.logging import setup_logging, get_ytdlp_logger
from scripts.updatescheduler import check_updates, update_checker
from scripts.voice import join_voice_channel, leave_voice_channel, handle_voice_state_update
from scripts.inactivity import start_inactivity_checker, check_inactivity
from scripts.messages import update_or_send_message, create_embed
from spotipy.oauth2 import SpotifyClientCredentials
from scripts.ytdlp import get_ytdlp_path, ytdlp_version
from scripts.ffmpeg import check_ffmpeg_in_path, install_ffmpeg_windows, install_ffmpeg_macos, install_ffmpeg_linux, get_ffmpeg_path
from scripts.cleardownloads import clear_downloads_folder
from scripts.restart import restart_bot
from scripts.load_commands import load_commands
from scripts.load_scripts import load_scripts
from scripts.activity import update_activity
from scripts.spotify import get_spotify_album_details, get_spotify_track_details, get_spotify_playlist_details
from scripts.priority import set_high_priority
from scripts.paths import get_downloads_dir, get_root_dir, get_absolute_path

# Load environment variables
load_dotenv()

# Load configuration
config_vars = load_config()
OWNER_ID = config_vars['OWNER_ID']
PREFIX = config_vars['PREFIX']
LOG_LEVEL = config_vars['LOG_LEVEL']
INACTIVITY_TIMEOUT = config_vars['INACTIVITY_TIMEOUT']
AUTO_LEAVE_EMPTY = config_vars['AUTO_LEAVE_EMPTY']
DEFAULT_VOLUME = config_vars['DEFAULT_VOLUME']
AUTO_CLEAR_DOWNLOADS = config_vars['AUTO_CLEAR_DOWNLOADS']
SHOW_PROGRESS_BAR = config_vars['SHOW_PROGRESS_BAR']
# Set up logging
setup_logging(LOG_LEVEL)

YTDLP_PATH = get_ytdlp_path()
FFMPEG_PATH = get_ffmpeg_path()

ROOT_DIR = Path(get_root_dir())
DOWNLOADS_DIR = ROOT_DIR / get_downloads_dir()
OWNER_ID = OWNER_ID

if not DOWNLOADS_DIR.exists():
    DOWNLOADS_DIR.mkdir()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True,
    owner_id=int(OWNER_ID)
)

command_logger = CommandLogger()

@bot.event
async def on_command(ctx):
    """Log commands when they are used"""
    command_name = ctx.command.name if ctx.command else "unknown"
    full_command = ctx.message.content
    username = str(ctx.author)
    command_logger.log_command(username, full_command)

@bot.event
async def on_command_error(ctx, error):
    print(f"Error in command {ctx.command}: {str(error)}")
    await ctx.send(
        embed=create_embed(
            "Error",
            f"Error: {str(error)}",
            color=0xe74c3c,
            ctx=ctx
        )
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Error: {str(error)}")

@bot.event
async def on_voice_state_update(member, before, after):
    """Event handler for voice state updates"""
    global music_bot
    await handle_voice_state_update(music_bot, member, before, after)

music_bot = None
@bot.event
async def on_ready():
    """Called when the bot is ready"""
    global music_bot 
    clear_downloads_folder()
    set_high_priority()
    prefix = config_vars.get('PREFIX', '!')  # Get prefix from config
    from scripts.activity import update_activity
    await update_activity(bot)
    owner_name = f"{RED}Not found.\nOwner could not be fetched. Do you share a server with the bot?\nPlease check your config.json{RESET}"
    try:
        owner = await bot.fetch_user(OWNER_ID)
        owner_name = f"{BLUE}{owner.name}{RESET}"
    except discord.NotFound:
        pass
    except Exception as e:
        owner_name = f"{RED}Error contacting owner: {str(e)}{RESET}"

    with open('scripts/consoleprint.txt', 'r') as f: print(f"{BLUE}{f.read()}{RESET}")
    commit_count = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD']).decode('utf-8').strip()
    print(f"{GREEN}\nCurrent commit count: {BLUE}{commit_count}{RESET}")
    print(f"{GREEN}YT-DLP version: {BLUE}{yt_dlp.version.__version__}{RESET}")
    print(f"----------------------------------------")
    print(f"{GREEN}Logged in as {RESET}{BLUE}{bot.user.name}")
    print(f"{GREEN}Bot ID: {RESET}{BLUE}{bot.user.id}")
    print(f"{GREEN}Bot Invite URL: {RESET}{BLUE}{discord.utils.oauth_url(bot.user.id)}{RESET}")
    print(f"----------------------------------------")
    print(f"{GREEN}Loaded configuration:{RESET}")
    print(f"{GREEN}Owner ID:{RESET} {BLUE}{OWNER_ID}{RESET} ")
    print(f"{GREEN}Owner name:{RESET} {BLUE}{owner_name}{RESET}")
    print(f"{GREEN}Command Prefix:{RESET} {BLUE}{PREFIX}{RESET} ")
    config = load_config()
    auto_update = config.get('AUTO_UPDATE', True)
    status_color = GREEN if auto_update else RED
    prefix = config_vars['PREFIX']
    disabled_msg = f'Disabled. To update your instance - use {prefix}update'
    update_msg = f"{GREEN}Auto update: {BLUE if auto_update else RED}{'Enabled' if auto_update else disabled_msg}{RESET}"
    print(update_msg)
    print(f"{GREEN}SponsorBlock:{RESET} {BLUE if config.get('SPONSORBLOCK', False) else RED}{'Enabled' if config.get('SPONSORBLOCK', False) else 'Disabled'}{RESET}")
    print(f"{GREEN}Clear downloads:{RESET} {BLUE if config.get('AUTO_CLEAR_DOWNLOADS', False) else RED}{'Enabled' if config.get('AUTO_CLEAR_DOWNLOADS', False) else 'Disabled'}{RESET} - {RED if config.get('AUTO_CLEAR_DOWNLOADS', False) else GREEN}Caching is {'disabled' if config.get('AUTO_CLEAR_DOWNLOADS', False) else 'enabled'}{RESET}")

    # Load scripts and commands
    load_scripts()
    await load_commands(bot)
    update_checker.start(bot) 
    if not music_bot:
        music_bot = MusicBot()
        await music_bot.setup(bot)

bot.remove_command('help')
bot.run(os.getenv('DISCORD_TOKEN'))
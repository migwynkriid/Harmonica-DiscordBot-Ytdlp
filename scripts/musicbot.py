import aiohttp
import asyncio
import discord
import json
import locale
import logging
import os
import pytz
import re
import shutil
import spotipy
import subprocess
import sys
import time
import unicodedata
import urllib.request
import yt_dlp
from collections import deque
from datetime import datetime
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pathlib import Path
from pytz import timezone
from scripts.constants import RED, GREEN, BLUE, RESET, YELLOW
from scripts.activity import update_activity
from scripts.after_playing_coro import AfterPlayingHandler
from scripts.cleardownloads import clear_downloads_folder
from scripts.clear_queue import clear_queue
from scripts.config import load_config, YTDL_OPTIONS, FFMPEG_OPTIONS, BASE_YTDL_OPTIONS
from scripts.downloadprogress import DownloadProgress
from scripts.duration import get_audio_duration
from scripts.format_size import format_size
from scripts.handle_playlist import PlaylistHandler
from scripts.handle_spotify import SpotifyHandler
from scripts.inactivity import start_inactivity_checker, check_inactivity
from scripts.load_commands import load_commands
from scripts.load_scripts import load_scripts
from scripts.logging import setup_logging, get_ytdlp_logger
from scripts.messages import update_or_send_message, create_embed
from scripts.play_next import play_next
from scripts.process_queue import process_queue
from scripts.restart import restart_bot
from scripts.spotify import get_spotify_album_details, get_spotify_track_details, get_spotify_playlist_details
from scripts.ui_components import NowPlayingView
from scripts.updatescheduler import check_updates, update_checker
from scripts.url_identifier import is_url, is_playlist_url, is_radio_stream, is_youtube_channel
from scripts.voice import join_voice_channel, leave_voice_channel, handle_voice_state_update
from scripts.ytdlp import get_ytdlp_path, ytdlp_version
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.cache_handler import CacheFileHandler
from scripts.caching import playlist_cache

config_vars = load_config()
INACTIVITY_TIMEOUT = config_vars.get('INACTIVITY_TIMEOUT', 60)

class MusicBot(PlaylistHandler, AfterPlayingHandler, SpotifyHandler):
    def __init__(self):
        """Initialize the music bot"""
        self.queue = []
        self.current_song = None
        self.is_playing = False
        self.voice_client = None
        self.waiting_for_song = False
        self.queue_lock = asyncio.Lock()
        self.download_queue = asyncio.Queue()
        self.currently_downloading = False
        self.command_queue = asyncio.Queue()
        self.command_processor_task = None
        self.download_lock = asyncio.Lock()
        self.bot_loop = None
        self.queued_messages = {}
        self.current_command_msg = None
        self.current_command_author = None
        self.status_messages = {}
        self.now_playing_message = None
        self.downloads_dir = Path(__file__).parent.parent / 'downloads'
        self.cookie_file = Path(__file__).parent.parent / 'cookies.txt'
        self.playback_start_time = None  # Track when the current song started playing
        self.in_progress_downloads = {}  # Track downloads in progress
        if not self.downloads_dir.exists():
            self.downloads_dir.mkdir()
        self.last_activity = time.time()
        self.inactivity_timeout = INACTIVITY_TIMEOUT
        self.inactivity_leave = config_vars.get('INACTIVITY_LEAVE', True)
        self._inactivity_task = None
        self.last_update = 0
        self._last_progress = -1
        self.last_known_ctx = None
        self.bot = None
        self.was_skipped = False  # Add flag to track if song was skipped
        self.cache_dir = Path(__file__).parent.parent / '.cache'
        self.spotify_cache = self.cache_dir / 'spotify'
        self.should_stop_downloads = False  # Flag to control download cancellation
        self.current_download_task = None  # Track current download task
        self.current_ydl = None  # Track current YoutubeDL instance
        self.duration_cache = {}  # Cache for storing audio durations
        
        # Create cache directories if they don't exist
        self.cache_dir.mkdir(exist_ok=True)
        self.spotify_cache.mkdir(exist_ok=True)

        load_dotenv(dotenv_path=".spotifyenv")
        client_id = os.getenv('SPOTIPY_CLIENT_ID')
        client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
        
        print(f"{GREEN}Spotify credentials found:{RESET} {BLUE if (client_id and client_secret) else RED}{'Yes' if (client_id and client_secret) else 'No'}{RESET}")
        
        if not client_id or not client_secret:
            print(f"{RED}Warning: Spotify credentials not found. Spotify functionality will be unavailable.{RESET}")
            print(f"{BLUE}https://developer.spotify.com/documentation/web-api/concepts/apps{RESET}")
            print(f"{BLUE}Update your {RESET}{YELLOW}.spotifyenv file{RESET}\n")
            self.sp = None
        else:
            try:
                cache_handler = CacheFileHandler(
                    cache_path=str(self.spotify_cache / '.spotify-token-cache')
                )
                client_credentials_manager = SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret,
                    cache_handler=cache_handler
                )
                self.sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
            except Exception as e:
                print(f"{RED}Error initializing Spotify client: {str(e)}{RESET}")
                self.sp = None

        if self.cookie_file.exists():
            print(f"{GREEN}YouTube cookies found:{RESET} {BLUE}Yes{RESET}")
        else:
            print(f"{GREEN}YouTube cookies found:{RESET} {RED}No{RESET}")
            print(f"{RED}Warning: YouTube cookies not found, YouTube functionality might be limited.{RESET}")
            print(f'{BLUE}Extract using "Get Cookies" extension and save it as cookies.txt in the root directory where you run the bot.{RESET}')
            print(f"{BLUE}https://github.com/yt-dlp/yt-dlp/wiki/How-to-use-cookies{RESET}\n")
            
        # Check for Genius lyrics token
        genius_token_file = Path(__file__).parent.parent / '.geniuslyrics'
        if genius_token_file.exists():
            with open(genius_token_file, 'r') as f:
                content = f.read().strip()
                has_token = content and not content.endswith('=')
            print(f"{GREEN}Genius lyrics token found:{RESET} {BLUE if has_token else RED}{'Yes' if has_token else 'No'}{RESET}")
            if not has_token:
                print(f"{RED}Warning: Genius lyrics token not found.\n{BLUE}AZLyrics will be used as a fallback.{RESET}")
                print(f"{BLUE}https://genius.com/api-clients{RESET}")
                print(f'{BLUE}Update your {RESET}{YELLOW}.geniuslyrics file{RESET}')

    async def setup(self, bot_instance):
        """Setup the bot with the event loop"""
        self.bot = bot_instance
        self.bot_loop = asyncio.get_event_loop()
        await self.start_command_processor()
        await start_inactivity_checker(self)
        asyncio.create_task(self.process_download_queue())
        self.bot.add_view(NowPlayingView())

    async def start_command_processor(self):
        """Start the command processor task"""
        if self.command_processor_task is None:
            self.command_processor_task = asyncio.create_task(self.process_command_queue())
            print('----------------------------------------')
        
        # Config file
        print(f"{GREEN}Config file location:{RESET} {BLUE}{Path(__file__).parent.parent / 'config.json'}{RESET}")

    async def process_command_queue(self):
        """Process commands from the queue one at a time"""
        while True:
            try:
                command_info = await self.command_queue.get()
                self.last_activity = time.time()
                ctx, query = command_info
                print(f"Processing command: {load_config()['PREFIX']}play {query}")

                try:
                    await self._handle_play_command(ctx, query)
                except Exception as e:
                    print(f"Error processing command: {e}")
                    error_embed = create_embed("Error", f"Failed to process command: {str(e)}", color=0xe74c3c, ctx=ctx)
                    await self.update_or_send_message(ctx, error_embed)
                finally:
                    self.command_queue.task_done()
            except Exception as e:
                print(f"Error in command processor: {str(e)}")
                await asyncio.sleep(1)

    async def _handle_play_command(self, ctx, query):
        """Internal method to handle a single play command"""
        if not ctx.voice_client and not await self.join_voice_channel(ctx):
            raise Exception("Could not join voice channel")
        self.last_activity = time.time()

        # Check if this query is already being downloaded
        if query in self.in_progress_downloads:
            print(f"Query '{query}' already downloading - queueing duplicate request")
            if self.in_progress_downloads[query]:  # If we have the song info
                song_info = self.in_progress_downloads[query]
                self.queue.append(song_info)
                queue_embed = create_embed(
                    "Added to Queue 🎵", 
                    f"[ {song_info['title']}]({song_info['url']})",
                    color=0x3498db,
                    thumbnail_url=song_info.get('thumbnail'),
                    ctx=ctx
                )
                queue_msg = await ctx.send(embed=queue_embed)
                self.queued_messages[song_info['url']] = queue_msg
            return

        processing_embed = create_embed(
            "Processing",
            f"Searching for {query}",
            color=0x3498db,
            ctx=ctx
        )
        status_msg = await self.update_or_send_message(ctx, processing_embed)
        download_info = {
            'query': query,
            'ctx': ctx,
            'status_msg': status_msg
        }
        await self.download_queue.put(download_info)
        print(f"Added to download queue: {query}")

    async def process_download_queue(self):
        """Process the download queue sequentially"""
        while True:
            try:
                download_info = await self.download_queue.get()               
                query = download_info['query']
                ctx = download_info['ctx']
                status_msg = download_info['status_msg']

                try:
                    async with self.download_lock:
                        self.currently_downloading = True
                        print(f"Starting download: {query}")
                        self.in_progress_downloads[query] = None  # Mark as downloading but no info yet
                        result = await self.download_song(query, status_msg=status_msg, ctx=ctx)
                        if result:
                            self.in_progress_downloads[query] = result  # Store the song info
                        if not result:
                            if not status_msg:
                                error_embed = create_embed("Error", "Failed to download song", color=0xe74c3c, ctx=ctx)
                                await self.update_or_send_message(ctx, error_embed)
                            continue
                        if status_msg and not result.get('is_from_playlist'):
                            try:
                                message_exists = True
                                try:
                                    await status_msg.fetch()
                                except discord.NotFound:
                                    message_exists = False               
                                if message_exists:
                                    await status_msg.delete()
                            except Exception as e:
                                print(f"Note: Could not delete processing message: {e}")
                        else:
                            if status_msg:
                                playlist_embed = create_embed(
                                    "Adding Playlist",
                                    f"Adding {len(result['entries'])} songs to queue...",
                                    color=0x3498db,
                                    ctx=ctx
                                )
                                await status_msg.edit(embed=playlist_embed)
                        if self.voice_client and self.voice_client.is_playing():
                            self.queue.append(result)
                            if not result.get('is_from_playlist'):
                                queue_embed = create_embed(
                                    "Added to Queue 🎵", 
                                    f"[ {result['title']}]({result['url']})",
                                    color=0x3498db,
                                    thumbnail_url=result.get('thumbnail'),
                                    ctx=ctx
                                )
                                queue_msg = await ctx.send(embed=queue_embed)
                                self.queued_messages[result['url']] = queue_msg
                        else:
                            self.queue.append(result)
                            await play_next(ctx)
                except Exception as e:
                    print(f"Error processing download: {str(e)}")
                    if status_msg:
                        error_embed = create_embed(
                            "Error ❌",
                            str(e),
                            color=0xe74c3c,
                            ctx=ctx if ctx else status_msg.channel
                        )
                        await status_msg.edit(embed=error_embed)
                    return None
                finally:
                    self.currently_downloading = False
                    self.download_queue.task_done()
            except Exception as e:
                print(f"Error in download queue processor: {str(e)}")
                await asyncio.sleep(1)

    async def cancel_downloads(self, disconnect_voice=True):
        """
        Cancel all active downloads and clear the download queue
        
        Args:
            disconnect_voice (bool): Whether to disconnect from voice chat after canceling downloads
        """
        self.should_stop_downloads = True
        
        # Cancel current download task if it exists
        if self.current_download_task and not self.current_download_task.done():
            self.current_download_task.cancel()
            try:
                await self.current_download_task
            except (asyncio.CancelledError, Exception):
                pass

        # Force close current yt-dlp instance if it exists
        if self.current_ydl:
            try:
                # Try to abort the current download
                if hasattr(self.current_ydl, '_download_retcode'):
                    self.current_ydl._download_retcode = 1
                # Close the instance
                self.current_ydl.close()
            except Exception as e:
                print(f"Error closing yt-dlp instance: {e}")
        
        # Clear the download queue
        while not self.download_queue.empty():
            try:
                self.download_queue.get_nowait()
                self.download_queue.task_done()
            except asyncio.QueueEmpty:
                break
                
        # Clear any incomplete downloads from the queue
        self.queue = [song for song in self.queue if not isinstance(song.get('file_path'), type(None))]
        
        # Clear in-progress downloads tracking
        self.in_progress_downloads.clear()
        
        # Wait a moment for any active downloads to notice the cancellation flag
        await asyncio.sleep(0.5)
        self.should_stop_downloads = False
        self.current_download_task = None

        # Stop any current playback
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        
        # Clear the queue and disconnect if requested
        self.queue.clear()
        if disconnect_voice:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect()
            
            # Reset the music bot state
            self.current_song = None
            self.is_playing = False
            await update_activity(self.bot, self.current_song, self.is_playing)

    def _download_hook(self, d):
        """Custom download hook that checks for cancellation"""
        if self.should_stop_downloads:
            raise Exception("Download cancelled by user")
        return d

    def create_progress_bar(self, percentage, length=10):
        """Create a progress bar with the given percentage"""
        filled = int(length * (percentage / 100))
        bar = '█' * filled + '░' * (length - filled)
        return f"[{bar}] {percentage}%"

    async def download_song(self, query, status_msg=None, ctx=None, skip_url_check=False):
        """Download a song from YouTube, Spotify, or handle radio stream"""
        if not skip_url_check and is_url(query):
            if is_youtube_channel(query):
                if status_msg:
                    await status_msg.edit(embed=create_embed(
                        "Error",
                        "Channel links are not supported.",
                        color=0xe74c3c,
                        ctx=ctx
                    ))
                return None

        try:
            # Check cache first for YouTube videos
            if 'youtube.com/watch' in query or 'youtu.be/' in query:
                video_id = None
                if 'youtube.com/watch' in query:
                    video_id = query.split('watch?v=')[1].split('&')[0]
                elif 'youtu.be/' in query:
                    video_id = query.split('youtu.be/')[1].split('?')[0]
                
                if video_id:
                    cached_info = playlist_cache.get_cached_info(video_id)
                    if cached_info and os.path.exists(cached_info['file_path']):
                        print(f"{GREEN}Found cached YouTube file: {video_id} - {cached_info.get('title', 'Unknown')}{RESET}")
                        if status_msg:
                            await status_msg.delete()
                        return {
                            'title': cached_info.get('title', 'Unknown'),  # Use cached title
                            'url': query,
                            'file_path': cached_info['file_path'],
                            'thumbnail': cached_info.get('thumbnail'),
                            'is_stream': False,
                            'is_from_playlist': is_playlist_url(query),
                            'ctx': status_msg.channel if status_msg else None,
                            'is_from_cache': True
                        }

            # If not in cache or not a YouTube video, proceed with normal download
            self._last_progress = -1
            if not skip_url_check:
                if is_playlist_url(query):
                    ctx = ctx or status_msg.channel if status_msg else None
                    await self._handle_playlist(query, ctx, status_msg)
                    return None
                if 'open.spotify.com/' in query:
                    if 'track/' in query:
                        spotify_details = await get_spotify_track_details(query)
                        if spotify_details:
                            query = spotify_details
                        else:
                            if status_msg:
                                await status_msg.edit(
                                    embed=create_embed(
                                        "Error",
                                        "Could not retrieve details from Spotify URL.",
                                        color=0xe74c3c,
                                        ctx=status_msg.channel
                                    )
                                )
                            return None
                    elif 'album/' in query:
                        tracks = await get_spotify_album_details(query)
                        first_song = None
                        for track in tracks:
                            print(f"Processing track: {track}")
                            song_info = await self.download_song(track, status_msg, ctx)
                            if song_info:
                                # Set requester information for each track
                                song_info['requester'] = ctx.author if ctx else None
                                if not first_song:
                                    first_song = song_info
                                else:
                                    async with self.queue_lock:
                                        self.queue.append(song_info)
                                        print(f"Added to queue: {song_info['title']}")
                        return first_song
                    elif 'playlist/' in query:
                        tracks = await get_spotify_playlist_details(query)
                        first_song = None
                        for track in tracks:
                            print(f"Processing track: {track}")
                            song_info = await self.download_song(track, status_msg, ctx)
                            if song_info:
                                # Set requester information for each track
                                song_info['requester'] = ctx.author if ctx else None
                                if not first_song:
                                    first_song = song_info
                                else:
                                    async with self.queue_lock:
                                        self.queue.append(song_info)
                                        print(f"Added to queue: {song_info['title']}")
                        return first_song

                if is_radio_stream(query):
                    print("Radio stream detected")
                    try:
                        stream_name = query.split('/')[-1].split('.')[0]
                        result = {
                            'title': stream_name,
                            'url': query,
                            'file_path': query,  
                            'is_stream': True,
                            'thumbnail': None
                        }
                        if status_msg:
                            await status_msg.delete()
                        return result
                    except Exception as e:
                        print(f"Error processing radio stream: {str(e)}")
                        if status_msg:
                            await status_msg.edit(
                                embed=create_embed(
                                    "Error",
                                    f"Failed to process radio stream: {str(e)}",
                                    color=0xe74c3c,
                                    ctx=status_msg.channel
                                )
                            )
                        return None

            if not self.downloads_dir.exists():
                self.downloads_dir.mkdir()
                
            # Create DownloadProgress instance with ctx
            progress = DownloadProgress(status_msg, None)
            progress.ctx = ctx or (status_msg.channel if status_msg else None)
            
            async def extract_info(ydl, url, download=True):
                """Wrap yt-dlp extraction in a cancellable task"""
                try:
                    self.current_ydl = ydl
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=download))
                finally:
                    self.current_ydl = None

            try:
                # Initialize default options
                ydl_opts = {**BASE_YTDL_OPTIONS}
                is_youtube_mix = False
                
                # Check if the input is a URL
                if is_url(query):
                    # Convert YouTube watch URL to live URL if it's a livestream
                    if 'youtube.com/watch' in query:
                        video_id = query.split('watch?v=')[1].split('&')[0]
                        # First check if it's a livestream without downloading
                        with yt_dlp.YoutubeDL({
                            **ydl_opts,
                            'extract_flat': True,
                            'quiet': True
                        }) as ydl:
                            try:
                                info = ydl.extract_info(query, download=False)
                                is_live = info.get('is_live', False) or info.get('live_status') in ['is_live', 'post_live', 'is_upcoming']
                                if is_live:
                                    query = f"https://www.youtube.com/live/{video_id}"
                            except Exception as e:
                                print(f"Error checking livestream status: {str(e)}")
                    
                    # Handle YouTube Mix playlists
                    is_youtube_mix = 'start_radio=1' in query or 'list=RD' in query
                    if is_youtube_mix:
                        ydl_opts['playlistend'] = config_vars.get('MIX_PLAYLIST_LIMIT', 50)
                else:
                    # If it's not a URL, treat it as a search term
                    query = f"ytsearch1:{query}"  # Only get the first result
                    ydl_opts['noplaylist'] = True  # Never process playlists for search queries

                # Skip pre-check for direct YouTube watch URLs (no playlist/mix)
                is_direct_watch = ('youtube.com/watch' in query or 'youtu.be/' in query) and not is_youtube_mix
                
                if not is_direct_watch and is_url(query):
                    # First, extract info without downloading to check if it's a livestream or mix
                    with yt_dlp.YoutubeDL({
                        **ydl_opts, 
                        'extract_flat': True,
                        'noplaylist': not is_youtube_mix  # Allow playlist only for Mix URLs
                    }) as ydl:
                        self.current_download_task = asyncio.create_task(extract_info(ydl, query, download=False))
                        try:
                            info_dict = await self.current_download_task
                            # Enhanced livestream detection
                            is_live = (
                                info_dict.get('is_live', False) or 
                                info_dict.get('live_status') in ['is_live', 'post_live', 'is_upcoming']
                            )

                            if is_live:
                                print(f"Livestream detected: {query}")
                                # Convert watch URL to live URL if needed
                                webpage_url = info_dict.get('webpage_url', query)
                                if 'youtube.com/watch' in webpage_url:
                                    video_id = info_dict.get('id', webpage_url.split('watch?v=')[1].split('&')[0])
                                    query = f"https://www.youtube.com/live/{video_id}"
                                    # Re-extract info with the live URL
                                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                        self.current_download_task = asyncio.create_task(extract_info(ydl, query, download=False))
                                        info_dict = await self.current_download_task

                                # Clean up the title by removing date, time and (live) suffix if present
                                title = info_dict.get('title', 'Livestream')
                                if title.endswith(datetime.now().strftime("%Y-%m-%d %H:%M")):
                                    title = title.rsplit(' ', 2)[0]  # Remove the date and time
                                if title.endswith('(live)'):
                                    title = title[:-6].strip()  # Remove (live) suffix
                                result = {
                                    'title': title,
                                    'url': query,
                                    'file_path': info_dict.get('url', query),
                                    'is_stream': True,
                                    'is_live': True,
                                    'thumbnail': info_dict.get('thumbnail'),
                                    'duration': None
                                }
                                if status_msg:
                                    await status_msg.delete()
                                return result

                            # Handle YouTube Mix playlist
                            if is_youtube_mix and info_dict.get('_type') == 'playlist':
                                print(f"YouTube Mix playlist detected: {query}")
                                entries = info_dict.get('entries', [])
                                if entries:
                                    total_videos = len(entries)
                                    playlist_title = info_dict.get('title', 'YouTube Mix')
                                    playlist_url = info_dict.get('webpage_url', query)
                                    
                                    if status_msg:
                                        description = f"[{playlist_title}]({playlist_url})\nEntries: {total_videos}\n\nThis might take a while..."
                                        playlist_embed = create_embed(
                                            "Processing YouTube Mix",
                                            description,
                                            color=0x3498db,
                                            ctx=progress.ctx
                                        )
                                        # Get thumbnail from first entry
                                        if entries and entries[0]:
                                            first_entry = entries[0]
                                            thumbnail_url = first_entry.get('thumbnails', [{}])[0].get('url') if first_entry.get('thumbnails') else None
                                            if not thumbnail_url:
                                                thumbnail_url = first_entry.get('thumbnail')
                                            if thumbnail_url:
                                                playlist_embed.set_thumbnail(url=thumbnail_url)
                                        await status_msg.edit(embed=playlist_embed)
                                        await status_msg.delete(delay=10)

                                    # Process the first song immediately
                                    first_entry = entries[0]
                                    first_video_url = f"https://youtube.com/watch?v={first_entry['id']}"
                                    first_song = await self.download_song(first_video_url, status_msg=None)
                                    
                                    if first_song:
                                        first_song['is_from_playlist'] = True
                                        # Process remaining songs in the background
                                        async def process_remaining_songs():
                                            try:
                                                for entry in entries[1:]:
                                                    if entry:
                                                        video_url = f"https://youtube.com/watch?v={entry['id']}"
                                                        song_info = await self.download_song(video_url, status_msg=None)
                                                        if song_info:
                                                            song_info['is_from_playlist'] = True
                                                            async with self.queue_lock:
                                                                self.queue.append(song_info)
                                                                if not self.is_playing and not self.voice_client.is_playing() and len(self.queue) == 1:
                                                                    await play_next(progress.ctx)
                                            except Exception as e:
                                                print(f"Error processing Mix playlist: {str(e)}")
                                        
                                        # Start background processing
                                        asyncio.create_task(process_remaining_songs())
                                        return first_song
                                raise Exception("No songs found in the Mix playlist")

                        except asyncio.CancelledError:
                            print("Info extraction cancelled")
                            raise Exception("Download cancelled")
                        except Exception as e:
                            print(f"Error checking livestream status: {e}")
                            is_live = False
                else:
                    # For search terms, just proceed with the download directly
                    pass
                
                # For non-livestream content, proceed with normal download
                ydl_opts = {
                    **BASE_YTDL_OPTIONS,
                    'outtmpl': os.path.join(self.downloads_dir, '%(id)s.%(ext)s'),
                    'cookiefile': self.cookie_file if self.cookie_file.exists() else None,
                    'progress_hooks': [
                        lambda d: self._download_hook(d),
                        lambda d: asyncio.run_coroutine_threadsafe(
                            progress.progress_hook(d),
                            self.bot_loop
                        ) if status_msg else None
                    ],
                    'default_search': 'ytsearch'
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    self.current_download_task = asyncio.create_task(extract_info(ydl, query, download=True))
                    try:
                        info = await self.current_download_task
                    except asyncio.CancelledError:
                        print("Download cancelled")
                        raise Exception("Download cancelled")
                    
                    if info.get('_type') == 'playlist' and not is_playlist_url(query):
                        # Handle search results that return a playlist
                        if not info.get('entries'):
                            raise Exception("No results found for your search.\nPlease try again with another search term")
                        info = info['entries'][0]
                        file_path = os.path.join(self.downloads_dir, f"{info['id']}.{info.get('ext', 'opus')}")
                    
                    elif info.get('_type') == 'playlist' and is_playlist_url(query):
                        # Handle actual playlist URLs
                        if not info.get('entries'):
                            raise Exception("Playlist is empty")

                        ctx = ctx or status_msg.channel if status_msg else None
                        first_video = info['entries'][0]
                        video_thumbnail = first_video.get('thumbnail')
                        playlist_title = info.get('title', 'Unknown Playlist')
                        playlist_url = info.get('webpage_url', query)
                        total_videos = len(info['entries'])

                        if status_msg:
                            playlist_embed = create_embed(
                                "Adding Playlist 🎵",
                                f"[ {playlist_title}]({playlist_url})\nDownloading first song...",
                                color=0x3498db,
                                thumbnail_url=video_thumbnail,
                                ctx=ctx
                            )
                            await status_msg.edit(embed=playlist_embed)

                        if info['entries']:
                            first_entry = info['entries'][0]
                            if not first_entry:
                                raise Exception("Failed to get first video from playlist")

                            first_file_path = os.path.join(self.downloads_dir, f"{first_entry['id']}.{first_entry.get('ext', 'opus')}")
                            first_song = {
                                'title': first_entry['title'],
                                'url': first_entry['webpage_url'] if first_entry.get('webpage_url') else first_entry['url'],
                                'file_path': first_file_path,
                                'thumbnail': first_entry.get('thumbnail'),
                                'ctx': ctx,
                                'is_from_playlist': True,
                                'requester': ctx.author if ctx else None  # Add requester information
                            }
                            remaining_entries = info['entries'][1:]
                            asyncio.create_task(self._queue_playlist_videos(
                                entries=remaining_entries,
                                ctx=ctx,
                                is_from_playlist=True,
                                status_msg=status_msg,
                                ydl_opts=ydl_opts,
                                playlist_title=playlist_title,
                                playlist_url=playlist_url,
                                total_videos=total_videos
                            ))

                            return first_song
                    else:
                        # Handle single video
                        file_path = os.path.join(self.downloads_dir, f"{info['id']}.{info.get('ext', 'opus')}")        
                    if status_msg:
                        try:
                            message_exists = True
                            try:
                                await status_msg.fetch()
                            except discord.NotFound:
                                message_exists = False               
                            if message_exists:
                                await status_msg.delete()
                        except Exception as e:
                            print(f"Note: Could not delete processing message: {e}")
                    
                    # Add requester information to the song info
                    if ctx:
                        info['requester'] = ctx.author
                    
                    # Get and cache the duration
                    duration = get_audio_duration(file_path)
                    if duration > 0:
                        self.duration_cache[file_path] = duration

                    # Add to cache for both YouTube direct links and Spotify->YouTube conversions
                    if os.path.exists(file_path) and info.get('id'):
                        video_id = info['id']
                        if not playlist_cache.is_video_cached(video_id):
                            playlist_cache.add_to_cache(
                                video_id, 
                                file_path,
                                thumbnail_url=info.get('thumbnail'),
                                title=info.get('title', 'Unknown')  # Save the title
                            )
                            print(f"{GREEN}Added Youtube file to cache: {video_id} - {info.get('title', 'Unknown')}{RESET}")

                    return {
                        'title': info['title'],
                        'url': info['webpage_url'] if info.get('webpage_url') else info['url'],
                        'file_path': file_path,
                        'thumbnail': info.get('thumbnail'),
                        'is_stream': False,
                        'is_from_playlist': is_playlist_url(query),
                        'ctx': status_msg.channel if status_msg else None
                    }
            except Exception as e:
                print(f"Error downloading song: {str(e)}")
                if status_msg:
                    error_embed = create_embed(
                        "Error ❌",
                        str(e),
                        color=0xe74c3c,
                        ctx=ctx if ctx else status_msg.channel
                    )
                    await status_msg.edit(embed=error_embed)
                raise

        except Exception as e:
            print(f"Error downloading song: {str(e)}")
            if status_msg:
                error_embed = create_embed(
                    "Error ❌",
                    str(e),
                    color=0xe74c3c,
                    ctx=ctx if ctx else status_msg.channel
                )
                await status_msg.edit(embed=error_embed)
            raise

    async def update_activity(self):
        """Update the bot's activity status"""
        await update_activity(self.bot, self.current_song, self.is_playing)

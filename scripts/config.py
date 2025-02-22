import json
import os
from time import sleep
from scripts.logging import get_ytdlp_logger
from scripts.paths import get_ytdlp_path, get_ffmpeg_path, get_ffprobe_path, get_cache_dir
from scripts.constants import RED, GREEN, BLUE, RESET

# Get the absolute path to the cache directory
CACHE_DIR = get_cache_dir()

# Safely create cache directory and subdirectories
if os.path.exists(CACHE_DIR) and not os.path.isdir(CACHE_DIR):
    os.remove(CACHE_DIR)  # Remove if it's a file
os.makedirs(CACHE_DIR, exist_ok=True)

for subdir in ['youtube-sigfuncs', 'youtube-nsig']:
    cache_subdir = os.path.join(CACHE_DIR, subdir)
    if os.path.exists(cache_subdir) and not os.path.isdir(cache_subdir):
        os.remove(cache_subdir)  # Remove if it's a file
    os.makedirs(cache_subdir, exist_ok=True)

def load_config():
    """Load or create the configuration file."""
    default_config = {
        "OWNER_ID": "220301180562046977",               # Owner ID
        "PREFIX": "!",                                  # Prefix for commands
        "LOG_LEVEL": "INFO",                            # Logging level
        "AUTO_UPDATE": True,                            # Enable/disable automatic updates
        "VOICE": {
            "INACTIVITY_LEAVE": False,                  # if True, leave voice channel when bot is inactive
            "INACTIVITY_TIMEOUT": 60,                   # in seconds
            "AUTO_LEAVE_EMPTY": True,                   # if True, leave voice channel when it is empty
            "DEFAULT_VOLUME": 100,                      # default volume for voice connections
        },
        "DOWNLOADS": {
            "AUTO_CLEAR": True,                         # if True, clear download directory on startup
            "MIX_PLAYLIST_LIMIT": 50,                   # Maximum number of songs to download from YouTube Mix playlists
            "SHUFFLE_DOWNLOAD": False,                  # Whether to shuffle download order in playlists
        },
        "MESSAGES": {
            "SHOW_PROGRESS_BAR": True,                  # if True, show download progress bar in Discord messages
            "DISCORD_UI_BUTTONS": False,                # if True, show Discord UI buttons
        },
        "PERMISSIONS": {
            "REQUIRES_DJ_ROLE": False,                  # if True, require a DJ role to use certain commands
        },
        "SPONSORBLOCK": False,                          # if True, enable SponsorBlock
    }

    # Get absolute path to config.json in root directory
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')

    # Create default config if it doesn't exist
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        print(f"\n{RED}A new config file has created using default values.{RESET}")
        sleep(1.5)
        print(f"{GREEN}Config file location: {BLUE}{config_path}{RESET}")
        print(f"{GREEN}Please edit your config file accordingly.{RESET}\n")
        sleep(1.5)

    # Load the config
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Check for missing keys and remove deprecated keys
    config_updated = False
    
    def sync_dict(current, default):
        """Recursively sync dictionary with default values:
        - Add missing keys
        - Remove deprecated keys
        - Keep existing values for valid keys"""
        updated = False
        
        # Add missing keys and update nested dicts
        for key, value in default.items():
            if key not in current:
                current[key] = value
                updated = True
            elif isinstance(value, dict) and isinstance(current[key], dict):
                if sync_dict(current[key], value):
                    updated = True
        
        # Remove deprecated keys
        deprecated_keys = [k for k in current.keys() if k not in default]
        for key in deprecated_keys:
            del current[key]
            updated = True
            
        return updated

    if sync_dict(config, default_config):
        config_updated = True
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        
    # Create a flattened version for backward compatibility
    flattened = {
        'OWNER_ID': config.get('OWNER_ID', default_config['OWNER_ID']),
        'PREFIX': config.get('PREFIX', default_config['PREFIX']),
        'LOG_LEVEL': config.get('LOG_LEVEL', default_config['LOG_LEVEL']),
        'INACTIVITY_LEAVE': config.get('VOICE', {}).get('INACTIVITY_LEAVE', default_config['VOICE']['INACTIVITY_LEAVE']),
        'INACTIVITY_TIMEOUT': config.get('VOICE', {}).get('INACTIVITY_TIMEOUT', default_config['VOICE']['INACTIVITY_TIMEOUT']),
        'AUTO_LEAVE_EMPTY': config.get('VOICE', {}).get('AUTO_LEAVE_EMPTY', default_config['VOICE']['AUTO_LEAVE_EMPTY']),
        'DEFAULT_VOLUME': config.get('VOICE', {}).get('DEFAULT_VOLUME', default_config['VOICE']['DEFAULT_VOLUME']),
        'AUTO_CLEAR_DOWNLOADS': config.get('DOWNLOADS', {}).get('AUTO_CLEAR', default_config['DOWNLOADS']['AUTO_CLEAR']),
        'MIX_PLAYLIST_LIMIT': config.get('DOWNLOADS', {}).get('MIX_PLAYLIST_LIMIT', default_config['DOWNLOADS']['MIX_PLAYLIST_LIMIT']),
        'SHUFFLE_DOWNLOAD': config.get('DOWNLOADS', {}).get('SHUFFLE_DOWNLOAD', default_config['DOWNLOADS']['SHUFFLE_DOWNLOAD']),
        'SHOW_PROGRESS_BAR': config.get('MESSAGES', {}).get('SHOW_PROGRESS_BAR', default_config['MESSAGES']['SHOW_PROGRESS_BAR']),
        'AUTO_UPDATE': config.get('AUTO_UPDATE', default_config['AUTO_UPDATE']),
        'SPONSORBLOCK': config.get('SPONSORBLOCK', default_config['SPONSORBLOCK']),
    }
    
    # Add the nested structure to the flattened config
    flattened['VOICE'] = config.get('VOICE', default_config['VOICE'])
    flattened['DOWNLOADS'] = config.get('DOWNLOADS', default_config['DOWNLOADS'])
    flattened['MESSAGES'] = config.get('MESSAGES', default_config['MESSAGES'])
    flattened['PERMISSIONS'] = config.get('PERMISSIONS', default_config['PERMISSIONS'])
    return flattened
        
# Get paths
FFMPEG_PATH = get_ffmpeg_path()
FFPROBE_PATH = get_ffprobe_path()
YTDLP_PATH = get_ytdlp_path()

# Export config variables for other modules to use
config_vars = load_config()

# Get config for volume
DEFAULT_VOLUME = config_vars.get('VOICE', {}).get('DEFAULT_VOLUME', 100)
# Convert DEFAULT_VOLUME from percentage (0-100) to float (0.0-1.0)
volume_float = DEFAULT_VOLUME / 100.0  # This makes 100% = 1.0, 75% = 0.75, 50% = 0.5, etc.

# Base yt-dlp options for downloading content
BASE_YTDL_OPTIONS = {
    'format': 'bestaudio[abr<=64]/bestaudio[abr<=72]/bestaudio[abr<=80]/bestaudio[abr<=88]/bestaudio[abr<=96]/bestaudio/worst', #using worst if everything else fails, some extractors do not offer audio only.
    'outtmpl': '%(id)s.%(ext)s',
    'extract_audio': True,
    'concurrent_fragments': 8,
    'concurrent-downloads': 4,
    'fragment_retries': 10,
    'retries': 5,
    'abort_on_unavailable_fragments': True,
    'nopostoverwrites': True,
    'windowsfilenames': True,
    'restrictfilenames': True,
    'noplaylist': True,
    'quiet': False,
    'no_warnings': False,
    'logger': get_ytdlp_logger(),
    'extract_flat': False,
    'force_generic_extractor': False,
    'verbose': True,
    'source_address': '0.0.0.0',
    'ffmpeg_location': FFMPEG_PATH,
    'ffprobe_location': FFPROBE_PATH,
    'yt_dlp_filename': YTDLP_PATH,
    'buffersize': 8192,
    'http_chunk_size': 1048576,
    'cachedir': CACHE_DIR,
    'write_download_archive': True,
    'player_client': 'web',
    'player_skip': ['mweb', 'android', 'ios'],
    'extractor_retries': 3,
    'geo_bypass': True,
    'socket_timeout': 10,
    'ignore_no_formats_error': True,
    'ignore_unavailable_video': True,
}

# Add SponsorBlock configuration if enabled in config
if config_vars.get('SPONSORBLOCK', False):
    sponsorblock_config = {
        'sponsorblock_remove': ['sponsor', 'intro', 'outro', 'selfpromo', 'interaction', 'music_offtopic'],
        'sponsorblock_api': 'https://sponsor.ajay.app',
        'postprocessors': [{
            'key': 'SponsorBlock',
            'when': 'before_dl',
            'api': 'https://sponsor.ajay.app',
            'categories': ['sponsor', 'intro', 'outro', 'selfpromo', 'interaction', 'music_offtopic']
        }, {
            'key': 'ModifyChapters',
            'remove_sponsor_segments': ['sponsor', 'intro', 'outro', 'selfpromo', 'interaction', 'music_offtopic']
        }]
    }
    BASE_YTDL_OPTIONS.update(sponsorblock_config)

# For backward compatibility
YTDL_OPTIONS = BASE_YTDL_OPTIONS

FFMPEG_OPTIONS = {
    'executable': FFMPEG_PATH,
    'options': (
        f'-loglevel {config_vars["LOG_LEVEL"].lower()} -v quiet -hide_banner '
        '-vn '
        '-b:a 96k '
        '-reconnect 1 '
        '-reconnect_streamed 1 '
        '-reconnect_delay_max 5 '
        '-threads 4 '
        '-af '
        'aresample=async=1:min_hard_comp=0.100000:max_soft_comp=0.100000:first_pts=0,'
        'equalizer=f=100:t=h:width=200:g=-3,'
        f'volume={volume_float} '
        '-buffer_size 128k'
    ),
}
import logging
import sys
from datetime import datetime

class MessageFilter(logging.Filter):
    """Filter out specific log messages"""
    def __init__(self, debug_mode=False):
        super().__init__()
        self.debug_mode = debug_mode
        # Loggers to completely filter out
        self.filtered_loggers = {
            'discord.voice_state',    # Voice connection state changes
            'discord.gateway',        # Gateway connection messages
            'discord.player',         # FFmpeg process messages
        }
        
        # Messages to filter from other loggers
        self.filtered_keywords = [
            'Ignoring exception in view',  # Ignore button interaction timeouts
            'Downloading webpage',         # Ignore yt-dlp download info
            'Downloading video',          # Ignore yt-dlp download info
            'Extracting URL',             # Ignore yt-dlp extraction info
            'Finished downloading',       # Ignore yt-dlp finish info
            'Deleting original file',     # Ignore yt-dlp cleanup info
            'Running FFmpeg',             # Ignore FFmpeg processing info
            'Post-process file',          # Ignore post-processing info
            'Voice connection complete',   # Voice connection messages
            'Voice handshake complete',    # Voice connection messages
            'Connecting to voice',         # Voice connection messages
            'Starting voice handshake',    # Voice connection messages
            'ffmpeg-location ffmpeg does not exist', # Ignore false FFmpeg warning
            'writing DASH m4a',           # Ignore DASH format warning
            'should have terminated with a return code',
            'has not terminated. Waiting to terminate',
            'discord.client: Attempting a reconnect in',
            'ffmpeg process',              # Ignore FFmpeg process termination messages
            'Dispatching event',           # Filter out Discord event dispatching messages
            'The voice handshake is being terminated', # Filter voice termination messages
            'discord.client Dispatching event',  # Filter out Discord event dispatching messages
            'discord.client',
            'discord.gateway',
            'discord.gateway Keeping shard ID', # Gateway shard messages
            'discord.gateway For Shard ID', # Gateway shard messages
        ]

    def filter(self, record):
        # In debug mode, don't filter anything
        if self.debug_mode:
            return True
            
        # Filter out messages from specific loggers
        if record.name in self.filtered_loggers:
            return False
            
        # For other loggers, filter by message content
        return not any(keyword in record.getMessage() for keyword in self.filtered_keywords)

class OutputCapture:
    """Captures ALL terminal output and writes it to the log file"""
    def __init__(self, log_file, stream=None):
        self.terminal = stream or sys.stdout
        self.log_file = open(log_file, 'a', encoding='utf-8')
        
    def write(self, message):
        # Write to terminal
        self.terminal.write(message)
        # Remove color codes and clean up the message
        clean_message = message.replace(GREEN, '').replace(BLUE, '').replace(RED, '').replace(RESET, '').strip()
        if clean_message:  # Only log non-empty messages
            # Add timestamp and write directly to file
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.log_file.write(f"{timestamp} {clean_message}\n")
            self.log_file.flush()
            
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

def setup_logging(log_level):
    """Set up logging configuration for all components."""
    # Import color codes and datetime
    global GREEN, BLUE, RED, RESET
    from datetime import datetime
    try:
        from bot import GREEN, BLUE, RED, RESET
    except ImportError:
        GREEN = BLUE = RED = RESET = ''
    
    # Check if we're in debug mode
    is_debug = log_level.upper() == 'DEBUG'

    # Remove any existing handlers
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)

    # Create handlers
    log_file = 'log.txt'
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    console_handler = logging.StreamHandler(sys.stdout)

    # Create formatter
    class ColoredFormatter(logging.Formatter):
        def format(self, record):
            if record.name == 'yt-dlp':
                record.name = f"{RED}yt-dlp{RESET}"
            if record.levelname == 'DEBUG':
                record.levelname = f"{GREEN}{record.levelname}{RESET}"
            if '[youtube]' in record.getMessage():
                record.msg = record.msg.replace('[youtube]', f'{RED}[youtube]{RESET}')
            if '[youtube:search]' in record.getMessage():
                record.msg = record.msg.replace('[youtube:search]', f'{BLUE}[youtube:search]{RESET}')
            if '[info]' in record.getMessage():
                record.msg = record.msg.replace('[info]', f'{BLUE}[info]{RESET}')
            if '[download]' in record.getMessage():
                record.msg = record.msg.replace('[download]', f'{BLUE}[download]{RESET}')
            if '[debug]' in record.getMessage():
                record.msg = record.msg.replace('[debug]', f'{BLUE}[debug]{RESET}')
            return super().format(record)

    formatter = ColoredFormatter('%(asctime)s %(levelname)s %(name)s %(message)s', 
                               datefmt='[%H:%M:%S]')
    
    # Add formatter to handlers
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Create message filter with debug mode setting
    message_filter = MessageFilter(debug_mode=is_debug)

    # Set log level
    log_level_value = getattr(logging, log_level.upper(), logging.INFO)
    root.setLevel(log_level_value)

    # Configure specific loggers that need to be filtered
    filtered_loggers = [
        'discord',
        'yt-dlp',
        'discord.voice_client',
        'discord.state',
        'discord.player',
        'discord.voice_state',
        'discord.interactions',
        'discord.webhook',
        'discord.ext.commands',
        'discord.ext.tasks',
        'discord.ext.voice_client',
        'discord.ext.commands.bot',
        'discord.ext.commands.core',
        'discord.ext.commands.errors',
        'discord.ext.commands.cog',
        'discord.ext.tasks.loop',
        'discord.ext',
        'discord.utils',
        'discord.intents'
    ]

    # Set up each Discord logger with the filter
    for logger_name in filtered_loggers:
        logger = logging.getLogger(logger_name)
        # Only apply filter if not in debug mode
        if not is_debug:
            logger.addFilter(message_filter)
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.setLevel(log_level_value)
        logger.propagate = False  # Prevent duplicate logging

    # Add handlers to root logger for non-Discord logs
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    
    # Capture ALL terminal output
    sys.stdout = OutputCapture(log_file, sys.stdout)
    sys.stderr = OutputCapture(log_file, sys.stderr)  # Also capture error output

def get_ytdlp_logger():
    """Get the yt-dlp logger for use in YTDL options."""
    return logging.getLogger('yt-dlp')

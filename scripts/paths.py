"""
Path management for external executables.
"""
import os
import sys
import platform

def _is_executable(path):
    """Check if a file exists and is executable."""
    return os.path.isfile(path) and os.access(path, os.X_OK)

def get_ytdlp_path():
    """Get the path to the yt-dlp executable."""
    if platform.system() == "Windows":
        return os.path.join(get_root_dir(), "yt-dlp.exe")
    else:
        # For Unix-like systems (Linux, macOS)
        return "yt-dlp"

def get_ffmpeg_path():
    """Get the path to the FFmpeg executable."""
    try:
        import subprocess
        import platform
        command = ['where' if platform.system() == 'Windows' else 'which', 'ffmpeg']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')[0]  # Take first result on Windows
    except:
        return "ffmpeg"  # Fallback to PATH

def get_ffprobe_path():
    """Get the path to the FFprobe executable."""
    try:
        import subprocess
        import platform
        command = ['where' if platform.system() == 'Windows' else 'which', 'ffprobe']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')[0]  # Take first result on Windows
    except:
        return "ffprobe"  # Fallback to PATH

def get_root_dir():
    """Get the root directory of the project."""
    return os.path.dirname(os.path.dirname(__file__))

def get_downloads_dir():
    """Get the path to the downloads directory."""
    return os.path.join(get_root_dir(), 'downloads')

def get_cache_dir():
    """Get the path to the cache directory."""
    return os.path.join(get_root_dir(), '.cache')

def get_cache_file(filename):
    """Get the path to a cache file."""
    return os.path.join(get_cache_dir(), filename)

def get_absolute_path(relative_path):
    """Convert a relative path to absolute path from root directory."""
    return os.path.join(get_root_dir(), relative_path)

def get_relative_path(absolute_path):
    """Convert an absolute path to relative path from root directory."""
    return os.path.relpath(absolute_path, get_root_dir())

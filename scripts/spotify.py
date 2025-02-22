import os
from pathlib import Path
import shutil

# Check if .spotifyenv exists, if not create it from example
spotifyenv_path = Path(__file__).parent.parent / '.spotifyenv'
spotifyenv_example_path = Path(__file__).parent.parent / '.spotifyenv.example'
if not spotifyenv_path.exists() and spotifyenv_example_path.exists():
    shutil.copy2(spotifyenv_example_path, spotifyenv_path)

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from dotenv import load_dotenv

# Load environment variables from .spotifyenv
load_dotenv('.spotifyenv')

# Initialize Spotify client
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'),
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET')
))

async def get_spotify_track_details(spotify_url):
    try:
        if 'track/' in spotify_url:
            track_id = spotify_url.split('track/')[-1].split('?')[0]
            track_info = sp.track(track_id)
            artist_name = track_info['artists'][0]['name']
            track_name = track_info['name']
            return f"{artist_name} - {track_name}", track_id
    except Exception as e:
        print(f"Error retrieving Spotify track details: {str(e)}")
        return None, None

async def get_spotify_album_details(spotify_url):
    try:
        if 'album/' in spotify_url:
            album_id = spotify_url.split('album/')[-1].split('?')[0]
            album_info = sp.album_tracks(album_id)
            tracks = [f"{track['artists'][0]['name']} - {track['name']}" for track in album_info['items']]
            return tracks
    except Exception as e:
        print(f"Error retrieving Spotify album details: {str(e)}")
        return []

async def get_spotify_playlist_details(spotify_url):
    try:
        if 'playlist/' in spotify_url:
            playlist_id = spotify_url.split('playlist/')[-1].split('?')[0]
            playlist_info = sp.playlist_tracks(playlist_id)
            tracks = [f"{track['track']['artists'][0]['name']} - {track['track']['name']}" for track in playlist_info['items']]
            return tracks
    except Exception as e:
        print(f"Error retrieving Spotify playlist details: {str(e)}")
        return []

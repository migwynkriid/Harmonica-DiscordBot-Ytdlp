import asyncio
import discord
import re
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from scripts.play_next import play_next
from dotenv import load_dotenv
from scripts.messages import create_embed
from scripts.duration import get_audio_duration

class SpotifyHandler:
    async def handle_spotify_url(self, url, ctx, status_msg=None):
        """Handle Spotify URLs by extracting track info and downloading via YouTube"""
        try:
            if not self.sp:
                raise ValueError("Spotify functionality is not available. Please check your Spotify credentials in .spotifyenv")

            spotify_match = re.match(r'https://open\.spotify\.com/(track|album|playlist)/([a-zA-Z0-9]+)', url)
            if not spotify_match:
                raise ValueError("Invalid Spotify URL")

            content_type, content_id = spotify_match.groups()

            if content_type == 'track':
                return await self.handle_spotify_track(content_id, ctx, status_msg)
            elif content_type == 'album':
                return await self.handle_spotify_album(content_id, ctx, status_msg)
            elif content_type == 'playlist':
                return await self.handle_spotify_playlist(content_id, ctx, status_msg)

        except Exception as e:
            print(f"Error handling Spotify URL: {str(e)}")
            if status_msg:
                error_embed = create_embed("Error", f"Failed to process Spotify content: {str(e)}", color=0xe74c3c, ctx=status_msg.channel)
                await status_msg.edit(embed=error_embed)
            return None

    async def handle_spotify_track(self, track_id, ctx, status_msg=None):
        """Handle a single Spotify track"""
        try:
            track = self.sp.track(track_id)
            if not track:
                raise ValueError("Could not find track on Spotify")

            artists = ", ".join([artist['name'] for artist in track['artists']])
            search_query = f"{track['name']} {artists}"

            if status_msg:
                await status_msg.edit(embed=create_embed(
                    "Processing",
                    f"Searching for {search_query}",
                    color=0x1DB954,
                    ctx=ctx
                ))

            # Download the song
            song_info = await self.download_song(search_query, status_msg=status_msg, ctx=ctx)
            
            # If song is successfully downloaded, add to queue and play
            if song_info:
                # Ensure the song is not marked as from a playlist
                song_info['is_from_playlist'] = False
                # Add requester information
                song_info['requester'] = ctx.author
                # Get duration using ffprobe
                song_info['duration'] = get_audio_duration(song_info['file_path'])
                # Add to queue
                self.queue.append(song_info)
                
                # If not currently playing, start playback
                from bot import music_bot
                if not music_bot.is_playing and not music_bot.voice_client.is_playing():
                    await play_next(ctx)
                else:
                    # Send "Added to Queue" message if we're not starting playback immediately
                    queue_pos = len(self.queue)
                    description = f"[🎵 {song_info['title']}]({song_info['url']})"
                    
                    # Only show position if current song is not looping
                    if self.current_song:
                        loop_cog = ctx.bot.get_cog('Loop')
                        current_song_url = self.current_song['url']
                        is_current_looping = loop_cog and current_song_url in loop_cog.looped_songs
                        if not is_current_looping:
                            description += f"\nPosition in queue: {queue_pos}"
                        
                    queue_embed = create_embed(
                        "Added to Queue",
                        description,
                        color=0x3498db,
                        thumbnail_url=song_info.get('thumbnail'),
                        ctx=ctx
                    )
                    queue_msg = await ctx.send(embed=queue_embed)
                    self.queued_messages[song_info['url']] = queue_msg
                
                return song_info
            
            return None

        except Exception as e:
            print(f"Error handling Spotify track: {str(e)}")
            if status_msg:
                await status_msg.edit(embed=create_embed(
                    "Error",
                    f"Failed to process Spotify track: {str(e)}",
                    color=0xe74c3c,
                    ctx=ctx
                ))
            raise

    async def handle_spotify_album(self, album_id, ctx, status_msg=None):
        """Handle a Spotify album"""
        try:
            album = self.sp.album(album_id)
            if not album:
                raise ValueError("Could not find album on Spotify")

            if status_msg:
                await status_msg.edit(embed=create_embed(
                    "Processing Album",
                    f"Processing album: {album['name']}\nTotal tracks: {album['total_tracks']}",
                    color=0x1DB954,
                    thumbnail_url=album['images'][0]['url'] if album['images'] else None,
                    ctx=ctx
                ))
            tracks = []
            results = self.sp.album_tracks(album_id)
            tracks.extend(results['items'])
            while results['next']:
                results = self.sp.next(results)
                tracks.extend(results['items'])
            if tracks:
                first_track = tracks[0]
                artists = ", ".join([artist['name'] for artist in first_track['artists']])
                search_query = f"{first_track['name']} {artists}"
                first_song = await self.download_song(search_query, status_msg=status_msg, ctx=ctx)
                if first_song:
                    first_song['is_from_playlist'] = True
                    first_song['requester'] = ctx.author
                    # Get duration using ffprobe
                    first_song['duration'] = get_audio_duration(first_song['file_path'])
                    self.queue.append(first_song)
                    if not self.is_playing and not self.voice_client.is_playing():
                        await play_next(ctx)

            if len(tracks) > 1:
                asyncio.create_task(self._process_spotify_tracks(
                    tracks[1:],
                    ctx,
                    status_msg,
                    f"Album: {album['name']}"
                ))

            return first_song if tracks else None

        except Exception as e:
            print(f"Error handling Spotify album: {str(e)}")
            raise

    async def handle_spotify_playlist(self, playlist_id, ctx, status_msg=None):
        """Handle a Spotify playlist"""
        try:
            playlist = self.sp.playlist(playlist_id)
            if not playlist:
                raise ValueError("Could not find playlist on Spotify")

            if status_msg:
                await status_msg.edit(embed=create_embed(
                    "Processing Playlist",
                    f"Processing playlist: {playlist['name']}\nTotal tracks: {playlist['tracks']['total']}",
                    color=0x1DB954,
                    thumbnail_url=playlist['images'][0]['url'] if playlist['images'] else None,
                    ctx=ctx
                ))

            tracks = []
            results = playlist['tracks']
            tracks.extend(results['items'])
            while results['next']:
                results = self.sp.next(results)
                tracks.extend(results['items'])

            if tracks:
                first_track = tracks[0]['track']
                artists = ", ".join([artist['name'] for artist in first_track['artists']])
                search_query = f"{first_track['name']} {artists}"
                
                first_song = await self.download_song(search_query, status_msg=status_msg, ctx=ctx)
                if first_song:
                    first_song['is_from_playlist'] = True
                    first_song['requester'] = ctx.author
                    # Get duration using ffprobe
                    first_song['duration'] = get_audio_duration(first_song['file_path'])
                    
                    # Create a new dictionary with all required fields
                    queue_entry = {
                        'title': first_song['title'],
                        'url': first_song['url'],
                        'file_path': first_song['file_path'],
                        'thumbnail': first_song.get('thumbnail'),
                        'duration': first_song['duration'],
                        'is_stream': first_song.get('is_stream', False),
                        'is_from_playlist': True,
                        'requester': ctx.author,
                        'ctx': ctx
                    }
                    
                    self.queue.append(queue_entry)
                    if not self.is_playing and not self.voice_client.is_playing():
                        await play_next(ctx)

            if len(tracks) > 1:
                asyncio.create_task(self._process_spotify_tracks(
                    [t['track'] for t in tracks[1:]],
                    ctx,
                    status_msg,
                    f"Playlist: {playlist['name']}"
                ))

            return first_song if tracks else None

        except Exception as e:
            print(f"Error handling Spotify playlist: {str(e)}")
            raise

    async def _process_spotify_tracks(self, tracks, ctx, status_msg, source_name):
        """Process remaining Spotify tracks in the background"""
        try:
            total_tracks = len(tracks)
            processed = 0

            for track in tracks:
                if not track:
                    continue

                artists = ", ".join([artist['name'] for artist in track['artists']])
                search_query = f"{track['name']} {artists}"
                
                song_info = await self.download_song(search_query, status_msg=None, ctx=ctx)
                if song_info:
                    # Get duration using ffprobe
                    song_info['duration'] = get_audio_duration(song_info['file_path'])
                    # Create a new dictionary with all required fields
                    queue_entry = {
                        'title': song_info['title'],
                        'url': song_info['url'],
                        'file_path': song_info['file_path'],
                        'thumbnail': song_info.get('thumbnail'),
                        'duration': song_info['duration'],
                        'is_stream': song_info.get('is_stream', False),
                        'is_from_playlist': True,
                        'requester': ctx.author,
                        'ctx': ctx
                    }
                    
                    self.queue.append(queue_entry)
                    
                    if not self.is_playing and not self.voice_client.is_playing():
                        await play_next(ctx)
                processed += 1
                if status_msg and processed % 5 == 0:
                    try:
                        await status_msg.edit(embed=create_embed(
                            "Processing",
                            f"Processing {source_name}\nProgress: {processed}/{total_tracks} tracks",
                            color=0x1DB954,
                            ctx=ctx
                        ))
                    except:
                        pass

            if status_msg:
                final_embed = create_embed(
                    "Complete",
                    f"Finished processing {source_name}\nTotal tracks added: {processed}",
                    color=0x1DB954,
                    ctx=ctx
                )
                try:
                    await status_msg.edit(embed=final_embed)
                    await status_msg.delete(delay=5)
                except:
                    pass

        except Exception as e:
            print(f"Error in _process_spotify_tracks: {str(e)}")
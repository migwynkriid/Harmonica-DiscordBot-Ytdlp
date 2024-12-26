import asyncio
import discord
import re
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from dotenv import load_dotenv

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
                error_embed = self.create_embed("Error", f"Failed to process Spotify content: {str(e)}", color=0xe74c3c, ctx=status_msg.channel)
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
                await status_msg.edit(embed=self.create_embed(
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
                
                # Add to queue
                self.queue.append(song_info)
                
                # If not currently playing, start playback
                if not self.is_playing and not self.voice_client.is_playing():
                    await self.play_next(ctx)
                
                return song_info
            
            return None

        except Exception as e:
            print(f"Error handling Spotify track: {str(e)}")
            if status_msg:
                await status_msg.edit(embed=self.create_embed(
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
                await status_msg.edit(embed=self.create_embed(
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
                    self.queue.append(first_song)
                    if not self.is_playing and not self.voice_client.is_playing():
                        await self.play_next(ctx)

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
                await status_msg.edit(embed=self.create_embed(
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
                    self.queue.append(first_song)
                    if not self.is_playing and not self.voice_client.is_playing():
                        await self.play_next(ctx)

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

                try:
                    song_info = await self.download_song(search_query, status_msg=None, ctx=ctx)
                    if song_info:
                        song_info['is_from_playlist'] = True
                        async with self.queue_lock:
                            self.queue.append(song_info)
                            if not self.is_playing and not self.voice_client.is_playing():
                                await self.play_next(ctx)
                except Exception as e:
                    print(f"Error processing track '{track['name']}': {str(e)}")
                    continue

                processed += 1
                if status_msg and processed % 5 == 0:
                    try:
                        await status_msg.edit(embed=self.create_embed(
                            "Processing",
                            f"Processing {source_name}\nProgress: {processed}/{total_tracks} tracks",
                            color=0x1DB954,
                            ctx=ctx
                        ))
                    except:
                        pass

            if status_msg:
                final_embed = self.create_embed(
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
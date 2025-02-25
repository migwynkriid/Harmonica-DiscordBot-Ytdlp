import discord
from discord.ext import commands
from scripts.repeatsong import repeat_song
from scripts.messages import create_embed
from scripts.permissions import check_dj_role

class Loop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.looped_songs = set()

    async def _toggle_loop(self, count: int = 999):
        """Core loop functionality that can be used by both command and button"""
        from bot import music_bot
        
        # Input validation
        if count < 1:
            return False, "Loop count must be a positive number!"
            
        if not music_bot.current_song:
            return False, "No song is currently playing!"

        current_song_url = music_bot.current_song['url']
        is_song_looped = current_song_url in self.looped_songs
        
        if not is_song_looped:
            self.looped_songs.add(current_song_url)
            # Find the position of the current song in the queue (if it exists)
            current_song_position = -1
            for i, song in enumerate(music_bot.queue):
                if song['url'] == current_song_url:
                    current_song_position = i
                    break
            
            # If current song is not in queue, position will be at start
            insert_position = current_song_position + 1 if current_song_position != -1 else 0
            
            # Insert the looped song right after the current position
            for _ in range(count):
                music_bot.queue.insert(insert_position, music_bot.current_song)
                insert_position += 1  # Increment position for next insertion
            
            # Set up callback for future repeats
            music_bot.after_song_callback = lambda: self.bot.loop.create_task(
                repeat_song(music_bot, None)  # We'll set the context later
            )
            
            return True, {
                'enabled': True,
                'song': music_bot.current_song,
                'count': count
            }
        else:
            # Remove song from looped songs set
            self.looped_songs.remove(current_song_url)
            
            # Clear the callback when loop is disabled
            music_bot.after_song_callback = None
            
            # Remove all songs from queue that match the current song's URL
            music_bot.queue = [song for song in music_bot.queue if song['url'] != current_song_url]
            
            return True, {
                'enabled': False,
                'song': music_bot.current_song
            }

    @commands.command(name='loop', aliases=['repeat'])
    @check_dj_role()
    async def loop(self, ctx, count: int = 999):
        """Toggle loop mode for the current song. Optionally specify number of times to add the song."""
        
        # Check if user is in voice chat
        if not ctx.author.voice:
            await ctx.send(embed=create_embed("Error", "You must be in a voice channel to use this command!", color=0xe74c3c, ctx=ctx))
            return
            
        # Check if bot is in same voice chat
        if not ctx.voice_client or ctx.author.voice.channel != ctx.voice_client.channel:
            await ctx.send(embed=create_embed("Error", "You must be in the same voice channel as the bot to use this command!", color=0xe74c3c, ctx=ctx))
            return
            
        success, result = await self._toggle_loop(count)
        
        if not success:
            await ctx.send(result)
            return

        color = 0x3498db if result['enabled'] else 0xe74c3c
        title = "Looping enabled :repeat: " if result['enabled'] else "Looping disabled :repeat: "
        description = f"[{result['song']['title']}]({result['song']['url']})"

        embed = create_embed(
            title,
            description,
            color=color,
            thumbnail_url=result['song'].get('thumbnail'),
            ctx=ctx
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Loop(bot))

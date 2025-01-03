import discord
from discord.ext import commands
from scripts.messages import create_embed

class QueueCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_member = None

    @commands.command(name='queue', aliases=['playing'])
    async def queue(self, ctx):
        """Show the current queue"""
        from __main__ import music_bot
        
        if not music_bot.current_song and not music_bot.queue and music_bot.download_queue.empty():
            await ctx.send(embed=create_embed("Queue Empty", "No songs in queue", color=0xe74c3c, ctx=ctx))
            return

        queue_text = ""
        position = 1

        if music_bot.current_song:
            queue_text += "**Now playing:**\n"
            loop_cog = self.bot.get_cog('Loop')
            is_looping = loop_cog and music_bot.current_song['url'] in loop_cog.looped_songs
            queue_text += f"[{music_bot.current_song['title']}]({music_bot.current_song['url']})"
            if is_looping:
                queue_text += " - :repeat:"
            queue_text += "\n\n"

        if music_bot.queue:
            loop_cog = self.bot.get_cog('Loop')
            current_song_url = music_bot.current_song['url'] if music_bot.current_song else None
            is_looping = loop_cog and current_song_url in loop_cog.looped_songs
            
            # First check if there are any non-looping songs to show
            has_non_looping_songs = False
            for song in music_bot.queue:
                if not (is_looping and song['url'] == current_song_url):
                    has_non_looping_songs = True
                    break
            
            if has_non_looping_songs:
                queue_text += "**Up Next:**\n"
                shown_songs = set()  # Track which songs we've already shown
                position = 1
                
                for song in music_bot.queue:
                    # Skip showing the looped song in queue
                    if is_looping and song['url'] == current_song_url:
                        continue
                        
                    song_title = song['title']
                    if song_title not in shown_songs:
                        queue_text += f"`{position}.` [{song_title}]({song['url']})\n"
                        shown_songs.add(song_title)
                        position += 1

        if not music_bot.download_queue.empty():
            queue_text += "\n**Downloading:**\n"
            downloading_count = music_bot.download_queue.qsize()
            queue_text += f"{downloading_count} song(s) in download queue\n"

        total_songs = (1 if music_bot.current_song else 0) + len(music_bot.queue)
        embed = create_embed(
            f"Waiting in queue",
            queue_text if queue_text else "Queue is empty",
            color=0x3498db,
            ctx=ctx
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(QueueCog(bot))
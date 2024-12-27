import discord
from discord.ext import commands

class QueueCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_member = None

    @commands.command(name='queue', aliases=['playing'])
    async def queue(self, ctx):
        """Show the current queue"""
        from __main__ import music_bot
        
        if not music_bot.queue and music_bot.download_queue.empty():
            await ctx.send(embed=music_bot.create_embed("Queue Empty", "No songs in queue", color=0xe74c3c, ctx=ctx))
            return

        queue_text = ""
        position = 1

        if music_bot.current_song:
            queue_text += "**Now Playing:**\n"
            queue_text += f" {music_bot.current_song['title']}]({music_bot.current_song['url']})\n\n"

        if music_bot.queue:
            queue_text += "**Up Next:**\n"
            for song in music_bot.queue:
                queue_text += f"`{position}.` [{song['title']}]({song['url']})\n"
                position += 1

        if not music_bot.download_queue.empty():
            queue_text += "\n**Downloading:**\n"
            downloading_count = music_bot.download_queue.qsize()
            queue_text += f" {downloading_count} song(s) in download queue\n"

        embed = music_bot.create_embed(
            f"Music Queue - {len(music_bot.queue)} song(s)",
            queue_text if queue_text else "Queue is empty",
            color=0x3498db,
            ctx=ctx
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(QueueCog(bot))
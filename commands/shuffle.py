from discord.ext import commands
from scripts.shufflelogic import shuffle_queue
from scripts.messages import create_embed
from scripts.permissions import check_dj_role

class ShuffleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_member = None

    @commands.command(name='shuffle')
    @check_dj_role()
    async def shuffle(self, ctx):
        """Randomly shuffle all songs in the queue"""
        from bot import music_bot
        
        # Check if user is in voice chat
        if not ctx.author.voice:
            await ctx.send(embed=create_embed("Error", "You must be in a voice channel to use this command!", color=0xe74c3c, ctx=ctx))
            return
            
        # Check if bot is in same voice chat
        if not ctx.voice_client or ctx.author.voice.channel != ctx.voice_client.channel:
            await ctx.send(embed=create_embed("Error", "You must be in the same voice channel as the bot to use this command!", color=0xe74c3c, ctx=ctx))
            return
            
        success = await shuffle_queue(ctx, music_bot)
        
        if success:
            await ctx.send(embed=create_embed("Queue Shuffled", "The queue has been randomly shuffled!\n Pending downloads are not shuffled", color=0x2ecc71, ctx=ctx))
        else:
            await ctx.send(embed=create_embed("Cannot Shuffle", "Nothing is playing or nothing is waiting in the queue!", color=0xe74c3c, ctx=ctx))

async def setup(bot):
    await bot.add_cog(ShuffleCog(bot))

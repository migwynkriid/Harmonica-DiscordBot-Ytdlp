import asyncio
import time
from scripts.clear_queue import clear_queue

async def start_inactivity_checker(bot_instance):
    """Start the inactivity checker"""
    try:
        await check_inactivity(bot_instance)
        bot_instance._inactivity_task = bot_instance.bot_loop.create_task(check_inactivity(bot_instance))
    except Exception as e:
        print(f"Error starting inactivity checker: {str(e)}")

async def check_inactivity(bot_instance):
    """Check for inactivity and leave voice if inactive too long"""
    while True:
        try:
            await asyncio.sleep(60)
            
            if bot_instance.voice_client and bot_instance.voice_client.is_connected():
                # Reset activity timer if music is playing or there are songs in queue
                if bot_instance.voice_client.is_playing() or bot_instance.queue:
                    bot_instance.last_activity = time.time()
                # Only disconnect if inactive AND no music is playing/queued
                elif (time.time() - bot_instance.last_activity > bot_instance.inactivity_timeout and 
                      bot_instance.inactivity_leave and 
                      not bot_instance.voice_client.is_playing() and 
                      not bot_instance.queue):
                    print(f"Leaving voice channel due to {bot_instance.inactivity_timeout} seconds of inactivity")
                    # Cancel any active downloads before disconnecting
                    await bot_instance.cancel_downloads()
                    await bot_instance.voice_client.disconnect()
                    clear_queue()
        except Exception as e:
            print(f"Error in inactivity checker: {str(e)}")
            await asyncio.sleep(60)

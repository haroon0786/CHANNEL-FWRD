import logging
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from aiohttp import web

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class ForwarderBot:
    def __init__(self):
        self.bot_token = "7815230273:AAGMwu78JgS88yO8OSi_kIW9D2OQw3yR4Q4"
        self.source_id = -1002438877384
        self.dest_id = -1002382776169
        self.media_groups = {}
        self.lock = asyncio.Lock()
        self.group_delay = 2.5  # Time to wait for album completion
        self.port = int(os.environ.get("PORT", 5000))

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not (update.channel_post and update.channel_post.chat.id == self.source_id):
            return

        msg = update.channel_post
        media_group_id = msg.media_group_id

        if media_group_id:
            async with self.lock:
                if media_group_id not in self.media_groups:
                    self.media_groups[media_group_id] = {
                        'messages': [],
                        'task': asyncio.create_task(
                            self.process_media_group(media_group_id, context)
                        )
                    }
                self.media_groups[media_group_id]['messages'].append(msg)
        else:
            await self.forward_single(msg, context)

    async def process_media_group(self, group_id: str, context: ContextTypes.DEFAULT_TYPE):
        await asyncio.sleep(self.group_delay)
        
        async with self.lock:
            if group_id not in self.media_groups:
                return

            messages = sorted(
                self.media_groups[group_id]['messages'],
                key=lambda x: x.message_id
            )

            try:
                # Forward messages in quick succession
                for msg in messages:
                    await context.bot.forward_message(
                        chat_id=self.dest_id,
                        from_chat_id=self.source_id,
                        message_id=msg.message_id
                    )
                    await asyncio.sleep(0.1)  # Maintain order and grouping
                
                logger.info(f"Forwarded album with {len(messages)} items")
            except Exception as e:
                logger.error(f"Album error: {e}")
            finally:
                del self.media_groups[group_id]

    async def forward_single(self, message, context):
        try:
            await context.bot.forward_message(
                chat_id=self.dest_id,
                from_chat_id=self.source_id,
                message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Forward error: {e}")

    async def web_server(self):
        app = web.Application()
        app.router.add_get("/", self.health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        return runner

    async def health_check(self, request):
        return web.Response(text="Bot is operational")

    async def run(self):
        # Start web server
        await self.web_server()
        
        # Initialize Telegram bot
        application = ApplicationBuilder().token(self.bot_token).build()
        application.add_handler(MessageHandler(filters.ALL, self.handle_message))
        
        await application.initialize()
        await application.start()
        logger.info("Bot started successfully")
        
        # Keep running
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    bot = ForwarderBot()
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

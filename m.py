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

class MediaGroupManager:
    def __init__(self):
        self.media_groups = {}
        self.lock = asyncio.Lock()
        self.MEDIA_GROUP_DELAY = 2.5  # Seconds to wait for album completion

    async def handle_media_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.channel_post
        media_group_id = message.media_group_id

        async with self.lock:
            if media_group_id not in self.media_groups:
                self.media_groups[media_group_id] = {
                    'messages': [],
                    'task': asyncio.create_task(self.process_media_group(media_group_id, context))
                }
            self.media_groups[media_group_id]['messages'].append(message)

    async def process_media_group(self, media_group_id: str, context: ContextTypes.DEFAULT_TYPE):
        await asyncio.sleep(self.MEDIA_GROUP_DELAY)
        
        async with self.lock:
            if media_group_id not in self.media_groups:
                return

            messages = sorted(
                self.media_groups[media_group_id]['messages'],
                key=lambda x: x.message_id
            )

            try:
                message_ids = [msg.message_id for msg in messages]
                await context.bot.forward_messages(
                    chat_id=int(os.environ['TARGET_ID']),
                    from_chat_id=int(os.environ['SOURCE_ID']),
                    message_ids=message_ids
                )
                logger.info(f"Forwarded media group {media_group_id} with {len(message_ids)} items")
            except Exception as e:
                logger.error(f"Media group error: {str(e)}")
            finally:
                del self.media_groups[media_group_id]

class TelegramBot:
    def __init__(self):
        self.media_manager = MediaGroupManager()
        self.port = int(os.environ.get('PORT', 5000))
        self.app = None

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if update.channel_post:
                if update.channel_post.media_group_id:
                    await self.media_manager.handle_media_group(update, context)
                else:
                    await self.forward_single_message(update.channel_post, context)
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")

    async def forward_single_message(self, message, context):
        try:
            await context.bot.forward_message(
                chat_id=int(os.environ['TARGET_ID']),
                from_chat_id=int(os.environ['SOURCE_ID']),
                message_id=message.message_id
            )
            logger.info("Forwarded single message")
        except Exception as e:
            logger.error(f"Forward error: {str(e)}")

    async def web_server(self):
        app = web.Application()
        app.router.add_get('/', self.health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        return app

    async def health_check(self, request):
        return web.Response(text="Bot is operational")

    async def start_bot(self):
        # Validate environment variables
        required_vars = ['BOT_TOKEN', 'SOURCE_ID', 'TARGET_ID']
        missing = [var for var in required_vars if not os.environ.get(var)]
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

        # Start web server
        await self.web_server()
        
        # Initialize Telegram bot
        application = ApplicationBuilder().token(os.environ['BOT_TOKEN']).build()
        application.add_handler(MessageHandler(filters.ALL, self.handle_message))
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        logger.info("Bot started successfully")
        await asyncio.Future()  # Run forever

if __name__ == '__main__':
    bot = TelegramBot()
    
    try:
        asyncio.run(bot.start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")

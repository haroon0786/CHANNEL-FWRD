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

class MediaGroupForwarder:
    def __init__(self):
        self.media_groups = {}
        self.lock = asyncio.Lock()
        self.base_delay = 3.0  # Base delay for media group collection
        self.per_item_delay = 0.15  # Delay per media item

    async def handle_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not update.channel_post:
                return

            message = update.channel_post
            source_id = int(os.environ['SOURCE_ID'])
            
            if message.chat.id != source_id:
                return

            if message.media_group_id:
                await self.handle_media_group(message, context)
            else:
                await self.forward_single(message, context)

        except Exception as e:
            logger.error(f"Update handling error: {str(e)}")

    async def handle_media_group(self, message, context):
        media_group_id = message.media_group_id
        async with self.lock:
            if media_group_id not in self.media_groups:
                self.media_groups[media_group_id] = {
                    'messages': [],
                    'task': None
                }
                # Dynamic delay based on expected group size
                self.media_groups[media_group_id]['task'] = asyncio.create_task(
                    self.process_media_group(media_group_id, context)
                )

            self.media_groups[media_group_id]['messages'].append(message)

    async def process_media_group(self, media_group_id, context):
        # Dynamic delay calculation
        await asyncio.sleep(self.base_delay + self.per_item_delay * 5)  # Base + buffer

        async with self.lock:
            if media_group_id not in self.media_groups:
                return

            messages = sorted(
                self.media_groups[media_group_id]['messages'],
                key=lambda x: x.message_id
            )

            try:
                # Forward messages with controlled timing
                for idx, msg in enumerate(messages):
                    await context.bot.forward_message(
                        chat_id=int(os.environ['TARGET_ID']),
                        from_chat_id=int(os.environ['SOURCE_ID']),
                        message_id=msg.message_id
                    )
                    if idx < len(messages) - 1:  # No delay after last message
                        await asyncio.sleep(self.per_item_delay)

                logger.info(f"Forwarded album ({len(messages)} items) successfully")

            except Exception as e:
                logger.error(f"Album forwarding failed: {str(e)}")
            finally:
                del self.media_groups[media_group_id]

    async def forward_single(self, message, context):
        try:
            await context.bot.forward_message(
                chat_id=int(os.environ['TARGET_ID']),
                from_chat_id=int(os.environ['SOURCE_ID']),
                message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Single message error: {str(e)}")

class WebServer:
    def __init__(self):
        self.port = int(os.environ.get('PORT', 10000))
        self.app = None

    async def start(self):
        app = web.Application()
        app.router.add_get('/', self.health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"Web server running on port {self.port}")
        return app

    async def health_check(self, request):
        return web.Response(text="Service operational")

async def main():
    # Validate environment variables
    required_vars = ['BOT_TOKEN', 'SOURCE_ID', 'TARGET_ID']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        return

    # Initialize components
    forwarder = MediaGroupForwarder()
    server = WebServer()
    
    # Start web server
    await server.start()
    
    # Start Telegram bot
    application = ApplicationBuilder().token(os.environ['BOT_TOKEN']).build()
    application.add_handler(MessageHandler(filters.ALL, forwarder.handle_update))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    logger.info("Bot started successfully")
    
    # Keep running
    while True:
        await asyncio.sleep(3600)  # Sleep indefinitely

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")

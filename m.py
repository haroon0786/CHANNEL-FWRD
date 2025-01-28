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

class AlbumForwarder:
    def __init__(self):
        self.media_groups = {}
        self.lock = asyncio.Lock()
        self.base_wait = 4.0  # Initial collection window (seconds)
        self.max_wait = 6.0   # Maximum collection time
        self.send_interval = 0.08  # Delay between forwards

    async def handle_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not update.channel_post:
                return

            message = update.channel_post
            source_id = int(os.environ['SOURCE_ID'])
            
            if message.chat.id != source_id:
                return

            if message.media_group_id:
                await self.process_album(message, context)
            else:
                await self.forward_single(message, context)

        except Exception as e:
            logger.error(f"Error handling update: {str(e)}")

    async def process_album(self, message, context):
        media_group_id = message.media_group_id
        async with self.lock:
            entry = self.media_groups.get(media_group_id)
            
            if not entry:
                # New album detected - start tracking
                self.media_groups[media_group_id] = {
                    'messages': [message],
                    'task': asyncio.create_task(
                        self.handle_album(media_group_id, context)
                    ),
                    'last_update': asyncio.get_event_loop().time()
                }
                logger.debug(f"New album detected: {media_group_id}")
            else:
                # Update existing album
                entry['messages'].append(message)
                entry['last_update'] = asyncio.get_event_loop().time()
                logger.debug(f"Updated album {media_group_id} ({len(entry['messages'])} items)")

    async def handle_album(self, media_group_id, context):
        """Main album handling coroutine with dynamic waiting"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            async with self.lock:
                entry = self.media_groups.get(media_group_id)
                if not entry:
                    return

                elapsed = asyncio.get_event_loop().time() - start_time
                inactive_time = asyncio.get_event_loop().time() - entry['last_update']

                # Check termination conditions
                if elapsed >= self.max_wait or inactive_time >= self.base_wait:
                    messages = sorted(entry['messages'], key=lambda x: x.message_id)
                    del self.media_groups[media_group_id]
                    break

            await asyncio.sleep(0.5)  # Check every 500ms

        # Forward collected messages
        try:
            logger.info(f"Forwarding album {media_group_id} ({len(messages)} items)")
            for idx, msg in enumerate(messages):
                await context.bot.forward_message(
                    chat_id=int(os.environ['TARGET_ID']),
                    from_chat_id=int(os.environ['SOURCE_ID']),
                    message_id=msg.message_id
                )
                if idx < len(messages) - 1:
                    await asyncio.sleep(self.send_interval)
            
            logger.info(f"Successfully forwarded album {media_group_id}")
        except Exception as e:
            logger.error(f"Album forwarding failed: {str(e)}")

    async def forward_single(self, message, context):
        try:
            await context.bot.forward_message(
                chat_id=int(os.environ['TARGET_ID']),
                from_chat_id=int(os.environ['SOURCE_ID']),
                message_id=message.message_id
            )
            logger.info("Forwarded single message")
        except Exception as e:
            logger.error(f"Single message error: {str(e)}")

async def web_server():
    app = web.Application()
    app.router.add_get('/', lambda _: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 10000)))
    await site.start()
    logger.info("Web server started")
    return app

async def main():
    # Validate environment
    required_vars = ['BOT_TOKEN', 'SOURCE_ID', 'TARGET_ID']
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        logger.critical(f"Missing variables: {', '.join(missing)}")
        return

    # Initialize components
    forwarder = AlbumForwarder()
    await web_server()

    # Start Telegram bot
    application = ApplicationBuilder() \
        .token(os.environ['BOT_TOKEN']) \
        .post_init(lambda _: logger.info("Bot initialized")) \
        .build()

    application.add_handler(MessageHandler(filters.ALL, forwarder.handle_update))
    
    await application.initialize()
    await application.start()
    logger.info("Bot started polling")
    
    # Keep alive
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical failure: {str(e)}")

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
        self.bot_token = os.getenv("BOT_TOKEN", "7815230273:AAGMwu78JgS88yO8OSi_kIW9D2OQw3yR4Q4")
        self.source_id = int(os.getenv("SOURCE_ID", "-1002438877384"))
        self.dest_id = int(os.getenv("DEST_ID", "-1002382776169"))
        self.media_groups = {}
        self.lock = asyncio.Lock()
        self.group_delay = 3.0  # Increased delay for reliability
        self.port = int(os.environ.get("PORT", 10000))

    async def handle_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not update.channel_post or update.channel_post.chat.id != self.source_id:
                return

            msg = update.channel_post
            logger.info(f"Received message ID: {msg.message_id}")

            if msg.media_group_id:
                async with self.lock:
                    group_id = msg.media_group_id
                    if group_id not in self.media_groups:
                        self.media_groups[group_id] = {
                            'messages': [],
                            'task': asyncio.create_task(self.process_group(group_id))
                        }
                    self.media_groups[group_id]['messages'].append(msg)
            else:
                await self.forward_single(msg)
                
        except Exception as e:
            logger.error(f"Update handling error: {e}")

    async def process_group(self, group_id: str):
        await asyncio.sleep(self.group_delay)
        
        async with self.lock:
            if group_id not in self.media_groups:
                return

            try:
                messages = sorted(self.media_groups[group_id]['messages'], 
                                key=lambda x: x.message_id)
                message_ids = [m.message_id for m in messages]
                
                logger.info(f"Processing album with {len(message_ids)} messages")
                
                # Use bulk forwarding API
                await application.bot.forward_messages(
                    chat_id=self.dest_id,
                    from_chat_id=self.source_id,
                    message_ids=message_ids
                )
                
                logger.info(f"Successfully forwarded album {group_id}")
                
            except Exception as e:
                logger.error(f"Album processing failed: {e}")
            finally:
                del self.media_groups[group_id]

    async def forward_single(self, message):
        try:
            await application.bot.forward_message(
                chat_id=self.dest_id,
                from_chat_id=self.source_id,
                message_id=message.message_id
            )
            logger.info(f"Forwarded single message {message.message_id}")
        except Exception as e:
            logger.error(f"Single message forwarding failed: {e}")

    async def health_check(self, request):
        return web.Response(text="OK")

    async def run_server(self):
        app = web.Application()
        app.router.add_get("/", self.health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        logger.info(f"Web server started on port {self.port}")
        return runner

async def main():
    bot = ForwarderBot()
    await bot.run_server()
    
    global application
    application = ApplicationBuilder().token(bot.bot_token).build()
    application.add_handler(MessageHandler(filters.ALL, bot.handle_update))
    
    await application.initialize()
    await application.start()
    logger.info("Bot started successfully")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped gracefully")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

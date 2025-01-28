import logging
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from aiohttp import web

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class BotServer:
    def __init__(self):
        self.port = int(os.environ.get("PORT", 10000))
        self.media_groups = {}
        self.lock = asyncio.Lock()
        self.delay = 2.5

    async def handle_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            source_id = -1002438877384  # Replace with your source channel ID
            dest_id = -1002382776169    # Replace with destination channel ID

            if not (update.channel_post and update.channel_post.chat.id == source_id):
                return

            msg = update.channel_post
            media_group_id = msg.media_group_id

            if media_group_id:
                async with self.lock:
                    if media_group_id not in self.media_groups:
                        self.media_groups[media_group_id] = {
                            'messages': [],
                            'task': None
                        }
                        self.media_groups[media_group_id]['task'] = asyncio.create_task(
                            self.process_group(media_group_id, context, source_id, dest_id)
                        )
                    
                    self.media_groups[media_group_id]['messages'].append(msg)
            else:
                await self.forward_single(msg, context, source_id, dest_id)
        except Exception as e:
            logger.error(f"Update handling error: {e}")

    async def process_group(self, group_id: str, context: ContextTypes.DEFAULT_TYPE, 
                          source_id: int, dest_id: int):
        await asyncio.sleep(self.delay)
        
        async with self.lock:
            if group_id not in self.media_groups:
                return

            messages = sorted(
                self.media_groups[group_id]['messages'],
                key=lambda x: x.message_id
            )

            try:
                message_ids = [m.message_id for m in messages]
                await context.bot.forward_messages(
                    chat_id=dest_id,
                    from_chat_id=source_id,
                    message_ids=message_ids
                )
                logger.info(f"Forwarded group {group_id} with {len(message_ids)} messages")
            except Exception as e:
                logger.error(f"Group processing error: {e}")
            finally:
                if group_id in self.media_groups:
                    del self.media_groups[group_id]

    async def forward_single(self, message, context, source_id, dest_id):
        try:
            await context.bot.forward_message(
                chat_id=dest_id,
                from_chat_id=source_id,
                message_id=message.message_id
            )
            logger.info(f"Forwarded message {message.message_id}")
        except Exception as e:
            logger.error(f"Single message error: {e}")

    async def web_server(self):
        try:
            app = web.Application()
            app.router.add_get("/", self.health_check)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host="0.0.0.0", port=self.port)
            await site.start()
            logger.info(f"Web server started on port {self.port}")
            return runner
        except Exception as e:
            logger.error(f"Web server failed: {e}")
            raise

    async def health_check(self, request):
        return web.Response(text="OK")

    async def run(self):
        try:
            # Initialize Telegram bot
            self.application = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
            self.application.add_handler(MessageHandler(filters.ALL, self.handle_update))
            
            # Start web server first
            runner = await self.web_server()
            
            # Start bot polling
            await self.application.initialize()
            await self.application.start()
            logger.info("Bot initialized")
            
            # Keep running
            while True:
                await asyncio.sleep(3600)
                
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            await self.shutdown(runner)
            
    async def shutdown(self, runner):
        try:
            await self.application.stop()
            await self.application.shutdown()
            await runner.cleanup()
            logger.info("Clean shutdown completed")
        except Exception as e:
            logger.error(f"Shutdown error: {e}")

if __name__ == '__main__':
    bot = BotServer()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        loop.close()

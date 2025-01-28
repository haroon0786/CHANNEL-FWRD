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

class BotServer:
    def __init__(self):
        self.port = int(os.environ.get("PORT", 5000))
        self.app = None
        self.media_groups = {}
        self.lock = asyncio.Lock()

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        source_id = -1001859547091  # Your source channel ID
        dest_id = -1002382776169   # Your destination channel ID

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

    async def process_group(self, group_id: str, context: ContextTypes.DEFAULT_TYPE, 
                          source_id: int, dest_id: int):
        await asyncio.sleep(2.5)
        
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
            except Exception as e:
                logging.error(f"Media group error: {e}")
            finally:
                del self.media_groups[group_id]

    async def forward_single(self, message, context, source_id, dest_id):
        try:
            await context.bot.forward_message(
                chat_id=dest_id,
                from_chat_id=source_id,
                message_id=message.message_id
            )
        except Exception as e:
            logging.error(f"Forward error: {e}")

    async def web_server(self):
        app = web.Application()
        app.router.add_get("/", self.health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        return app

    async def health_check(self, request):
        return web.Response(text="Bot is running")

    async def start(self):
        # Start web server
        await self.web_server()
        
        # Start Telegram bot
        application = ApplicationBuilder().token(os.environ.get("BOT_TOKEN")).build()
        application.add_handler(MessageHandler(filters.ALL, self.handle_message))
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        logging.info("Bot started successfully")

if __name__ == '__main__':
    bot_server = BotServer()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_server.start())
    loop.run_forever()

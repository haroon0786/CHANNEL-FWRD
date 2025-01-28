import logging
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MediaGroupForwarder:
    def __init__(self):
        self.media_groups = {}
        self.lock = asyncio.Lock()
        self.delay = 2.5  # Adjust based on network latency

    async def handle_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        source_id = -1002438877384  # Your source channel ID
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
                logger.info(f"Forwarded media group {group_id} with {len(message_ids)} items")
            except Exception as e:
                logger.error(f"Media group error: {e}")
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
            logger.error(f"Forward error: {e}")

async def http_server():
    async def handler(reader, writer):
        data = await reader.read(1024)
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
        await writer.drain()
        writer.close()

    port = int(os.environ.get("PORT", 8000))
    server = await asyncio.start_server(handler, '0.0.0.0', port)
    logger.info(f"HTTP server running on port {port}")
    async with server:
        await server.serve_forever()

async def main():
    forwarder = MediaGroupForwarder()
    
    application = ApplicationBuilder().token('7909869778:AAFj7OEWQFvkw8kYIlN5gFEa7l1hzEkyRQ0').build()
    application.add_handler(MessageHandler(filters.ALL, forwarder.handle_update))

    # Create tasks for both services
    http_task = asyncio.create_task(http_server())
    bot_task = asyncio.create_task(application.run_polling())

    # Wait for both tasks (this will run forever until one crashes)
    await asyncio.gather(http_task, bot_task)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

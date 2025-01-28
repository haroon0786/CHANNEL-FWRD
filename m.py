import logging
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

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
                
                # Batch forward using Telegram's bulk forwarding
                await context.bot.forward_messages(
                    chat_id=dest_id,
                    from_chat_id=source_id,
                    message_ids=message_ids
                )
                
                logging.info(f"Forwarded media group {group_id} with {len(message_ids)} items")
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

# Simple HTTP handler for Render health checks
async def health_check_server():
    async def handler(reader, writer):
        data = await reader.read(1024)
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
        await writer.drain()
        writer.close()
    
    port = int(os.environ.get("PORT", 8000))
    server = await asyncio.start_server(handler, '0.0.0.0', port)
    async with server:
        await server.serve_forever()

async def main():
    # Initialize components
    forwarder = MediaGroupForwarder()
    application = ApplicationBuilder().token('7909869778:AAFj7OEWQFvkw8kYIlN5gFEa7l1hzEkyRQ0').build()
    application.add_handler(MessageHandler(filters.ALL, forwarder.handle_update))

    # Create tasks for both bot and health check server
    bot_task = asyncio.create_task(application.run_polling())
    server_task = asyncio.create_task(health_check_server())

    # Run both tasks concurrently
    await asyncio.gather(bot_task, server_task)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot shutdown requested")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
    finally:
        logging.info("Application shutdown complete")

from telethon import TelegramClient
import asyncio
import os

# Telegram configuration
API_ID = 21097321
API_HASH = 'd5957effa1be96cb1fe521f7bde75f40'
PHONE_NUMBER = '+5516981183730'

# Target chat and topic ID
CHAT_ID = -1002359501336  # ID do grupo ou canal
TOPIC_ID = None  # ID do tópico (Defina como None para enviar para o chat principal)

# Configurações personalizadas
ADD_TEXT = True  # True para adicionar texto com ffmpeg, False para desativar
SEND_IMAGES = True  # True para enviar imagens
SEND_VIDEOS = True  # True para enviar vídeos

# Text to overlay (se ADD_TEXT for True)
TEXT_LINE1 = "DraLarissa.github.io"
TEXT_LINE2 = ""

# Queues for parallel processing
download_queue = asyncio.Queue()
ffmpeg_queue = asyncio.Queue()
send_queue = asyncio.Queue()

# Initialize Telegram client
client = TelegramClient('bot_session', API_ID, API_HASH)

async def add_text_to_media(input_path):
    try:
        output_path = f"{os.path.splitext(input_path)[0]}_with_text{os.path.splitext(input_path)[1]}"
        
        command = [
            'ffmpeg', '-i', input_path,
            '-vf', f"drawtext=text='{TEXT_LINE1}':fontcolor=white:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2-30," \
                   f"drawtext=text='{TEXT_LINE2}':fontcolor=white:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2+10",
            '-y', output_path
        ]
        
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process.communicate()
        
        if process.returncode == 0 and os.path.exists(output_path):
            os.remove(input_path)
            return output_path
        return input_path
    except Exception as e:
        print(f"Error adding text overlay: {e}")
        return input_path

async def send_worker():
    while True:
        try:
            file_path = await send_queue.get()
            print(f"Sending: {file_path}")
            
            if TOPIC_ID:
                await client.send_file(CHAT_ID, file_path, reply_to=TOPIC_ID)
            else:
                await client.send_file(CHAT_ID, file_path)
            
            print(f"Sent successfully: {file_path}")
            if os.path.exists(file_path):
                os.remove(file_path)
            
            await asyncio.sleep(150)  # Rate limit protection
            send_queue.task_done()
        except Exception as e:
            print(f"Send error: {e}")
            if os.path.exists(file_path):
                os.remove(file_path)
            send_queue.task_done()

async def main():
    await client.start(phone=PHONE_NUMBER)
    print("Bot started!")
    
    workers = []
    workers.append(asyncio.create_task(send_worker()))
    await asyncio.gather(*workers)

if __name__ == '__main__':
    client.loop.run_until_complete(main())

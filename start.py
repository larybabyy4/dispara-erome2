from telethon import TelegramClient
import asyncio
import os
import subprocess
from collections import deque

# Telegram configuration
API_ID = 26968169
API_HASH = '5768aedba5732b11a1288965b57472e7'
PHONE_NUMBER = '+5516982194939'

# Target chat ID
CHAT_ID = -1002462947693

# Configurações personalizadas
ADD_TEXT = True  # True para adicionar texto com ffmpeg, False para desativar
SEND_IMAGES = True  # True para enviar imagens
SEND_VIDEOS = True  # True para enviar vídeos

# Text to overlay (se ADD_TEXT for True)
TEXT_LINE1 = "DraLarissa.github.io"
TEXT_LINE2 = "+"

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
            '-vf', f"drawtext=text='{TEXT_LINE1}':fontcolor=white:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2-30,"
                   f"drawtext=text='{TEXT_LINE2}':fontcolor=white:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2+10",
            '-y', output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        if process.returncode == 0 and os.path.exists(output_path):
            os.remove(input_path)
            return output_path
        return input_path
    except Exception as e:
        print(f"Error adding text overlay: {e}")
        return input_path

async def download_worker():
    while True:
        try:
            link = await download_queue.get()
            print(f"Downloading: {link}")
            
            # Download using gallery-dl
            process = await asyncio.create_subprocess_shell(
                f'gallery-dl {link}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Find downloaded files
            for root, _, files in os.walk('.'):
                for file in files:
                    if (SEND_IMAGES and file.endswith(('.jpg', '.jpeg', '.png'))) or \
                       (SEND_VIDEOS and file.endswith(('.mp4', '.gif'))):
                        file_path = os.path.join(root, file)
                        await ffmpeg_queue.put(file_path)
            
            download_queue.task_done()
        except Exception as e:
            print(f"Download error: {e}")
            download_queue.task_done()

async def ffmpeg_worker():
    while True:
        try:
            file_path = await ffmpeg_queue.get()
            print(f"Processing with FFmpeg: {file_path}")
            
            if ADD_TEXT:
                processed_path = await add_text_to_media(file_path)
            else:
                processed_path = file_path
            
            if processed_path:
                await send_queue.put(processed_path)
            
            ffmpeg_queue.task_done()
        except Exception as e:
            print(f"FFmpeg error: {e}")
            ffmpeg_queue.task_done()

async def send_worker():
    while True:
        try:
            file_path = await send_queue.get()
            print(f"Sending: {file_path}")
            
            await client.send_file(CHAT_ID, file_path)
            print(f"Sent successfully: {file_path}")
            
            if os.path.exists(file_path):
                os.remove(file_path)
            
            await asyncio.sleep(30)  # Rate limit protection
            send_queue.task_done()
        except Exception as e:
            print(f"Send error: {e}")
            if os.path.exists(file_path):
                os.remove(file_path)
            send_queue.task_done()

async def monitor_links():
    while True:
        try:
            if os.path.exists('links.txt'):
                with open('links.txt', 'r') as file:
                    links = file.readlines()
                
                if links:
                    # Clear the file
                    open('links.txt', 'w').close()
                    
                    # Add links to download queue
                    for link in links:
                        link = link.strip()
                        if link:
                            await download_queue.put(link)
            
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Monitor error: {e}")
            await asyncio.sleep(5)

async def main():
    await client.start(phone=PHONE_NUMBER)
    print("Bot started!")
    
    # Start multiple workers for each task
    workers = []
    
    # Download workers (3 concurrent downloads)
    for _ in range(3):
        workers.append(asyncio.create_task(download_worker()))
    
    # FFmpeg workers (2 concurrent processes)
    for _ in range(2):
        workers.append(asyncio.create_task(ffmpeg_worker()))
    
    # Send worker (1 worker due to rate limits)
    workers.append(asyncio.create_task(send_worker()))
    
    # Start link monitor
    workers.append(asyncio.create_task(monitor_links()))
    
    # Wait for all workers
    await asyncio.gather(*workers)

if __name__ == '__main__':
    client.loop.run_until_complete(main())

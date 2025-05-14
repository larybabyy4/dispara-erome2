from telethon import TelegramClient
import asyncio
import os
import subprocess
import json
import time
import logging
from datetime import datetime
import random

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_log.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TelegramBot")

# Telegram configuration
API_ID = 29908657
API_HASH = '84c6469e3aecab7e85b2665bdd91ee9a'
PHONE_NUMBER = '+5516981184516'

# Target chat ID (pode ser um canal, grupo ou chat privado)
CHAT_ID = -1002609020063

# Lista de canais adicionais para envio (opcional)
ADDITIONAL_CHANNELS = []  # Adicione IDs de outros canais aqui se necessário
# Exemplo: ADDITIONAL_CHANNELS = [-1001234567890, -1009876543210]

# Configurações personalizáveis
ADD_TEXT = True  # True para adicionar texto com ffmpeg, False para desativar
SEND_IMAGES = True  # True para enviar imagens
SEND_VIDEOS = True  # True para enviar vídeos

# Text to overlay (se ADD_TEXT for True)
TEXT_LINE1 = "DraLarissa.github.io"
TEXT_LINE2 = ""

# Texto padrão da legenda para envios no Telegram
DEFAULT_CAPTION = "+ Só as de 18+ \n @Dezoitinhasbot @Dezoitinhasbot \n @Dezoitinhasbot @Dezoitinhasbot \n \n \n  Muito Conteúdo, Muito Mesmo! \n  @DraLarissaLinksBot @DraLarissaLinksBot \n @DraLarissaLinksBot  \n \n Site Oficial \n https://DraLarissa.github.io      \n \n \n    " 

# Arquivo para armazenar links processados e seu status
PROCESSED_LINKS_FILE = "processed_links.json"
RETRY_DELAY = 300  # 5 minutos para tentar novamente em caso de falha

# Queues for parallel processing
download_queue = asyncio.Queue()
ffmpeg_queue = asyncio.Queue()
send_queue = asyncio.Queue()
retry_queue = asyncio.Queue()

# Status tracking
processed_links = {}

# Intervalo de delay saudável (em segundos)
DELAY_MIN = 5  # Mínimo de 5 segundos
DELAY_MAX = 15  # Máximo de 15 segundos

# Initialize Telegram client
client = TelegramClient('bot_session', API_ID, API_HASH)

def load_processed_links():
    if os.path.exists(PROCESSED_LINKS_FILE):
        try:
            with open(PROCESSED_LINKS_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error("Erro ao carregar arquivo de links processados. Iniciando novo registro.")
    return {}

def save_processed_links():
    with open(PROCESSED_LINKS_FILE, 'w') as f:
        json.dump(processed_links, f, indent=4)

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
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(output_path):
            os.remove(input_path)
            return output_path
        else:
            logger.error(f"Erro FFmpeg: {stderr.decode()}")
            return input_path
    except Exception as e:
        logger.error(f"Erro ao adicionar texto: {e}")
        return input_path

async def download_worker():
    while True:
        try:
            link, attempt = await download_queue.get()
            
            # Verificar se o link já foi processado com sucesso
            if link in processed_links and processed_links[link]["status"] == "success":
                logger.info(f"Link já enviado com sucesso anteriormente: {link}")
                download_queue.task_done()
                continue
                
            logger.info(f"Baixando: {link} (Tentativa: {attempt})")
            
            # Registrar link em processamento
            processed_links[link] = {
                "status": "downloading",
                "timestamp": datetime.now().isoformat(),
                "attempts": attempt
            }
            save_processed_links()
            
            # Download usando gallery-dl
            process = await asyncio.create_subprocess_shell(
                f'gallery-dl {link}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Erro ao baixar {link}: {stderr.decode()}")
                processed_links[link]["status"] = "download_failed"
                processed_links[link]["error"] = stderr.decode()
                save_processed_links()
                
                # Retentar depois
                if attempt < 3:
                    logger.info(f"Agendando nova tentativa para {link}")
                    await asyncio.sleep(RETRY_DELAY)
                    await download_queue.put((link, attempt + 1))
                else:
                    logger.error(f"Falha definitiva após 3 tentativas: {link}")
            else:
                # Encontrar arquivos baixados
                files_found = False
                for root, _, files in os.walk('.'):
                    for file in files:
                        if (SEND_IMAGES and file.endswith(('.jpg', '.jpeg', '.png'))) or \
                           (SEND_VIDEOS and file.endswith(('.mp4', '.gif'))):
                            file_path = os.path.join(root, file)
                            await ffmpeg_queue.put((file_path, link))
                            files_found = True
                
                if not files_found:
                    logger.warning(f"Nenhum arquivo de mídia encontrado para {link}")
                    processed_links[link]["status"] = "no_media_found"
                    save_processed_links()
            
            download_queue.task_done()
        except Exception as e:
            logger.error(f"Erro no worker de download: {e}")
            download_queue.task_done()

async def ffmpeg_worker():
    while True:
        try:
            file_path, link = await ffmpeg_queue.get()
            logger.info(f"Processando com FFmpeg: {file_path} do link {link}")
            
            processed_links[link]["status"] = "processing"
            save_processed_links()
            
            if ADD_TEXT:
                processed_path = await add_text_to_media(file_path)
            else:
                processed_path = file_path
            
            if processed_path:
                # Extrair o nome do arquivo para usar como parte da legenda
                file_name = os.path.basename(processed_path)
                await send_queue.put((processed_path, link, file_name))
            else:
                logger.error(f"Falha ao processar {file_path}")
                processed_links[link]["status"] = "processing_failed"
                save_processed_links()
            
            ffmpeg_queue.task_done()
        except Exception as e:
            logger.error(f"Erro no worker de FFmpeg: {e}")
            ffmpeg_queue.task_done()

# Função para gerar um delay saudável
async def healthy_delay():
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    logger.info(f"Aguardando {delay:.2f} segundos para evitar limites de taxa...")
    await asyncio.sleep(delay)

async def send_worker():
    while True:
        try:
            file_path, link, file_name = await send_queue.get()
            logger.info(f"Enviando: {file_path}")
            
            # Adicionar delay saudável antes de enviar
            await healthy_delay()
            
            processed_links[link]["status"] = "sending"
            save_processed_links()
            
            # Obter a legenda atual do arquivo de configuração
            caption = get_current_caption(file_name)
            
            # Enviar arquivo com legenda
            message = await client.send_file(CHAT_ID, file_path, caption=caption)
            
            if message:
                logger.info(f"Enviado com sucesso: {file_path} para {message.chat.title if hasattr(message.chat, 'title') else 'chat privado'}")
                
                # Atualizar status para sucesso
                processed_links[link]["status"] = "success"
                processed_links[link]["sent_timestamp"] = datetime.now().isoformat()
                processed_links[link]["message_id"] = message.id
                save_processed_links()
                
                # Remover link do arquivo links.txt assim que for enviado com sucesso
                await remove_link_from_file(link)
            else:
                logger.warning(f"Envio retornou None para {file_path}")
                processed_links[link]["status"] = "send_failed"
                processed_links[link]["error"] = "Envio retornou None"
                save_processed_links()
            
            # Remover arquivo após envio
            if os.path.exists(file_path):
                os.remove(file_path)
            
            send_queue.task_done()
        except Exception as e:
            logger.error(f"Erro ao enviar {file_path}: {e}")
            
            processed_links[link]["status"] = "send_failed"
            processed_links[link]["error"] = str(e)
            save_processed_links()
            
            # Limpar arquivo se ainda existir
            if os.path.exists(file_path):
                os.remove(file_path)
                
            # Agendar nova tentativa
            await retry_queue.put((link, 1))
            send_queue.task_done()

async def remove_link_from_file(link_to_remove):
    """Remove um link específico do arquivo links.txt"""
    if not os.path.exists('links.txt'):
        return
        
    try:
        # Ler todos os links
        with open('links.txt', 'r') as file:
            links = [line.strip() for line in file.readlines()]
        
        # Filtrar o link específico
        links = [link for link in links if link != link_to_remove]
        
        # Reescrever o arquivo sem o link removido
        with open('links.txt', 'w') as file:
            for link in links:
                file.write(f"{link}\n")
                
        logger.info(f"Link removido de links.txt após envio bem-sucedido: {link_to_remove}")
    except Exception as e:
        logger.error(f"Erro ao remover link do arquivo: {e}")

def get_current_caption(file_name):
    """Obter a legenda personalizada do arquivo de configuração ou usar a padrão"""
    try:
        if os.path.exists("caption.txt"):
            with open("caption.txt", "r", encoding="utf-8") as f:
                caption = f.read().strip()
                if caption:
                    # Substituir placeholders se necessário
                    caption = caption.replace("{file_name}", file_name)
                    caption = caption.replace("{date}", datetime.now().strftime("%d/%m/%Y"))
                    return caption
    except Exception as e:
        logger.error(f"Erro ao ler legenda: {e}")
    
    return DEFAULT_CAPTION

async def retry_worker():
    """Worker dedicado a tentar novamente envios que falharam"""
    while True:
        try:
            link, attempt = await retry_queue.get()
            
            # Se já tiver muitas tentativas, desiste
            if attempt > 3:
                logger.error(f"Desistindo de retentar link após múltiplas falhas: {link}")
                retry_queue.task_done()
                continue
                
            logger.info(f"Agendando nova tentativa para link falho: {link} (Tentativa: {attempt})")
            
            # Aguardar antes de tentar novamente
            await asyncio.sleep(RETRY_DELAY)
            
            # Colocar de volta na fila de download
            await download_queue.put((link, attempt))
            retry_queue.task_done()
        except Exception as e:
            logger.error(f"Erro no worker de retry: {e}")
            retry_queue.task_done()

async def monitor_links():
    while True:
        try:
            if os.path.exists('links.txt'):
                # Ler links mantendo a ordem original
                with open('links.txt', 'r') as file:
                    links = [link.strip() for link in file.readlines() if link.strip()]
                
                if links:
                    # Processar links sem remover nenhum ainda
                    new_links = []
                    
                    for link in links:
                        if link not in processed_links:
                            # Link totalmente novo - adicionar à fila
                            new_links.append(link)
                            await download_queue.put((link, 1))
                            logger.info(f"Novo link adicionado à fila: {link}")
                        elif processed_links[link]["status"] == "success":
                            # Este link já foi processado com sucesso - será removido
                            logger.info(f"Link já processado com sucesso, será removido: {link}")
                        else:
                            # Link em processamento ou com falha - verificar se precisa retentar
                            new_links.append(link)
                            status = processed_links[link]["status"]
                            attempts = processed_links[link].get("attempts", 0)
                            
                            if status in ["download_failed", "processing_failed", "send_failed"] and attempts < 3:
                                logger.info(f"Reagendando link com falha: {link} (Status: {status}, Tentativas: {attempts})")
                                await download_queue.put((link, attempts + 1))
                    
                    # Atualizar o arquivo links.txt com os links restantes
                    with open('links.txt', 'w') as file:
                        for link in links:
                            # Manter o link se não foi processado com sucesso
                            if link not in processed_links or processed_links[link]["status"] != "success":
                                file.write(f"{link}\n")
            
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Erro no monitoramento de links: {e}")
            await asyncio.sleep(10)

async def generate_status_report():
    """Gera relatório periódico sobre o status dos links processados"""
    while True:
        try:
            now = datetime.now()
            logger.info(f"Gerando relatório de status - {now.strftime('%H:%M:%S')}")
            
            # Verificar links pendentes no arquivo
            pending_links = []
            if os.path.exists('links.txt'):
                with open('links.txt', 'r') as file:
                    pending_links = [link.strip() for link in file.readlines() if link.strip()]
            
            # Estatísticas gerais
            total_links = len(processed_links)
            successful = sum(1 for link in processed_links if processed_links[link]["status"] == "success")
            failed = sum(1 for link in processed_links if processed_links[link]["status"] in ["download_failed", "processing_failed", "send_failed"])
            in_progress = total_links - successful - failed
            
            with open("status_report.txt", "w", encoding="utf-8") as f:
                f.write(f"📊 RELATÓRIO DE STATUS - {now.strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write(f"======================================\n\n")
                f.write(f"Total de links processados: {total_links}\n")
                f.write(f"✅ Enviados com sucesso: {successful}\n")
                f.write(f"❌ Falhas: {failed}\n")
                f.write(f"⏳ Em processamento: {in_progress}\n")
                f.write(f"📋 Links pendentes na fila: {len(pending_links)}\n\n")
                
                # Links pendentes na fila
                if pending_links:
                    f.write("🔄 LINKS PENDENTES\n")
                    f.write("======================================\n")
                    for i, link in enumerate(pending_links[:20], 1):  # Mostrar até 20 links
                        status_info = ""
                        if link in processed_links:
                            status = processed_links[link]["status"]
                            attempts = processed_links[link].get("attempts", 0)
                            status_info = f" - Status: {status}, Tentativas: {attempts}"
                        f.write(f"{i}. {link}{status_info}\n")
                    
                    if len(pending_links) > 20:
                        f.write(f"...e mais {len(pending_links) - 20} links\n")
                    f.write("\n")
                
                # Últimos envios bem-sucedidos
                recent_success = [(link, info) for link, info in processed_links.items() 
                                 if info["status"] == "success" and "sent_timestamp" in info]
                recent_success.sort(key=lambda x: x[1]["sent_timestamp"], reverse=True)
                
                if recent_success:
                    f.write("✅ ÚLTIMOS ENVIOS BEM-SUCEDIDOS\n")
                    f.write("======================================\n")
                    for i, (link, info) in enumerate(recent_success[:10], 1):  # Últimos 10 envios
                        sent_time = datetime.fromisoformat(info["sent_timestamp"]).strftime('%d/%m/%Y %H:%M:%S')
                        f.write(f"{i}. {link} - Enviado em: {sent_time}\n")
                    f.write("\n")
                
                # Falhas recentes
                recent_failures = [(link, info) for link, info in processed_links.items() 
                                  if info["status"] in ["download_failed", "processing_failed", "send_failed"]]
                
                if recent_failures:
                    f.write("❌ FALHAS RECENTES\n")
                    f.write("======================================\n")
                    for i, (link, info) in enumerate(recent_failures[:10], 1):  # Últimas 10 falhas
                        f.write(f"{i}. {link}\n")
                        f.write(f"   Status: {info['status']}\n")
                        f.write(f"   Tentativas: {info.get('attempts', 1)}\n")
                        if "error" in info:
                            error_msg = info["error"]
                            if len(error_msg) > 100:
                                error_msg = error_msg[:100] + "..."
                            f.write(f"   Erro: {error_msg}\n")
                    f.write("\n")
                
                # Resumo detalhado
                f.write("📋 DETALHES COMPLETOS\n")
                f.write("======================================\n")
                for link, info in processed_links.items():
                    f.write(f"\nLink: {link}\n")
                    f.write(f"Status: {info['status']}\n")
                    f.write(f"Tentativas: {info.get('attempts', 1)}\n")
                    f.write(f"Timestamp: {info['timestamp']}\n")
                    if "error" in info:
                        f.write(f"Erro: {info['error']}\n")
                    if "sent_timestamp" in info:
                        f.write(f"Enviado em: {info['sent_timestamp']}\n")
                    if "message_id" in info:
                        f.write(f"ID da mensagem: {info['message_id']}\n")
            
            # Também salvar uma versão JSON para facilitar análise
            with open("status_report.json", "w") as f:
                json.dump({
                    "timestamp": now.isoformat(),
                    "stats": {
                        "total": total_links,
                        "successful": successful,
                        "failed": failed,
                        "in_progress": in_progress,
                        "pending": len(pending_links)
                    },
                    "pending_links": pending_links,
                    "details": processed_links
                }, f, indent=4)
            
            await asyncio.sleep(300)  # Atualizar a cada 5 minutos
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}")
            await asyncio.sleep(300)

async def main():
    global processed_links
    processed_links = load_processed_links()
    
    await client.start(phone=PHONE_NUMBER)
    logger.info("Bot iniciado!")
    
    # Verificar informações sobre o chat alvo
    try:
        entity = await client.get_entity(CHAT_ID)
        if hasattr(entity, 'title'):
            logger.info(f"Conectado ao canal/grupo: {entity.title}")
        else:
            logger.info(f"Conectado ao chat: {entity.id}")
    except Exception as e:
        logger.error(f"Não foi possível obter informações do chat {CHAT_ID}: {e}")
    
    # Verificar canais adicionais
    for channel_id in ADDITIONAL_CHANNELS:
        try:
            entity = await client.get_entity(channel_id)
            logger.info(f"Canal adicional conectado: {entity.title if hasattr(entity, 'title') else channel_id}")
        except Exception as e:
            logger.error(f"Não foi possível conectar ao canal adicional {channel_id}: {e}")
    
    # Mostrar configurações atuais
    logger.info(f"Adição de texto: {ADD_TEXT}")
    logger.info(f"Envio de imagens: {SEND_IMAGES}")
    logger.info(f"Envio de vídeos: {SEND_VIDEOS}")
    
    # Start multiple workers for each task
    workers = []
    
    # Download workers (3 concurrent downloads)
    for i in range(3):
        workers.append(asyncio.create_task(download_worker()))
    
    # FFmpeg workers (2 concurrent processes)
    for i in range(2):
        workers.append(asyncio.create_task(ffmpeg_worker()))
    
    # Send worker (1 worker due to rate limits)
    workers.append(asyncio.create_task(send_worker()))
    
    # Retry worker
    workers.append(asyncio.create_task(retry_worker()))
    
    # Status report generator
    workers.append(asyncio.create_task(generate_status_report()))
    
    # Start link monitor
    workers.append(asyncio.create_task(monitor_links()))
    
    # Wait for all workers
    try:
        await asyncio.gather(*workers)
    except Exception as e:
        logger.critical(f"Erro crítico no bot: {e}")

if __name__ == '__main__':
    client.loop.run_until_complete(main())

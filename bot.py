# Импортируем нужные библиотеки для веб-сервера
from flask import Flask
from threading import Thread
import os

# --- Веб-сервер для UptimeRobot ---
app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

def run():
  app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# --- Конец части с веб-сервером ---


# --- ОСНОВНОЙ КОД БОТА (остается почти без изменений) ---
import telebot
from telebot import types
from youtubesearchpython import VideosSearch
import yt_dlp
import requests
from PIL import Image
from io import BytesIO
import math

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
DOWNLOAD_PATH = 'downloads' 
# --- КОНЕЦ НАСТРОЕК ---

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

user_data = {}
bot = telebot.TeleBot(BOT_TOKEN)

# ... (ВЕСЬ КОД ФУНКЦИЙ БОТА ОСТАЕТСЯ ЗДЕСЬ) ...
# download_video, create_preview_collage, send_welcome, 
# send_search_results, send_page, handle_text, callback_handler
# Скопируйте сюда все функции из предыдущего ответа, они не меняются.
# Начало с: def download_video(video_id, chat_id):
# ... и до конца: if chat_id in user_data: del user_data[chat_id]

# --- Функции для скачивания ---

def download_video(video_id, chat_id):
    """Скачивает видео с YouTube по ID и возвращает путь к файлу."""
    url = f'https://www.youtube.com/watch?v={video_id}'
    output_template = os.path.join(DOWNLOAD_PATH, f'{chat_id}_{video_id}.mp4')
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'format_sort': ['filesize'],
        'max_filesize': 50 * 1024 * 1024, # 50MB
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if os.path.exists(output_template):
            return output_template
        else:
            return None
    except Exception as e:
        print(f"Ошибка при скачивании видео {video_id}: {e}")
        return None

def create_preview_collage(results, chat_id):
    """Создает коллаж из 10 превью и возвращает путь к нему."""
    thumbnails = []
    for video in results:
        try:
            thumb_url = video['thumbnails'][0]['url']
            response = requests.get(thumb_url)
            img = Image.open(BytesIO(response.content))
            img = img.resize((160, 90))
            thumbnails.append(img)
        except Exception:
            thumbnails.append(Image.new('RGB', (160, 90)))
            
    if not thumbnails: return None

    cols, rows = 5, 2
    collage = Image.new('RGB', (cols * 160, rows * 90))
    
    for i, thumb in enumerate(thumbnails):
        collage.paste(thumb, ((i % cols) * 160, (i // cols) * 90))

    collage_path = os.path.join(DOWNLOAD_PATH, f'preview_{chat_id}.jpg')
    collage.save(collage_path)
    return collage_path

# --- Обработчики команд и сообщений ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Просто отправь мне текст, и я найду для тебя видео на YouTube.")

def send_search_results(chat_id, query, page=0):
    """Основная функция для поиска и отправки результатов."""
    try:
        msg = bot.send_message(chat_id, f"🔍 Ищу видео по запросу: *{query}*...", parse_mode="Markdown")
        search = VideosSearch(query, limit=20)
        all_results = search.result()['result']

        if not all_results:
            bot.edit_message_text("😕 К сожалению, по вашему запросу ничего не найдено.", chat_id, msg.message_id)
            return

        user_data[chat_id] = {'query': query, 'results': all_results, 'page': page}
        send_page(chat_id, msg.message_id)
    except Exception as e:
        print(f"Ошибка при поиске: {e}")
        bot.send_message(chat_id, "❌ Ой, что-то пошло не так. Попробуйте еще раз.")

def send_page(chat_id, message_id=None):
    """Отправляет конкретную страницу результатов."""
    data = user_data.get(chat_id)
    if not data:
        bot.send_message(chat_id, "Ваш поиск истек. Пожалуйста, начните заново.")
        return
        
    page = data['page']
    results_to_show = data['results'][page*10 : page*10 + 10]

    if not results_to_show:
        bot.send_message(chat_id, "Больше видео по этому запросу не найдено.")
        return

    collage_path = create_preview_collage(results_to_show, chat_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for i, video in enumerate(results_to_show):
        num = page * 10 + i + 1
        title = (video['title'][:30] + '..') if len(video['title']) > 30 else video['title']
        buttons.append(types.InlineKeyboardButton(f"{num}. {title}", callback_data=f"dl_{video['id']}_{page}"))
    markup.add(*buttons)
    
    nav_buttons = []
    if page > 0: nav_buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page-1}"))
    if len(data['results']) > (page + 1) * 10: nav_buttons.append(types.InlineKeyboardButton("➡️ Вперед", callback_data=f"page_{page+1}"))
    nav_buttons.append(types.InlineKeyboardButton("🔄 Новый поиск", callback_data="new_search"))
    markup.add(*nav_buttons)

    text = f"✅ Результаты по запросу: *{data['query']}*\nСтраница {page + 1}.\n\nНажмите на кнопку для скачивания:"

    if collage_path:
        with open(collage_path, 'rb') as photo:
            if message_id: bot.delete_message(chat_id, message_id)
            bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode="Markdown")
        os.remove(collage_path)
    else:
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        else: bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    send_search_results(message.chat.id, message.text, page=0)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    data = call.data
    
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)

    if data.startswith("dl_"):
        video_id = data.split('_')[1]
        bot.send_message(chat_id, "⏳ Начинаю скачивание видео...")
        video_path = download_video(video_id, chat_id)
        
        if video_path:
            with open(video_path, 'rb') as video_file:
                bot.send_video(chat_id, video_file, caption="✅ Ваше видео готово!", supports_streaming=True)
            os.remove(video_path)
        else:
            bot.send_message(chat_id, "😥 Не удалось скачать видео (слишком большое). Попробуйте другое.")
        
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔄 Начать новый поиск", callback_data="new_search"))
        bot.send_message(chat_id, "Что делаем дальше?", reply_markup=markup)

    elif data.startswith("page_"):
        page = int(data.split('_')[1])
        user_data[chat_id]['page'] = page
        bot.delete_message(chat_id, call.message.message_id)
        send_page(chat_id)

    elif data == "new_search":
        bot.send_message(chat_id, "Введите новый запрос для поиска.")
        if chat_id in user_data: del user_data[chat_id]

# --- ЗАПУСК ВСЕГО ---
keep_alive() # Запускаем веб-сервер
print("Бот запущен...")
bot.infinity_polling()

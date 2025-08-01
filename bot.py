import telebot
from telebot import types
from youtubesearchpython import VideosSearch
import yt_dlp
import os
import requests
from PIL import Image
from io import BytesIO
import math

# --- НАСТРОЙКИ ---
# !!! ВАЖНО: Не вписывайте токен сюда. Мы будем использовать переменные окружения.
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
# Путь для сохранения временных файлов (видео и превью)
DOWNLOAD_PATH = 'downloads' 
# --- КОНЕЦ НАСТРОЕК ---

# Проверяем, существует ли папка для загрузок, если нет - создаем
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# Словарь для хранения результатов поиска для каждого пользователя
# Структура: {chat_id: {'query': 'текст запроса', 'results': [...], 'page': 0}}
user_data = {}

bot = telebot.TeleBot(BOT_TOKEN)

# --- Функции для скачивания ---

def download_video(video_id, chat_id):
    """Скачивает видео с YouTube по ID и возвращает путь к файлу."""
    url = f'https://www.youtube.com/watch?v={video_id}'
    output_template = os.path.join(DOWNLOAD_PATH, f'{chat_id}_{video_id}.mp4')
    
    # Настройки для yt-dlp: выбираем лучший формат mp4 с видео и звуком, не превышающий 50MB (ограничение Telegram)
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'format_sort': ['filesize'], # Сортируем по размеру, чтобы попытаться скачать файл до 50МБ
        'max_filesize': 50 * 1024 * 1024, # 50MB
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Проверяем, скачался ли файл
        if os.path.exists(output_template):
            return output_template
        else:
            return None # Файл оказался слишком большим и не был скачан
    except Exception as e:
        print(f"Ошибка при скачивании видео {video_id}: {e}")
        return None

def create_preview_collage(results, chat_id):
    """Создает коллаж из 10 превью и возвращает путь к нему."""
    thumbnails = []
    for video in results:
        try:
            # Получаем превью HQ, если нет - стандартное
            thumb_url = video['thumbnails'][0]['url']
            response = requests.get(thumb_url)
            img = Image.open(BytesIO(response.content))
            # Уменьшаем до стандартного размера, чтобы коллаж не был гигантским
            img = img.resize((160, 90))
            thumbnails.append(img)
        except Exception:
            # Если не удалось скачать превью, создаем черный квадрат
            thumbnails.append(Image.new('RGB', (160, 90)))
            
    if not thumbnails:
        return None

    # Располагаем превью в 2 ряда по 5 штук
    cols, rows = 5, 2
    collage_width = cols * 160
    collage_height = rows * 90
    collage = Image.new('RGB', (collage_width, collage_height))
    
    for i, thumb in enumerate(thumbnails):
        x = (i % cols) * 160
        y = (i // cols) * 90
        collage.paste(thumb, (x, y))

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
        
        # Ищем 20 результатов, чтобы иметь запас для пагинации
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
    start_index = page * 10
    end_index = start_index + 10
    results_to_show = data['results'][start_index:end_index]

    if not results_to_show:
        bot.send_message(chat_id, "Больше видео по этому запросу не найдено.")
        return

    # Создаем коллаж превью
    collage_path = create_preview_collage(results_to_show, chat_id)

    # Создаем клавиатуру с кнопками
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for i, video in enumerate(results_to_show):
        # Нумерация с 1 до 10
        num = start_index + i + 1
        # Обрезаем длинные названия
        title = (video['title'][:30] + '..') if len(video['title']) > 30 else video['title']
        # Callback_data: 'dl_VIDEOID_PAGENUMBER'
        buttons.append(types.InlineKeyboardButton(f"{num}. {title}", callback_data=f"dl_{video['id']}_{page}"))
    markup.add(*buttons)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Назад (кнопки)", callback_data=f"page_{page-1}"))
    if len(data['results']) > end_index:
        nav_buttons.append(types.InlineKeyboardButton("➡️ Следующие 10", callback_data=f"page_{page+1}"))
    
    # Кнопка для нового поиска
    nav_buttons.append(types.InlineKeyboardButton("🔄 Новый поиск", callback_data="new_search"))
    markup.add(*nav_buttons)

    text = (
        f"✅ Найдено видео по запросу: *{data['query']}*\n"
        f"Страница {page + 1}. Превью расположены по порядку:\n"
        "1-5 в верхнем ряду, 6-10 в нижнем.\n\n"
        "Нажмите на кнопку, чтобы скачать видео:"
    )

    if collage_path:
        with open(collage_path, 'rb') as photo:
            # Если это первая отправка - создаем новое сообщение, если обновление - редактируем
            if message_id:
                bot.delete_message(chat_id, message_id)
            bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode="Markdown")
        os.remove(collage_path) # Удаляем коллаж после отправки
    else: # Если коллаж не создался
        if message_id:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


@bot.message_handler(func=lambda message: True)
def handle_text(message):
    send_search_results(message.chat.id, message.text, page=0)

# --- Обработчик нажатий на кнопки ---

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    data = call.data
    
    # Удаляем старое сообщение с кнопками, чтобы не было "висящих" часов
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)

    if data.startswith("dl_"):
        parts = data.split('_')
        video_id = parts[1]
        
        bot.send_message(chat_id, "⏳ Начинаю скачивание видео. Обычно это занимает от 10 до 60 секунд. Пожалуйста, подождите...")
        video_path = download_video(video_id, chat_id)
        
        if video_path:
            with open(video_path, 'rb') as video_file:
                bot.send_video(chat_id, video_file, caption="✅ Ваше видео готово!", supports_streaming=True)
            os.remove(video_path) # Удаляем видео после отправки
        else:
            bot.send_message(chat_id, "😥 Не удалось скачать видео. Вероятно, оно слишком большое (больше 50 МБ). Попробуйте выбрать другое.")
            
        # Возвращаем кнопки поиска
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Начать новый поиск", callback_data="new_search"))
        bot.send_message(chat_id, "Что делаем дальше?", reply_markup=markup)

    elif data.startswith("page_"):
        page = int(data.split('_')[1])
        user_data[chat_id]['page'] = page
        bot.delete_message(chat_id, call.message.message_id) # Удаляем старое сообщение с коллажем
        send_page(chat_id) # Отправляем новую страницу

    elif data == "new_search":
        # Просто просим ввести новый запрос
        bot.send_message(chat_id, "Введите новый запрос для поиска.")
        # Очищаем старые данные, чтобы не занимать память
        if chat_id in user_data:
            del user_data[chat_id]


if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
import requests
import math
from pymongo.errors import DuplicateKeyError
from io import BytesIO
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    ConversationHandler,
)
from PIL import Image, ImageDraw, ImageFont
from config import API_TOKEN, collection_memes, collection_caption, collection_users

MEMES_PER_PAGE = 10  # Количество мемов на странице
NUM_COLUMNS = 2  # Количество колонок для мемов
# Количество мемов в одной колонке
MEMES_PER_COLUMN = math.ceil(MEMES_PER_PAGE / NUM_COLUMNS)


# Функция обработки команды /start
def start(update: Update, context: CallbackContext) -> None:
    # Создаем кнопки для команд /help, /meme и /cancel
    buttons = [["/help", "/meme", "/cancel"]]
    reply_markup = ReplyKeyboardMarkup(
        buttons, resize_keyboard=True, one_time_keyboard=True
    )

    user = update.effective_user
    user_data = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }

    # Поиск документа по полю "user_id"
    query = {"user_id": user.id}
    existing_user = collection_users.find_one(query)

    if existing_user:
        # Обновление существующего документа
        collection_users.update_one(query, {"$set": user_data})
        context.bot.send_message(
            chat_id=update.effective_chat.id, text="Данные обновлены"
        )
    else:
        # Вставка нового документа
        collection_users.insert_one(user_data)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Привет! Я могу помочь тебе с выбором мемов. Просто выбери команду из списка:",
            reply_markup=reply_markup,
        )


# Функция обработки команды /help
def help_command(update: Update, context: CallbackContext) -> None:
    # Отправляем сообщение с инструкцией о том, как пользоваться ботом
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Я могу помочь тебе с выбором мемов. Просто напиши /meme, и я покажу тебе список мемов. Затем выбери мем из списка, и я отправлю его тебе.",
    )


# Функция обработки команды /cancel, которая удаляет из словаря user_data ключи
# 'text', 'boxes', 'text_step', 'meme_id', 'edit_text_clicked' и 'meme_received', если они есть в словаре.
# Затем отправляет сообщение с текстом "До свидания!" и возвращает значение ConversationHandler.END, чтобы завершить текущий ConversationHandler.
def cancel(update: Update, context: CallbackContext) -> int:
    user_data = context.user_data
    if "text" in user_data:
        del user_data["text"]
    if "boxes" in user_data:
        del user_data["boxes"]
    if "text_step" in user_data:
        del user_data["text_step"]
    if "meme_id" in user_data:
        del user_data["meme_id"]
    if "edit_text_clicked" in user_data:
        del user_data["edit_text_clicked"]
    if "meme_received" in user_data:
        del user_data["meme_received"]
    update.message.reply_text("До свидания!")
    return ConversationHandler.END


# Функция получения списка мемов
def get_memes(update: Update, context: CallbackContext, page_num: int = 1) -> None:
    memes_list = []
    # получаем все мемы из базы данных
    memes = collection_memes.find()

    # проходимся по каждому мему и добавляем его в список
    # for meme in memes:
    for meme in memes:
        memes_list.append(
            {
                "id": meme["id"],
                "name": meme["name"],
                "url": meme["url"],
                "width": meme["width"],
                "height": meme["height"],
                "box_count": meme["box_count"],
                "captions": meme["captions"],
            }
        )
    # разбиваем список мемов на страницы
    num_pages = math.ceil(len(memes_list) / MEMES_PER_PAGE)
    memes_list = memes_list[(page_num - 1) * MEMES_PER_PAGE : page_num * MEMES_PER_PAGE]
    # формируем кнопки для переключения страниц
    buttons = []
    if page_num > 1:
        buttons.append(
            InlineKeyboardButton(
                "< Предыдущая страница", callback_data=f"switch {page_num - 1}"
            )
        )
    if page_num < num_pages:
        buttons.append(
            InlineKeyboardButton(
                "Следующая страница >", callback_data=f"switch {page_num + 1}"
            )
        )
    # формируем кнопки для выбора мема
    keyboard = []
    for i in range(MEMES_PER_COLUMN):
        row = []
        for j in range(NUM_COLUMNS):
            index = i + j * MEMES_PER_COLUMN
            if index < len(memes_list):
                meme = memes_list[index]
                row.append(
                    InlineKeyboardButton(
                        f"{meme['name']}",
                        callback_data=f'meme {meme["id"]} {(meme["box_count"])}',
                    )
                )
        keyboard.append(row)
    keyboard.append(buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)
    # формируем текст сообщения с мемами и кнопками для переключения страниц
    reply_text = f"Страница {page_num}/{num_pages}"
    context.bot.send_message(
        chat_id=update.effective_chat.id, text=reply_text, reply_markup=reply_markup
    )


# Функция обработки выбора мема из списка
def meme(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(text="Мем загружается, подождите...")

    # Get meme and caption information from the database
    meme_id, num_boxes = query.data.split()[1:]
    num_boxes = int(num_boxes)
    context.user_data["meme_id"] = meme_id
    context.user_data["text"] = {}
    context.user_data["text_step"] = 0
    context.user_data["boxes"] = num_boxes
    context.user_data["meme_received"] = True

    meme = collection_memes.find_one({"id": meme_id})
    captions_info = collection_caption.find_one({"template_id": meme_id})
    captions = captions_info["text_boxes"]
    max_text_size = captions_info["max_text_size"]
    font_name = captions_info["font"]

    # Generate sample text

    sample_text = [f"Text {i+1}" for i in range(num_boxes)]

    # Открываем изображение мема
    response = requests.get(meme["url"])
    image = Image.open(BytesIO(response.content))
    draw = ImageDraw.Draw(image)

    # Отрисовываем текст
    for i in range(num_boxes):
        caption = captions[i]
        x1, y1 = caption["x"], caption["y"]
        w, h = caption["width"], caption["height"]
        color = caption["color"]
        fill_color = (
            tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
            if len(color) == 7
            else (0, 0, 0)
        )
        font = ImageFont.truetype(font_name, size=int(max_text_size))
        text = sample_text[i]
        text_box = (x1, y1, x1 + w, y1 + h)

        # Calculate the position of the center of the rectangle based on the size of the text
        center_x = (text_box[0] + text_box[2]) // 2
        center_y = (text_box[1] + text_box[3]) // 2

        # draw the text in the image
        line_bbox = font.getbbox("hg")
        line_height = line_bbox[3] - line_bbox[1]
        y = center_y - ((line_height * 1) // 2)
        x = center_x - ((font.getbbox(text)[2] - font.getbbox(text)[0]) // 2)
        draw.text((x, y), text, font=font, fill=fill_color)

    # Создаем кнопки для возврата к списку мемов или изменения текста
    buttons = [
        InlineKeyboardButton("Список мемов", callback_data="list"),
        InlineKeyboardButton("Изменить текст", callback_data="add_text_to_meme"),
    ]
    reply_markup = InlineKeyboardMarkup([buttons])

    # Send the generated meme to the user
    image_bytes = BytesIO()
    image.save(image_bytes, format="jpeg")
    image_bytes.seek(0)
    context.bot.send_photo(
        chat_id=update.effective_chat.id,
        reply_markup=reply_markup,
        photo=image_bytes,
        caption="Пример мема с текстовыми полями",
    )


# Функция show_memes вызывает функцию get_memes для отображения списка мемов на первой странице. Функция используется для обработки команды /meme.
def show_memes(update: Update, context: CallbackContext) -> None:
    get_memes(update, context, 1)


# Функция добавления текста в выбранный мем
def add_text_to_meme(update: Update, context: CallbackContext) -> None:
    # Помечаем, что была нажата кнопка изменения текста
    context.user_data["edit_text_clicked"] = True
    # Отправляем сообщение с просьбой ввести текст для первой ячейки
    context.bot.send_message(
        chat_id=update.effective_chat.id, text="Введите текст для ячейки 1"
    )
    # Устанавливаем номер текущей ячейки на 0
    context.user_data["text_step"] = 0


# Функция добавления текста в ячейки мема
def set_text(update: Update, context: CallbackContext) -> None:
    user_data = context.user_data
    edit_text_clicked = user_data.get("edit_text_clicked", False)

    if edit_text_clicked:
        text = update.message.text
        text_step = user_data.get("text_step", 0)
        boxes = user_data.get("boxes", 0)

        if text_step < boxes:
            text_dict = user_data.get("text", {})
            text_dict[text_step] = text
            user_data["text"] = text_dict
            user_data["text_step"] += 1
            if text_step + 1 < boxes:
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Введите текст для ячейки {text_step + 2}",
                )
            else:
                meme_id = user_data.get("meme_id", None)
                captions_info = collection_caption.find_one({"template_id": meme_id})
                captions = captions_info["text_boxes"]

                text_arr = []
                if boxes:
                    for i in range(boxes):
                        text_arr.append({"text": text_dict.get(i, "")})
                        captions[i]["text"] = text_dict.get(i, "")

                # Open the meme image and draw the text on it
                meme = collection_memes.find_one({"id": meme_id})
                response = requests.get(meme["url"])
                image = Image.open(BytesIO(response.content))
                draw = ImageDraw.Draw(image)

                for i, caption in enumerate(captions):
                    text = text_arr[i]["text"]
                    x, y = caption["x"], caption["y"]
                    width, height = caption["width"], caption["height"]
                    color = caption["color"]
                    fill_color = (
                        tuple(int(color[i : i + 2], 16))
                        if len(color) == 7
                        else (0, 0, 0)
                    )

                    # Get the maximum text size and font name from captions
                    max_text_size = captions_info["max_text_size"]
                    font_name = captions_info["font"]

                    # Calculate the font size based on the text length and maximum text size
                    text_size = min(
                        int(max_text_size), width // max(len(text.split()), 1)
                    )

                    # Load the font with the specified size
                    font = ImageFont.truetype(font_name, size=text_size)

                    # Calculate line height based on the font size
                    line_height = int(
                        (font.getbbox(" ")[3] - font.getbbox(" ")[1]) * 0.9
                    )

                    # Wrap text into multiple lines
                    words = text.split(" ")
                    lines = []
                    line = ""
                    for word in words:
                        if draw.textbbox((0, 0), line + word, font=font)[2] < width:
                            line += word + " "
                        else:
                            lines.append(line.rstrip())
                            line = word + " "
                    if line:
                        lines.append(line.rstrip())

                    # Draw text on the image
                    for j, line in enumerate(lines):
                        line_width, line_height = (
                            font.getbbox(line)[2] - font.getbbox(line)[0],
                            font.getbbox(line)[3] - font.getbbox(line)[1],
                        )
                        x_offset = (width - line_width) // 2
                        y_offset = (height - line_height * len(lines)) // 2
                        draw.text(
                            (x + x_offset, y + y_offset + j * line_height),
                            line,
                            font=font,
                            fill=fill_color,
                        )

                # Send the generated meme to the user
                image_bytes = BytesIO()
                image.save(image_bytes, format="jpeg")
                image_bytes.seek(0)
                # Создаем инлайн-кнопки для редактирования текста или завершения создания мема
                edit_all_text_button = InlineKeyboardButton(
                    "Редактировать все текста", callback_data="edit_all_text_button"
                )
                edit_text_by_id = InlineKeyboardButton(
                    "Редактировать один текст", callback_data="edit_text_by_id"
                )
                finish_button = InlineKeyboardButton(
                    "Я доволен", callback_data="finish"
                )
                reply_markup = InlineKeyboardMarkup(
                    [[edit_all_text_button], [edit_text_by_id], [finish_button]]
                )

                context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_bytes,
                    reply_markup=reply_markup,
                )

                # Update the user's account with the text array
                user = update.effective_user
                if user:
                    user_id = user.id
                    updated_text_arr = []
                    for i, text_entry in enumerate(text_arr):
                        text_entry[
                            "id"
                        ] = i  # Assign the sequential ID to the text entry
                        updated_text_arr.append(text_entry)

                    collection_users.update_one(
                        {"user_id": user_id},
                        {"$set": {"text_meme": updated_text_arr}},
                        upsert=True,
                    )
                else:
                    collection_users.insert_one(
                        {"user_id": user.id, "text_meme": text_arr}
                    )

                user_data["text_step"] = 0
                user_data["edit_text_clicked"] = False

                # user_data["text"] = {}
                # user_data["text_step"] = 0
                # user_data["edit_text_clicked"] = False
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Что-то пошло не так. Попробуйте еще раз.",
            )
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Пожалуйста, сначала нажмите кнопку "Изменить текст"',
        )


def edit_all_text_button(update: Update, context: CallbackContext) -> None:
    user_data = context.user_data
    user_data["edit_text_clicked"] = True
    user_data["text_step"] = 0
    user_data["text"] = {}
    user_data["meme_received"] = True
    boxes = user_data.get("boxes", 0)

    if boxes:
        context.bot.send_message(
            chat_id=update.effective_chat.id, text=f"Введите текст для ячейки 1"
        )
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Что-то пошло не так. Попробуйте еще раз.",
        )


def edit_text_by_id(update: Update, context: CallbackContext) -> None:
    user_data = context.user_data
    user_id = update.effective_user.id
    database_entry = collection_users.find_one({"user_id": user_id})

    if database_entry is not None:
        text_meme = database_entry.get("text_meme", [])

        if len(text_meme) > 0:
            user_data["edit_text_by_id"] = True
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Пожалуйста, введите номер текста, который вы хотите отредактировать:",
            )
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="У вас нет сохраненных текстов. Пожалуйста, создайте текст с помощью команды /set_text.",
            )
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="У вас нет сохраненных текстов. Пожалуйста, создайте текст с помощью команды /set_text.",
        )


def handle_text_number(update: Update, context: CallbackContext) -> None:
    user_data = context.user_data
    user_id = update.effective_user.id
    database_entry = collection_users.find_one({"user_id": user_id})

    if database_entry is not None:
        text_meme = database_entry.get("text_meme", [])
        edit_text_by_id = user_data.get("edit_text_by_id", False)

        if len(text_meme) > 0 and edit_text_by_id:
            message = update.message.text

            if message.isdigit():
                text_number = int(message)
                if 0 <= text_number < len(text_meme):
                    # Store the text number in user data
                    user_data["text_number"] = text_number

                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Текущий текст для номера {text_number}:\n\n{text_meme[text_number]['text']}\n\nПожалуйста, введите новый текст:",
                    )
                else:
                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Недопустимый номер текста. Попробуйте еще раз.",
                    )
            else:
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Пожалуйста, введите корректный номер текста.",
                )
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Что-то пошло не так. Попробуйте еще раз.",
            )
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="У вас нет сохраненных текстов. Пожалуйста, создайте текст с помощью команды /set_text.",
        )


def update_text_by_number(update: Update, context: CallbackContext) -> None:
    user_data = context.user_data
    user_id = update.effective_user.id
    database_entry = collection_users.find_one({"user_id": user_id})

    if database_entry is not None:
        text_meme = database_entry.get("text_meme", [])
        text_number = user_data.get("text_number")

        if len(text_meme) > 0 and text_number is not None:
            new_text = update.message.text

            if text_number < len(text_meme):
                # Update the text in the text meme
                text_meme[text_number]["text"] = new_text

                # Update the database entry with the modified text meme
                collection_users.update_one(
                    {"user_id": user_id},
                    {"$set": {"text_meme": text_meme}},
                )

                # Generate the meme with the edited text
                # ...
                # Add the code to generate the meme with the edited text
                # ...

                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Текст успешно обновлен и добавлен в мем.",
                )
            else:
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Недопустимый номер текста. Попробуйте еще раз.",
                )
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Что-то пошло не так. Попробуйте еще раз.",
            )
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="У вас нет сохраненных текстов. Пожалуйста, создайте текст с помощью команды /set_text.",
        )


# Функция обработки нажатия кнопки "Закончить" в диалоговом режиме. Она очищает пользовательские данные и отправляет сообщение с благодарностью за использование бота.
def finish_button_callback(update: Update, context: CallbackContext) -> None:
    user_data = context.user_data
    user_data.clear()
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Спасибо за использование бота! Хорошего дня :)",
    )


# Функция switch_page обрабатывает запрос пользователя на переключение страницы со списком мемов.
# Функция извлекает номер страницы из запроса и вызывает функцию get_memes, передавая ей номер запрошенной страницы.
def switch_page(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    page_num = int(query.data.split()[1])
    get_memes(update, context, page_num)


def main() -> None:
    # Создание экземпляра бота
    updater = Updater(API_TOKEN, use_context=True)

    # Получение диспетчера для регистрации обработчиков
    dispatcher = updater.dispatcher

    # Регистрация обработчика команды /start
    dispatcher.add_handler(CommandHandler("start", start))

    # Регистрация обработчика команды /help
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Регистрация обработчика команды /cancel
    dispatcher.add_handler(CommandHandler("cancel", cancel))

    # Регистрация обработчика команды /meme
    dispatcher.add_handler(CommandHandler("meme", lambda u, c: get_memes(u, c, 1)))

    # Регистрация обработчика команды /set_text
    dispatcher.add_handler(CommandHandler("set_text", set_text))

    # Регистрация обработчика callback-запросов на изменение текста
    dispatcher.add_handler(
        CallbackQueryHandler(edit_all_text_button, pattern="edit_all_text_button")
    )

    dispatcher.add_handler(
        CallbackQueryHandler(edit_text_by_id, pattern="edit_text_by_id")
    )

    # Регистрация обработчика callback-запросов на завершение работы бота
    dispatcher.add_handler(
        CallbackQueryHandler(finish_button_callback, pattern="finish")
    )

    # Регистрация обработчика callback-запросов на переключение страниц списка мемов
    dispatcher.add_handler(CallbackQueryHandler(switch_page, pattern=r"^switch \d+$"))

    # Регистрация обработчика callback-запросов на выбор мема
    dispatcher.add_handler(CallbackQueryHandler(meme, pattern=r"^meme \d+ \d+$"))

    # Регистрация обработчика callback-запросов на отображение списка мемов
    dispatcher.add_handler(CallbackQueryHandler(show_memes, pattern="^list$"))

    # Регистрация обработчика callback-запросов на добавление текста на мем
    dispatcher.add_handler(
        CallbackQueryHandler(add_text_to_meme, pattern="add_text_to_meme")
    )

    # Регистрация обработчика для ввода текста
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, set_text))

    # Запуск бота
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
W

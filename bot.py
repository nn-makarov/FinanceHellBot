import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from database import Database

# ========== НАСТРОЙКА ЛОГГИНГА ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== ЗАГРУЗКА ТОКЕНА ==========
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("Токен не найден! Проверь файл .env")
    exit(1)
logger.info(f"Токен загружен: {BOT_TOKEN[:10]}...")

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db = Database()

# ========== FSM СОСТОЯНИЯ ==========
class CategoryStates(StatesGroup):
    waiting_for_category_name = State()
    waiting_for_category_emoji = State()

class ExpenseStates(StatesGroup):
    waiting_for_amount = State()

class SettingsStates(StatesGroup):
    editing_categories = State()

# ========== СЛОВАРИ ДЛЯ ВРЕМЕННЫХ ДАННЫХ ==========
user_temp_data = {}  # {user_id: {'editing_mode': True/False, 'selected_category': id}}

# ========== ФУНКЦИИ ДЛЯ КЛАВИАТУР ==========
async def get_main_keyboard(user_id):
    """Основная клавиатура (для добавления расходов)"""
    categories = db.get_user_categories(user_id)
    buttons = []
    row = []
    
    # Категории расходов (по 2 в ряд)
    for cat_id, name, emoji in categories:
        btn_text = f"{emoji} {name}"
        row.append(KeyboardButton(text=btn_text))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    # Служебные кнопки
    buttons.append([
        KeyboardButton(text="📊 Статистика"),
        KeyboardButton(text="⚙️ Настройки")
    ])
    
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выбери категорию"
    )

async def get_settings_keyboard():
    """Клавиатура настроек"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Редактировать категории")],
            [KeyboardButton(text="🧹 Очистить статистику")],  
            [KeyboardButton(text="📤 Экспорт данных")],
            [KeyboardButton(text="⬅️ Назад в меню")]
        ],
        resize_keyboard=True
    )

async def get_edit_keyboard(user_id):
    """Клавиатура для редактирования категорий"""
    categories = db.get_user_categories(user_id)
    buttons = []
    row = []
    
    # Категории (по 2 в ряд)
    for cat_id, name, emoji in categories:
        btn_text = f"{emoji} {name}"
        row.append(KeyboardButton(text=btn_text))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    # Служебные кнопки
    buttons.append([KeyboardButton(text="➕ Новая категория")])
    buttons.append([
        KeyboardButton(text="📊 Статистика"),
        KeyboardButton(text="✅ Завершить редактирование")
    ])
    
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Долгое нажатие удаляет категорию"
    )

# ========== ОБРАБОТЧИКИ ==========

# ----- СТАРТ И ГЛАВНОЕ МЕНЮ -----
@dp.message(Command("start"))
async def start_command(message: Message):
    """Умный старт: показывает основное меню без принудительного редактирования"""
    user_id = message.from_user.id
    
    # Инициализируем стандартные категории, если пользователь новый
    categories = db.get_user_categories(user_id)
    if not categories:
        db.init_user_categories(user_id)
        categories = db.get_user_categories(user_id)
    
    await message.answer(
        f"👋 Добро пожаловать в Финансовый помощник!\n\n"
        f"У тебя настроено {len(categories)} категорий.\n"
        f"Выбери категорию для добавления расхода или зайди в настройки ⚙️",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await get_main_keyboard(user_id)
    )

# ----- СТАТИСТИКА -----
@dp.message(F.text == "📊 Статистика")
async def handle_stats(message: Message):
    """Показывает статистику"""
    user_id = message.from_user.id
    
    # Определяем, какую клавиатуру показывать после статистики
    if user_id in user_temp_data and user_temp_data[user_id].get('editing_mode'):
        reply_markup = await get_edit_keyboard(user_id)
    else:
        reply_markup = await get_main_keyboard(user_id)
    
    try:
        import matplotlib.pyplot as plt
        import io
        
        stats = db.get_category_stats(user_id, days=30)
        
        if not stats:
            await message.answer(
                "📭 За последний месяц трат нет.",
                reply_markup=reply_markup
            )
            return
        
        # Создаем график
        categories = [cat for cat, _ in stats]
        amounts = [amt for _, amt in stats]
        
        plt.figure(figsize=(10, 10))
        plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=90)
        plt.title('📊 Расходы по категориям (30 дней)')
        plt.axis('equal')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        total = sum(amounts)
        
        await message.answer_photo(
            BufferedInputFile(buf.read(), filename="stats.png"),
            caption=f"📈 *Статистика за 30 дней*\n\n"
                   f"Всего потрачено: *{total:.2f} руб.*\n"
                   f"Категорий: {len(categories)}\n"
                   f"Средний чек: {total/len(stats):.2f} руб.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
    except ImportError:
        # Текстовая версия
        stats = db.get_category_stats(user_id, days=30)
        total = sum(amt for _, amt in stats)
        
        text = "📊 *Статистика за 30 дней:*\n\n"
        for category, amount in stats:
            percent = (amount / total) * 100
            text += f"{category}: *{amount:.2f} руб.* ({percent:.1f}%)\n"
        text += f"\n*Итого: {total:.2f} руб.*"
        
        await message.answer(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )


# ----- НАСТРОЙКИ -----
@dp.message(F.text == "⚙️ Настройки")
async def handle_settings(message: Message):
    """Вход в меню настроек"""
    user_id = message.from_user.id
    
    await message.answer(
        "⚙️ *Настройки*\n\n"
        "Что хочешь настроить?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await get_settings_keyboard()
    )


@dp.message(F.text == "🧹 Очистить статистику")
async def handle_clear_stats(message: Message):
    """Очистка статистики с подтверждением"""
    
    # Клавиатура для подтверждения
    confirm_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Да, удалить всю статистику")],
            [KeyboardButton(text="❌ Нет, отменить")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer(
        "⚠️ *Внимание!* Это удалит ВСЮ историю расходов.\n\n"
        "Категории останутся, но все записи о расходах будут удалены.\n"
        "Это действие нельзя отменить!\n\n"
        "Продолжить?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=confirm_keyboard
    )

@dp.message(F.text == "✅ Да, удалить всю статистику")
async def handle_clear_confirm(message: Message):
    """Подтверждение очистки статистики"""
    user_id = message.from_user.id
    
    deleted_count = db.clear_user_statistics(user_id)
    
    await message.answer(
        f"✅ Статистика очищена!\n"
        f"Удалено записей: *{deleted_count}*\n\n"
        f"Категории сохранены. Можно начать вести учёт заново!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await get_settings_keyboard()
    )

@dp.message(F.text == "❌ Нет, отменить")
async def handle_clear_cancel(message: Message):
    """Отмена очистки"""
    await message.answer(
        "Очистка отменена ✅",
        reply_markup=await get_settings_keyboard()
    )


@dp.message(F.text == "📝 Редактировать категории")
async def handle_edit_categories(message: Message):
    """Вход в режим редактирования категорий"""
    user_id = message.from_user.id
    
    # Входим в режим редактирования
    if user_id not in user_temp_data:
        user_temp_data[user_id] = {}
    user_temp_data[user_id]['editing_mode'] = True
    
    await message.answer(
        "📝 *Режим редактирования категорий*\n\n"
        "• Долгое нажатие на категорию — удаляет её\n"
        "• Кнопка «➕ Новая категория» — добавляет новую\n"
        "• «✅ Завершить редактирование» — выходит из режима",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await get_edit_keyboard(user_id)
    )


@dp.message(F.text == "⬅️ Назад в меню")
async def handle_back_to_menu(message: Message):
    """Возврат в главное меню"""
    user_id = message.from_user.id
    
    # Выходим из режима редактирования если были в нём
    if user_id in user_temp_data and user_temp_data[user_id].get('editing_mode'):
        user_temp_data[user_id]['editing_mode'] = False
    
    await message.answer(
        "Возвращаемся в главное меню...",
        reply_markup=await get_main_keyboard(user_id)
    )


    # ----- ЭКСПОРТ ДАННЫХ -----
@dp.message(F.text == "📤 Экспорт данных")
async def handle_export(message: Message):
    """Экспорт данных (заглушка)"""
    user_id = message.from_user.id
    total_expenses = db.get_today_expenses(user_id)
    
    await message.answer(
        f"📤 *Экспорт данных*\n\n"
        f"Эта функция в разработке.\n"
        f"Скоро можно будет экспортировать данные в Excel.\n\n"
        f"Сегодня потрачено: *{total_expenses} руб.*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await get_settings_keyboard()
    )

# ----- РЕЖИМ РЕДАКТИРОВАНИЯ КАТЕГОРИЙ -----
@dp.message(F.text == "➕ Новая категория")
async def add_category_start(message: Message, state: FSMContext):
    """Начало добавления новой категории"""
    user_id = message.from_user.id
    
    # Проверяем, что пользователь в режиме редактирования
    if user_id not in user_temp_data or not user_temp_data[user_id].get('editing_mode'):
        await message.answer("❌ Сначала зайди в режим редактирования категорий!")
        return
    
    await state.clear()
    
    await message.answer(
        "✏️ Введи название для новой категории:\n"
        "_Например: Техника, Обучение, Здоровье_",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.set_state(CategoryStates.waiting_for_category_name)


@dp.message(F.text == "✅ Завершить редактирование")
async def finish_editing(message: Message):
    """Выход из режима редактирования"""
    user_id = message.from_user.id
    
    if user_id in user_temp_data:
        user_temp_data[user_id]['editing_mode'] = False
    
    await message.answer(
        "✅ Изменения сохранены! Возвращаемся в настройки...",
        reply_markup=await get_settings_keyboard()
    )


# ----- РЕЖИМ ДОБАВЛЕНИЯ РАСХОДОВ -----
@dp.message(F.text.regexp(r'^[^\s]+\s.+$'))  # Сообщение вида "🍕 Еда"
async def handle_category_select(message: Message, state: FSMContext):
    logger.info(f"[DEBUG] Получено: '{message.text}', User: {message.from_user.id}")
    """Обработка выбора категории для добавления расхода"""
    user_id = message.from_user.id
    pressed_text = message.text
    
    # КРИТИЧЕСКИ ВАЖНО: игнорируем служебные кнопки
    service_buttons = [
        "📊 Статистика", 
        "⚙️ Настройки", 
        "📝 Редактировать категории",
        "📤 Экспорт данных", 
        "⬅️ Назад в меню",
        "➕ Новая категория",
        "✅ Завершить редактирование"
    ]
    
    if pressed_text in service_buttons:
        return  # Пусть эти кнопки обрабатываются своими хендлерами
    
    # Если пользователь в режиме редактирования - это ДОЛЖНО быть удаление
    if user_id in user_temp_data and user_temp_data[user_id].get('editing_mode'):
        # Долгое нажатие в режиме редактирования = УДАЛЕНИЕ
        categories = db.get_user_categories(user_id)
        for cat_id, name, emoji in categories:
            if pressed_text == f"{emoji} {name}":
                db.delete_category(user_id, cat_id)
                await message.answer(
                    f"🗑️ Категория «{name}» удалена!",
                    reply_markup=await get_edit_keyboard(user_id)
                )
                return
        await message.answer("Категория не найдена")
        return
    
    # Если НЕ в режиме редактирования - это ВЫБОР категории для расхода
    categories = db.get_user_categories(user_id)
    for cat_id, name, emoji in categories:
        if pressed_text == f"{emoji} {name}":
            # Сохраняем выбранную категорию
            if user_id not in user_temp_data:
                user_temp_data[user_id] = {}
            user_temp_data[user_id]['selected_category'] = cat_id
            user_temp_data[user_id]['selected_name'] = name
            user_temp_data[user_id]['selected_emoji'] = emoji
            
            await message.answer(
                f"Выбрано: {emoji} *{name}*\n\n"
                "📥 Введи сумму расхода:",
                parse_mode=ParseMode.MARKDOWN
            )
            await state.set_state(ExpenseStates.waiting_for_amount)
            return
    
    await message.answer("Категория не найдена")

@dp.message(ExpenseStates.waiting_for_amount)
async def handle_expense_amount(message: Message, state: FSMContext):
    """Обработка ввода суммы расхода"""
    user_id = message.from_user.id
    
    try:
        amount = float(message.text.replace(',', '.'))
        
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля!")
            return
        
        # Проверяем выбранную категорию
        if user_id not in user_temp_data or 'selected_category' not in user_temp_data[user_id]:
            await message.answer("❌ Сначала выбери категорию!")
            await state.clear()
            return
        
        cat_id = user_temp_data[user_id]['selected_category']
        cat_name = user_temp_data[user_id]['selected_name']
        cat_emoji = user_temp_data[user_id]['selected_emoji']
        
        # Добавляем расход
        db.add_expense(user_id, cat_id, amount)
        
        # Очищаем временные данные
        if user_id in user_temp_data:
            if 'selected_category' in user_temp_data[user_id]:
                del user_temp_data[user_id]['selected_category']
            if 'selected_name' in user_temp_data[user_id]:
                del user_temp_data[user_id]['selected_name']
            if 'selected_emoji' in user_temp_data[user_id]:
                del user_temp_data[user_id]['selected_emoji']
        
        await message.answer(
            f"✅ Расход добавлен!\n"
            f"{cat_emoji} *{cat_name}*: {amount:.2f} руб.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=await get_main_keyboard(user_id)
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введи число! Например: 1500 или 299.99")




@dp.message(CategoryStates.waiting_for_category_name)
async def add_category_name(message: Message, state: FSMContext):
    """Получаем название категории"""
    name = message.text.strip()
    
    if len(name) > 20:
        await message.answer("❌ Слишком длинное название (макс 20 символов)")
        return
    
    await state.update_data(category_name=name)
    await message.answer(
        f"📝 Название: *{name}*\n\n"
        "Теперь отправь эмодзи для категории (или любой символ):\n"
        "_Пропустить — отправь /skip_",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.set_state(CategoryStates.waiting_for_category_emoji)

@dp.message(CategoryStates.waiting_for_category_emoji)
async def add_category_emoji(message: Message, state: FSMContext):
    """Завершаем создание категории"""
    user_data = await state.get_data()
    name = user_data['category_name']
    
    if message.text == "/skip":
        emoji = "➕"
    else:
        emoji = message.text[:2]
    
    # Добавляем в БД
    db.add_category(message.from_user.id, name, emoji)
    
    await message.answer(
        f"✅ Категория добавлена!\n{emoji} *{name}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await get_edit_keyboard(message.from_user.id)
    )
    await state.clear()
 

# ========== ЗАПУСК БОТА ==========
async def main():
    logger.info("Запуск бота...")
    me = await bot.get_me()
    logger.info(f"Бот @{me.username} запущен!")
    print(f"\n=== Бот @{me.username} запущен ===")
    print("Бот готов к работе! Напиши /start или нажми кнопку START")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from config import MAINTENANCE_TYPES, INTERVAL_FIELDS, REPAIR_CATEGORIES


# ============================================================
# REPLY-КЛАВИАТУРЫ (внизу экрана)
# ============================================================

def main_menu():
    """Главное меню бота."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Мои машины"), KeyboardButton(text="➕ Добавить машину")],
            [KeyboardButton(text="📊 Обновить пробег"), KeyboardButton(text="📝 Добавить замену")],
            [KeyboardButton(text="🔧 Добавить работу")],
        ],
        resize_keyboard=True,
    )


def skip_or_enter():
    """Кнопка «Пропустить» для анкеты."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True,
    )


# ============================================================
# INLINE-КЛАВИАТУРЫ (внутри сообщений)
# ============================================================

def vehicles_inline(vehicles, prefix="vehicle_"):
    """Список машин для выбора. prefix задаёт действие."""
    buttons = []
    for v in vehicles:
        vid, brand, model, year, mileage = v
        buttons.append([InlineKeyboardButton(
            text=f"{brand} {model} ({year}) — {mileage} км",
            callback_data=f"{prefix}{vid}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def vehicle_actions(vehicle_id):
    """Действия с выбранной машиной."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛢 Что менять?", callback_data=f"status_{vehicle_id}")],
        [InlineKeyboardButton(text="📜 История", callback_data=f"hist_{vehicle_id}_all")],
        [
            InlineKeyboardButton(text="🔧 Только ремонты", callback_data=f"hist_{vehicle_id}_repair"),
            InlineKeyboardButton(text="🛢 Только замены", callback_data=f"hist_{vehicle_id}_consumable"),
        ],
        [InlineKeyboardButton(text="📤 Экспорт CSV", callback_data=f"export_{vehicle_id}")],
        [InlineKeyboardButton(text="💰 Расходы", callback_data=f"costs_{vehicle_id}")],
        [InlineKeyboardButton(text="✏️ Изменить пробег", callback_data=f"upd_mileage_{vehicle_id}")],
        [InlineKeyboardButton(text="⚙️ Интервалы", callback_data=f"intervals_{vehicle_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_vehicle_{vehicle_id}")],
    ])


def maintenance_types_inline():
    """Выбор типа обслуживания при добавлении записи о расходнике."""
    buttons = []
    for key, label in MAINTENANCE_TYPES.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"mtype_{key}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def intervals_inline():
    """Список полей интервалов для редактирования."""
    buttons = []
    for key, label in INTERVAL_FIELDS.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"editint_{key}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_vehicle")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_only():
    """Только кнопка «Назад»."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_vehicle")]
    ])


# ============================================================
# КНОПКИ ПОД НАПОМИНАНИЯМИ
# ============================================================

def reminder_actions_inline(vehicle_id, type_key):
    """Три кнопки под напоминанием о расходнике."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Уже поменял",
            callback_data=f"remind_done_{vehicle_id}_{type_key}",
        )],
        [
            InlineKeyboardButton(
                text="⏰ Напомнить позже",
                callback_data=f"remind_snooze_{vehicle_id}_{type_key}",
            ),
            InlineKeyboardButton(
                text="❌ Пропустить на месяц",
                callback_data=f"remind_skip_{vehicle_id}_{type_key}",
            ),
        ],
    ])


def mileage_reminder_inline(vehicle_id):
    """Кнопка под напоминанием об обновлении пробега."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📊 Обновить пробег",
            callback_data=f"upd_mileage_{vehicle_id}",
        )],
    ])


# ============================================================
# КНОПКИ ДЛЯ РЕМОНТОВ
# ============================================================

def repair_added_inline(record_id):
    """Кнопки под сообщением о добавленной работе."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✏️ Изменить категорию",
            callback_data=f"repair_editcat_{record_id}",
        )],
    ])


def categories_inline(record_id):
    """Список категорий для выбора."""
    buttons = []
    for key, label in REPAIR_CATEGORIES.items():
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"repair_setcat_{record_id}_{key}",
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="repair_cancel_cat")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
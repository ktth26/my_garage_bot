from datetime import datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
from config import (
    MILEAGE_REMINDER_DAYS, WARN_KM_LEFT, WARN_DAYS_LEFT,
    OVERDUE_REMINDER_DAYS, MAINTENANCE_TYPES,
)
from keyboards import reminder_actions_inline, mileage_reminder_inline

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ
# ============================================================

def check_item(v, type_key, label, interval_km, interval_months):
    """Проверяет один пункт обслуживания.
    Возвращает:
      None — всё хорошо (не скоро, не просрочено)
      ('soon', km_left, days_left) — скоро менять
      ('overdue', km_left, days_left) — просрочено
    """
    last = db.get_last_maintenance(v["id"], type_key)
    if not last:
        return None

    last_mileage = last["mileage"]
    last_date = datetime.fromisoformat(last["date"]).date()
    today = datetime.now().date()

    km_left = None
    days_left = None
    is_overdue = False
    is_soon = False

    if interval_km:
        km_left = (last_mileage + interval_km) - v["current_mileage"]
        if km_left <= 0:
            is_overdue = True
        elif km_left <= WARN_KM_LEFT:
            is_soon = True

    if interval_months:
        next_date = last_date + timedelta(days=interval_months * 30)
        days_left = (next_date - today).days
        if days_left <= 0:
            is_overdue = True
        elif days_left <= WARN_DAYS_LEFT:
            is_soon = True

    if is_overdue:
        return ("overdue", km_left, days_left)
    if is_soon:
        return ("soon", km_left, days_left)
    return None


def is_snoozed(vehicle_id, type_key):
    """Проверяет, отложено ли напоминание сейчас."""
    until = db.get_snooze_until(vehicle_id, type_key)
    if not until:
        return False
    return datetime.now() < datetime.fromisoformat(until)


def should_send_overdue(vehicle_id, type_key):
    """Просрочка: отправляем раз в OVERDUE_REMINDER_DAYS."""
    last = db.get_last_warning(vehicle_id, type_key, "overdue")
    if not last:
        return True
    days_since = (datetime.now() - datetime.fromisoformat(last)).days
    return days_since >= OVERDUE_REMINDER_DAYS


def should_send_soon(vehicle_id, type_key):
    """«Скоро» — отправляем один раз, пока не сбросят заменой."""
    last = db.get_last_warning(vehicle_id, type_key, "soon")
    return last is None


def format_left(km_left, days_left):
    """Формирует текст «осталось X км / Y дней»."""
    parts = []
    if km_left is not None:
        if km_left <= 0:
            parts.append(f"просрочено на {abs(km_left)} км")
        else:
            parts.append(f"осталось {km_left} км")
    if days_left is not None:
        if days_left <= 0:
            parts.append(f"просрочено на {abs(days_left)} дн.")
        else:
            parts.append(f"осталось {days_left} дн.")
    return ", ".join(parts) if parts else ""


# ============================================================
# ГЛАВНАЯ ПРОВЕРКА
# ============================================================

async def daily_check(bot: Bot):
    """Каждое утро проверяем все машины и рассылаем напоминания.
    Ремонты (kind='repair') в напоминаниях НЕ участвуют.
    """
    print(f"[{datetime.now().isoformat()}] Планировщик: проверка...")

    vehicles = db.get_all_vehicles()

    items = [
        ("oil", "Моторное масло", "oil_interval_km", "oil_interval_months"),
        ("air_filter", "Воздушный фильтр", "air_filter_interval_km", "air_filter_interval_months"),
        ("cabin_filter", "Салонный фильтр", "cabin_filter_interval_km", "cabin_filter_interval_months"),
        ("brake_fluid", "Тормозная жидкость", "brake_fluid_interval_km", "brake_fluid_interval_months"),
        ("coolant", "Охлаждающая жидкость", "coolant_interval_km", "coolant_interval_months"),
        ("spark_plugs", "Свечи зажигания", "spark_plugs_interval_km", None),
        ("to", "Общее ТО", "to_interval_km", "to_interval_months"),
        ("grm", "ГРМ", "grm_interval_km", "grm_interval_months"),
    ]

    for v in vehicles:
        user_id = v["user_id"]
        vehicle_id = v["id"]
        name = f"{v['brand']} {v['model']}"

        # ---------- 1. Напоминание об обновлении пробега ----------
        last_upd = v.get("last_mileage_update")
        if last_upd:
            days_since = (datetime.now() - datetime.fromisoformat(last_upd)).days
            last_reminder = v.get("last_reminder_sent")
            can_remind = True
            if last_reminder:
                days_since_reminder = (datetime.now() - datetime.fromisoformat(last_reminder)).days
                if days_since_reminder < MILEAGE_REMINDER_DAYS:
                    can_remind = False

            if days_since >= MILEAGE_REMINDER_DAYS and can_remind:
                try:
                    await bot.send_message(
                        user_id,
                        f"📊 Давно не обновляли пробег для <b>{name}</b> "
                        f"({days_since} дн. назад).\n\n"
                        f"Введите актуальный пробег — иначе я не смогу "
                        f"точно рассчитать следующее ТО.",
                        parse_mode="HTML",
                        reply_markup=mileage_reminder_inline(vehicle_id),
                    )
                    db.set_last_reminder(vehicle_id)
                except Exception as e:
                    print(f"Ошибка отправки пользователю {user_id}: {e}")

        # ---------- 2. Проверка ТО по каждому пункту ----------
        for type_key, label, km_field, months_field in items:
            if is_snoozed(vehicle_id, type_key):
                continue

            interval_km = v.get(km_field)
            interval_months = v.get(months_field) if months_field else None

            result = check_item(v, type_key, label, interval_km, interval_months)
            if result is None:
                continue

            kind, km_left, days_left = result
            left_text = format_left(km_left, days_left)

            if kind == "overdue":
                if not should_send_overdue(vehicle_id, type_key):
                    continue
                icon = "🔴"
                status_word = "просрочено!"
            else:  # soon
                if not should_send_soon(vehicle_id, type_key):
                    continue
                icon = "🟡"
                status_word = "скоро менять"

            try:
                await bot.send_message(
                    user_id,
                    f"⚠️ <b>{name}</b>\n\n"
                    f"{icon} <b>{label}</b> — {status_word}\n"
                    f"<i>{left_text}</i>\n\n"
                    f"Что сделать?",
                    parse_mode="HTML",
                    reply_markup=reminder_actions_inline(vehicle_id, type_key),
                )
                db.log_warning(vehicle_id, type_key, kind)
            except Exception as e:
                print(f"Ошибка отправки пользователю {user_id}: {e}")


def start_scheduler(bot: Bot):
    """Запускаем ежедневную проверку в 10:00 по Москве."""
    scheduler.add_job(
        daily_check,
        trigger="cron",
        hour=10,
        minute=0,
        args=[bot],
        id="daily_check",
        replace_existing=True,
    )
    scheduler.start()
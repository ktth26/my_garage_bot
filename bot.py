import asyncio
import csv
import io
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile

from config import (
    BOT_TOKEN,
    DEFAULT_OIL_INTERVAL_KM, DEFAULT_OIL_INTERVAL_MONTHS,
    DEFAULT_AIR_FILTER_INTERVAL_KM, DEFAULT_AIR_FILTER_INTERVAL_MONTHS,
    DEFAULT_CABIN_FILTER_INTERVAL_KM, DEFAULT_CABIN_FILTER_INTERVAL_MONTHS,
    DEFAULT_BRAKE_FLUID_INTERVAL_KM, DEFAULT_BRAKE_FLUID_INTERVAL_MONTHS,
    DEFAULT_COOLANT_INTERVAL_KM, DEFAULT_COOLANT_INTERVAL_MONTHS,
    DEFAULT_SPARK_PLUGS_INTERVAL_KM,
    DEFAULT_TO_INTERVAL_KM, DEFAULT_TO_INTERVAL_MONTHS,
    DEFAULT_GRM_INTERVAL_KM, DEFAULT_GRM_INTERVAL_MONTHS,
    MAINTENANCE_TYPES, INTERVAL_FIELDS, GUIDES, REPAIR_CATEGORIES,
    WARN_KM_LEFT, WARN_DAYS_LEFT,
    SNOOZE_DAYS, SKIP_DAYS,
)
import database as db
from keyboards import (
    main_menu, skip_or_enter, vehicles_inline, vehicle_actions,
    maintenance_types_inline, intervals_inline, back_only,
    reminder_actions_inline, mileage_reminder_inline,
    repair_added_inline, categories_inline,
)
from states import (
    AddVehicle, AddMaintenance, AddRepair, UpdateMileage,
    EditInterval, EditCategory,
)
from scheduler import start_scheduler

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# УТИЛИТЫ
# ============================================================

def is_skip(text: str) -> bool:
    return text.strip().lower() in ("пропустить", "skip", "-", "нет")


def parse_int(text: str):
    try:
        return int(text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        return None


def parse_float(text: str):
    try:
        return float(text.strip().replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def parse_date(text: str):
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fmt_date(iso_date: str) -> str:
    try:
        return datetime.fromisoformat(iso_date).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return iso_date or "—"


def vehicle_checks(v: dict):
    """Список пунктов для проверки: (type_key, label, km, months)."""
    return [
        ("oil", "Моторное масло", v["oil_interval_km"], v["oil_interval_months"]),
        ("air_filter", "Воздушный фильтр", v["air_filter_interval_km"], v["air_filter_interval_months"]),
        ("cabin_filter", "Салонный фильтр", v["cabin_filter_interval_km"], v["cabin_filter_interval_months"]),
        ("brake_fluid", "Тормозная жидкость", v["brake_fluid_interval_km"], v["brake_fluid_interval_months"]),
        ("coolant", "Охлаждающая жидкость", v["coolant_interval_km"], v["coolant_interval_months"]),
        ("spark_plugs", "Свечи зажигания", v["spark_plugs_interval_km"], None),
        ("to", "Общее ТО", v["to_interval_km"], v["to_interval_months"]),
        ("grm", "ГРМ", v["grm_interval_km"], v["grm_interval_months"]),
    ]


def calc_status(v: dict, type_key: str, interval_km, interval_months):
    last = db.get_last_maintenance(v["id"], type_key)
    if not last:
        return "❔", "нет данных"

    last_mileage = last["mileage"]
    last_date = datetime.fromisoformat(last["date"]).date()
    today = datetime.now().date()

    emoji = "✅"
    parts = []

    if interval_km:
        km_left = (last_mileage + interval_km) - v["current_mileage"]
        if km_left <= 0:
            emoji = "🔴"
            parts.append(f"просрочено на {abs(km_left)} км")
        elif km_left <= WARN_KM_LEFT:
            if emoji != "🔴":
                emoji = "🟡"
            parts.append(f"осталось {km_left} км")
        else:
            parts.append(f"осталось {km_left} км")

    if interval_months:
        next_date = last_date + timedelta(days=interval_months * 30)
        days_left = (next_date - today).days
        if days_left <= 0:
            emoji = "🔴"
            parts.append(f"просрочено на {abs(days_left)} дн.")
        elif days_left <= WARN_DAYS_LEFT:
            if emoji != "🔴":
                emoji = "🟡"
            parts.append(f"осталось {days_left} дн.")
        else:
            parts.append(f"осталось {days_left} дн.")

    return emoji, ", ".join(parts) if parts else "ок"


def record_label(rec: dict) -> str:
    """Человекочитаемая метка для записи истории."""
    if rec.get("kind") == "repair":
        name = rec.get("custom_name") or "Работа"
        cat = rec.get("category")
        cat_label = REPAIR_CATEGORIES.get(cat, "")
        if cat_label:
            return f"🔧 {name} ({cat_label})"
        return f"🔧 {name}"
    else:
        return MAINTENANCE_TYPES.get(rec.get("type"), rec.get("type") or "—")


# ============================================================
# СТАРТ
# ============================================================

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    db.add_user(message.from_user.id, message.from_user.username or "")
    await message.answer(
        "🚗 Добро пожаловать в <b>Мой Гараж</b>!\n\n"
        "Я помогу следить за состоянием машины: напомню о замене масла, "
        "фильтров и жидкостей, посчитаю расходы, а также сохраню историю "
        "всех ремонтов.\n\n"
        "Добавьте машину кнопкой <b>➕ Добавить машину</b>.",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())


# ============================================================
# АНКЕТА: ДОБАВЛЕНИЕ МАШИНЫ
# ============================================================

@dp.message(F.text == "➕ Добавить машину")
async def start_add_vehicle(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AddVehicle.brand)
    await message.answer("Введите <b>марку</b> машины (например, Toyota):", parse_mode="HTML")


@dp.message(AddVehicle.brand)
async def av_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text.strip())
    await state.set_state(AddVehicle.model)
    await message.answer("Введите <b>модель</b> (например, Camry):", parse_mode="HTML")


@dp.message(AddVehicle.model)
async def av_model(message: Message, state: FSMContext):
    await state.update_data(model=message.text.strip())
    await state.set_state(AddVehicle.year)
    await message.answer("Введите <b>год выпуска</b> (например, 2018):", parse_mode="HTML")


@dp.message(AddVehicle.year)
async def av_year(message: Message, state: FSMContext):
    year = parse_int(message.text)
    if not year or year < 1950 or year > datetime.now().year + 1:
        await message.answer("Введите корректный год (например, 2018):")
        return
    await state.update_data(year=year)
    await state.set_state(AddVehicle.vin)
    await message.answer(
        "Введите <b>VIN</b> или нажмите «Пропустить»:",
        reply_markup=skip_or_enter(), parse_mode="HTML",
    )


@dp.message(AddVehicle.vin)
async def av_vin(message: Message, state: FSMContext):
    vin = "" if is_skip(message.text) else message.text.strip().upper()
    await state.update_data(vin=vin)
    await state.set_state(AddVehicle.current_mileage)
    await message.answer(
        "Введите <b>текущий пробег</b> в км (только число):",
        reply_markup=main_menu(), parse_mode="HTML",
    )


@dp.message(AddVehicle.current_mileage)
async def av_mileage(message: Message, state: FSMContext):
    mileage = parse_int(message.text)
    if mileage is None or mileage < 0:
        await message.answer("Введите корректное число км:")
        return
    await state.update_data(current_mileage=mileage)
    await state.set_state(AddVehicle.monthly_mileage)
    await message.answer("Введите <b>среднемесячный пробег</b> в км (например, 1500):", parse_mode="HTML")


@dp.message(AddVehicle.monthly_mileage)
async def av_monthly(message: Message, state: FSMContext):
    mm = parse_int(message.text)
    if mm is None or mm < 0:
        await message.answer("Введите корректное число км в месяц:")
        return
    await state.update_data(monthly_mileage=mm)
    await state.set_state(AddVehicle.oil_interval_km)
    await message.answer(GUIDES["oil"], parse_mode="HTML")
    await message.answer(
        f"<b>Замена масла</b> — через сколько км? "
        f"(по умолчанию {DEFAULT_OIL_INTERVAL_KM}, нажмите «Пропустить»):",
        reply_markup=skip_or_enter(), parse_mode="HTML",
    )


async def _save_and_ask(
    message: Message, state: FSMContext,
    field_name: str, default_value, default_is_none: bool,
    next_state, next_guide_key: str,
    next_question: str, next_default_text: str,
):
    if is_skip(message.text):
        val = None if default_is_none else default_value
    else:
        val = parse_int(message.text)
        if val is None:
            await message.answer("Введите число или «Пропустить»:")
            return
    await state.update_data(**{field_name: val})
    await state.set_state(next_state)
    if next_guide_key:
        await message.answer(GUIDES[next_guide_key], parse_mode="HTML")
    await message.answer(
        f"{next_question} (по умолчанию {next_default_text}):",
        reply_markup=skip_or_enter(), parse_mode="HTML",
    )


@dp.message(AddVehicle.oil_interval_km)
async def av_oil_km(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "oil_interval_km", DEFAULT_OIL_INTERVAL_KM, False,
        AddVehicle.oil_interval_months, None,
        "<b>Замена масла</b> — через сколько месяцев?",
        str(DEFAULT_OIL_INTERVAL_MONTHS),
    )


@dp.message(AddVehicle.oil_interval_months)
async def av_oil_months(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "oil_interval_months", DEFAULT_OIL_INTERVAL_MONTHS, False,
        AddVehicle.air_filter_interval_km, "air_filter",
        "<b>Воздушный фильтр</b> — через сколько км?",
        str(DEFAULT_AIR_FILTER_INTERVAL_KM),
    )


@dp.message(AddVehicle.air_filter_interval_km)
async def av_af_km(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "air_filter_interval_km", DEFAULT_AIR_FILTER_INTERVAL_KM, False,
        AddVehicle.air_filter_interval_months, None,
        "<b>Воздушный фильтр</b> — через сколько месяцев?",
        str(DEFAULT_AIR_FILTER_INTERVAL_MONTHS),
    )


@dp.message(AddVehicle.air_filter_interval_months)
async def av_af_months(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "air_filter_interval_months", DEFAULT_AIR_FILTER_INTERVAL_MONTHS, False,
        AddVehicle.cabin_filter_interval_km, "cabin_filter",
        "<b>Салонный фильтр</b> — через сколько км?",
        str(DEFAULT_CABIN_FILTER_INTERVAL_KM),
    )


@dp.message(AddVehicle.cabin_filter_interval_km)
async def av_cf_km(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "cabin_filter_interval_km", DEFAULT_CABIN_FILTER_INTERVAL_KM, False,
        AddVehicle.cabin_filter_interval_months, None,
        "<b>Салонный фильтр</b> — через сколько месяцев?",
        str(DEFAULT_CABIN_FILTER_INTERVAL_MONTHS),
    )


@dp.message(AddVehicle.cabin_filter_interval_months)
async def av_cf_months(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "cabin_filter_interval_months", DEFAULT_CABIN_FILTER_INTERVAL_MONTHS, False,
        AddVehicle.brake_fluid_interval_km, "brake_fluid",
        "<b>Тормозная жидкость</b> — через сколько км?",
        str(DEFAULT_BRAKE_FLUID_INTERVAL_KM),
    )


@dp.message(AddVehicle.brake_fluid_interval_km)
async def av_bf_km(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "brake_fluid_interval_km", DEFAULT_BRAKE_FLUID_INTERVAL_KM, False,
        AddVehicle.brake_fluid_interval_months, None,
        "<b>Тормозная жидкость</b> — через сколько месяцев?",
        str(DEFAULT_BRAKE_FLUID_INTERVAL_MONTHS),
    )


@dp.message(AddVehicle.brake_fluid_interval_months)
async def av_bf_months(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "brake_fluid_interval_months", DEFAULT_BRAKE_FLUID_INTERVAL_MONTHS, False,
        AddVehicle.coolant_interval_km, "coolant",
        "<b>Охлаждающая жидкость</b> — через сколько км?",
        str(DEFAULT_COOLANT_INTERVAL_KM),
    )


@dp.message(AddVehicle.coolant_interval_km)
async def av_co_km(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "coolant_interval_km", DEFAULT_COOLANT_INTERVAL_KM, False,
        AddVehicle.coolant_interval_months, None,
        "<b>Охлаждающая жидкость</b> — через сколько месяцев?",
        str(DEFAULT_COOLANT_INTERVAL_MONTHS),
    )


@dp.message(AddVehicle.coolant_interval_months)
async def av_co_months(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "coolant_interval_months", DEFAULT_COOLANT_INTERVAL_MONTHS, False,
        AddVehicle.spark_plugs_interval_km, "spark_plugs",
        "<b>Свечи зажигания</b> — через сколько км?",
        str(DEFAULT_SPARK_PLUGS_INTERVAL_KM),
    )


@dp.message(AddVehicle.spark_plugs_interval_km)
async def av_sp_km(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "spark_plugs_interval_km", DEFAULT_SPARK_PLUGS_INTERVAL_KM, False,
        AddVehicle.to_interval_km, "to",
        "<b>Общее ТО</b> — через сколько км?",
        str(DEFAULT_TO_INTERVAL_KM),
    )


@dp.message(AddVehicle.to_interval_km)
async def av_to_km(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "to_interval_km", DEFAULT_TO_INTERVAL_KM, False,
        AddVehicle.to_interval_months, None,
        "<b>Общее ТО</b> — через сколько месяцев?",
        str(DEFAULT_TO_INTERVAL_MONTHS),
    )


@dp.message(AddVehicle.to_interval_months)
async def av_to_months(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "to_interval_months", DEFAULT_TO_INTERVAL_MONTHS, False,
        AddVehicle.grm_interval_km, "grm",
        "<b>ГРМ</b> — через сколько км?",
        str(DEFAULT_GRM_INTERVAL_KM),
    )


@dp.message(AddVehicle.grm_interval_km)
async def av_grm_km(message: Message, state: FSMContext):
    await _save_and_ask(
        message, state,
        "grm_interval_km", DEFAULT_GRM_INTERVAL_KM, False,
        AddVehicle.grm_interval_months, None,
        "<b>ГРМ</b> — через сколько месяцев?",
        str(DEFAULT_GRM_INTERVAL_MONTHS),
    )


@dp.message(AddVehicle.grm_interval_months)
async def av_grm_months(message: Message, state: FSMContext):
    val = DEFAULT_GRM_INTERVAL_MONTHS if is_skip(message.text) else parse_int(message.text)
    if val is None:
        await message.answer("Введите число или «Пропустить»:")
        return
    await state.update_data(grm_interval_months=val)
    await state.set_state(AddVehicle.last_oil_date)
    await message.answer(
        "Последний вопрос: когда вы <b>последний раз меняли масло</b>?\n"
        "Введите дату в формате <b>ДД.ММ.ГГГГ</b> или «Пропустить»:",
        reply_markup=skip_or_enter(), parse_mode="HTML",
    )


@dp.message(AddVehicle.last_oil_date)
async def av_last_oil_date(message: Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(last_oil_date=None, last_oil_mileage=None)
        await finish_vehicle(message, state)
        return
    date = parse_date(message.text)
    if not date:
        await message.answer("Неверный формат. Введите ДД.ММ.ГГГГ или «Пропустить»:")
        return
    await state.update_data(last_oil_date=date)
    await state.set_state(AddVehicle.last_oil_mileage)
    await message.answer("На каком пробеге меняли масло? (число км):")


@dp.message(AddVehicle.last_oil_mileage)
async def av_last_oil_mileage(message: Message, state: FSMContext):
    mileage = parse_int(message.text)
    if mileage is None:
        await message.answer("Введите число:")
        return
    await state.update_data(last_oil_mileage=mileage)
    await finish_vehicle(message, state)


async def finish_vehicle(message: Message, state: FSMContext):
    data = await state.get_data()
    vehicle_id = db.add_vehicle(message.from_user.id, data)

    if data.get("last_oil_date") and data.get("last_oil_mileage") is not None:
        db.add_maintenance(
            vehicle_id, "oil", data["last_oil_date"],
            data["last_oil_mileage"], notes="Добавлено при первом заполнении",
        )

    await state.clear()
    await message.answer(
        f"✅ Машина добавлена!\n\n"
        f"<b>{data['brand']} {data['model']} ({data['year']})</b>\n"
        f"Пробег: {data['current_mileage']} км\n"
        f"Среднемесячный: {data['monthly_mileage']} км\n\n"
        f"Бот будет проверять статус каждое утро и напомнит, когда пора что-то менять.",
        reply_markup=main_menu(), parse_mode="HTML",
    )


# ============================================================
# МОИ МАШИНЫ
# ============================================================

@dp.message(F.text == "🚗 Мои машины")
async def my_vehicles(message: Message, state: FSMContext):
    await state.clear()
    vehicles = db.get_user_vehicles(message.from_user.id)
    if not vehicles:
        await message.answer("У вас пока нет машин. Нажмите «➕ Добавить машину».")
        return
    await message.answer("Выберите машину:", reply_markup=vehicles_inline(vehicles, "vehicle_"))


@dp.callback_query(F.data.startswith("vehicle_"))
async def vehicle_card(call: CallbackQuery):
    vehicle_id = int(call.data.split("_")[1])
    v = db.get_vehicle_dict(vehicle_id)
    if not v:
        await call.answer("Машина не найдена")
        return
    text = (
        f"🚗 <b>{v['brand']} {v['model']} ({v['year']})</b>\n"
        f"VIN: {v['vin'] or '—'}\n"
        f"Текущий пробег: <b>{v['current_mileage']} км</b>\n"
        f"Среднемесячный: {v['monthly_mileage']} км"
    )
    await call.message.edit_text(text, reply_markup=vehicle_actions(vehicle_id), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "back_to_vehicle")
async def back_to_vehicle(call: CallbackQuery, state: FSMContext):
    await state.clear()
    vehicles = db.get_user_vehicles(call.from_user.id)
    await call.message.edit_text("Выберите машину:", reply_markup=vehicles_inline(vehicles, "vehicle_"))
    await call.answer()


# ============================================================
# СТАТУС
# ============================================================

@dp.callback_query(F.data.startswith("status_"))
async def status(call: CallbackQuery):
    vehicle_id = int(call.data.split("_")[1])
    v = db.get_vehicle_dict(vehicle_id)
    if not v:
        await call.answer("Машина не найдена")
        return

    lines = [f"🔧 <b>Статус: {v['brand']} {v['model']}</b>",
             f"Текущий пробег: {v['current_mileage']} км\n"]

    for type_key, label, ikm, imonths in vehicle_checks(v):
        emoji, txt = calc_status(v, type_key, ikm, imonths)
        lines.append(f"{emoji} <b>{label}</b>: {txt}")

    await call.message.edit_text("\n".join(lines), reply_markup=vehicle_actions(vehicle_id), parse_mode="HTML")
    await call.answer()


# ============================================================
# ИСТОРИЯ (с фильтрами)
# ============================================================

@dp.callback_query(F.data.startswith("hist_"))
async def history(call: CallbackQuery):
    # hist_<vehicle_id>_<filter>
    parts = call.data.split("_", 2)
    vehicle_id = int(parts[1])
    filter_kind = parts[2]  # all / repair / consumable

    kind_filter = None
    title_suffix = ""
    if filter_kind == "repair":
        kind_filter = "repair"
        title_suffix = " — ремонты"
    elif filter_kind == "consumable":
        kind_filter = "consumable"
        title_suffix = " — замены"

    records = db.get_history(vehicle_id, kind_filter)

    if not records:
        await call.message.edit_text(
            f"📜 <b>История{title_suffix}</b>\n\nПусто.",
            reply_markup=vehicle_actions(vehicle_id),
            parse_mode="HTML",
        )
        await call.answer()
        return

    lines = [f"📜 <b>История{title_suffix}</b>\n"]
    for r in records[:25]:
        label = record_label(r)
        date = fmt_date(r["date"])
        cost = (r["cost_parts"] or 0) + (r["cost_work"] or 0)
        cost_str = f" — {cost:.0f} ₽" if cost > 0 else ""
        lines.append(f"{date} — {label} — {r['mileage']} км{cost_str}")
    if len(records) > 25:
        lines.append(f"\n... и ещё {len(records) - 25} записей")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=vehicle_actions(vehicle_id),
        parse_mode="HTML",
    )
    await call.answer()


# ============================================================
# ЭКСПОРТ CSV (расширенный)
# ============================================================

@dp.callback_query(F.data.startswith("export_"))
async def export_csv(call: CallbackQuery):
    vehicle_id = int(call.data.split("_")[1])
    v = db.get_vehicle_dict(vehicle_id)
    records = db.get_history(vehicle_id, None)
    if not records:
        await call.answer("История пуста — нечего экспортировать.", show_alert=True)
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Дата", "Вид", "Категория", "Название",
        "Пробег (км)", "Запчасти (₽)", "Работы (₽)", "Итого (₽)", "Заметки",
    ])
    for r in records:
        kind_label = "Ремонт" if r.get("kind") == "repair" else "Замена"
        if r.get("kind") == "repair":
            cat = r.get("category") or ""
            cat_label = REPAIR_CATEGORIES.get(cat, cat)
            name = r.get("custom_name") or ""
        else:
            cat_label = ""
            name = MAINTENANCE_TYPES.get(r.get("type"), r.get("type") or "")
        writer.writerow([
            r["date"], kind_label, cat_label, name,
            r["mileage"],
            r["cost_parts"] or 0,
            r["cost_work"] or 0,
            (r["cost_parts"] or 0) + (r["cost_work"] or 0),
            r["notes"] or "",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    filename = f"history_{v['brand']}_{v['model']}_{datetime.now().strftime('%Y%m%d')}.csv"
    file = BufferedInputFile(csv_bytes, filename=filename)
    await call.message.answer_document(file, caption=f"📤 История: {v['brand']} {v['model']}")
    await call.answer()


# ============================================================
# РАСХОДЫ (с разбивкой)
# ============================================================

@dp.callback_query(F.data.startswith("costs_"))
async def costs_show(call: CallbackQuery):
    vehicle_id = int(call.data.split("_")[1])
    v = db.get_vehicle_dict(vehicle_id)

    parts, work = db.get_total_costs(vehicle_id)
    parts = parts or 0
    work = work or 0
    total = parts + work

    by_kind = db.get_costs_by_kind(vehicle_id)
    cons_parts, cons_work = by_kind.get("consumable", (0, 0))
    rep_parts, rep_work = by_kind.get("repair", (0, 0))
    cons_total = (cons_parts or 0) + (cons_work or 0)
    rep_total = (rep_parts or 0) + (rep_work or 0)

    lines = [
        f"💰 <b>Расходы: {v['brand']} {v['model']}</b>\n",
        f"Всего: <b>{total:.0f} ₽</b>",
        f"├ Замены (расходники): {cons_total:.0f} ₽",
        f"└ Ремонты: {rep_total:.0f} ₽",
    ]

    by_cat = db.get_costs_by_category(vehicle_id)
    if by_cat:
        lines.append("\n<b>По категориям:</b>")
        for cat, p, w in by_cat:
            cat_total = (p or 0) + (w or 0)
            if cat_total <= 0:
                continue
            cat_label = REPAIR_CATEGORIES.get(cat, MAINTENANCE_TYPES.get(cat, cat))
            lines.append(f"• {cat_label}: {cat_total:.0f} ₽")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=vehicle_actions(vehicle_id),
        parse_mode="HTML",
    )
    await call.answer()


# ============================================================
# ОБНОВЛЕНИЕ ПРОБЕГА
# ============================================================

@dp.message(F.text == "📊 Обновить пробег")
async def update_mileage_start(message: Message, state: FSMContext):
    await state.clear()
    vehicles = db.get_user_vehicles(message.from_user.id)
    if not vehicles:
        await message.answer("Сначала добавьте машину.")
        return
    await message.answer("Выберите машину:", reply_markup=vehicles_inline(vehicles, "upd_mileage_"))


@dp.callback_query(F.data.startswith("upd_mileage_"))
async def update_mileage_prompt(call: CallbackQuery, state: FSMContext):
    vehicle_id = int(call.data.split("_")[2])
    await state.set_state(UpdateMileage.new_mileage)
    await state.update_data(vehicle_id=vehicle_id)
    await call.message.answer("Введите новый пробег (число км):")
    await call.answer()


@dp.message(UpdateMileage.new_mileage)
async def update_mileage_save(message: Message, state: FSMContext):
    mileage = parse_int(message.text)
    if mileage is None or mileage < 0:
        await message.answer("Введите корректное число:")
        return
    data = await state.get_data()
    db.update_mileage(data["vehicle_id"], mileage)
    await state.clear()
    await message.answer(
        f"✅ Пробег обновлён: <b>{mileage} км</b>",
        reply_markup=main_menu(), parse_mode="HTML",
    )


# ============================================================
# РЕДАКТИРОВАНИЕ ИНТЕРВАЛОВ
# ============================================================

@dp.callback_query(F.data.startswith("intervals_"))
async def intervals_menu(call: CallbackQuery, state: FSMContext):
    vehicle_id = int(call.data.split("_")[1])
    await state.update_data(vehicle_id=vehicle_id)
    await call.message.edit_text(
        "⚙️ <b>Интервалы обслуживания</b>\n\nВыберите, что изменить:",
        reply_markup=intervals_inline(), parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("editint_"))
async def edit_interval_prompt(call: CallbackQuery, state: FSMContext):
    field = call.data.split("_", 1)[1]
    await state.update_data(field=field)
    await state.set_state(EditInterval.new_value)
    label = INTERVAL_FIELDS.get(field, field)
    await call.message.edit_text(
        f"Введите новое значение для «<b>{label}</b>» (целое число):",
        parse_mode="HTML", reply_markup=back_only(),
    )
    await call.answer()


@dp.message(EditInterval.new_value)
async def edit_interval_save(message: Message, state: FSMContext):
    val = parse_int(message.text)
    if val is None or val <= 0:
        await message.answer("Введите положительное целое число:")
        return
    data = await state.get_data()
    db.update_interval(data["vehicle_id"], data["field"], val)
    label = INTERVAL_FIELDS.get(data["field"], data["field"])
    await state.clear()
    await message.answer(
        f"✅ Интервал обновлён: <b>{label}</b> → {val}",
        reply_markup=main_menu(), parse_mode="HTML",
    )


# ============================================================
# ДОБАВЛЕНИЕ ЗАМЕНЫ (расходники)
# ============================================================

@dp.message(F.text == "📝 Добавить замену")
async def add_maintenance_start(message: Message, state: FSMContext):
    await state.clear()
    vehicles = db.get_user_vehicles(message.from_user.id)
    if not vehicles:
        await message.answer("Сначала добавьте машину.")
        return
    await message.answer("Выберите машину:", reply_markup=vehicles_inline(vehicles, "addmaint_"))


@dp.callback_query(F.data.startswith("addmaint_"))
async def addmaint_choose_type(call: CallbackQuery, state: FSMContext):
    vehicle_id = int(call.data.split("_")[1])
    await state.set_state(AddMaintenance.choose_type)
    await state.update_data(vehicle_id=vehicle_id)
    await call.message.answer("Что делали?", reply_markup=maintenance_types_inline())
    await call.answer()


@dp.callback_query(F.data.startswith("mtype_"), AddMaintenance.choose_type)
async def addmaint_type(call: CallbackQuery, state: FSMContext):
    type_key = call.data.split("_", 1)[1]
    await state.update_data(type=type_key)
    await state.set_state(AddMaintenance.date)
    await call.message.answer("Введите дату в формате <b>ДД.ММ.ГГГГ</b>:", parse_mode="HTML")
    await call.answer()


@dp.message(AddMaintenance.date)
async def addmaint_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if not date:
        await message.answer("Неверный формат. Введите ДД.ММ.ГГГГ:")
        return
    await state.update_data(date=date)
    await state.set_state(AddMaintenance.mileage)
    await message.answer("Введите пробег на момент работы (км):")


@dp.message(AddMaintenance.mileage)
async def addmaint_mileage(message: Message, state: FSMContext):
    mileage = parse_int(message.text)
    if mileage is None:
        await message.answer("Введите число:")
        return
    await state.update_data(mileage=mileage)
    await state.set_state(AddMaintenance.cost_parts)
    await message.answer("Стоимость запчастей (₽)? Введите 0, если не указывать:")


@dp.message(AddMaintenance.cost_parts)
async def addmaint_parts(message: Message, state: FSMContext):
    val = parse_float(message.text)
    if val is None:
        await message.answer("Введите число:")
        return
    await state.update_data(cost_parts=val)
    await state.set_state(AddMaintenance.cost_work)
    await message.answer("Стоимость работ (₽)?")


@dp.message(AddMaintenance.cost_work)
async def addmaint_work(message: Message, state: FSMContext):
    val = parse_float(message.text)
    if val is None:
        await message.answer("Введите число:")
        return
    await state.update_data(cost_work=val)
    await state.set_state(AddMaintenance.notes)
    await message.answer("Заметки (или «Пропустить»):", reply_markup=skip_or_enter())


@dp.message(AddMaintenance.notes)
async def addmaint_notes(message: Message, state: FSMContext):
    notes = "" if is_skip(message.text) else message.text.strip()
    data = await state.get_data()
    db.add_maintenance(
        data["vehicle_id"], data["type"], data["date"], data["mileage"],
        data["cost_parts"], data["cost_work"], notes,
    )
    v = db.get_vehicle_dict(data["vehicle_id"])
    if v and data["mileage"] > v["current_mileage"]:
        db.update_mileage(data["vehicle_id"], data["mileage"])

    await state.clear()
    label = MAINTENANCE_TYPES.get(data["type"], data["type"])
    await message.answer(
        f"✅ Запись добавлена: <b>{label}</b>\n"
        f"Дата: {fmt_date(data['date'])}\n"
        f"Пробег: {data['mileage']} км\n"
        f"Запчасти: {data['cost_parts']} ₽ | Работы: {data['cost_work']} ₽",
        reply_markup=main_menu(), parse_mode="HTML",
    )


# ============================================================
# ДОБАВЛЕНИЕ РАБОТЫ (ремонты)
# ============================================================

@dp.message(F.text == "🔧 Добавить работу")
async def add_repair_start(message: Message, state: FSMContext):
    await state.clear()
    vehicles = db.get_user_vehicles(message.from_user.id)
    if not vehicles:
        await message.answer("Сначала добавьте машину.")
        return
    await message.answer("Выберите машину:", reply_markup=vehicles_inline(vehicles, "addrepair_"))


@dp.callback_query(F.data.startswith("addrepair_"))
async def addrepair_choose_vehicle(call: CallbackQuery, state: FSMContext):
    vehicle_id = int(call.data.split("_")[1])
    await state.update_data(vehicle_id=vehicle_id)
    await state.set_state(AddRepair.name)
    await call.message.answer(
        "Что делали? Введите коротко, например:\n"
        "<i>Замена амортизаторов передних</i>\n"
        "<i>Ремонт рулевой рейки</i>\n"
        "<i>Замена лобового стекла</i>",
        parse_mode="HTML",
    )
    await call.answer()


@dp.message(AddRepair.name)
async def addrepair_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Слишком короткое название. Введите ещё раз:")
        return
    await state.update_data(custom_name=name)
    await state.set_state(AddRepair.date)
    await message.answer("Введите дату в формате <b>ДД.ММ.ГГГГ</b>:", parse_mode="HTML")


@dp.message(AddRepair.date)
async def addrepair_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if not date:
        await message.answer("Неверный формат. Введите ДД.ММ.ГГГГ:")
        return
    await state.update_data(date=date)
    await state.set_state(AddRepair.mileage)
    await message.answer("Введите пробег на момент работы (км):")


@dp.message(AddRepair.mileage)
async def addrepair_mileage(message: Message, state: FSMContext):
    mileage = parse_int(message.text)
    if mileage is None:
        await message.answer("Введите число:")
        return
    await state.update_data(mileage=mileage)
    await state.set_state(AddRepair.cost_parts)
    await message.answer("Стоимость запчастей (₽)? Введите 0 или «Пропустить», если не указывать:",
                         reply_markup=skip_or_enter())


@dp.message(AddRepair.cost_parts)
async def addrepair_parts(message: Message, state: FSMContext):
    if is_skip(message.text):
        val = 0
    else:
        val = parse_float(message.text)
        if val is None:
            await message.answer("Введите число или «Пропустить»:")
            return
    await state.update_data(cost_parts=val)
    await state.set_state(AddRepair.cost_work)
    await message.answer("Стоимость работ (₽)? Введите 0 или «Пропустить»:",
                         reply_markup=skip_or_enter())


@dp.message(AddRepair.cost_work)
async def addrepair_work(message: Message, state: FSMContext):
    if is_skip(message.text):
        val = 0
    else:
        val = parse_float(message.text)
        if val is None:
            await message.answer("Введите число или «Пропустить»:")
            return
    await state.update_data(cost_work=val)
    await state.set_state(AddRepair.notes)
    await message.answer("Заметки (или «Пропустить»):", reply_markup=skip_or_enter())


@dp.message(AddRepair.notes)
async def addrepair_notes(message: Message, state: FSMContext):
    notes = "" if is_skip(message.text) else message.text.strip()
    data = await state.get_data()

    record_id = db.add_repair(
        data["vehicle_id"], data["custom_name"], data["date"], data["mileage"],
        cost_parts=data["cost_parts"], cost_work=data["cost_work"], notes=notes,
    )

    # Обновляем пробег машины, если записанный больше текущего
    v = db.get_vehicle_dict(data["vehicle_id"])
    if v and data["mileage"] > v["current_mileage"]:
        db.update_mileage(data["vehicle_id"], data["mileage"])

    # Получаем запись, чтобы узнать присвоенную категорию
    rec = db.get_record(record_id)
    cat_key = rec.get("category") if rec else None
    cat_label = REPAIR_CATEGORIES.get(cat_key, "—")

    await state.update_data(record_id=record_id)
    await state.set_state(AddRepair.confirm)

    await message.answer(
        f"✅ <b>Работа добавлена</b>\n\n"
        f"<b>{data['custom_name']}</b>\n"
        f"Категория: <b>{cat_label}</b>\n"
        f"Дата: {fmt_date(data['date'])}\n"
        f"Пробег: {data['mileage']} км\n"
        f"Запчасти: {data['cost_parts']} ₽ | Работы: {data['cost_work']} ₽",
        reply_markup=repair_added_inline(record_id),
        parse_mode="HTML",
    )


# ============================================================
# ИЗМЕНЕНИЕ КАТЕГОРИИ
# ============================================================

@dp.callback_query(F.data.startswith("repair_editcat_"))
async def repair_editcat(call: CallbackQuery, state: FSMContext):
    record_id = int(call.data.split("_")[2])
    await state.set_state(EditCategory.choose)
    await state.update_data(record_id=record_id)
    await call.message.edit_text(
        "Выберите новую категорию:",
        reply_markup=categories_inline(record_id),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("repair_setcat_"))
async def repair_setcat(call: CallbackQuery, state: FSMContext):
    # repair_setcat_<record_id>_<category_key>
    parts = call.data.split("_", 3)
    record_id = int(parts[2])
    category = parts[3]

    db.update_record_category(record_id, category)
    rec = db.get_record(record_id)
    cat_label = REPAIR_CATEGORIES.get(category, category)
    name = rec.get("custom_name") if rec else "—"

    await state.clear()

    await call.message.edit_text(
        f"✅ Категория обновлена\n\n"
        f"<b>{name}</b>\n"
        f"Новая категория: <b>{cat_label}</b>",
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "repair_cancel_cat")
async def repair_cancel_cat(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Отменено.")
    await call.answer()


# ============================================================
# НАПОМИНАНИЯ
# ============================================================

@dp.callback_query(F.data.startswith("remind_done_"))
async def remind_done(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_", 3)
    vehicle_id = int(parts[2])
    type_key = parts[3]

    await state.set_state(AddMaintenance.date)
    await state.update_data(vehicle_id=vehicle_id, type=type_key)

    label = MAINTENANCE_TYPES.get(type_key, type_key)
    await call.message.answer(
        f"Отлично, запишем замену: <b>{label}</b>\n\n"
        f"Введите дату в формате <b>ДД.ММ.ГГГГ</b>:",
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("remind_snooze_"))
async def remind_snooze(call: CallbackQuery):
    parts = call.data.split("_", 3)
    vehicle_id = int(parts[2])
    type_key = parts[3]

    db.set_snooze(vehicle_id, type_key, SNOOZE_DAYS)
    label = MAINTENANCE_TYPES.get(type_key, type_key)

    await call.message.edit_text(
        f"⏰ Хорошо, напомню про <b>{label}</b> через {SNOOZE_DAYS} дней.\n\n"
        f"Если поменяете раньше — отметьте в боте: «📝 Добавить замену».",
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("remind_skip_"))
async def remind_skip(call: CallbackQuery):
    parts = call.data.split("_", 3)
    vehicle_id = int(parts[2])
    type_key = parts[3]

    db.set_snooze(vehicle_id, type_key, SKIP_DAYS)
    label = MAINTENANCE_TYPES.get(type_key, type_key)

    await call.message.edit_text(
        f"❌ Понял, не буду напоминать про <b>{label}</b> {SKIP_DAYS} дней.\n\n"
        f"Если передумаете — статус всегда виден в карточке машины.",
        parse_mode="HTML",
    )
    await call.answer()


# ============================================================
# УДАЛЕНИЕ МАШИНЫ
# ============================================================

@dp.callback_query(F.data.startswith("del_vehicle_"))
async def delete_vehicle(call: CallbackQuery):
    vehicle_id = int(call.data.split("_")[2])
    db.delete_vehicle(vehicle_id)
    await call.message.edit_text("🗑 Машина удалена.")
    await call.answer()


# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    db.init_db()
    start_scheduler(bot)
    print("Бот запущен. Планировщик активен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
import sqlite3
from datetime import datetime, timedelta

from config import CATEGORY_KEYWORDS, DEFAULT_REPAIR_CATEGORY, MAINTENANCE_TYPES

DB_PATH = "garage.db"


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ
# ============================================================

def detect_category(name: str) -> str:
    """Определяет категорию ремонта по названию.
    Ищет ключевые слова по порядку категорий в CATEGORY_KEYWORDS.
    Возвращает ключ категории или DEFAULT_REPAIR_CATEGORY."""
    if not name:
        return DEFAULT_REPAIR_CATEGORY
    low = name.lower()
    for cat_key, words in CATEGORY_KEYWORDS.items():
        if cat_key == "other":
            continue
        for word in words:
            if word in low:
                return cat_key
    return DEFAULT_REPAIR_CATEGORY


# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================

def init_db():
    """Создаёт таблицы. Добавляет недостающие колонки, если структура обновилась."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Пользователи
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TEXT
        )
    """)

    # Машины
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            brand TEXT,
            model TEXT,
            year INTEGER,
            vin TEXT,
            current_mileage INTEGER,
            monthly_mileage INTEGER,
            oil_interval_km INTEGER,
            oil_interval_months INTEGER,
            air_filter_interval_km INTEGER,
            air_filter_interval_months INTEGER,
            cabin_filter_interval_km INTEGER,
            cabin_filter_interval_months INTEGER,
            brake_fluid_interval_km INTEGER,
            brake_fluid_interval_months INTEGER,
            coolant_interval_km INTEGER,
            coolant_interval_months INTEGER,
            spark_plugs_interval_km INTEGER,
            to_interval_km INTEGER,
            to_interval_months INTEGER,
            grm_interval_km INTEGER,
            grm_interval_months INTEGER,
            last_mileage_update TEXT,
            last_reminder_sent TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # История обслуживания (расширенная)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER,
            kind TEXT DEFAULT 'consumable',
            type TEXT,
            category TEXT,
            custom_name TEXT,
            date TEXT,
            mileage INTEGER,
            cost_parts REAL DEFAULT 0,
            cost_work REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles (id)
        )
    """)

    # Отложенные напоминания
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminder_snooze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER,
            type TEXT,
            snooze_until TEXT,
            UNIQUE(vehicle_id, type),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles (id)
        )
    """)

    # Лог предупреждений
    cur.execute("""
        CREATE TABLE IF NOT EXISTS warnings_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER,
            type TEXT,
            warning_kind TEXT,
            sent_at TEXT,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles (id)
        )
    """)

    # ---- Миграции: добавляем недостающие колонки в существующие таблицы ----
    # vehicles
    for col, coltype in [
        ("air_filter_interval_months", "INTEGER"),
        ("cabin_filter_interval_months", "INTEGER"),
        ("brake_fluid_interval_km", "INTEGER"),
        ("grm_interval_km", "INTEGER"),
        ("grm_interval_months", "INTEGER"),
        ("last_mileage_update", "TEXT"),
        ("last_reminder_sent", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE vehicles ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass

    # maintenance_history — новые колонки
    for col, coltype in [
        ("kind", "TEXT DEFAULT 'consumable'"),
        ("category", "TEXT"),
        ("custom_name", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE maintenance_history ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass

    # ---- Заполняем старые записи дефолтами ----
    # kind = consumable у всех, где NULL
    cur.execute("UPDATE maintenance_history SET kind = 'consumable' WHERE kind IS NULL OR kind = ''")
    # category для расходников — по типу
    for type_key in MAINTENANCE_TYPES.keys():
        cur.execute(
            "UPDATE maintenance_history SET category = ? WHERE type = ? AND (category IS NULL OR category = '')",
            (type_key, type_key),
        )

    conn.commit()
    conn.close()


# ============================================================
# ПОЛЬЗОВАТЕЛИ
# ============================================================

def add_user(user_id, username):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
        (user_id, username, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ============================================================
# МАШИНЫ
# ============================================================

def add_vehicle(user_id, data: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO vehicles (
            user_id, brand, model, year, vin, current_mileage, monthly_mileage,
            oil_interval_km, oil_interval_months,
            air_filter_interval_km, air_filter_interval_months,
            cabin_filter_interval_km, cabin_filter_interval_months,
            brake_fluid_interval_km, brake_fluid_interval_months,
            coolant_interval_km, coolant_interval_months,
            spark_plugs_interval_km,
            to_interval_km, to_interval_months,
            grm_interval_km, grm_interval_months,
            last_mileage_update, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        data.get("brand"), data.get("model"), data.get("year"), data.get("vin"),
        data.get("current_mileage"), data.get("monthly_mileage"),
        data.get("oil_interval_km"), data.get("oil_interval_months"),
        data.get("air_filter_interval_km"), data.get("air_filter_interval_months"),
        data.get("cabin_filter_interval_km"), data.get("cabin_filter_interval_months"),
        data.get("brake_fluid_interval_km"), data.get("brake_fluid_interval_months"),
        data.get("coolant_interval_km"), data.get("coolant_interval_months"),
        data.get("spark_plugs_interval_km"),
        data.get("to_interval_km"), data.get("to_interval_months"),
        data.get("grm_interval_km"), data.get("grm_interval_months"),
        datetime.now().isoformat(),
        datetime.now().isoformat(),
    ))
    vehicle_id = cur.lastrowid
    conn.commit()
    conn.close()
    return vehicle_id


def get_user_vehicles(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, brand, model, year, current_mileage FROM vehicles WHERE user_id = ?",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_vehicle_dict(vehicle_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_vehicles():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM vehicles")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_mileage(vehicle_id, new_mileage):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE vehicles SET current_mileage = ?, last_mileage_update = ? WHERE id = ?",
        (new_mileage, datetime.now().isoformat(), vehicle_id),
    )
    conn.commit()
    conn.close()


def update_interval(vehicle_id, field, value):
    allowed = (
        "oil_interval_km", "oil_interval_months",
        "air_filter_interval_km", "air_filter_interval_months",
        "cabin_filter_interval_km", "cabin_filter_interval_months",
        "brake_fluid_interval_km", "brake_fluid_interval_months",
        "coolant_interval_km", "coolant_interval_months",
        "spark_plugs_interval_km",
        "to_interval_km", "to_interval_months",
        "grm_interval_km", "grm_interval_months",
    )
    if field not in allowed:
        raise ValueError(f"Unknown field: {field}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"UPDATE vehicles SET {field} = ? WHERE id = ?", (value, vehicle_id))
    conn.commit()
    conn.close()


def set_last_reminder(vehicle_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE vehicles SET last_reminder_sent = ? WHERE id = ?",
        (datetime.now().isoformat(), vehicle_id),
    )
    conn.commit()
    conn.close()


def delete_vehicle(vehicle_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM maintenance_history WHERE vehicle_id = ?", (vehicle_id,))
    cur.execute("DELETE FROM reminder_snooze WHERE vehicle_id = ?", (vehicle_id,))
    cur.execute("DELETE FROM warnings_log WHERE vehicle_id = ?", (vehicle_id,))
    cur.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
    conn.commit()
    conn.close()


# ============================================================
# ИСТОРИЯ — ДОБАВЛЕНИЕ
# ============================================================

def add_maintenance(vehicle_id, type_, date, mileage,
                    cost_parts=0, cost_work=0, notes=""):
    """Добавляет расходник (из анкеты или записи о замене)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO maintenance_history
            (vehicle_id, kind, type, category, custom_name, date, mileage,
             cost_parts, cost_work, notes, created_at)
        VALUES (?, 'consumable', ?, ?, NULL, ?, ?, ?, ?, ?, ?)
    """, (vehicle_id, type_, type_, date, mileage,
          cost_parts, cost_work, notes, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    clear_snooze(vehicle_id, type_)
    clear_warnings(vehicle_id, type_)


def add_repair(vehicle_id, name, date, mileage,
               category=None, cost_parts=0, cost_work=0, notes=""):
    """Добавляет ремонт/работу. Категория определяется автоматически,
    если не передана явно."""
    if category is None:
        category = detect_category(name)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO maintenance_history
            (vehicle_id, kind, type, category, custom_name, date, mileage,
             cost_parts, cost_work, notes, created_at)
        VALUES (?, 'repair', NULL, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (vehicle_id, category, name, date, mileage,
          cost_parts, cost_work, notes, datetime.now().isoformat()))
    record_id = cur.lastrowid
    conn.commit()
    conn.close()
    return record_id


# ============================================================
# ИСТОРИЯ — ЧТЕНИЕ
# ============================================================

def get_last_maintenance(vehicle_id, type_):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM maintenance_history
        WHERE vehicle_id = ? AND type = ? AND kind = 'consumable'
        ORDER BY date DESC, id DESC LIMIT 1
    """, (vehicle_id, type_))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_history(vehicle_id, filter_kind=None):
    """Возвращает историю.
    filter_kind:
      None         — всё вместе
      'consumable' — только расходники
      'repair'     — только ремонты
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if filter_kind is None:
        cur.execute(
            "SELECT * FROM maintenance_history WHERE vehicle_id = ? ORDER BY date DESC, id DESC",
            (vehicle_id,),
        )
    else:
        cur.execute(
            "SELECT * FROM maintenance_history WHERE vehicle_id = ? AND kind = ? "
            "ORDER BY date DESC, id DESC",
            (vehicle_id, filter_kind),
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_record(record_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM maintenance_history WHERE id = ?", (record_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_record_category(record_id, category):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE maintenance_history SET category = ? WHERE id = ?",
        (category, record_id),
    )
    conn.commit()
    conn.close()


# ============================================================
# РАСХОДЫ
# ============================================================

def get_total_costs(vehicle_id):
    """Сумма: (запчасти, работы) по всем записям."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT SUM(cost_parts), SUM(cost_work) FROM maintenance_history WHERE vehicle_id = ?",
        (vehicle_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row if row else (0, 0)


def get_costs_by_kind(vehicle_id):
    """Сумма по видам: {'consumable': (parts, work), 'repair': (parts, work)}."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT kind, SUM(cost_parts), SUM(cost_work)
        FROM maintenance_history
        WHERE vehicle_id = ?
        GROUP BY kind
    """, (vehicle_id,))
    rows = cur.fetchall()
    conn.close()
    result = {
        "consumable": (0, 0),
        "repair": (0, 0),
    }
    for kind, parts, work in rows:
        if kind in result:
            result[kind] = (parts or 0, work or 0)
    return result


def get_costs_by_category(vehicle_id):
    """Сумма по категориям: список (category, parts, work), где сумма > 0."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT category, SUM(cost_parts), SUM(cost_work)
        FROM maintenance_history
        WHERE vehicle_id = ? AND category IS NOT NULL
        GROUP BY category
        ORDER BY (SUM(cost_parts) + SUM(cost_work)) DESC
    """, (vehicle_id,))
    rows = cur.fetchall()
    conn.close()
    return [(cat, parts or 0, work or 0) for cat, parts, work in rows]


# ============================================================
# SNOOZE
# ============================================================

def set_snooze(vehicle_id, type_, days):
    until = (datetime.now() + timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO reminder_snooze (vehicle_id, type, snooze_until)
        VALUES (?, ?, ?)
        ON CONFLICT(vehicle_id, type) DO UPDATE SET snooze_until = excluded.snooze_until
    """, (vehicle_id, type_, until))
    conn.commit()
    conn.close()


def get_snooze_until(vehicle_id, type_):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT snooze_until FROM reminder_snooze WHERE vehicle_id = ? AND type = ?",
        (vehicle_id, type_),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def clear_snooze(vehicle_id, type_):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM reminder_snooze WHERE vehicle_id = ? AND type = ?",
        (vehicle_id, type_),
    )
    conn.commit()
    conn.close()


# ============================================================
# ЛОГ ПРЕДУПРЕЖДЕНИЙ
# ============================================================

def log_warning(vehicle_id, type_, kind):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO warnings_log (vehicle_id, type, warning_kind, sent_at)
        VALUES (?, ?, ?, ?)
    """, (vehicle_id, type_, kind, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_last_warning(vehicle_id, type_, kind):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT sent_at FROM warnings_log
        WHERE vehicle_id = ? AND type = ? AND warning_kind = ?
        ORDER BY sent_at DESC LIMIT 1
    """, (vehicle_id, type_, kind))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def clear_warnings(vehicle_id, type_):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM warnings_log WHERE vehicle_id = ? AND type = ?",
        (vehicle_id, type_),
    )
    conn.commit()
    conn.close()
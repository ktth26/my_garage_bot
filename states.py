from aiogram.fsm.state import State, StatesGroup


class AddVehicle(StatesGroup):
    """Анкета при добавлении новой машины."""
    brand = State()
    model = State()
    year = State()
    vin = State()
    current_mileage = State()
    monthly_mileage = State()

    # Интервалы — 8 пунктов обслуживания
    oil_interval_km = State()
    oil_interval_months = State()
    air_filter_interval_km = State()
    air_filter_interval_months = State()
    cabin_filter_interval_km = State()
    cabin_filter_interval_months = State()
    brake_fluid_interval_km = State()
    brake_fluid_interval_months = State()
    coolant_interval_km = State()
    coolant_interval_months = State()
    spark_plugs_interval_km = State()
    to_interval_km = State()
    to_interval_months = State()
    grm_interval_km = State()
    grm_interval_months = State()

    # Последняя замена масла (опционально)
    last_oil_date = State()
    last_oil_mileage = State()


class AddMaintenance(StatesGroup):
    """Запись о выполненной замене расходника."""
    choose_type = State()
    date = State()
    mileage = State()
    cost_parts = State()
    cost_work = State()
    notes = State()


class AddRepair(StatesGroup):
    """Запись о ремонте (произвольная работа)."""
    vehicle_id = State()        # выбранная машина (кладём в data, а не как state)
    name = State()              # название работы
    date = State()
    mileage = State()
    cost_parts = State()
    cost_work = State()
    notes = State()
    confirm = State()           # после сохранения — предложение изменить категорию


class UpdateMileage(StatesGroup):
    """Обновление текущего пробега машины."""
    new_mileage = State()


class EditInterval(StatesGroup):
    """Редактирование одного интервала из настроек."""
    new_value = State()


class EditCategory(StatesGroup):
    """Изменение категории у конкретной записи."""
    choose = State()
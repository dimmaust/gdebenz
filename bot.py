import json
import logging
import requests
import subprocess
from html import escape as html_escape
from pathlib import Path
from dotenv import load_dotenv
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
import asyncio

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
CITIES_FILE = BASE_DIR / "cities.json"
SUBSCRIBERS_FILE = BASE_DIR / "subscribers.json"
PENDING_FILE = BASE_DIR / "pending.json"

API_URL = "https://gdebenz.ru/api/stations"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

FUEL_NAMES = {
    "92": "АИ-92",
    "95": "АИ-95",
    "98": "АИ-98",
    "100": "АИ-100",
    "ДТ": "ДТ",
}
ALL_FUELS = list(FUEL_NAMES.keys())

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()
router = Router()


# --- Утилиты для работы с JSON ---

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --- Работа с подписчиками ---

def get_subscriber(chat_id: str) -> dict:
    return load_json(SUBSCRIBERS_FILE).get(chat_id, {})


def update_subscriber(chat_id: str, data: dict):
    subscribers = load_json(SUBSCRIBERS_FILE)
    subscribers[chat_id] = data
    save_json(SUBSCRIBERS_FILE, subscribers)


def remove_subscriber(chat_id: str):
    subscribers = load_json(SUBSCRIBERS_FILE)
    subscribers.pop(chat_id, None)
    save_json(SUBSCRIBERS_FILE, subscribers)


def is_approved(chat_id: str) -> bool:
    return chat_id in load_json(SUBSCRIBERS_FILE)


def is_admin(chat_id: str) -> bool:
    return ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID


# --- Работа с заявками ---

def get_pending(chat_id: str) -> dict:
    return load_json(PENDING_FILE).get(chat_id, {})


def add_pending(chat_id: str, data: dict):
    pending = load_json(PENDING_FILE)
    pending[chat_id] = data
    save_json(PENDING_FILE, pending)


def remove_pending(chat_id: str):
    pending = load_json(PENDING_FILE)
    pending.pop(chat_id, None)
    save_json(PENDING_FILE, pending)


def get_all_pending() -> dict:
    return load_json(PENDING_FILE)


# --- Геокодирование ---

def get_city_coords(city_name: str) -> dict | None:
    params = {
        "q": city_name,
        "format": "json",
        "limit": 1,
        "accept-language": "ru",
    }
    headers = {"User-Agent": "GdeBenzBot/1.0"}

    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            return None

        place = data[0]
        lat = float(place["lat"])
        lon = float(place["lon"])

        bbox = place.get("boundingbox", [])
        if len(bbox) == 4:
            lat1, lat2 = float(bbox[0]), float(bbox[1])
            lon1, lon2 = float(bbox[2]), float(bbox[3])
        else:
            lat1, lat2 = lat - 0.075, lat + 0.075
            lon1, lon2 = lon - 0.075, lon + 0.075

        return {"lat1": lat1, "lon1": lon1, "lat2": lat2, "lon2": lon2}
    except Exception as e:
        logger.error(f"Ошибка при геокодировании: {e}")
        return None


def ensure_city(city_input: str) -> bool:
    cities = load_json(CITIES_FILE)
    if city_input in cities:
        return True
    coords = get_city_coords(city_input)
    if not coords:
        return False
    cities[city_input] = coords
    save_json(CITIES_FILE, cities)
    return True


# --- Работа с АЗС ---

def get_stations(city: str) -> list:
    cities = load_json(CITIES_FILE)
    if city not in cities:
        return []
    coords = cities[city]
    params = {
        "lat1": coords["lat1"], "lon1": coords["lon1"],
        "lat2": coords["lat2"], "lon2": coords["lon2"],
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Ошибка при запросе API: {e}")
        return []


def format_status_text(status: str) -> str:
    return {
        "yes": "✅ Есть топливо",
        "queue": "⚠️ Очередь",
        "no": "❌ Нет топлива",
    }.get(status, "❓ Неизвестно")


def user_display(sub: dict) -> str:
    name = sub.get("name", "")
    username = sub.get("username", "")
    if name and username:
        return f"{name} (@{username})"
    if name:
        return name
    if username:
        return f"@{username}"
    return "без имени"


# --- Хелпер: проверка доступа ---

async def check_access(message: Message) -> str | None:
    chat_id = str(message.chat.id)

    if is_admin(chat_id):
        return chat_id

    if is_approved(chat_id):
        return chat_id

    pending = get_pending(chat_id)
    if pending:
        await message.answer("⏳ Ваша заявка на рассмотрении. Ожидайте.")
    else:
        await message.answer(
            "🔒 Доступ ограничен.\n\n"
            "Отправьте /start для подачи заявки на доступ."
        )
    return None


# === КОМАНДЫ ПОЛЬЗОВАТЕЛЕЙ ===

@router.message(Command("start"))
async def cmd_start(message: Message):
    chat_id = str(message.chat.id)

    if is_admin(chat_id):
        await message.answer(
            "👑 <b>Добро пожаловать, администратор!</b>\n\n"
            "<b>Ваши команды:</b>\n"
            "/pending - Заявки на доступ\n"
            "/approve <id> - Одобрить заявку\n"
            "/reject <id> - Отклонить заявку\n"
            "/users - Список подписчиков\n"
            "/kick <id> - Удалить подписчика\n"
            "/stats - Статистика\n"
            "/update - Обновить из git\n\n"
            "<b>Команды подписчика:</b>\n"
            "/status, /city, /fuel, /brands, /where, /help",
            parse_mode="HTML",
        )
        return

    if is_approved(chat_id):
        sub = get_subscriber(chat_id)
        await message.answer(
            f"👋 С возвращением, {user_display(sub)}!\n\n"
            "<b>Команды:</b>\n"
            "/status - Мои настройки\n"
            "/city <город> - Мой город\n"
            "/fuel <типы> - Мои виды топлива\n"
            "/brands <сети> - Мои сети АЗС\n"
            "/where - Где есть топливо\n"
            "/unsubscribe - Отписаться\n"
            "/help - Справка",
            parse_mode="HTML",
        )
        return

    pending = get_pending(chat_id)
    if pending:
        await message.answer("⏳ Ваша заявка уже на рассмотрении. Ожидайте.")
        return

    name = message.from_user.full_name or ""
    username = message.from_user.username or ""

    add_pending(chat_id, {
        "name": name,
        "username": username,
        "requested_at": now_str(),
    })

    await message.answer(
        "📋 <b>Заявка отправлена!</b>\n\n"
        "Администратор рассмотрит вашу заявку.\n"
        "Вы получите уведомление, когда доступ будет открыт.",
        parse_mode="HTML",
    )

    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"📬 <b>Новая заявка на доступ</b>\n\n"
                f"👤 {name} (@{username})\n"
                f"🆔 <code>{chat_id}</code>\n"
                f"🕐 {now_str()}\n\n"
                f"/approve {chat_id}\n"
                f"/reject {chat_id}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить админа: {e}")


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not await check_access(message):
        return

    text = (
        "📖 <b>Справка</b>\n\n"
        "Бот мониторит наличие топлива на АЗС.\n\n"
        "<b>Команды:</b>\n"
        "/status - Мои текущие настройки\n"
        "/city <город> - Город мониторинга\n"
        "/fuel <типы> - Виды топлива (92 95 98 100 ДТ)\n"
        "/brands <сети> - Сети АЗС (пусто = все)\n"
        "/where - АЗС с топливом\n"
        "/unsubscribe - Отписаться от уведомлений"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message):
    if not await check_access(message):
        return

    chat_id = str(message.chat.id)
    sub = get_subscriber(chat_id)

    city = sub.get("city", "не задан")
    fuel_types = sub.get("fuel_types", [])
    brands = sub.get("brands", [])

    fuel_str = ", ".join(FUEL_NAMES.get(f, f) for f in fuel_types) if fuel_types else "все"
    brands_str = ", ".join(brands) if brands else "все"

    cities = load_json(CITIES_FILE)
    city_display = city if city in cities else f"{city} (не найден)"

    text = (
        "⚙️ <b>Ваши настройки</b>\n\n"
        f"🏙 Город: <code>{city_display}</code>\n"
        f"⛽ Топливо: {fuel_str}\n"
        f"🏢 Сети АЗС: {brands_str}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("city"))
async def cmd_city(message: Message):
    if not await check_access(message):
        return

    chat_id = str(message.chat.id)
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Укажите город: /city орёл", parse_mode="HTML")
        return

    city_input = args[1].strip().lower()

    if not ensure_city(city_input):
        await message.answer(f"❌ Не удалось найти город «{city_input}».")
        return

    sub = get_subscriber(chat_id)
    sub["city"] = city_input
    update_subscriber(chat_id, sub)

    await message.answer(f"✅ Ваш город: <code>{city_input}</code>", parse_mode="HTML")


@router.message(Command("fuel"))
async def cmd_fuel(message: Message):
    if not await check_access(message):
        return

    chat_id = str(message.chat.id)
    args = message.text.split()

    if len(args) < 2:
        await message.answer(
            "Укажите виды топлива:\n/fuel 92 95\n/fuel 95 ДТ\n\n"
            "Доступно: 92, 95, 98, 100, ДТ",
            parse_mode="HTML",
        )
        return

    fuel_input = [f.upper() for f in args[1:]]
    valid = []
    for f in fuel_input:
        if f in ALL_FUELS:
            valid.append(f)
        else:
            await message.answer(f"❌ Неизвестный вид топлива: {f}\nДоступно: {', '.join(ALL_FUELS)}")
            return

    sub = get_subscriber(chat_id)
    sub["fuel_types"] = valid
    update_subscriber(chat_id, sub)

    names = ", ".join(FUEL_NAMES.get(f, f) for f in valid)
    await message.answer(f"✅ Отслеживаемое топливо: {names}")


@router.message(Command("brands"))
async def cmd_brands(message: Message):
    if not await check_access(message):
        return

    chat_id = str(message.chat.id)
    args = message.text.split()

    if len(args) < 2:
        sub = get_subscriber(chat_id)
        sub["brands"] = []
        update_subscriber(chat_id, sub)
        await message.answer("✅ Теперь отслеживаются все сети АЗС.")
        return

    brands = args[1:]
    sub = get_subscriber(chat_id)
    sub["brands"] = brands
    update_subscriber(chat_id, sub)

    await message.answer(f"✅ Отслеживаемые сети: {', '.join(brands)}")


@router.message(Command("where"))
async def cmd_where(message: Message):
    if not await check_access(message):
        return

    chat_id = str(message.chat.id)
    sub = get_subscriber(chat_id)

    city = sub.get("city", "oryol")
    fuel_types = sub.get("fuel_types", ["95"])
    brands = sub.get("brands", [])

    stations = get_stations(city)
    if not stations:
        await message.answer("❌ Не удалось получить данные об АЗС.")
        return

    if brands:
        stations = [s for s in stations if s.get("brand") in brands]

    has_fuel = []
    for s in stations:
        fuels_now = s.get("fuels_now", "")
        available = [f.strip() for f in fuels_now.split(",") if f.strip()]
        if fuel_types:
            matching = [f for f in available if f in fuel_types]
            if matching:
                has_fuel.append((s, matching))
        elif available:
            has_fuel.append((s, available))

    if not has_fuel:
        await message.answer("❌ Сейчас нет АЗС с искомым топливом.")
        return

    has_fuel.sort(key=lambda x: x[0].get("status") != "yes")

    lines = [f"⛽ <b>АЗС с топливом ({len(has_fuel)}):</b>\n"]

    for station, fuels in has_fuel[:20]:
        name = station.get("name") or station.get("brand") or "Неизвестно"
        addr = station.get("addr", "")
        status = station.get("status")
        lat = station["lat"]
        lon = station["lon"]
        yandex_url = f"https://yandex.ru/maps/?pt={lon},{lat}&z=16&l=map"

        lines.append(f"<b>{name}</b>")
        if addr:
            lines.append(f"  📍 {addr}")
        lines.append(f"  {format_status_text(status)}")
        lines.append(f"  ⛽ {', '.join(FUEL_NAMES.get(f, f) for f in fuels)}")
        lines.append(f"  🗺 <a href=\"{yandex_url}\">Яндекс.Карты</a>")
        lines.append("")

    if len(has_fuel) > 20:
        lines.append(f"... и ещё {len(has_fuel) - 20} АЗС")

    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    chat_id = str(message.chat.id)

    if not is_approved(chat_id):
        await message.answer("Вы не подписаны.")
        return

    remove_subscriber(chat_id)
    await message.answer("🔕 Вы отписались от уведомлений.")


# === КОМАНДЫ АДМИНИСТРАТОРА ===

@router.message(Command("pending"))
async def cmd_pending(message: Message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        await message.answer("⛔ Нет доступа.")
        return

    pending = get_all_pending()
    if not pending:
        await message.answer("📭 Нет заявок.")
        return

    lines = ["📋 <b>Заявки на доступ:</b>\n"]
    for pid, info in pending.items():
        name = info.get("name", "")
        username = info.get("username", "")
        dt = info.get("requested_at", "")
        display = f"{name} (@{username})" if username else name
        lines.append(f"👤 {display}\n🆔 <code>{pid}</code>\n🕐 {dt}\n")

    lines.append("Одобрить: /approve <id>\nОтклонить: /reject <id>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("approve"))
async def cmd_approve(message: Message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        await message.answer("⛔ Нет доступа.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /approve <chat_id>")
        return

    target_id = args[1]
    pending = get_pending(target_id)

    if not pending:
        await message.answer("❌ Заявка не найдена.")
        return

    subscriber = {
        "city": "oryol",
        "fuel_types": ["95"],
        "brands": [],
        "name": pending.get("name", ""),
        "username": pending.get("username", ""),
        "approved_at": now_str(),
        "notifications_sent": 0,
    }
    update_subscriber(target_id, subscriber)
    remove_pending(target_id)

    display = user_display(subscriber)
    await message.answer(f"✅ Одобрен: {display} (<code>{target_id}</code>)", parse_mode="HTML")

    try:
        await bot.send_message(
            target_id,
            "✅ <b>Доступ открыт!</b>\n\n"
            "Теперь вы можете пользоваться ботом.\n"
            "Настройки по умолчанию: Орёл, АИ-95.\n\n"
            "/city, /fuel, /brands — для настройки\n"
            "/where — АЗС с топливом\n"
            "/help — справка",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление {target_id}: {e}")


@router.message(Command("reject"))
async def cmd_reject(message: Message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        await message.answer("⛔ Нет доступа.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /reject <chat_id>")
        return

    target_id = args[1]
    pending = get_pending(target_id)

    if not pending:
        await message.answer("❌ Заявка не найдена.")
        return

    display = user_display(pending)
    remove_pending(target_id)

    await message.answer(f"❌ Отклонён: {display} (<code>{target_id}</code>)", parse_mode="HTML")

    try:
        await bot.send_message(
            target_id,
            "❌ Ваша заявка на доступ отклонена.",
        )
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление {target_id}: {e}")


@router.message(Command("users"))
async def cmd_users(message: Message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        await message.answer("⛔ Нет доступа.")
        return

    subscribers = load_json(SUBSCRIBERS_FILE)
    if not subscribers:
        await message.answer("👥 Нет подписчиков.")
        return

    lines = [f"👥 <b>Подписчики ({len(subscribers)}):</b>\n"]

    for sid, sub in subscribers.items():
        display = user_display(sub)
        city = sub.get("city", "?")
        fuels = ", ".join(FUEL_NAMES.get(f, f) for f in sub.get("fuel_types", []))
        brands = ", ".join(sub.get("brands", [])) or "все"
        approved = sub.get("approved_at", "?")
        notifs = sub.get("notifications_sent", 0)

        lines.append(
            f"👤 <b>{display}</b>\n"
            f"  🆔 <code>{sid}</code>\n"
            f"  🏙 {city} | ⛽ {fuels} | 🏢 {brands}\n"
            f"  📅 {approved} | 📩 {notifs} уведомлений\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("kick"))
async def cmd_kick(message: Message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        await message.answer("⛔ Нет доступа.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /kick <chat_id>")
        return

    target_id = args[1]

    if not is_approved(target_id):
        await message.answer("❌ Подписчик не найден.")
        return

    sub = get_subscriber(target_id)
    display = user_display(sub)
    remove_subscriber(target_id)

    await message.answer(f"🗑 Удалён: {display} (<code>{target_id}</code>)", parse_mode="HTML")

    try:
        await bot.send_message(
            target_id,
            "🚫 Вы были отключены от бота администратором.",
        )
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление {target_id}: {e}")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        await message.answer("⛔ Нет доступа.")
        return

    subscribers = load_json(SUBSCRIBERS_FILE)
    pending = load_json(PENDING_FILE)

    total = len(subscribers)
    pending_count = len(pending)

    if total == 0:
        await message.answer("📊 Нет данных.")
        return

    cities = {}
    fuel_counter = {}
    brand_counter = {}
    total_notifs = 0

    for sub in subscribers.values():
        city = sub.get("city", "oryol")
        cities[city] = cities.get(city, 0) + 1

        for f in sub.get("fuel_types", []):
            fuel_counter[f] = fuel_counter.get(f, 0) + 1

        for b in sub.get("brands", []):
            brand_counter[b] = brand_counter.get(b, 0) + 1

        total_notifs += sub.get("notifications_sent", 0)

    lines = [
        "📊 <b>Статистика</b>\n",
        f"👥 Подписчиков: <b>{total}</b>",
        f"📋 Заявок: <b>{pending_count}</b>",
        f"📩 Уведомлений отправлено: <b>{total_notifs}</b>\n",
        "<b>По городам:</b>",
    ]
    for city, count in sorted(cities.items(), key=lambda x: -x[1]):
        lines.append(f"  🏙 {city}: {count}")

    lines.append("\n<b>По топливу:</b>")
    for fuel, count in sorted(fuel_counter.items(), key=lambda x: -x[1]):
        lines.append(f"  ⛽ {FUEL_NAMES.get(fuel, fuel)}: {count}")

    if brand_counter:
        lines.append("\n<b>По сетям:</b>")
        for brand, count in sorted(brand_counter.items(), key=lambda x: -x[1]):
            lines.append(f"  🏢 {brand}: {count}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("update"))
async def cmd_update(message: Message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        await message.answer("⛔ Нет доступа.")
        return

    install_dir = str(BASE_DIR)
    venv_pip = str(BASE_DIR / "venv" / "bin" / "pip")

    await message.answer("🔄 Обновляю из репозитория...")

    # Сохраняем конфигурацию и данные перед обновлением
    protected_files = [".env", "cities.json", "subscribers.json", "pending.json", "state.json"]
    backups = {}
    for fname in protected_files:
        fpath = BASE_DIR / fname
        if fpath.exists():
            backups[fname] = fpath.read_text(encoding="utf-8")

    # Запоминаем хэш requirements.txt до обновления
    req_file = BASE_DIR / "requirements.txt"
    req_hash_before = ""
    if req_file.exists():
        req_hash_before = subprocess.run(
            ["md5sum", str(req_file)], capture_output=True, text=True
        ).stdout.split()[0]

    # git fetch + reset
    subprocess.run(["git", "fetch", "origin"], capture_output=True, cwd=install_dir)
    result = subprocess.run(
        ["git", "reset", "--hard", "origin/main"], capture_output=True, text=True, cwd=install_dir
    )

    if result.returncode != 0:
        await message.answer(
            f"❌ Ошибка git reset:\n<pre>{html_escape(result.stderr[:500])}</pre>",
            parse_mode="HTML",
        )
        return

    output = result.stdout.strip()

    # Восстанавливаем конфигурацию и данные
    for fname, content in backups.items():
        fpath = BASE_DIR / fname
        fpath.write_text(content, encoding="utf-8")

    if "Already up to date" in output and not backups:
        await message.answer("✅ Уже актуальная версия. Обновление не требуется.")
        return

    # Проверяем, изменился ли requirements.txt
    req_hash_after = ""
    if req_file.exists():
        req_hash_after = subprocess.run(
            ["md5sum", str(req_file)], capture_output=True, text=True
        ).stdout.split()[0]

    pip_output = ""
    if req_hash_before != req_hash_after:
        await message.answer("📦 Обновляю зависимости...")
        pip_result = subprocess.run(
            [venv_pip, "install", "-q", "-r", str(req_file)],
            capture_output=True, text=True,
        )
        if pip_result.returncode != 0:
            await message.answer(
                f"❌ Ошибка установки зависимостей:\n<pre>{html_escape(pip_result.stderr[:500])}</pre>",
                parse_mode="HTML",
            )
            return
        pip_output = "\n📦 Зависимости обновлены"

    # Права
    subprocess.run(["chown", "-R", "gdebenz:gdebenz", install_dir], capture_output=True)

    await message.answer(
        f"✅ Обновление загружено{pip_output}\n\n"
        f"<pre>{html_escape(output[:500])}</pre>\n\n"
        "🔄 Перезапускаю сервисы...",
        parse_mode="HTML",
    )

    # Перезапуск сервисов (бот перезапустится сам)
    subprocess.run(["systemctl", "restart", "gdebenz"], capture_output=True)
    subprocess.run(["systemctl", "restart", "gdebenz-bot"], capture_output=True)


# === ЗАПУСК ===

async def main():
    logger.info("Запуск Telegram-бота GdeBenz")
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

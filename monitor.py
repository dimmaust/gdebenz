import json
import time
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
CITIES_FILE = BASE_DIR / "cities.json"
SUBSCRIBERS_FILE = BASE_DIR / "subscribers.json"

API_URL = "https://gdebenz.ru/api/stations"
POLL_INTERVAL = 300  # 5 minutes

FUEL_NAMES = {
    "92": "АИ-92",
    "95": "АИ-95",
    "98": "АИ-98",
    "100": "АИ-100",
    "ДТ": "ДТ",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_stations(city: str) -> list:
    cities = load_json(CITIES_FILE)
    if city not in cities:
        logger.error(f"Город {city} не найден в cities.json")
        return []

    coords = cities[city]
    params = {
        "lat1": coords["lat1"],
        "lon1": coords["lon1"],
        "lat2": coords["lat2"],
        "lon2": coords["lon2"],
    }

    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Ошибка при запросе API для {city}: {e}")
        return []


def build_state_key(station_id: str, fuel: str) -> str:
    return f"{station_id}_{fuel}"


def check_fuel(station: dict, fuel_types: list) -> dict:
    result = {}
    fuels_now = station.get("fuels_now", "")
    available = [f.strip() for f in fuels_now.split(",") if f.strip()]

    for fuel in fuel_types:
        key = build_state_key(station["osm_id"], fuel)
        result[key] = fuel in available

    return result


def send_telegram(chat_id: str, message: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=data, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Ошибка при отправке в Telegram (chat_id={chat_id}): {e}")


def increment_notification_counter(chat_ids: list):
    subscribers = load_json(SUBSCRIBERS_FILE)
    changed = False
    for cid in chat_ids:
        if cid in subscribers:
            subscribers[cid]["notifications_sent"] = subscribers[cid].get("notifications_sent", 0) + 1
            changed = True
    if changed:
        save_json(SUBSCRIBERS_FILE, subscribers)


def notify_change(chat_ids: list, station: dict, fuel: str, appeared: bool):
    fuel_name = FUEL_NAMES.get(fuel, fuel)
    name = station.get("name") or station.get("brand") or "Неизвестно"
    lat = station["lat"]
    lon = station["lon"]
    yandex_url = f"https://yandex.ru/maps/?pt={lon},{lat}&z=16&l=map"

    if appeared:
        emoji = "⛽"
        action = "Появился"
    else:
        emoji = "❌"
        action = "Закончился"

    message = (
        f"{emoji} {action} {fuel_name}\n\n"
        f"АЗС: {name}\n"
        f"Координаты: {lat:.4f}, {lon:.4f}\n\n"
        f"Яндекс.Карты:\n{yandex_url}"
    )

    logger.info(f"Уведомление: {action} {fuel_name} на {name} → {len(chat_ids)} подписчикам")
    for chat_id in chat_ids:
        send_telegram(chat_id, message)

    increment_notification_counter(chat_ids)


def get_subscribers_by_city(subscribers: dict) -> dict:
    result = {}
    for chat_id, sub in subscribers.items():
        city = sub.get("city", "oryol")
        if city not in result:
            result[city] = []
        result[city].append(chat_id)
    return result


def get_all_fuel_types_for_city(subscribers: dict, city: str) -> list:
    types = set()
    for sub in subscribers.values():
        if sub.get("city", "oryol") == city:
            types.update(sub.get("fuel_types", ["95"]))
    return list(types)


def monitor_city(city: str, chat_ids: list, subscribers: dict, all_fuel_types: list):
    stations = get_stations(city)
    if not stations:
        logger.warning(f"Не удалось получить данные об АЗС для {city}")
        return

    state = load_json(STATE_FILE)
    old_city_state = state.get(city, {})
    new_city_state = {}

    for station in stations:
        fuel_status = check_fuel(station, all_fuel_types)
        new_city_state.update(fuel_status)

    for key, is_available in new_city_state.items():
        was_available = old_city_state.get(key)

        if was_available is None:
            continue

        if is_available != was_available:
            station_id, fuel = key.rsplit("_", 1)
            station = next(
                (s for s in stations if s["osm_id"] == station_id), None
            )
            if not station:
                continue

            interested = []
            for chat_id in chat_ids:
                sub = subscribers[chat_id]
                sub_fuels = sub.get("fuel_types", ["95"])
                sub_brands = sub.get("brands", [])

                if fuel not in sub_fuels:
                    continue
                if sub_brands and station.get("brand") not in sub_brands:
                    continue
                interested.append(chat_id)

            if interested:
                notify_change(interested, station, fuel, appeared=is_available)

    state[city] = new_city_state
    save_json(STATE_FILE, state)


def monitor_cycle():
    subscribers = load_json(SUBSCRIBERS_FILE)
    if not subscribers:
        return

    city_groups = get_subscribers_by_city(subscribers)

    for city, chat_ids in city_groups.items():
        all_fuel_types = get_all_fuel_types_for_city(subscribers, city)
        try:
            monitor_city(city, chat_ids, subscribers, all_fuel_types)
        except Exception as e:
            logger.error(f"Ошибка мониторинга города {city}: {e}")

    logger.info(f"Цикл завершён. Городов: {len(city_groups)}, подписчиков: {len(subscribers)}")


def main():
    logger.info("Запуск сервиса мониторинга GdeBenz")

    while True:
        try:
            monitor_cycle()
        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

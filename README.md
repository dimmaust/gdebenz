# GdeBenz Monitor Bot

Telegram-бот для мониторинга наличия топлива на АЗС на основе данных сайта gdebenz.ru.

## Установка
Установка одной командой

curl -sSL https://raw.githubusercontent.com/dimmaust/gdebenz/main/install.sh | sudo bash

Скрипт спросит два значения:
- Telegram Bot Token — от @BotFather
- Ваш Telegram ID — от @userinfobot


```bash
sudo useradd -r -s /bin/false gdebenz
sudo mkdir -p /opt/gdebenz
sudo cp *.py *.json *.txt /opt/gdebenz/
sudo cp .env /opt/gdebenz/
cd /opt/gdebenz
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo chown -R gdebenz:gdebenz /opt/gdebenz
```

## Настройка

Отредактируйте `.env`:

```
TELEGRAM_BOT_TOKEN=ваш_токен_бота
ADMIN_CHAT_ID=ваш_chat_id
```

`ADMIN_CHAT_ID` — ваш Telegram ID (узнать можно у @userinfobot).

## Запуск через systemd

```bash
sudo cp gdebenz.service /etc/systemd/system/
sudo cp gdebenz-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gdebenz gdebenz-bot
sudo systemctl start gdebenz gdebenz-bot
```

## Команды

### Для пользователей

| Команда | Описание |
|---------|----------|
| `/start` | Подать заявку на доступ |
| `/help` | Справка |
| `/status` | Мои настройки |
| `/city <город>` | Город мониторинга |
| `/fuel <типы>` | Виды топлива (92 95 ДТ) |
| `/brands <сети>` | Сети АЗС (пусто = все) |
| `/where` | Где есть топливо |
| `/unsubscribe` | Отписаться |

### Для администратора

| Команда | Описание |
|---------|----------|
| `/pending` | Список заявок |
| `/approve <id>` | Одобрить заявку |
| `/reject <id>` | Отклонить заявку |
| `/users` | Список подписчиков с деталями |
| `/kick <id>` | Удалить подписчика |
| `/stats` | Статистика (города, топливо, сети) |

## Схема работы

1. Пользователь нажимает `/start` → заявка уходит администратору
2. Администратор видит заявку через `/pending` или в личном чате
3. `/approve <id>` → пользователь получает доступ
4. Пользователь настраивает город, топливо, бренды
5. Мониторинг каждые 5 минут проверяет изменения и шлёт уведомления

## Управление

```bash
sudo systemctl status gdebenz gdebenz-bot
sudo journalctl -u gdebenz -f
sudo journalctl -u gdebenz-bot -f
sudo systemctl restart gdebenz gdebenz-bot
```

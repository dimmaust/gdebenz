# GdeBenz Monitor Bot — Установка на Ubuntu

Пошаговая инструкция по развёртыванию на виртуальном сервере с Ubuntu 22.04+.

---

## Шаг 0. Подготовка

### 0.1 Получить токен бота

1. Открыть Telegram, найти **@BotFather**
2. Отправить `/newbot`
3. Ввести имя бота (например: `GdeBenz Monitor`)
4. Ввести username бота (например: `gdebenz_monitor_bot`)
5. BotFather выдаст токен вида:
   ```
   123456789:ABCdefGhIjKlMnOpQrStUvWxYz
   ```
6. **Сохранить токен** — он понадобится на шаге 3

### 0.2 Узнать свой Telegram ID

1. Открыть Telegram, найти **@userinfobot**
2. Отправить `/start`
3. Бот ответит вашим ID (число вида `123456789`)
4. **Сохранить ID** — это будет `ADMIN_CHAT_ID`

### 0.3 Подключиться к серверу

```bash
ssh root@ваш_сервер_ip
```

---

## Шаг 1. Обновить систему

```bash
apt update && apt upgrade -y
```

---

## Шаг 2. Установить Python и зависимости

```bash
apt install -y python3 python3-pip python3-venv git
```

Проверить версию Python (нужна 3.10+):

```bash
python3 --version
```

---

## Шаг 3. Создать пользователя и директорию

```bash
# Создать системного пользователя (без логина, без домашней)
sudo useradd -r -s /bin/false gdebenz

# Создать директорию проекта
sudo mkdir -p /opt/gdebenz
```

---

## Шаг 4. Загрузить файлы проекта

### Вариант A: через SCP (с локального компьютера)

На локальном компьютере:

```bash
scp -r gdebenz/* root@ваш_сервер_ip:/opt/gdebenz/
```

### Вариант B: через git (если проект в репозитории)

```bash
cd /opt/gdebenz
git clone https://github.com/ваш_репозиторий/gdebenz.git .
```

### Вариант C: вручную через nano

```bash
nano /opt/gdebenz/bot.py
# вставить содержимое, Ctrl+O сохранить, Ctrl+X выйти
# повторить для каждого файла
```

---

## Шаг 5. Настроить окружение

Отредактировать файл `.env`:

```bash
nano /opt/gdebenz/.env
```

Заполнить:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIjKlMnOpQrStUvWxYz
ADMIN_CHAT_ID=123456789
```

- `TELEGRAM_BOT_TOKEN` — токен от BotFather (шаг 0.1)
- `ADMIN_CHAT_ID` — ваш Telegram ID (шаг 0.2)

---

## Шаг 6. Создать виртуальное окружение и установить зависимости

```bash
cd /opt/gdebenz
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

Проверить:

```bash
/opt/gdebenz/venv/bin/python -c "import aiogram; print(aiogram.__version__)"
```

---

## Шаг 7. Настроить права доступа

```bash
# Все файлы принадлежат пользователю gdebenz
sudo chown -R gdebenz:gdebenz /opt/gdebenz

# Права на чтение/запись
sudo chmod -R 755 /opt/gdebenz
sudo chmod 600 /opt/gdebenz/.env
```

---

## Шаг 8. Установить systemd-сервисы

```bash
# Копировать файлы сервисов
sudo cp /opt/gdebenz/gdebenz.service /etc/systemd/system/
sudo cp /opt/gdebenz/gdebenz-bot.service /etc/systemd/system/

# Перечитать конфигурацию systemd
sudo systemctl daemon-reload

# Включить автозапуск при загрузке
sudo systemctl enable gdebenz gdebenz-bot

# Запустить сервисы
sudo systemctl start gdebenz gdebenz-bot
```

---

## Шаг 9. Проверить работу

### Статус сервисов

```bash
sudo systemctl status gdebenz gdebenz-bot
```

Должно быть:

```
● gdebenz.service - GdeBenz Fuel Monitor
     Active: active (running) ...

● gdebenz-bot.service - GdeBenz Telegram Bot
     Active: active (running) ...
```

### Логи мониторинга

```bash
sudo journalctl -u gdebenz -f
```

Ожидаемый вывод:

```
Запуск сервиса мониторинга GdeBenz
Цикл завершён. Городов: 0, подписчиков: 0
```

### Логи бота

```bash
sudo journalctl -u gdebenz-bot -f
```

Ожидаемый вывод:

```
Запуск Telegram-бота GdeBenz
```

---

## Шаг 10. Настроить бота в Telegram

### 10.1 Активировать администратора

1. Открыть Telegram
2. Найти своего бота по username
3. Отправить `/start`
4. Бот покажет админ-панель с командами

### 10.2 Подключить первого подписчика

Попросить пользователя:
1. Найти бота в Telegram
2. Отправить `/start`
3. Бот ответит: «Заявка отправлена!»

Как администратор:
1. Получите уведомление о заявке
2. Отправьте `/pending` — увидите список заявок
3. Отправьте `/approve 123456789` — одобрите (подставить реальный chat_id)

Пользователь получит уведомление «Доступ открыт!» и сможет пользоваться ботом.

---

## Полезные команды

### Просмотр логов

```bash
# Логи мониторинга (последние 50 строк)
sudo journalctl -u gdebenz -n 50

# Логи бота в реальном времени
sudo journalctl -u gdebenz-bot -f

# Логи с ошибками
sudo journalctl -u gdebenz -p err
sudo journalctl -u gdebenz-bot -p err
```

### Управление сервисами

```bash
# Остановить
sudo systemctl stop gdebenz gdebenz-bot

# Запустить
sudo systemctl start gdebenz gdebenz-bot

# Перезапустить
sudo systemctl restart gdebenz gdebenz-bot

# Отключить автозапуск
sudo systemctl disable gdebenz gdebenz-bot
```

### Редактирование конфигурации

```bash
# Изменить токен или ID админа
sudo nano /opt/gdebenz/.env
sudo systemctl restart gdebenz gdebenz-bot

# Добавить город вручную
sudo nano /opt/gdebenz/cities.json
```

### Обновление кода

**Через Telegram (рекомендуется):**

Администратор отправляет боту команду `/update`.

Бот автоматически:
1. Сделает `git pull`
2. Обновит зависимости, если изменился `requirements.txt`
3. Перезапустит оба сервиса

**Вручную через SSH (запасной вариант):**

```bash
sudo systemctl stop gdebenz gdebenz-bot
cd /opt/gdebenz
sudo -u gdebenz git pull
source venv/bin/activate
pip install -r requirements.txt
deactivate
sudo chown -R gdebenz:gdebenz /opt/gdebenz
sudo systemctl start gdebenz gdebenz-bot
```

---

## Решение проблем

### Бот не отвечает

1. Проверить токен: `cat /opt/gdebenz/.env`
2. Проверить логи: `sudo journalctl -u gdebenz-bot -n 20`
3. Проверить статус: `sudo systemctl status gdebenz-bot`

### Сервис не запускается

```bash
# Проверить права
ls -la /opt/gdebenz/

# Проверить Python
/opt/gdebenz/venv/bin/python --version

# Попробовать запустить вручную
cd /opt/gdebenz
sudo -u gdebenz /opt/gdebenz/venv/bin/python bot.py
```

### Нет уведомлений

1. Проверить что сервис мониторинга работает: `sudo systemctl status gdebenz`
2. Проверить подписчика: в Telegram `/status`
3. Проверить город: `/where` — есть ли АЗС
4. Проверить логи: `sudo journalctl -u gdebenz -f`

### Уведомления приходят, но не отслеживаются изменения

Первый запуск только записывает состояние. Изменения начнут отслеживаться со второго цикла (через 5 минут).

---

## Структура файлов

```
/opt/gdebenz/
├── .env                # Токен и ID админа (секретный)
├── bot.py              # Telegram-бот
├── monitor.py          # Сервис мониторинга
├── cities.json         # База городов с координатами
├── subscribers.json    # Одобренные подписчики
├── pending.json        # Заявки на доступ
├── state.json          # Состояние АЗС (для отслеживания изменений)
├── requirements.txt    # Python-зависимости
├── gdebenz.service     # systemd-юнит мониторинга
├── gdebenz-bot.service # systemd-юнит бота
└── venv/               # Виртуальное окружение Python
```

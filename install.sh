#!/bin/bash
set -e

REPO="https://github.com/dimmaust/gdebenz"
INSTALL_DIR="/opt/gdebenz"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# --- Проверка root ---
if [ "$(id -u)" -ne 0 ]; then
    error "Запустите скрипт от root: sudo bash install.sh"
fi

echo ""
echo "========================================="
echo "  GdeBenz Monitor Bot — Установка"
echo "========================================="
echo ""

# --- Ввод данных ---
read -rp "Telegram Bot Token: " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    error "Токен не может быть пустым"
fi

read -rp "Ваш Telegram ID (ADMIN_CHAT_ID): " ADMIN_ID
if [ -z "$ADMIN_ID" ]; then
    error "ADMIN_CHAT_ID не может быть пустым"
fi

echo ""
info "Начинаю установку..."
echo ""

# --- Шаг 1: Системные зависимости ---
info "Обновление системы..."
apt-get update -qq > /dev/null 2>&1
apt-get install -y -qq python3 python3-pip python3-venv git > /dev/null 2>&1
info "Системные зависимости установлены"

# --- Шаг 2: Проверка Python ---
PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    error "Требуется Python 3.10+, установлен $PYTHON_VER"
fi
info "Python $PYTHON_VER"

# --- Шаг 3: Создание пользователя ---
if ! id -u gdebenz > /dev/null 2>&1; then
    useradd -r -s /bin/false gdebenz
    info "Пользователь gdebenz создан"
else
    info "Пользователь gdebenz уже существует"
fi

# --- Шаг 4: Клонирование репозитория ---
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Репозиторий уже существует, обновляю..."
    cd "$INSTALL_DIR"
    sudo -u gdebenz git pull > /dev/null 2>&1 || warn "git pull не удался, продолжаю с текущей версией"
else
    if [ -d "$INSTALL_DIR" ]; then
        warn "Директория $INSTALL_DIR существует, удаляю..."
        rm -rf "$INSTALL_DIR"
    fi
    git clone "$REPO" "$INSTALL_DIR" > /dev/null 2>&1
    info "Репозиторий клонирован"
fi

cd "$INSTALL_DIR"

# --- Шаг 5: Удаление лишних файлов (на случай если попали в git) ---
rm -f "$INSTALL_DIR/venv" 2>/dev/null || true

# --- Шаг 6: .env ---
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    sed -i "s/your_bot_token_here/$BOT_TOKEN/" "$INSTALL_DIR/.env"
    sed -i "s/your_admin_chat_id_here/$ADMIN_ID/" "$INSTALL_DIR/.env"
    info ".env создан из шаблона"
else
    info ".env уже существует, пропускаю"
fi

# --- Шаг 7: Виртуальное окружение ---
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$INSTALL_DIR/requirements.txt"
deactivate
info "Виртуальное окружение и зависимости установлены"

# --- Шаг 8: Пустые JSON (если не было) ---
for f in subscribers.json pending.json state.json; do
    if [ ! -f "$INSTALL_DIR/$f" ]; then
        echo "{}" > "$INSTALL_DIR/$f"
    fi
done
info "JSON-файлы проверены"

# --- Шаг 9: Права доступа ---
chown -R gdebenz:gdebenz "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/.env"
info "Права доступа настроены"

# --- Шаг 10: systemd-сервисы ---
cat > /etc/systemd/system/gdebenz.service << 'EOF'
[Unit]
Description=GdeBenz Fuel Monitor
After=network.target

[Service]
Type=simple
User=gdebenz
Group=gdebenz
WorkingDirectory=/opt/gdebenz
ExecStart=/opt/gdebenz/venv/bin/python monitor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/gdebenz-bot.service << 'EOF'
[Unit]
Description=GdeBenz Telegram Bot
After=network.target

[Service]
Type=simple
User=gdebenz
Group=gdebenz
WorkingDirectory=/opt/gdebenz
ExecStart=/opt/gdebenz/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gdebenz gdebenz-bot > /dev/null 2>&1
info "systemd-сервисы установлены"

# --- Шаг 11: Запуск ---
systemctl restart gdebenz gdebenz-bot
sleep 2

BOT_STATUS=$(systemctl is-active gdebenz-bot)
MON_STATUS=$(systemctl is-active gdebenz)

echo ""
echo "========================================="
echo "  Установка завершена!"
echo "========================================="
echo ""
echo "  Мониторинг:  $MON_STATUS"
echo "  Бот:         $BOT_STATUS"
echo ""
echo "  Директория:  $INSTALL_DIR"
echo "  Логи бота:   journalctl -u gdebenz-bot -f"
echo "  Логи монит.: journalctl -u gdebenz -f"
echo ""
echo "  Следующие шаги:"
echo "  1. Откройте Telegram, найдите своего бота"
echo "  2. Отправьте /start"
echo "  3. Попросите пользователей отправить /start"
echo "  4. Одобряйте заявки командой /approve <id>"
echo ""

if [ "$BOT_STATUS" != "active" ]; then
    warn "Бот не запустился! Проверьте логи:"
    echo "  journalctl -u gdebenz-bot -n 20 --no-pager"
fi

if [ "$MON_STATUS" != "active" ]; then
    warn "Мониторинг не запустился! Проверьте логи:"
    echo "  journalctl -u gdebenz -n 20 --no-pager"
fi

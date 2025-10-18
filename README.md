# 🤖 **Telegram AI Bot**

Многофункциональный Telegram-бот с поддержкой различных **AI-моделей**, анализа **документов** и **генерации изображений** — и всё это **бесплатно**.

---

![Python](https://img.shields.io/badge/python-3.11-blue)
![Contributions](https://img.shields.io/badge/PRs-welcome-orange)
![Status](https://img.shields.io/badge/status-active-brightgreen)

---

## 📑 **Навигация**

* [Основные возможности](#-основные-возможности)
* [Архитектура](#-архитектура)
* [Установка](#-установка)
* [Быстрый старт](#-быстрый-старт)
* [Использование](#-использование)
* [Конфигурация](#-конфигурация)
* [Провайдеры](#-провайдеры)
* [Технические детали](#-технические-детали)
* [Безопасность](#-безопасность)
* [Развёртывание](#-развёртывание)
* [Руководство по развёртыванию](#-руководство-по-развёртыванию)
* [Вклад и развитие](#-вклад-и-развитие)

---

## ✨ **Основные возможности**

* 🧠 **Множество AI-моделей:** GPT-5, Claude, DeepSeek и др.
* 📄 **Работа с документами:** анализ PDF, DOCX, TXT с RAG (Retrieval-Augmented Generation)
* 🖼️ **Генерация изображений:** Nano-Banana, Flux и другие модели
* 🎯 **Function Calling:** AI умеет сам использовать встроенные инструменты
* 💬 **Умная история:** автоматическая суммаризация и сжатие контекста
* 👥 **Групповые чаты:** поддержка работы через упоминания
* 🎨 **Стикеры:** выразительные ответы в чате

---

## 🏗️ **Архитектура проекта**

```
tgbot/
├── bot.py                  # Основной модуль (обработчики команд)
├── gpt4freepro.py          # Провайдер gpt4free.pro API
├── puterjs.py              # Провайдер Puter.js API
├── ai_tools.py             # Инструменты (function calling)
├── document_processor.py   # Обработка документов + RAG
├── requirements.txt        # Зависимости
├── .env                    # Конфигурация (НЕ коммитить!)
└── models.json             # Кэш доступных моделей
```

---

## ⚡ **Быстрый старт**

```bash
git clone <URL_репозитория>
cd tgbot && pip install -r requirements.txt
echo "TELEGRAM_BOT_TOKEN=<токен>" > .env
python bot.py
```

> 🎉 Через минуту бот готов к работе!

Пример:

```bash
/model gpt-4
Привет! Расскажи, как работает твой RAG-анализ?
```

---

## 📦 **Установка**

### 1. Клонирование репозитория

```bash
git clone <URL_вашего_репозитория>
cd tgbot
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка `.env`

```env
TELEGRAM_BOT_TOKEN=ваш_токен_бота
GPT4FREE_API_BASE=https://gpt4free.pro/v1
GPT4FREE_API_KEY=опциональный_ключ
TWOCAPTCHA_API_KEY=опциональный_ключ_для_капчи
```

### 4. Получение токена Telegram-бота

1. Откройте [@BotFather](https://t.me/BotFather)
2. Выполните `/newbot`
3. Скопируйте токен в `.env`

### 5. Запуск

```bash
python bot.py
```

---

## 🎮 **Использование**

### ⚙️ Основные команды

| Команда    | Описание                            |
| ---------- | ----------------------------------- |
| `/start`   | Приветствие и запуск                |
| `/help`    | Справка по командам                 |
| `/model`   | Выбор AI-модели                     |
| `/clear`   | Очистка истории                     |
| `/mode`    | Выбор режима работы                 |
| `/image`   | Генерация изображения               |
| `/docs`    | Управление загруженными документами |
| `/profile` | Настройки пользователя              |
| `/stats`   | Статистика (для админов)            |

---

### 🧩 Режимы работы

> 💬 **Обычный режим:** интерактивный диалог с AI
> 📚 **Документный режим:** ответы только на основе ваших файлов
> 🛠️ **Режим с инструментами:** AI решает, когда подключить поиск по документам

---

### 📄 Работа с документами

1. Отправьте файл (PDF, DOCX, TXT) в чат
2. Бот проиндексирует содержимое
3. Задавайте вопросы по содержимому
4. Используйте `/docs` для управления

---

### 🖼️ Генерация изображений

```
/image красивый закат над океаном
```

или опишите сцену после выбора модели через `/model`.

---

### 👥 Групповые чаты

1. Добавьте бота в группу
2. Упомяните его сообщением `@ваш_бот привет!`
3. Бот ответит прямо в группе

---

## ⚙️ **Конфигурация**

### 🔐 Администраторы

```python
ADMIN_IDS = [ваш_telegram_id]
```

### ⚙️ Параметры

```python
TELEGRAM_MESSAGE_LIMIT = 4000
MAX_HISTORY_MESSAGES = 20
MAX_GROUP_HISTORY_MESSAGES = 3
MAX_HISTORY_TOKENS = 20000
MAX_GROUP_HISTORY_TOKENS = 5000
SUMMARIZE_THRESHOLD = 10
DEFAULT_MODEL = 'gpt-5-chat'
```

---

## 🔧 **Провайдеры**

### 🧩 gpt4free.pro

* Поддерживает GPT-4, Claude, DeepSeek
* Генерация текста и изображений
* 🔁 При недоступности — бот автоматически переключается на резервный API

### ⚡ Puter.js

* Альтернативный API-провайдер
* Используется в качестве резервного

---

## 📚 **Технические детали**

### 🧠 История диалогов

* Автоматическое удаление технических сообщений
* Сжатие кода в ответах
* Суммаризация и усечение старых сообщений

### 🛠️ Function Calling

AI может вызывать встроенные функции, например:

| Инструмент            | Назначение                                |
| --------------------- | ----------------------------------------- |
| `search_in_documents` | Поиск информации в загруженных документах |

### 📖 RAG (Retrieval-Augmented Generation)

1. Извлечение текста из документа
2. Поиск релевантных фрагментов
3. Передача контекста модели AI для ответа

---

## 🔒 **Безопасность**

> ⚠️ **Важно:** не публикуйте `.env` и токены
> ✅ Добавьте `.env` в `.gitignore`
> 🧱 Регулярно обновляйте зависимости и проверяйте логи

---

## 🗂 **Файлы данных**

| Файл / Папка                  | Назначение                         |
| ----------------------------- | ---------------------------------- |
| `chat_memory.json`            | История диалогов                   |
| `documents_index.json`        | Индекс документов                  |
| `user_documents/`             | Хранение пользовательских файлов   |
| `models.json`                 | Кэш доступных моделей              |
| `puter_models_cache.json`     | Кэш моделей Puter                  |
| `puter_models_blacklist.json` | Чёрный список неработающих моделей |

---

## 🐛 **Отладка**

Логи:

```
[bot]            — события бота
[gpt4freepro]    — логика API
[puterjs]        — запросы к Puter.js
[document_proc]  — загрузка и анализ документов
```

---

## 🚀 **Развёртывание**

### 🖥️ Локально

```bash
python bot.py
```

### 🧳 В фоне (Linux)

```bash
nohup python bot.py > bot.log 2>&1 &
```

### 🐳 Через Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

---

# 🚀 **Руководство по развёртыванию**

# 🚀 Руководство по развёртыванию

Это руководство поможет вам развернуть бота на различных платформах.

## 📋 Содержание

- [Локальный запуск](#локальный-запуск)
- [Linux сервер](#linux-сервер)
- [Systemd сервис](#systemd-сервис)
- [Docker](#docker)
- [VPS/VDS рекомендации](#vpsvds-рекомендации)
- [Troubleshooting](#troubleshooting)

---

## 🖥️ Локальный запуск

### Windows

```powershell
# 1. Клонируйте репозиторий
git clone <your-repo-url>
cd tgbot

# 2. Создайте виртуальное окружение
python -m venv .venv
.venv\Scripts\activate

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Настройте .env
copy .env.example .env
# Отредактируйте .env, добавьте TELEGRAM_BOT_TOKEN

# 5. Запустите бота
python bot.py
```

### Linux/Mac

```bash
# 1. Клонируйте репозиторий
git clone <your-repo-url>
cd tgbot

# 2. Создайте виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Настройте .env
cp .env.example .env
nano .env  # Добавьте TELEGRAM_BOT_TOKEN

# 5. Запустите бота
python bot.py
```

---

## 🐧 Linux сервер

### Установка на чистый Ubuntu/Debian сервер

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python 3.11+
sudo apt install python3.11 python3.11-venv python3-pip git -y

# Клонирование проекта
cd /opt
sudo git clone <your-repo-url> tgbot
cd tgbot

# Создание виртуального окружения
sudo python3.11 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

# Настройка .env
sudo cp .env.example .env
sudo nano .env  # Добавьте токены

# Создание пользователя для бота
sudo useradd -r -s /bin/false tgbot
sudo chown -R tgbot:tgbot /opt/tgbot

# Первый запуск (тест)
sudo -u tgbot .venv/bin/python bot.py
```

### Запуск в фоне с nohup

```bash
# Запуск
nohup python bot.py > bot.log 2>&1 &

# Проверка
ps aux | grep bot.py

# Остановка
kill $(pgrep -f bot.py)

# Просмотр логов
tail -f bot.log
```

---

## ⚙️ Systemd сервис

Создайте systemd сервис для автозапуска бота:

```bash
# Создайте файл сервиса
sudo nano /etc/systemd/system/tgbot.service
```

Содержимое файла:

```ini
[Unit]
Description=Telegram AI Bot
After=network.target

[Service]
Type=simple
User=tgbot
Group=tgbot
WorkingDirectory=/opt/tgbot
Environment="PATH=/opt/tgbot/.venv/bin"
ExecStart=/opt/tgbot/.venv/bin/python /opt/tgbot/bot.py
Restart=always
RestartSec=10

# Логирование
StandardOutput=append:/opt/tgbot/logs/bot.log
StandardError=append:/opt/tgbot/logs/bot_error.log

[Install]
WantedBy=multi-user.target
```

Управление сервисом:

```bash
# Создайте директорию для логов
sudo mkdir -p /opt/tgbot/logs
sudo chown tgbot:tgbot /opt/tgbot/logs

# Перезагрузите systemd
sudo systemctl daemon-reload

# Включите автозапуск
sudo systemctl enable tgbot

# Запустите сервис
sudo systemctl start tgbot

# Проверьте статус
sudo systemctl status tgbot

# Просмотр логов
sudo journalctl -u tgbot -f

# Остановка
sudo systemctl stop tgbot

# Перезапуск
sudo systemctl restart tgbot
```

---

## 🐳 Docker

### Dockerfile

Создайте `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Установка зависимостей системы
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование requirements.txt
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Создание директорий
RUN mkdir -p user_documents logs

# Запуск
CMD ["python", "bot.py"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  tgbot:
    build: .
    container_name: tgbot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./user_documents:/app/user_documents
      - ./chat_memory.json:/app/chat_memory.json
      - ./documents_index.json:/app/documents_index.json
      - ./logs:/app/logs
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Использование

```bash
# Сборка и запуск
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down

# Перезапуск
docker-compose restart

# Пересборка после изменений
docker-compose up -d --build
```

---

## 🌐 VPS/VDS рекомендации

### Минимальные требования

- **CPU**: 1 ядро (рекомендуется 2)
- **RAM**: 512 MB (рекомендуется 1 GB)
- **Диск**: 5 GB (SSD предпочтительнее)
- **ОС**: Ubuntu 22.04 LTS / Debian 11+

### Рекомендуемые провайдеры

- **Для России**: Timeweb, Beget, Selectel
- **Международные**: DigitalOcean, Hetzner, Linode, Vultr
- **Бюджетные**: Contabo, OVH

### Безопасность

```bash
# Настройка firewall
sudo ufw allow 22/tcp
sudo ufw enable

# Автоматические обновления безопасности
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades

# Ограничение SSH доступа (опционально)
sudo nano /etc/ssh/sshd_config
# Установите: PermitRootLogin no
sudo systemctl restart sshd
```

### Мониторинг

```bash
# Установка htop для мониторинга
sudo apt install htop -y

# Проверка использования ресурсов
htop

# Проверка логов
sudo journalctl -u tgbot --since "1 hour ago"

# Проверка дискового пространства
df -h

# Проверка памяти
free -h
```

---

## 🔧 Troubleshooting

### Бот не запускается

```bash
# Проверьте логи
sudo journalctl -u tgbot -n 50

# Проверьте .env файл
cat .env | grep TELEGRAM_BOT_TOKEN

# Проверьте права доступа
ls -la /opt/tgbot

# Тест запуска вручную
sudo -u tgbot /opt/tgbot/.venv/bin/python /opt/tgbot/bot.py
```

### Проблемы с зависимостями

```bash
# Переустановка зависимостей
pip install --upgrade --force-reinstall -r requirements.txt

# Проверка версии Python
python --version  # Должен быть 3.11+
```

### Проблемы с памятью

```bash
# Очистка кэша документов
rm -f documents_index.json
rm -rf user_documents/*

# Очистка истории
rm -f chat_memory.json

# Перезапуск с ограничением памяти (systemd)
# Добавьте в [Service]:
MemoryLimit=512M
```

### Бот отвечает медленно

1. Проверьте скорость интернета на сервере
2. Попробуйте другую модель AI
3. Уменьшите MAX_HISTORY_MESSAGES в bot.py
4. Используйте более быстрый провайдер (gpt4freepro обычно быстрее)

### Ошибки API

```bash
# Проверьте доступность API
curl https://gpt4free.pro/v1/models

# Проверьте токены Puter
python -c "import puterjs; print(len(puterjs.get_working_auth_tokens()))"

# Обновите кэш моделей
rm -f puter_models_cache.json
sudo systemctl restart tgbot
```

---

## 📝 Обновление бота

```bash
# Остановка
sudo systemctl stop tgbot

# Бэкап данных
cp chat_memory.json chat_memory.json.backup
cp documents_index.json documents_index.json.backup

# Обновление кода
cd /opt/tgbot
sudo git pull

# Обновление зависимостей
sudo .venv/bin/pip install -r requirements.txt --upgrade

# Запуск
sudo systemctl start tgbot

# Проверка
sudo systemctl status tgbot
```

---

## 📞 Поддержка

Если у вас возникли проблемы:

1. Проверьте [Troubleshooting](#troubleshooting)
2. Посмотрите Issues в GitHub
3. Создайте новую Issue с подробным описанием
4. Свяжитесь через Telegram (если указан в README)

---

**Удачного развёртывания! 🚀**


---

## 🤝 **Вклад и развитие**

1. Создайте новую ветку
2. Проверьте работоспособность кода
3. Добавьте комментарии к изменениям
4. Опишите суть изменений в Pull Request

### 🛣️ Roadmap

* Пока-что все что нужно реализовано

---

## 📄 **Лицензия**

**MIT License** — свободное использование с указанием авторства.

---

## 📞 **Контакты**

* Создайте *Issue* в репозитории
* Или отправьте сообщение в Telegram (если указан контакт)

---

**Сделано с ❤️ для сообщества**

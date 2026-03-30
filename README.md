# Telegram VPN Bot

Телеграм бот для управления личными VPN серверами на базе Xray.

## Возможности

- Подключение и развертывание личных VPN серверов
- Автоматическое создание VLESS ключей
- Управление пользователями на серверах
- Админ панель со статистикой и рассылкой

## Установка

1. Установите PostgreSQL:
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib

# Создайте базу данных
sudo -u postgres psql
CREATE DATABASE tgbot;
CREATE USER postgres WITH PASSWORD 'postgres';
GRANT ALL PRIVILEGES ON DATABASE tgbot TO postgres;
\q
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Настройте [`config.py`](config.py):
```python
BOT_TOKEN = "ваш_токен_бота"
WEBHOOK_URL = "https://ваш-домен.com/webhook"
ADMIN_IDS = [ваш_telegram_id]

# Настройки БД
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "tgbot"
DB_USER = "postgres"
DB_PASSWORD = "postgres"
```

4. Запустите бота:
```bash
python bot.py
```

## Настройка вебхука

Для работы вебхука вам нужен:
- Домен с SSL сертификатом
- Nginx или другой reverse proxy

Пример конфигурации Nginx:
```nginx
server {
    listen 443 ssl;
    server_name ваш-домен.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Использование

### Для пользователей:
1. `/start` - начать работу с ботом
2. "Добавить сервер" - подключить новый VPN сервер
3. "Мои серверы" - просмотр списка серверов
4. Выбор сервера - просмотр пользователей и их VLESS ключей
5. "Добавить пользователя" - создать нового VPN пользователя

### Для администраторов:
1. `/admin` - открыть админ панель
2. "Статистика" - просмотр статистики бота
3. "Рассылка" - отправить сообщение всем пользователям

## Структура проекта

- [`bot.py`](bot.py) - главный файл бота с вебхуком
- [`config.py`](config.py) - конфигурация
- [`database.py`](database.py) - модели базы данных
- [`handlers.py`](handlers.py) - обработчики команд пользователей
- [`admin.py`](admin.py) - админ панель
- [`xray_manager.py`](xray_manager.py) - управление Xray
- [`xray_client.py`](xray_client.py) - клиент для работы с Xray
- [`xray_cli.py`](xray_cli.py) - CLI интерфейс

## Важные моменты

- Данные для входа на сервер (логин/пароль) НЕ сохраняются в БД
- Сохраняется только IP сервера и созданные VLESS ключи
- Email для новых VPN пользователей генерируется автоматически
- Используется протокол VLESS с Reality

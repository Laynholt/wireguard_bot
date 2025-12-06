# WireGuard Telegram Bot

## Установка и первичная настройка

### 1. Клонирование репозитория

```bash
git clone https://github.com/Laynholt/wireguard_bot.git
```

```bash
cd wireguard_bot/stuff
```

### 2. Создание файла пользовательской конфигурации

В каталоге `wireguard_bot/stuff` лежит шаблон конфигурации:

* `base_config.json` — шаблон (не изменяется)

Скопируйте шаблон:

```bash
cp base_config.json user_config.json
```

Все дальнейшие изменения делаются в `user_config.json`.

---

### 3. Настройка `user_config.json`

Пример блока настроек:

```json
{
    "local_ip": "10.0.0.",
    "server_ip": "",
    "server_port": "51820",
    "dns_server_name": "adguardhome",
    "is_dns_server_in_docker": 1,

    "users_database_path": "stuff/wireguard_users.db",

    "logs_dir": "stuff/logs",
    "base_log_filename": "telegram_bot",
    "max_log_length": 5000,

    "telegram_token": "",
    "telegram_admin_ids": [],
    "telegram_max_concurrent_messages": 5,
    "telegram_max_message_length": 3000,

    "work_user": "user",
    "wireguard_folder": "/home/user/wireguard",
    "wireguard_config_filepath": "/home/user/wireguard/config/wg_confs/wg0.conf",
    "wireguard_log_filepath": "/home/user/wireguard/config/logs/stats.json",
    "system_names": ["logs", "coredns", "server", "templates", "wg_confs", "wg_confs_backup", ".donoteditthisfile"],

    "allowed_username_pattern": "a-zA-Z0-9_"
}
```

Ниже кратко, что нужно настроить:

#### Сетевые параметры

* **`local_ip`** — базовая локальная подсеть для WireGuard-клиентов.
  Например: `"10.0.0."` → пользователям будут выдаваться адреса вида `10.0.0.X`.

* **`server_ip`** — внешний IP-адрес или доменное имя WireGuard-сервера
  (то, что клиент указывает в `Endpoint`).

* **`server_port`** — UDP-порт WireGuard-сервера (например, `"51820"`).

* **`dns_server_name`** — имя DNS-сервера, IP-адрес которого будет попадать в конфиги клиентов
  (например, имя контейнера с AdGuard Home: `"adguardhome"`. Можно сразу указать IP-адрес).

* **`is_dns_server_in_docker`** — флаг, находится ли DNS-сервер в Docker-сети:

  * `1` — DNS-сервер работает в Docker-сети вместе с WireGuard;
  * `0` — внешний/хостовый DNS-сервер.

---

#### База данных пользователей

* **`users_database_path`** — путь к файлу SQLite-базы пользователей.
  По умолчанию: `"stuff/wireguard_users.db"`.

---

#### Логи бота

* **`logs_dir`** — каталог для логов бота, например `"stuff/logs"`.

* **`base_log_filename`** — базовое имя файла логов, например `"telegram_bot"`
  (фактически будет что-то вроде `telegram_bot.log`).

* **`max_log_length`** — максимальная длина лог-сообщения, которое бот может отправить в Telegram.

---

#### Настройки Telegram

* **`telegram_token`** — токен вашего Telegram-бота от `@BotFather`.

* **`telegram_admin_ids`** — список Telegram ID администраторов,
  например: `[123456789, 987654321]`.

* **`telegram_max_concurrent_messages`** — максимальное количество параллельных обрабатываемых сообщений.

* **`telegram_max_message_length`** — максимальная длина текстового сообщения, отправляемого ботом.

---

#### Пути к WireGuard и системные настройки

* **`work_user`** — системный пользователь, от имени которого будут выполняться команды
  (например, `"user"` — должен существовать в системе).

* **`wireguard_folder`** — корневая папка с конфигурацией WireGuard,
  например: `"/home/user/wireguard"`.

* **`wireguard_config_filepath`** — путь к основному конфигу WireGuard-сервера,
  например: `"/home/user/wireguard/config/wg_confs/wg0.conf"`.

* **`wireguard_log_filepath`** — путь к файлу статистики/логов WireGuard,
  например: `"/home/user/wireguard/config/logs/stats.json"`.

* **`system_names`** — список системных каталогов внутри `wireguard_folder`,
  которые используются сервисом (`logs`, `coredns`, `server`, `templates`, `wg_confs`, `wg_confs_backup`, `.donoteditthisfile` и т.п.) и не должны произвольно изменяться.

---

#### Ограничения на имена пользователей

* **`allowed_username_pattern`** — допустимые символы в имени пользователя
  (шаблон для регулярного выражения).
  Значение `"a-zA-Z0-9_"` означает: латинские буквы в обоих регистрах, цифры и подчёркивание.

---

После настройки `user_config.json` бот готов к запуску через `bot.py`.

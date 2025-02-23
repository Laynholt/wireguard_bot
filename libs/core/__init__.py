import os
import sys
import shutil
from .config import Config
from .logger import RotatingCharFileHandler

# Пути к файлам конфигурации
base_config_path = "stuff/base_config.json"
user_config_path = "stuff/user_config.json"

# Проверяем, существует ли файл user_config.json
if not os.path.exists(user_config_path):
    # Проверяем, существует ли base_config.json
    if not os.path.exists(base_config_path):
        print(f"Файл {base_config_path} не найден. Пожалуйста, добавьте его в папку stuff и попробуйте снова.")
        sys.exit(1)
    
    # Копируем base_config.json в user_config.json
    shutil.copy(base_config_path, user_config_path)
    
    # Завершаем выполнение программы с уведомлением пользователя
    print(f"Файл конфигурации {user_config_path} не найден. Он был создан на основе {base_config_path}.")
    print("Пожалуйста, заполните его необходимыми данными и перезапустите программу.")
    sys.exit(1)  # Завершаем выполнение программы с кодом ошибки 1

# Загружаем конфигурацию из user_config.json
config = Config.load_from_file(user_config_path)

# Экспортируем конфигурацию, чтобы она была доступна при импорте модуля
__all__ = ["config", "RotatingCharFileHandler"]

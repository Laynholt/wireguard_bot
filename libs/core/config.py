from typing import List
from pydantic import BaseModel, Field


class Config(BaseModel):
    # Сетевые параметры
    local_ip: str = Field(default="")
    server_ip: str = Field(default="")
    server_port: str = Field(default="")
    dns_server_name: str = Field(default="")
    is_dns_server_in_docker: bool = Field(default=False)

    # Параметры базы данных
    users_database_path: str = Field(default="")
    
    # Путь к папке с логами
    logs_dir: str = Field(default="logs")
    base_log_filename: str = Field(default="log")
    max_log_length: int = Field(default=5000)

    # Параметры Telegram
    telegram_token: str = Field(default="")
    telegram_admin_ids: List[int] = Field(default_factory=list)
    telegram_max_concurrent_messages: int = Field(default=5)
    telegram_max_message_length: int = Field(default=3000)

    # Системные настройки
    wireguard_folder: str = Field(default="")
    wireguard_config_filepath: str = Field(default="")
    system_names: List[str] = Field(default_factory=list)

    # Регулярное выражение для разрешённых символов
    allowed_username_pattern: str = Field(default=r'a-zA-Z0-9_')

    @classmethod
    def load_from_file(cls, file_path: str) -> "Config":
        """Загружает конфигурацию из файла JSON с помощью parse_raw."""
        with open(file_path, "r") as file:
            return cls.parse_raw(file.read())

    def save_to_file(self, file_path: str) -> None:
        """Сохраняет текущую конфигурацию в файл JSON."""
        with open(file_path, "w") as file:
            file.write(self.model_dump_json(indent=4))

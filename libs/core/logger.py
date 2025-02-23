import os
import logging

class RotatingCharFileHandler(logging.Handler):
    """
    Обработчик логов, который ограничивает размер файла по количеству символов
    и создаёт новый файл при достижении лимита.
    """
    def __init__(self, base_filename: str, max_chars: int = 5000):
        super().__init__()
        self.base_filename = base_filename
        self.max_chars = max_chars
        self.current_file = None
        self.current_filename = None
        self._open_new_file()

    def _open_new_file(self):
        """Создаёт новый файл для логирования."""
        os.makedirs(os.path.dirname(self.base_filename), exist_ok=True)
        
        num = 1
        while True:
            new_filename = f"{self.base_filename}_{num}.log"
            if not os.path.exists(new_filename):
                break
            num += 1

        self.current_filename = new_filename
        self.current_file = open(self.current_filename, "w", encoding="utf-8")

    def emit(self, record):
        """Записывает сообщение в файл и проверяет лимит символов."""
        log_entry = self.format(record) + "\n"
        
        if self.current_file is not None:
            self.current_file.write(log_entry)
            self.current_file.flush()  # Принудительная запись в файл

            if self.current_file.tell() >= self.max_chars:
                self.current_file.close()
                self._open_new_file()

    def close(self):
        """Закрывает текущий файл при завершении работы логгера."""
        if self.current_file:
            self.current_file.close()
        super().close()

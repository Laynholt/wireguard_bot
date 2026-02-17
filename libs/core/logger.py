import os
import glob
import logging
from typing import List, Tuple

class RotatingCharFileHandler(logging.Handler):
    """
    Обработчик логов, который ограничивает размер файла по количеству символов
    и создаёт новый файл при достижении лимита.
    """
    def __init__(self, base_filename: str, max_chars: int = 5000, max_files: int = 10):
        super().__init__()
        self.base_filename = base_filename
        self.max_chars = max_chars
        self.max_files = max(1, max_files)
        self.current_file = None
        self.current_filename = None
        
        self._prepare()
        self._open_new_file()

    def _prepare(self):
        """Создает папку с логами, если ее еще нет."""
        dir_name = os.path.dirname(self.base_filename)
        
        if not os.path.exists(dir_name) or not os.path.isdir(dir_name): 
            os.makedirs(dir_name, exist_ok=True)

    def _list_log_files(self) -> List[Tuple[int, str]]:
        """
        Возвращает список логов вида (index, path), отсортированный по index.
        """
        files: List[Tuple[int, str]] = []
        prefix = f"{self.base_filename}_"
        suffix = ".log"
        for log_file in glob.glob(f"{self.base_filename}_*.log"):
            name = os.path.basename(log_file)
            if not (name.startswith(os.path.basename(prefix)) and name.endswith(suffix)):
                continue
            index_part = name[len(os.path.basename(prefix)):-len(suffix)]
            if not index_part.isdigit():
                continue
            files.append((int(index_part), log_file))
        files.sort(key=lambda x: x[0])
        return files

    def _open_new_file(self):
        """Создаёт новый файл для логирования."""
        existing = self._list_log_files()
        next_index = (existing[-1][0] + 1) if existing else 1
        new_filename = f"{self.base_filename}_{next_index}.log"

        self.current_filename = new_filename
        self.current_file = open(self.current_filename, "w", encoding="utf-8")
        self._cleanup_old_files()

    def _cleanup_old_files(self) -> None:
        """
        Оставляет только max_files последних логов.
        """
        files = self._list_log_files()
        if len(files) <= self.max_files:
            return

        for _, old_file in files[:len(files) - self.max_files]:
            try:
                os.remove(old_file)
            except OSError:
                pass

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

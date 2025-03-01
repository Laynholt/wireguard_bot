from typing import Callable, Optional

class FunctionResult:
    """
    Класс для представления результата выполнения операций над пользователями WireGuard.

    Attributes:
        status (bool): Статус выполнения операции (успешно или нет).
        description (str): Поясняющая строка, содержащая информацию об ошибке или успехе операции.
    """
    def __init__(self, status: bool, description: str) -> None:
        self.status = status 
        self.description = description

    def return_with_print(self, error_handler: Optional[Callable[[], None]] = None, add_to_print: str = '') -> 'FunctionResult':
        """
        Возвращает результат выполнения функции с выводом описания результата.

        Args:
            error_handler (callable): Функция для обработки ошибок, которую нужно вызвать в случае ошибки.
            add_to_print (str): Добавляет строку вывода после description.

        Returns:
            FunctionResult: Результат выполнения функции.
        """
        if self.description:
            prefix = 'Ошибка! ' if self.status is False else ''
            print(f'{prefix}{self.description}')
        
        if add_to_print:
            print(add_to_print)

        if error_handler and self.status is False:
            error_handler()  # Вызываем переданную функцию без дополнительных аргументов здесь

        return self
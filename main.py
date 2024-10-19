import os
import sys
import platform

import libs.wireguard.utils as utils
from libs.wireguard.user_control import add_user, remove_user, comment_or_uncomment_user, print_user_qrcode

if platform.system() == "Linux":
    import termios
    import tty
elif platform.system() == "Windows":
    import msvcrt

menu_options = [
    "Добавить пользователя",
    "Удалить пользователя",
    "Комментировать/Раскомментировать пользователя",
    "Сгенерировать QR-код пользователя",
    "Выход"
]

# Функция для чтения символов с клавиатуры (Linux)
def read_single_keypress_linux():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd) # type: ignore
    try:
        tty.setraw(sys.stdin.fileno()) # type: ignore
        ch = sys.stdin.read(1)
        if ch == '\x1b':  # Обработка стрелок
            ch += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings) # type: ignore
    return ch

# Функция для чтения символов с клавиатуры (Windows)
def read_single_keypress_windows():
    ch = msvcrt.getch() # type: ignore
    if ch in (b'\x00', b'\xe0'):  # Обработка стрелок
        ch += msvcrt.getch() # type: ignore
    return ch.decode('utf-8')

# Функция для отображения меню
def display_menu(selected_index):
    os.system('cls' if platform.system() == 'Windows' else 'clear')  # Очистка экрана
    print("Используйте стрелки вверх/вниз для навигации и нажмите Enter для выбора:")
    for i, option in enumerate(menu_options):
        if i == selected_index:
            print(f"> {option} <")
        else:
            print(f"  {option}")

# Основная функция меню
def main_menu():
    selected_index = 0
    while True:
        display_menu(selected_index)
        if platform.system() == "Linux":
            key = read_single_keypress_linux()
        elif platform.system() == "Windows":
            key = read_single_keypress_windows()
        else:
            raise NotImplementedError("Операционная система не поддерживается.")

        if key in ('\x1b[A', '\xe0H', '\x00H'):  # Стрелка вверх
            selected_index = (selected_index - 1) % len(menu_options)
        elif key in ('\x1b[B', '\xe0P', '\x00P'):  # Стрелка вниз
            selected_index = (selected_index + 1) % len(menu_options)
        elif key == '\r':  # Enter
            os.system('cls' if platform.system() == 'Windows' else 'clear')
            if selected_index == len(menu_options) - 1:  # Выход
                sys.exit(0)
            else:
                handle_menu_selection(selected_index)

# Обработка выбора пункта меню
def handle_menu_selection(index):
    print("Введите имена пользователей через пробел:")
    user_names = input().split()

    ret_val = None
    need_restart_wireguard = False

    for user_name in user_names:
        if index == 0:
            print(f"Добавление пользователя: {user_name}")
            # Вызов функции для добавления пользователя
            ret_val = add_user(user_name)
        elif index == 1:
            print(f"Удаление пользователя: {user_name}")
            # Вызов функции для удаления пользователя
            ret_val = remove_user(user_name)
        elif index == 2:
            print(f"Комментирование/Раскомментирование пользователя: {user_name}")
            # Вызов функции для комментирования/раскомментирования пользователя
            ret_val = comment_or_uncomment_user(user_name)
        elif index == 3:
            print(f"Генерация QR-кода для пользователя: {user_name}")
            # Вызов функции для генерации QR-кода
            print_user_qrcode(user_name)

        if ret_val is not None and ret_val.status is True:
            need_restart_wireguard = True
    if need_restart_wireguard:
        utils.log_and_restart_wireguard()

    input("Нажмите Enter, чтобы вернуться в меню...")
    os.system('cls' if platform.system() == 'Windows' else 'clear')

if __name__ == "__main__":
    main_menu()
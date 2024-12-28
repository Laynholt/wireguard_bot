import argparse

from libs.wireguard import config  
from libs.wireguard import stats

if __name__ == "__main__":
    # Путь к файлу wg0.conf
    conf_file_path = config.wireguard_config_filepath

    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser(description="WireGuard peer status with sorting options.")
    parser.add_argument('-s', '--sort', choices=['allowed_ips', 'transfer_sent'],
                        help="Specify the sorting option: 'allowed_ips' or 'transfer_sent'.")
    args = parser.parse_args()

    # Парсим файл конфигурации
    peers = stats.parse_wg_conf(conf_file_path)

    # Проверяем, передан ли аргумент сортировки
    if args.sort:
        # Если передан параметр сортировки, используем его
        stats.display_wg_status_with_names(peers, sort_by=args.sort)
    else:
        # Если параметр сортировки не передан, предлагаем выбрать вручную
        print("Choose sorting option:")
        print("1. Sort by allowed_ips")
        print("2. Sort by transfer_sent")

        sort_option = input("Enter choice (1 or 2): ").strip()
        if sort_option == "1":
            stats.display_wg_status_with_names(peers, sort_by=stats.SortBy.ALLOWED_IPS)
        elif sort_option == "2":
            stats.display_wg_status_with_names(peers, sort_by=stats.SortBy.TRANSFER_SENT)
        else:
            print("Invalid choice")
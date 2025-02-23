import argparse

from libs.core import config  
from libs.wireguard import stats

if __name__ == "__main__":
    # Путь к файлу wg0.conf
    conf_file_path = config.wireguard_config_filepath

    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser(description="WireGuard peer status with sorting options.")
    parser.add_argument('-s', '--sort', choices=['allowed_ips', 'transfer_sent'],
                        help="Specify the sorting option: 'allowed_ips' or 'transfer_sent'.")
    args = parser.parse_args()

    sort_option = None
    if args.sort:
        sort_option = args.sort
    else:
        print("Choose sorting option:")
        print("1. Sort by allowed_ips")
        print("2. Sort by transfer_sent")
        
        sort_option = input("Enter choice (1 or 2): ").strip()
        if sort_option == "1":
            sort_option = stats.SortBy.ALLOWED_IPS
        elif sort_option == "2":
            sort_option = stats.SortBy.TRANSFER_SENT
        else:
            print("Invalid choice")
            
    if sort_option:
        wireguard_stats = stats.accumulate_wireguard_stats(
            conf_file_path=config.wireguard_config_filepath,
            json_file_path=config.wireguard_log_filepath,
            sort_by=sort_option,
        )
        
        stats.display_merged_data(wireguard_stats)
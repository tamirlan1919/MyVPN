# === Настройки ===
import os
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TOKEN')
# Имя контейнера wg-easy, заданное в docker run --name
WG_EASY_CONTAINER = "wg-easy"
# Папка, смонтированная в docker run как volume: -v ~/.wg-easy:/etc/wireguard
WG_CONFIG_PATH = os.path.expanduser("~/.wg-easy")

import asyncio
import logging
import os
import subprocess

import qrcode
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from aiogram import F, Router

# --------------------------
# Настройки WireGuard
# --------------------------
WG_INTERFACE = "wg0"
WG_SERVER_PUBLIC_IP = "185.125.228.240"     # IP или домен вашего WG-сервера
WG_PORT = 51821                    # Порт WireGuard (по умолчанию 51820/udp)
WG_SERVER_PUBLIC_KEY = "6uc+uEJQ7+uOohlG7eSNegR9oK8MWDMi6PIjw8MLO18="  # Можно получить, выполнив wg show
WG_DNS = "8.8.8.8"                 # DNS, который пропишем в конфиг
WG_NET = "10.8.0."                 # Начало подсети, напр. 10.8.0.X
CURRENT_CLIENT_IP_LAST_OCTET = 2   # В реальном проекте хранить в БД!

# --------------------------
# Настройки бота
# --------------------------


# Создаём роутер (в aiogram 3 рекомендуют разносить хендлеры по модулям и подключать их в Dispatcher)
router = Router()

# --------------------------
# Функции для работы с WireGuard
# --------------------------
def generate_wg_keys():
    """
    Генерирует приватный и публичный ключи через вызов shell-команд.
    Возвращает кортеж (private_key, public_key).
    """
    private_key = subprocess.check_output(["wg", "genkey"]).decode("utf-8").strip()
    public_key = subprocess.check_output(
        ["wg", "pubkey"], input=private_key.encode("utf-8")
    ).decode("utf-8").strip()
    return private_key, public_key

def add_peer_to_server(public_key: str, client_ip: str):
    """
    Добавляем пира в running-config сервера WireGuard командой:
    wg set <wg0> peer <public_key> allowed-ips <client_ip>/32
    Важно: для персистентности ещё нужно писать в /etc/wireguard/wg0.conf.
    """
    subprocess.run([
        "docker", "exec", "wg-easy",
        "wg", "set", WG_INTERFACE,
        "peer", public_key,
        "allowed-ips", f"{client_ip}/32"
    ])

def create_client_config(private_key: str, client_ip: str) -> str:
    """
    Формирует текст конфигурации (WireGuard .conf) для клиента.
    """
    return f"""[Interface]
PrivateKey = {private_key}
Address = {client_ip}/24
DNS = {WG_DNS}

[Peer]
PublicKey = {WG_SERVER_PUBLIC_KEY}
AllowedIPs = 0.0.0.0/0
Endpoint = {WG_SERVER_PUBLIC_IP}:{WG_PORT}
PersistentKeepalive = 25
"""

# --------------------------
# Хендлер на /start
# --------------------------
def generate_keys():
    """
    Генерация приватного и публичного ключей внутри контейнера wg-easy.
    1) wg genkey
    2) wg pubkey (через input приватного ключа)
    """
    # Генерируем приватный ключ
    private_key = subprocess.check_output(
        ["docker", "exec", "wg-easy", "wg", "genkey"]
    ).decode().strip()

    # Генерируем публичный ключ, передавая приватный ключ на stdin
    public_key = subprocess.check_output(
        ["docker", "exec", "-i", "wg-easy", "wg", "pubkey"],
        input=private_key.encode()
    ).decode().strip()

    return private_key, public_key

def add_peer(public_key: str, ip_address: str):
    """
    Добавляем нового пира в конфигурацию WG (внутри контейнера).
    Команда:
      wg set wg0 peer <public_key> allowed-ips <ip_address>/32
    """
    subprocess.run([
        "docker", "exec", "wg-easy",
        "wg", "set", WG_INTERFACE,
        "peer", public_key,
        "allowed-ips", f"{ip_address}/32"
    ], check=True)

def create_client_conf(private_key: str, client_ip: str) -> str:
    """
    Формируем текст клиентского .conf-файла.
    ВАЖНО: WG_SERVER_PUBLIC_KEY здесь мы не берём из “wg show”,
    так как wg-easy уже всё хранит внутри себя. Можно было бы
    тоже достать через "docker exec wg-easy wg show wg0".
    Но для примера вставим "!!! ВПИШИТЕ СЮДА ПУБЛИК-КЛЮЧ !!!"
    """
    # Если хотите “чистый” серверный public key (который wg-easy использует),
    # сделайте: server_pub = subprocess.check_output([... "wg show wg0 public-key"...])
    # Но wg show public-key напрямую не работает. Можно парсить вывод "wg show wg0".
    # Для простоты вручную вставьте ваш серверный pubkey, если знаете его.

    WG_SERVER_PUBLIC_KEY = "!!!_ВПИШИТЕ_СЮДА_ПУБЛИК_КЛЮЧ_СЕРВЕРА_!!!"

    conf = f"""[Interface]
PrivateKey = {private_key}
Address = {client_ip}/24
DNS = {WG_DNS}

[Peer]
PublicKey = {WG_SERVER_PUBLIC_KEY}
AllowedIPs = 0.0.0.0/0
Endpoint = {WG_SERVER_PUBLIC_IP}:{WG_PORT}
PersistentKeepalive = 25
"""
    return conf

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    global CURRENT_IP_LAST_OCTET

    # 1. Генерируем ключи (peer) внутри контейнера
    private_key, public_key = generate_keys()

    # 2. Назначаем IP (наивно инкрементируем)
    client_ip = f"{WG_NET}{CURRENT_IP_LAST_OCTET}"
    CURRENT_IP_LAST_OCTET += 1

    # 3. Добавляем пира через wg set
    add_peer(public_key, client_ip)

    # 4. Создаём клиентский конфиг
    client_conf = create_client_conf(private_key, client_ip)

    # 5. Генерируем QR-код из client_conf
    qr_img = qrcode.make(client_conf)
    qr_file = "wg_qr.png"
    qr_img.save(qr_file)

    # 6. Пишем конфиг во временный файл
    conf_file = "wg-client.conf"
    with open(conf_file, "w") as f:
        f.write(client_conf)

    # 7. Отправляем .conf как документ + QR-код как фото
    await bot.send_document(
        chat_id=message.chat.id,
        document=FSInputFile(conf_file),
        caption="Ваш WireGuard-конфиг (через Docker wg-easy)"
    )
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=FSInputFile(qr_file),
        caption="QR-код для мобильного приложения WireGuard"
    )

    # Чистим временные файлы
    os.remove(conf_file)
    os.remove(qr_file)

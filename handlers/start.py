import subprocess
import tempfile

from aiogram import Router, types
from aiogram.filters import CommandStart, Command
import qrcode
from aiogram.types import FSInputFile

from config.config import *
from text.text import start
router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """
    По команде /start бот:
     1. Создаёт нового клиента в wg-easy (docker exec wg-easy ...)
     2. Находит сгенерированный конфиг peer_<username>.conf
     3. Генерирует QR-код и отправляет пользователю
     4. Отправляет сам конфиг-файл
    """
    user_id = message.from_user.id
    user_name = message.from_user.username or f"user_{user_id}"

    await message.answer("Секундочку! Генерирую VPN-конфиг и QR-код...")

    # 1. Создаём нового клиента через wg-easy
    create_cmd = [
        "docker", "exec", WG_EASY_CONTAINER,
        "/usr/bin/wg-easy", "create", user_name
    ]
    try:
        subprocess.run(create_cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        # Если что-то пошло не так при создании
        error_text = e.stderr.decode('utf-8')
        await message.answer(f"Ошибка при создании клиента: {error_text}")
        return

    # 2. Определяем путь к конфигу
    conf_filename = f"peer_{user_name}.conf"
    conf_filepath = os.path.join(WG_CONFIG_PATH, conf_filename)

    if not os.path.exists(conf_filepath):
        await message.answer("Не удалось найти файл конфигурации WireGuard. Проверьте логи.")
        return

    # 3. Читаем конфигурацию и делаем QR-код
    with open(conf_filepath, 'r') as f:
        conf_data = f.read()

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(conf_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Сохраняем QR во временный файл
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        qr_temp_file = tmp.name
        img.save(qr_temp_file)

    # Отправляем QR-код
    await message.answer_photo(photo=FSInputFile(qr_temp_file))

    # Удаляем временный файл с QR-кодом
    if os.path.exists(qr_temp_file):
        os.remove(qr_temp_file)

    # 4. Отправляем файл конфигурации
    await message.answer_document(document=FSInputFile(conf_filepath))
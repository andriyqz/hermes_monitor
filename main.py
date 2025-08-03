import os
import re
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

from core.hermes import HermesScraper

load_dotenv()
API_TOKEN = os.getenv('API_TOKEN')
PROXY_URL = os.getenv('PROXY_URL')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

sent_skus = set()
monitor_tasks = {}  # (url, keyword, chat_id): asyncio.Task


@dp.message(Command("start"))
async def handle_start(message: types.Message):
    text = (
        "👋 Приветствую!\n\n"
        "📌 Вот что ты можешь сделать:\n"
        "`/add <ссылка> <ключевое_слово>` — добавить мониторинг\n"
        "`/remove <ссылка> <ключевое_слово>` — остановить мониторинг\n"
        "`/list` — посмотреть список активных мониторингов\n\n"
        "Если что-то непонятно — пиши, помогу!"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("add"))
async def handle_add(message: types.Message):
    try:
        url_match = re.search(r'https?://[^\s]+', message.text)
        if not url_match:
            return await message.answer("❌ Не могу найти ссылку в сообщении. Попробуй ещё раз.")

        url = url_match.group(0)
        keyword = message.text.replace('/add', '').replace(url, '').strip()
        if not keyword:
            return await message.answer("⚠️ Пожалуйста, укажи ключевое слово после ссылки.")

        key = (url, keyword, message.chat.id)

        if key in monitor_tasks:
            return await message.answer("⏳ Мониторинг с такими параметрами уже запущен.")

        task = asyncio.create_task(start_monitoring(url, keyword, message.chat.id))
        monitor_tasks[key] = task

        await message.answer(
            f"✅ Отлично! Мониторинг для ключевого слова *{keyword}* успешно запущен.\n"
            f"Я буду присылать тебе обновления, как только они появятся.",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        await message.answer(f"⚠️ Произошла ошибка: {str(e)}")


@dp.message(Command("remove"))
async def handle_remove(message: types.Message):
    try:
        url_match = re.search(r'https?://[^\s]+', message.text)
        if not url_match:
            return await message.answer("❌ Не удалось найти ссылку. Проверь, пожалуйста.")

        url = url_match.group(0)
        keyword = message.text.replace('/remove', '').replace(url, '').strip()
        if not keyword:
            return await message.answer("⚠️ Пожалуйста, укажи ключевое слово для остановки мониторинга.")

        key = (url, keyword, message.chat.id)

        task = monitor_tasks.get(key)
        if task:
            task.cancel()
            del monitor_tasks[key]
            await message.answer(
                f"🛑 Мониторинг для ключевого слова *{keyword}* остановлен.\n"
                f"Если захочешь возобновить — просто добавь его снова командой `/add`.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.answer("❗ Мониторинг с такими параметрами не найден.")

    except Exception as e:
        await message.answer(f"⚠️ Ошибка при остановке мониторинга: {str(e)}")


@dp.message(Command("list"))
async def handle_list(message: types.Message):
    user_tasks = [(url, keyword) for (url, keyword, chat_id) in monitor_tasks.keys() if chat_id == message.chat.id]

    if not user_tasks:
        await message.answer("📭 У тебя пока нет активных мониторингов.\n"
                             "Добавь первый с помощью команды `/add`!")
        return

    text_lines = ["📋 *Твои активные мониторинги:*"]
    for i, (url, keyword) in enumerate(user_tasks, start=1):
        text_lines.append(
            f"{i}. 🔎 *{keyword}*\n"
            f"   Ссылка: [Перейти]({url})\n"
            f"   Для остановки: `/remove {url} {keyword}`"
        )

    text = "\n\n".join(text_lines)
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


async def start_monitoring(url, keyword, chat_id):
    base_url = url.split('/category')[0]
    scraper = HermesScraper(proxy=PROXY_URL)

    try:
        async for item in scraper.monitor_for_item(category_url=url, key=keyword):
            sku = item.get('sku')
            stock = item.get('stock', {})
            in_stock = stock.get('ecom') or stock.get('retail') or stock.get('hasVariantInEcomStock')

            print(item)

            if sku and in_stock and sku not in sent_skus:
                sent_skus.add(sku)
                await send_item_to_user(chat_id=chat_id, item=item, base_url=base_url)
    except asyncio.CancelledError:
        print(f"[Мониторинг остановлен] {keyword} - {url}")
    except Exception as e:
        print(f"[Ошибка мониторинга] {e}")


async def send_item_to_user(chat_id: int, item: dict, base_url: str):
    title = item.get('title', 'Без названия')
    price = item.get('price', 'N/A')
    url_path = item.get('url', '')
    full_url = f"{base_url}{url_path}" if url_path else ''

    text = f"👜 *{title}*\n💶 Цена: {price} EUR\n"
    if full_url:
        text += f"[🔗 Перейти к товару]({full_url})"

    image_url = extract_first_image_url(item)
    if image_url:
        await bot.send_photo(chat_id, photo=image_url, caption=text, parse_mode=ParseMode.MARKDOWN)
    else:
        await bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)


def extract_first_image_url(item: dict) -> str:
    assets = item.get('assets', [])
    for asset in assets:
        if asset.get('type') == 'image':
            url = asset.get('url')
            if url:
                return f"https:{url}"
    return ''


async def main():
    global sent_skus
    sent_skus = set()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
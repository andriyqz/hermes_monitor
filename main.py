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
        "👋 Hello!\n\n"
        "📌 Here’s what you can do:\n"
        "`/add <link> <keyword>` — add monitoring\n"
        "`/remove <link> <keyword>` — stop monitoring\n"
        "`/list` — see a list of active monitorings\n\n"
        "If something isn’t clear — write to me, I’ll help!"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("add"))
async def handle_add(message: types.Message):
    try:
        url_match = re.search(r'https?://[^\s]+', message.text)
        if not url_match:
            return await message.answer("❌ I can’t find a link in the message. Try again.")

        url = url_match.group(0)
        keyword = message.text.replace('/add', '').replace(url, '').strip()
        if not keyword:
            return await message.answer("⚠️ Please provide a keyword after the link.")

        key = (url, keyword, message.chat.id)

        if key in monitor_tasks:
            return await message.answer("⏳ Monitoring with these parameters is already running.")

        task = asyncio.create_task(start_monitoring(url, keyword, message.chat.id))
        monitor_tasks[key] = task

        await message.answer(
            f"✅ Great! Monitoring for the keyword *{keyword}* has been started.\n"
            f"I’ll send you updates as soon as they appear.",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        await message.answer(f"⚠️ An error occurred: {str(e)}")


@dp.message(Command("remove"))
async def handle_remove(message: types.Message):
    try:
        url_match = re.search(r'https?://[^\s]+', message.text)
        if not url_match:
            return await message.answer("❌ Couldn’t find a link. Please check.")

        url = url_match.group(0)
        keyword = message.text.replace('/remove', '').replace(url, '').strip()
        if not keyword:
            return await message.answer("⚠️ Please provide a keyword to stop monitoring.")

        key = (url, keyword, message.chat.id)

        task = monitor_tasks.get(key)
        if task:
            task.cancel()
            del monitor_tasks[key]
            await message.answer(
                f"🛑 Monitoring for the keyword *{keyword}* has been stopped.\n"
                f"If you want to restart it — just add it again using `/add`.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.answer("❗ Monitoring with these parameters was not found.")

    except Exception as e:
        await message.answer(f"⚠️ Error while stopping monitoring: {str(e)}")


@dp.message(Command("list"))
async def handle_list(message: types.Message):
    user_tasks = [(url, keyword) for (url, keyword, chat_id) in monitor_tasks.keys() if chat_id == message.chat.id]

    if not user_tasks:
        await message.answer("📭 You don’t have any active monitorings yet.\n"
                             "Add the first one using `/add`!")
        return

    text_lines = ["📋 *Your active monitorings:*"]
    for i, (url, keyword) in enumerate(user_tasks, start=1):
        text_lines.append(
            f"{i}. 🔎 *{keyword}*\n"
            f"   Link: [Open]({url})\n"
            f"   To stop: `/remove {url} {keyword}`"
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
        print(f"[Monitoring stopped] {keyword} - {url}")
    except Exception as e:
        print(f"[Monitoring error] {e}")


async def send_item_to_user(chat_id: int, item: dict, base_url: str):
    title = item.get('title', 'Untitled')
    price = item.get('price', 'N/A')
    url_path = item.get('url', '')
    full_url = f"{base_url}{url_path}" if url_path else ''

    text = f"👜 *{title}*\n💶 Price: {price} EUR\n"
    if full_url:
        text += f"[🔗 View item]({full_url})"

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

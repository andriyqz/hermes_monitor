import asyncio
import json
import aiohttp
from bs4 import BeautifulSoup


class HermesScraper:
    def __init__(self, proxy: str):
        self.proxy = proxy

    async def fetch_category_items(self, category_url: str) -> dict:
        async with aiohttp.ClientSession() as session:
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://www.hermes.com',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            }

            async with session.get(category_url, proxy=self.proxy, headers=headers) as response:
                html = await response.text()
                soup = BeautifulSoup(html, features='html.parser')
                state_script = soup.find('script', id='hermes-state')

                if not state_script:
                    raise ValueError("Could not find 'hermes-state' script tag.")

                state_data = json.loads(state_script.string.strip())
                items_key = self._extract_items_key(state_data)

                if not items_key:
                    print(state_data)
                    raise KeyError("Could not find items key in JSON.")
                return state_data[items_key]['b']

    async def monitor_for_item(self, category_url: str, key: str, interval: int = 10):
        while True:
            try:
                items = await self.fetch_category_items(category_url=category_url)

                for item in items['products']['items']:
                    if key.lower() in item['title'].lower():
                        yield item

            except Exception as e:
                print(f"[Ошибка мониторинга] {e}")

            await asyncio.sleep(interval)

    def _extract_items_key(self, state_data: dict) -> str | None:
        for key, value in state_data.items():
            try:
                if value.get('b', {}).get('total'):
                    return key
            except (AttributeError, TypeError):
                continue
        return None

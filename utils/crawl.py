import asyncio
from crawl4ai import AsyncWebCrawler

async def main():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://www.81scf.com/contatti/")
        print(result.markdown)

asyncio.run(main())

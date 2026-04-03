import asyncio

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("data:text/html,<title>Paper Agent CI</title><h1>ok</h1>")
        title = await page.title()
        assert title == "Paper Agent CI", f"unexpected title: {title!r}"
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

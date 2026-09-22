import asyncio
from urllib.parse import urljoin
from playwright.async_api import async_playwright

MARKTPLAATS_URL = (
    "https://www.marktplaats.nl/q/gratis/"
    "#PriceCentsTo:500|distanceMeters:8000|postcode:3116"
)


async def main():

    print("======================================")
    print("   MARKTPLAATS TEST")
    print("======================================")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        print("🔎 Marktplaats openen...")

        await page.goto(
            MARKTPLAATS_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        await page.wait_for_timeout(8000)

        links = await page.locator(
            'a[href*="/v/"]'
        ).all()

        print()
        print(
            f"📦 {len(links)} links gevonden"
        )
        print()

        gezien = set()

        for link in links:

            try:
                titel = await link.inner_text()
                href = await link.get_attribute("href")

                if not titel or not href:
                    continue

                href = urljoin(
                    "https://www.marktplaats.nl",
                    href
                )

                if href in gezien:
                    continue

                gezien.add(href)

                print("📋 TITEL:")
                print(titel.strip())
                print()
                print("🔗 LINK:")
                print(href)
                print()
                print("--------------------------------------")

            except Exception as e:
                print("Fout:", e)

        await browser.close()

        print()
        print("✅ TEST KLAAR")


if __name__ == "__main__":
    asyncio.run(main())

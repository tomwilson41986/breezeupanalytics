#!/usr/bin/env python3
"""Playwright script to inspect OBS catalog SPA network requests.

Use this to discover/verify API endpoints when the SPA changes.
Requires: pip install playwright && python -m playwright install chromium

Usage:
    python scripts/inspect_obs_spa.py [sale_id]
    python scripts/inspect_obs_spa.py 149
"""

import asyncio
import json
import sys

from playwright.async_api import async_playwright


async def inspect_sale(sale_id: str = "149"):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        api_calls: list[dict] = []

        def on_request(request):
            if "wp-json" in request.url or "api" in request.url.lower():
                api_calls.append({
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                })

        async def on_response(response):
            url = response.url
            if "wp-json" in url:
                try:
                    body = await response.json()
                    # Save the response
                    safe_name = url.split("/")[-1].split("?")[0]
                    with open(f"/tmp/obs_api_{safe_name}.json", "w") as f:
                        json.dump(body, f, indent=2)
                    print(f"  Saved: {url} ({response.status})")
                except Exception:
                    print(f"  Response: {url} ({response.status}, non-JSON)")

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"Navigating to catalog #{sale_id}...")
        await page.goto(f"https://obssales.com/catalog/#{sale_id}", wait_until="networkidle")

        print(f"\nCaptured {len(api_calls)} API calls:")
        for call in api_calls:
            print(f"  {call['method']} {call['url']}")

        await browser.close()


if __name__ == "__main__":
    sale_id = sys.argv[1] if len(sys.argv) > 1 else "149"
    asyncio.run(inspect_sale(sale_id))

"""Render submitted pages in an isolated, offline browser context."""
import os


def render(source, width, height):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("Install requirements.txt and run python -m playwright install chromium first.") from error
    try:
        with sync_playwright() as playwright:
            options = {"headless": True}
            if os.environ.get("CHROME_PATH"):
                options["executable_path"] = os.environ["CHROME_PATH"]
            browser = playwright.chromium.launch(**options)
            try:
                context = browser.new_context(viewport={"width": width, "height": height},
                                              service_workers="block", accept_downloads=False)
                page = context.new_page()
                # Opaque origin; no network, frames, popups, forms, or local files.
                policy = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; sandbox allow-scripts"
                delivered = False
                def route_request(route):
                    nonlocal delivered
                    if not delivered and route.request.url == "https://layout.invalid/" and route.request.is_navigation_request():
                        delivered = True
                        route.fulfill(status=200, content_type="text/html; charset=utf-8",
                                      headers={"Content-Security-Policy": policy}, body=source)
                    else:
                        route.abort()
                context.route("**/*", route_request)
                page.goto("https://layout.invalid/", wait_until="load", timeout=10000)
                page.wait_for_timeout(750)
                return page.screenshot(type="png", timeout=10000, animations="disabled")
            finally:
                browser.close()
    except Exception as error:
        raise RuntimeError("Could not render HTML. Ensure Playwright Chromium is installed. " + str(error)[:250]) from error

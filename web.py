import os
from aiohttp import web

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _read(filename: str) -> str:
    with open(os.path.join(TEMPLATES_DIR, filename), encoding="utf-8") as f:
        return f.read()


async def terms(request):
    return web.Response(text=_read("terms.html"), content_type="text/html")


async def privacy(request):
    return web.Response(text=_read("privacy.html"), content_type="text/html")


async def start_web(port: int = 8080):
    app = web.Application()
    app.router.add_get("/terms", terms)
    app.router.add_get("/privacy", privacy)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server running on port {port}")

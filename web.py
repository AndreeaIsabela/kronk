from aiohttp import web

TERMS_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Terms of Service — Kronk Bot</title>
<style>body{font-family:sans-serif;max-width:700px;margin:60px auto;padding:0 20px;line-height:1.6;color:#222}</style>
</head>
<body>
<h1>Terms of Service</h1>
<p><strong>Last updated: 2026-06-13</strong></p>

<p>By using the Kronk Discord bot ("the Bot"), you agree to these terms.</p>

<h2>Usage</h2>
<ul>
  <li>The Bot is provided for use within authorised Discord servers only.</li>
  <li>Do not abuse or attempt to exploit the Bot's commands.</li>
  <li>The Bot may be updated or taken offline at any time without notice.</li>
</ul>

<h2>Disclaimer</h2>
<p>The Bot is provided "as is" without warranty of any kind. We are not liable for missed timers, outages, or any other issues arising from its use.</p>

<h2>Contact</h2>
<p>Questions? Reach out to a server administrator.</p>
</body>
</html>"""

PRIVACY_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Privacy Policy — Kronk Bot</title>
<style>body{font-family:sans-serif;max-width:700px;margin:60px auto;padding:0 20px;line-height:1.6;color:#222}</style>
</head>
<body>
<h1>Privacy Policy</h1>
<p><strong>Last updated: 2026-06-13</strong></p>

<h2>Data we collect</h2>
<p>When you use the <code>/pet-buff</code> command, the Bot temporarily stores:</p>
<ul>
  <li>Your Discord user ID</li>
  <li>Your display name at the time of the command</li>
  <li>The timer expiry timestamp</li>
  <li>The ID of the channel where the command was used</li>
</ul>

<h2>How it's used</h2>
<p>This data is used solely to schedule and post buff timer notifications in your Discord server. It is never shared with third parties.</p>

<h2>Retention</h2>
<p>Data is deleted automatically when your timer expires (within 2 hours). If the Bot is offline when a timer expires, the data is deleted on next startup.</p>

<h2>Contact</h2>
<p>Questions? Reach out to a server administrator.</p>
</body>
</html>"""


async def terms(request):
    return web.Response(text=TERMS_HTML, content_type="text/html")


async def privacy(request):
    return web.Response(text=PRIVACY_HTML, content_type="text/html")


async def start_web(port: int = 8080):
    app = web.Application()
    app.router.add_get("/terms", terms)
    app.router.add_get("/privacy", privacy)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server running on port {port}")


import os
import re
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

API_BASE = os.getenv("API_BASE", "https://yunus-bhai-visit-ff.onrender.com/bd")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")

HELP_TEXT = (
    "👋 Assalamu Alaikum!\n\n"
    "Use: /visit <uid> (Free Fire ID)\n"
    "Example: /visit 654754678\n\n"
    "Endpoint: https://yunus-bhai-visit-ff.onrender.com/bd/<uid>"
)

UID_RE = re.compile(r"^\d{5,15}$")

app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def visit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a UID. Example: /visit 654754678")
        return
    uid = context.args[0].strip()
    if not UID_RE.match(uid):
        await update.message.reply_text("UID must be 5–15 digits. Example: 654754678")
        return
    url = f"{API_BASE.rstrip('/')}/{uid}"
    try:
        await update.chat.send_action(action="typing")
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        body = e.response.text
        if len(body) > 200:
            body = body[:200] + "…"
        await update.message.reply_text(f"❌ API error {e.response.status_code}: {body}")
        return
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to reach API: {e}")
        return

    if isinstance(data, dict):
        lines = []
        title = data.get("title") or data.get("name") or "Free Fire Profile"
        lines.append(f"<b>{title}</b>")
        for key in ["uid","player_id","id","nickname","level","region","rank","guild","visits","profile_url","updated_at"]:
            if key in data and data[key] is not None:
                label = key.replace("_"," ").title()
                lines.append(f"• <b>{label}</b>: {data[key]}")
        extras = {k: v for k, v in data.items() if k not in {"title","name","uid","player_id","id","nickname","level","region","rank","guild","visits","profile_url","updated_at"}}
        if extras:
            lines.append("\n<code>Other:</code>")
            preview = str(extras)
            if len(preview) > 800:
                preview = preview[:800] + "…"
            lines.append(f"<code>{preview}</code>")
        text = "\n".join(lines)
    else:
        blob = str(data)
        if len(blob) > 1000:
            blob = blob[:1000] + "…"
        text = f"<code>{blob}</code>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def echo_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (update.message.text or "").strip()
    if UID_RE.match(msg):
        context.args = [msg]
        return await visit_cmd(update, context)
    return await help_cmd(update, context)

# register handlers
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CommandHandler("visit", visit_cmd))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_unknown))

@app.on_event("startup")
async def on_startup():
    # initialize/start bot (no polling)
    await application.initialize()
    await application.start()
    public_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")
    if public_url:
        webhook_url = public_url.rstrip("/") + f"/webhook/{BOT_TOKEN}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", params={"url": webhook_url})
        print("Webhook set to:", webhook_url)
    else:
        print("WARNING: PUBLIC URL not found; set PUBLIC_URL or use Render Web Service.")

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != BOT_TOKEN:
        return JSONResponse({"ok": False, "error": "invalid token"}, status_code=403)
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

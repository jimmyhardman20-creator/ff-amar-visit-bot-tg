import os
import re
import asyncio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# --- CONFIG ---
API_BASE = os.getenv("API_BASE", "https://yunus-bhai-visit-kore-ff-phi.vercel.app/bd")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PING_URL = os.getenv("PING_URL", "https://ff-amar-visit-bot-tg.onrender.com")  # keep-awake ping target

if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")

HELP_TEXT = (
    "👋 Assalamu Alaikum!\n\n"
    "Use: /visit <uid> (Free Fire ID)\n"
    "Example: /visit 654754678\n\n"
    "I will fetch your Free Fire profile visit info from the API."
    # (endpoint line intentionally removed)
)

UID_RE = re.compile(r"^\d{5,15}$")
UID_SEARCH_RE = re.compile(r"(\d{5,15})")  # fallback: first 5–15 digit run

app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()


# --- Keep Awake System ---
async def keep_awake():
    """Ping the API every 5 minutes to prevent free instances from sleeping."""
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(PING_URL)
                print(f"Ping {PING_URL}: {r.status_code}")
        except Exception as e:
            print(f"Ping failed: {e}")
        await asyncio.sleep(300)


# --- Telegram Handlers ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def visit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1) Try to get UID from args
    uid = None
    if context.args:
        uid = context.args[0].strip()
    # 2) Fallback: extract digits from message text
    if not uid:
        msg = (update.effective_message.text or "").strip()
        m = UID_SEARCH_RE.search(msg)
        if m:
            uid = m.group(1)

    if not uid or not UID_RE.match(uid):
        await update.message.reply_text("UID must be 5–15 digits. Example: 654754678")
        return

    url = f"{API_BASE.rstrip('/')}/{uid}"

    try:
        await update.chat.send_action(action="typing")
    except Exception:
        pass

    # Call API
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

    # Format to the requested style
    try:
        ff_uid = data.get("uid") or data.get("UID") or uid
        name = data.get("name") or data.get("nickname") or "N/A"
        region = data.get("region") or "N/A"
        level = data.get("level") or "N/A"
        likes = data.get("likes") or data.get("Likes") or "N/A"
        target = data.get("target") or data.get("Target") or "N/A"
        success = data.get("success") or data.get("Success") or "N/A"
        failed = data.get("failed") or data.get("Failed") or "N/A"

        text = (
            "✅ <b>Visit Completed Successfully</b>\n\n"
            f"<b>UID:</b> {ff_uid}\n"
            f"<b>Name:</b> {name}\n"
            f"<b>Region:</b> {region}\n"
            f"<b>Level:</b> {level}\n"
            f"<b>Likes:</b> {likes}\n\n"
            f"<b>Target:</b> {target}\n"
            f"<b>Success:</b> {success}\n"
            f"<b>Failed:</b> {failed}"
        )
    except Exception as e:
        text = f"⚠️ Unexpected API format: {e}\n\n<code>{data}</code>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def echo_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If user just sends digits, treat as UID
    msg = (update.message.text or "").strip()
    if UID_RE.match(msg):
        context.args = [msg]
        return await visit_cmd(update, context)
    return await help_cmd(update, context)


# --- Register Handlers ---
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CommandHandler("visit", visit_cmd))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_unknown))


# --- Health Endpoints (for Render) ---
@app.get("/", response_class=PlainTextResponse)
async def root():
    return "ok"

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


# --- Lifecycle: set webhook + start ping task ---
@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    asyncio.create_task(keep_awake())  # background ping loop

    public_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")
    if public_url:
        webhook_url = public_url.rstrip("/") + f"/webhook/{BOT_TOKEN}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                params={"url": webhook_url}
            )
        print("Webhook set to:", webhook_url)
    else:
        print("WARNING: PUBLIC URL not found; set PUBLIC_URL or rely on RENDER_EXTERNAL_URL.")


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

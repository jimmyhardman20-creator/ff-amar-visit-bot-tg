
# Telegram FF Webhook Bot (Render Web Service)

1) Create a **Web Service** in Render and connect this repo.
2) Set Environment Variables:
   - `TELEGRAM_BOT_TOKEN` = token from BotFather
   - `API_BASE` (optional) = https://yunus-bhai-visit-ff.onrender.com/bd
   - (Optional) `PUBLIC_URL` if `RENDER_EXTERNAL_URL` is not present.
3) Deploy. Render will scan the `Procfile` and run on `$PORT`.
4) Webhook is set automatically on startup to `${RENDER_EXTERNAL_URL}/webhook/<TOKEN>`.

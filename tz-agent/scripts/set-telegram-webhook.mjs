const token = process.env.TELEGRAM_BOT_TOKEN?.trim();
const secret = process.env.TELEGRAM_WEBHOOK_SECRET?.trim();
const url = process.env.WEBHOOK_URL?.trim();

if (!token || !secret || !url) {
  console.error("Нужны переменные TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET и WEBHOOK_URL.");
  process.exit(1);
}

const response = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    url,
    secret_token: secret,
    allowed_updates: ["message", "edited_message"],
    drop_pending_updates: false,
  }),
});

const payload = await response.json();
console.log(JSON.stringify({
  ok: payload.ok === true,
  description: typeof payload.description === "string" ? payload.description : "",
}));

if (payload.ok !== true) process.exit(1);

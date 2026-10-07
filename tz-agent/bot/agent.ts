import { defineAgent } from "@cursor/bdk";

export default defineAgent({
  name: "Сборщик ТЗ",
  description: "Поэтапно собирает техническое задание у заказчика в Telegram и сохраняет результат каждого этапа.",
  model: {
    id: "grok-4.7",
    params: [{ id: "effort", value: "high" }],
  },
  tools: ["read", "grep", "glob", "ls"],
  hosting: {
    egressDomains: ["api.telegram.org", "smtp.gmail.com"],
    secretNames: [
      "TELEGRAM_BOT_TOKEN",
      "TELEGRAM_WEBHOOK_SECRET",
      "SMTP_USER",
      "SMTP_PASSWORD",
      "TZ_OWNER_EMAIL",
    ],
  },
});

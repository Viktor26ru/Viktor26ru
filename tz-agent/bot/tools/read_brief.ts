import { defineTool } from "@cursor/bdk/tools";
import { z } from "zod";
import { loadBrief } from "../lib/archive.js";
import { progressFooter, resolveChatId, viewForModel } from "../lib/logic.js";

export default defineTool({
  description: "Прочитать сохранённое ТЗ этого чата: этап, пробелы, факты, предложения и документы. Не показывает другие чаты.",
  effect: "read",
  inputSchema: z.object({
    chatId: z.string().min(1).max(40).optional().describe("Только для проверки вне Telegram. В диалоге с заказчиком не передавай."),
  }),
  async execute({ chatId }, ctx) {
    const resolved = resolveChatId(ctx.session, chatId);
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const now = new Date().toISOString();
    const brief = await loadBrief(ctx.host, resolved.chatId, now);
    return {
      ok: true,
      chatId: resolved.chatId,
      footer: progressFooter(brief),
      brief: viewForModel(brief),
    };
  },
});

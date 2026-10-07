import { prompt } from "@cursor/bdk";
import { defineTool } from "@cursor/bdk/tools";
import { z } from "zod";
import { commitBrief } from "../lib/archive.js";
import { applyRecord, missingSlots, pendingSuggestions, progressView, resolveChatId, STAGES, SUGGESTION_STATUSES } from "../lib/logic.js";

const slotHelp = STAGES.map((stage) => `${stage.id}: ${stage.slots.map((slot) => slot.key).join(", ")}`).join("; ");

export default defineTool({
  description: prompt`
    Записать факты, решение заказчика по предложению или разбор файла.
    Ключи пунктов: ${slotHelp}. Общие заметки: notes.
    Пример ключа: goal.problem. Предложение со статусом pending, пока заказчик сам не принял, отклонил или изменил его.
    Не записывай свою догадку как факт.
  `,
  effect: "write",
  dryRunResult: () => ({ ok: false, dryRun: true }),
  inputSchema: z.object({
    chatId: z.string().min(1).max(40).optional(),
    slots: z.array(z.object({
      key: z.string().min(3).max(80),
      value: z.string().min(1).max(8000),
    })).max(20).optional(),
    suggestions: z.array(z.object({
      id: z.string().min(1).max(40).optional(),
      proposal: z.string().min(8).max(2000),
      why: z.string().min(8).max(2000),
      status: z.enum(SUGGESTION_STATUSES),
      customerDecision: z.string().max(2000).optional(),
    })).max(5).optional(),
    documentNotes: z.array(z.object({
      id: z.string().min(1).max(80),
      analysis: z.string().min(8).max(8000),
    })).max(5).optional(),
  }),
  async execute(input, ctx) {
    const resolved = resolveChatId(ctx.session, input.chatId);
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const hasWork = (input.slots?.length ?? 0) + (input.suggestions?.length ?? 0) + (input.documentNotes?.length ?? 0) > 0;
    if (!hasWork) return { ok: false, error: "Нечего записывать." };
    const now = new Date().toISOString();
    let errors: string[] = [];
    let applied = 0;
    const brief = await commitBrief(ctx.host, resolved.chatId, now, (current) => {
      const result = applyRecord(current, input, now);
      errors = result.errors;
      applied = result.applied;
      return result.brief;
    }, ctx.artifacts);
    const view = progressView(brief);
    return {
      ok: applied > 0,
      applied,
      errors,
      stage: view.stageTitle,
      missing: missingSlots(brief),
      pendingSuggestions: pendingSuggestions(brief).map((item) => ({ id: item.id, proposal: item.proposal })),
      completed: view.completed,
      stageTotal: view.stageTotal,
    };
  },
});

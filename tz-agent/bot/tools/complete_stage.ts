import { prompt } from "@cursor/bdk";
import { defineTool } from "@cursor/bdk/tools";
import { z } from "zod";
import { commitBrief, loadBrief, writeStageReport } from "../lib/archive.js";
import { enqueueMail, flushPendingMail } from "../lib/email.js";
import {
  customerLabel,
  missingSlots,
  progressView,
  resolveChatId,
  stageById,
  stagePosition,
  STAGES,
  tryComplete,
} from "../lib/logic.js";

type Completion = ReturnType<typeof tryComplete>;

export default defineTool({
  description: prompt`
    Закрыть текущий этап и сохранить подробный результат для анализа.
    Вызывай, когда пункты этапа заполнены словами заказчика, а предложения этого этапа уже решены им.
    narrative — разбор: что поняли, риски и что это значит для следующей работы.
    Этап spec закрывай только после ответа заказчика на уже показанную сводку.
  `,
  effect: "write",
  dryRunResult: () => ({ ok: false, dryRun: true }),
  inputSchema: z.object({
    chatId: z.string().min(1).max(40).optional(),
    narrative: z.string().min(30).max(20000),
  }),
  async execute({ chatId, narrative }, ctx) {
    const resolved = resolveChatId(ctx.session, chatId);
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const now = new Date().toISOString();
    const preview = tryComplete(await loadBrief(ctx.host, resolved.chatId, now), narrative, now);
    if (!preview.ok) return { ok: false, errors: preview.errors, missing: preview.missing };

    let failure: { errors: string[]; missing: string[] } | undefined;
    let settled: Extract<Completion, { ok: true }> = preview;
    const brief = await commitBrief(ctx.host, resolved.chatId, now, (latest) => {
      const again = tryComplete(latest, narrative, now);
      if (!again.ok) {
        failure = { errors: again.errors, missing: again.missing };
        return latest;
      }
      failure = undefined;
      settled = again;
      return again.duplicate ? latest : again.brief;
    }, ctx.artifacts);
    if (failure) return { ok: false, errors: failure.errors, missing: failure.missing };

    const stage = stageById(settled.stage);
    const report = settled.report;
    await writeStageReport(ctx.host, resolved.chatId, settled.stage, settled.hash, report);
    await ctx.artifacts.tag({
      kind: "stage-report",
      key: `report:${resolved.chatId}:${settled.stage}:${settled.hash}`,
      title: `${customerLabel(brief)}: ${stage?.title ?? settled.stage}`,
      data: {
        chatId: resolved.chatId,
        stageId: settled.stage,
        stageIndex: stagePosition(settled.stage),
        title: stage?.title ?? settled.stage,
        emailStatus: ctx.session.purpose === "eval" ? "skipped_eval" : "queued",
        completedAt: now,
        hash: settled.hash,
      },
      contents: report,
      contentType: "text/markdown; charset=utf-8",
    });
    let emailStatus = "skipped_eval";
    if (ctx.session.purpose !== "eval") {
      await enqueueMail(ctx.host, {
        id: `${resolved.chatId}:${settled.stage}:${settled.hash}`,
        chatId: resolved.chatId,
        subject: `${settled.revision ? "Обновление ТЗ" : "ТЗ"} ${stagePosition(settled.stage)}/${STAGES.length}: ${stage?.title ?? settled.stage} — ${customerLabel(brief)}`,
        bodyPath: `mail/${settled.hash}.txt`,
        attempts: 0,
        lastError: "",
        createdAt: now,
      }, report);
      const flush = await flushPendingMail(ctx.host);
      emailStatus = flush.sent > 0 ? "sent" : "queued";
    }
    const view = progressView(brief);
    return {
      ok: true,
      duplicate: settled.duplicate,
      stage: settled.stage,
      nextStage: view.stageTitle,
      completed: view.completed,
      stageTotal: view.stageTotal,
      missing: missingSlots(brief),
      specApproved: view.specApproved,
      emailStatus,
    };
  },
});

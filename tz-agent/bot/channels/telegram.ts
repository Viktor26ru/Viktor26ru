import type { JsonValue } from "@cursor/bdk";
import { defineChannel, localDev, POST, sharedSecretAuth } from "@cursor/bdk/channels";
import { z } from "zod";
import { readText, rememberAgentTurn, rememberCustomerTurn, storeDocument } from "../lib/archive.js";
import { extractText } from "../lib/extract.js";
import {
  commandOf,
  continuationToken,
  helpText,
  interviewPrompt,
  progressFooter,
  scrubSecrets,
  viewForModel,
} from "../lib/logic.js";
import {
  downloadTelegramFile,
  parseInbound,
  sendTelegramText,
  sendTyping,
  storedFilePath,
} from "../lib/telegram-api.js";

type TelegramState = {
  chatId: string;
  replyToMessageId: number;
};

async function claimDelivery(kv: { get(key: string): Promise<JsonValue | undefined>; put(key: string, value: JsonValue): Promise<void>; delete(key: string): Promise<void> }, key: string): Promise<boolean> {
  const existing = await kv.get(key);
  if (existing) return false;
  await kv.put(key, { at: new Date().toISOString() });
  return true;
}

export default defineChannel<TelegramState>({
  state: { chatId: "", replyToMessageId: 0 },
  auth: [
    localDev(),
    sharedSecretAuth({
      header: "X-Telegram-Bot-Api-Secret-Token",
      secret: "TELEGRAM_WEBHOOK_SECRET",
    }),
  ],
  routes: [
    POST("/webhook", {
      description: "Входящее сообщение Telegram. Заказчик отвечает на вопросы и присылает файлы.",
      bodySchema: z.unknown(),
      handler: async (_request, { send, waitUntil, body, host, artifacts }) => {
        const inbound = parseInbound(body);
        if (!inbound) return new Response(null, { status: 202 });
        const now = new Date().toISOString();
        try {
          const freshFiles: { name: string; textExtracted: boolean }[] = [];
          for (const file of inbound.files) {
            const downloaded = await downloadTelegramFile(file.fileId);
            if (!downloaded.ok) {
              freshFiles.push({ name: file.name, textExtracted: false });
              continue;
            }
            const extracted = extractText(file.name, file.mime, downloaded.bytes);
            await storeDocument(host, inbound.chatId, {
              id: file.uniqueId,
              name: file.name,
              mime: file.mime,
              size: downloaded.bytes.byteLength,
              storedPath: storedFilePath(file.uniqueId, file.name),
              textExcerpt: scrubSecrets(extracted.text).slice(0, 8000),
              analysis: "",
              receivedAt: now,
            }, downloaded.bytes, artifacts);
            freshFiles.push({ name: file.name, textExtracted: extracted.text.trim().length > 0 });
          }
          const brief = await rememberCustomerTurn(host, {
            chatId: inbound.chatId,
            updateId: inbound.updateId,
            at: now,
            text: scrubSecrets(inbound.text),
            fileIds: inbound.files.map((file) => file.uniqueId),
            userId: inbound.userId,
            name: inbound.name,
            username: inbound.username,
          }, artifacts);
          await host.kv.put(`reply:${inbound.chatId}`, inbound.messageId);
          const command = commandOf(inbound.text);
          if (command === "help" || command === "progress") {
            const text = command === "help" ? helpText(brief) : progressFooter(brief);
            await sendTelegramText(inbound.chatId, text, inbound.messageId);
            return new Response(null, { status: 202 });
          }
          if (command === "report") {
            const latest = brief.stageReports[brief.stageReports.length - 1];
            const stored = latest ? await readText(host, inbound.chatId, `reports/${latest.stage}-${latest.hash}.md`) : undefined;
            await sendTelegramText(
              inbound.chatId,
              stored ?? `Закрытых этапов пока нет.\n\n${progressFooter(brief)}`,
              inbound.messageId,
            );
            return new Response(null, { status: 202 });
          }
          const prompt = command === "start"
            ? `${interviewPrompt(brief, "Заказчик открыл диалог.", freshFiles)}\n\nКратко объясни, как пойдёт сбор задания, и задай вопросы первого незакрытого этапа.`
            : interviewPrompt(brief, scrubSecrets(inbound.text), freshFiles);
          await sendTyping(inbound.chatId);
          waitUntil(send(prompt, {
            continuationToken: continuationToken(inbound.chatId),
            admission: "coalesce",
            title: `ТЗ ${inbound.name || inbound.chatId}`,
            state: { chatId: inbound.chatId, replyToMessageId: inbound.messageId },
            workspaceFiles: {
              "brief-state.json": JSON.stringify({ ...viewForModel(brief), newFiles: freshFiles }, null, 2),
            },
          }));
        } catch (error) {
          const message = scrubSecrets(error instanceof Error ? error.message : String(error)).slice(0, 500);
          console.error(`telegram ingest failed: ${message}`);
          await host.kv.put(`failed-update:${inbound.updateId}`, {
            at: now,
            chatId: inbound.chatId,
            error: message,
          });
          await sendTelegramText(
            inbound.chatId,
            "Я сохранил сбой в журнале и не стёр прошлые ответы. Пришлите сообщение ещё раз.",
            inbound.messageId,
          );
        }
        return new Response(null, { status: 202 });
      },
    }),
  ],
  events: {
    async "message.completed"(event, _channel, ctx) {
      if (event.data.parentCallId || !event.data.text.trim()) return;
      const turnId = event.turnId ?? `index-${event.index}`;
      await ctx.host.kv.put(`draft:${event.sessionId}:${turnId}`, event.data.text);
    },
    async "turn.completed"(event, channel, ctx) {
      const turnId = event.turnId ?? `index-${event.index}`;
      const drafted = await ctx.host.kv.get(`draft:${event.sessionId}:${turnId}`);
      const draft = typeof drafted === "string" ? drafted.trim() : "";
      const result = event.data.result?.trim() ?? "";
      const text = result.length >= draft.length ? result : draft;
      if (!text) return;
      const chatId = channel.state.chatId;
      if (!chatId) return;
      const key = `delivered:${event.sessionId}:${turnId}`;
      if (!(await claimDelivery(ctx.host.kv, key))) return;
      const brief = await rememberAgentTurn(ctx.host, chatId, turnId, text, event.at);
      const replyTo = await ctx.host.kv.get(`reply:${chatId}`);
      const sent = await sendTelegramText(
        chatId,
        `${text}\n\n${progressFooter(brief)}`,
        typeof replyTo === "number" ? replyTo : undefined,
      );
      if (!sent.ok) {
        await ctx.host.kv.delete(key);
        console.error(`telegram reply failed: ${sent.error}`);
      }
    },
    async "turn.failed"(event, channel, ctx) {
      if (event.data.status === "cancelled") return;
      const chatId = channel.state.chatId;
      if (!chatId) return;
      const turnId = event.turnId ?? `fail-${event.index}`;
      const key = `delivered:${event.sessionId}:${turnId}`;
      if (!(await claimDelivery(ctx.host.kv, key))) return;
      const replyTo = await ctx.host.kv.get(`reply:${chatId}`);
      const sent = await sendTelegramText(
        chatId,
        "Ответ не собрался, но ваше сообщение уже сохранено. Напишите ещё раз или пришлите /progress, чтобы увидеть, на каком этапе мы остановились.",
        typeof replyTo === "number" ? replyTo : channel.state.replyToMessageId || undefined,
      );
      if (!sent.ok) await ctx.host.kv.delete(key);
    },
  },
});

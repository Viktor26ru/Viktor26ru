import { defineArtifacts } from "@cursor/bdk/artifacts";
import { z } from "zod";

const snapshot = z.object({
  chatId: z.string(),
  customer: z.string(),
  stageId: z.string(),
  stageIndex: z.number(),
  stageTotal: z.number(),
  stageTitle: z.string(),
  completed: z.number(),
  missing: z.array(z.string()),
  pendingSuggestions: z.number(),
  documents: z.number(),
  messages: z.number(),
  updatedAt: z.string(),
  specApproved: z.boolean(),
});

const registry = z.object({
  chats: z.array(z.object({
    chatId: z.string(),
    customer: z.string(),
    stageTitle: z.string(),
    completed: z.number(),
    total: z.number(),
    updatedAt: z.string(),
  })),
});

const stageReport = z.object({
  chatId: z.string(),
  stageId: z.string(),
  stageIndex: z.number(),
  title: z.string(),
  emailStatus: z.string(),
  completedAt: z.string(),
  hash: z.string(),
});

export default defineArtifacts({
  agentTool: false,
  kinds: {
    brief: {
      description: "Текущий прогресс одного заказчика. Обновляется по ходу диалога.",
      schema: snapshot,
    },
    registry: {
      description: "Список всех диалогов сбора ТЗ и на каком они этапе.",
      schema: registry,
    },
    "stage-report": {
      description: "Подробный результат закрытого этапа для дальнейшего анализа.",
      schema: stageReport,
    },
  },
});

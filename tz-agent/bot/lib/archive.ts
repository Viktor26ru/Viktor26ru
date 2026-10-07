import type { HostContext, JsonValue } from "@cursor/bdk";
import { supportsKvCas } from "@cursor/bdk";
import {
  type Brief,
  type StageId,
  type StoredDocument,
  addAgentTurn,
  addCustomerTurn,
  addDocument,
  analysisSnapshot,
  customerLabel,
  emptyBrief,
  isBrief,
  partitionFor,
  progressFooter,
} from "./logic.js";

type ArtifactTagger = {
  tag(input: {
    kind: string;
    key?: string;
    title?: string;
    data: JsonValue;
    contents?: string;
    contentType?: string;
    sessionId?: string;
  }): Promise<unknown>;
};

export type ArchiveHost = {
  kv: HostContext["kv"];
  files: HostContext["files"];
};

export function asJson(value: unknown): JsonValue {
  return JSON.parse(JSON.stringify(value)) as JsonValue;
}

export function chatScope(chatId: string): { scope: { kind: "deployment"; partition: string } } {
  return { scope: { kind: "deployment", partition: partitionFor(chatId) } };
}

const rootScope = { scope: { kind: "deployment" as const } };

export function briefKey(chatId: string): string {
  return `brief:${chatId}`;
}

export async function mutateJson<T>(
  kv: HostContext["kv"],
  key: string,
  fallback: T,
  update: (current: T) => T,
): Promise<T> {
  if (supportsKvCas(kv)) {
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const current = await kv.getWithVersion(key);
      const base = current ? (current.value as T) : structuredClone(fallback);
      const next = update(structuredClone(base));
      const encoded = asJson(next);
      const result = current
        ? await kv.putIfVersion(key, encoded, current.version)
        : await kv.putIfAbsent(key, encoded);
      if (result.ok) return next;
    }
    throw new Error(`Не удалось сохранить ${key} после нескольких попыток.`);
  }
  const existing = await kv.get(key);
  const base = existing === undefined ? structuredClone(fallback) : (existing as T);
  const next = update(structuredClone(base));
  await kv.put(key, asJson(next));
  return next;
}

async function mirrorBrief(files: HostContext["files"], brief: Brief): Promise<void> {
  const scope = chatScope(brief.chatId);
  await files.write("brief.json", JSON.stringify(brief, null, 2), scope);
  await files.write("progress.txt", progressFooter(brief), scope);
}

async function tagQuietly(artifacts: ArtifactTagger | undefined, input: Parameters<ArtifactTagger["tag"]>[0]): Promise<void> {
  if (!artifacts) return;
  try {
    await artifacts.tag(input);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`artifact tag failed: ${message.slice(0, 300)}`);
  }
}

async function publish(host: ArchiveHost, brief: Brief, artifacts?: ArtifactTagger): Promise<void> {
  await mirrorBrief(host.files, brief);
  const snapshot = analysisSnapshot(brief);
  const registry = await mutateJson(host.kv, "registry", { chats: [] as { chatId: string }[] }, (current) => {
    const chats = Array.isArray(current.chats) ? current.chats : [];
    const entry = {
      chatId: brief.chatId,
      customer: customerLabel(brief),
      stageTitle: snapshot.stageTitle,
      completed: snapshot.completed,
      total: snapshot.stageTotal,
      updatedAt: brief.updatedAt,
    };
    return { chats: [entry, ...chats.filter((item) => item.chatId !== brief.chatId)].slice(0, 200) };
  });
  await host.files.write("registry.json", JSON.stringify(registry, null, 2), rootScope);
  await tagQuietly(artifacts, {
    kind: "brief",
    key: `brief:${brief.chatId}`,
    title: `${customerLabel(brief)}: ${snapshot.stageTitle}`,
    data: asJson(snapshot),
    contents: `${progressFooter(brief)}\n\n${JSON.stringify(brief.slots, null, 2)}`,
    contentType: "text/plain; charset=utf-8",
  });
  await tagQuietly(artifacts, {
    kind: "registry",
    key: "registry",
    title: "Все диалоги сбора ТЗ",
    data: asJson(registry),
    contents: JSON.stringify(registry, null, 2),
    contentType: "application/json",
  });
}

export async function loadBrief(host: ArchiveHost, chatId: string, now: string): Promise<Brief> {
  const value = await host.kv.get(briefKey(chatId));
  if (isBrief(value) && value.chatId === chatId) return value;
  return emptyBrief(chatId, now);
}

export async function commitBrief(
  host: ArchiveHost,
  chatId: string,
  now: string,
  update: (brief: Brief) => Brief,
  artifacts?: ArtifactTagger,
): Promise<Brief> {
  const saved = await mutateJson(host.kv, briefKey(chatId), emptyBrief(chatId, now), (current) => {
    const base = isBrief(current) && current.chatId === chatId ? current : emptyBrief(chatId, now);
    return update(base);
  });
  await publish(host, saved, artifacts);
  return saved;
}

export async function rememberCustomerTurn(
  host: ArchiveHost,
  inbound: {
    chatId: string;
    updateId: number;
    at: string;
    text: string;
    fileIds: string[];
    userId: string;
    name: string;
    username: string;
  },
  artifacts?: ArtifactTagger,
): Promise<Brief> {
  const saved = await commitBrief(host, inbound.chatId, inbound.at, (brief) => addCustomerTurn(brief, inbound).brief, artifacts);
  await host.files.write(
    `turns/up-${inbound.updateId}.json`,
    JSON.stringify({ role: "customer", at: inbound.at, text: inbound.text, fileIds: inbound.fileIds }),
    chatScope(inbound.chatId),
  );
  return saved;
}

export async function rememberAgentTurn(
  host: ArchiveHost,
  chatId: string,
  turnId: string,
  text: string,
  at: string,
): Promise<Brief> {
  const saved = await commitBrief(host, chatId, at, (brief) => addAgentTurn(brief, turnId, text, at).brief);
  const safeTurn = turnId.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 80);
  await host.files.write(
    `turns/agent-${safeTurn}.json`,
    JSON.stringify({ role: "agent", at, text }),
    chatScope(chatId),
  );
  return saved;
}

export async function storeDocument(
  host: ArchiveHost,
  chatId: string,
  document: StoredDocument,
  bytes: Uint8Array,
  artifacts?: ArtifactTagger,
): Promise<Brief> {
  const scope = chatScope(chatId);
  await host.files.write(document.storedPath, bytes, scope);
  if (document.textExcerpt) await host.files.write(`${document.storedPath}.txt`, document.textExcerpt, scope);
  return commitBrief(host, chatId, document.receivedAt, (brief) => addDocument(brief, document).brief, artifacts);
}

export async function writeStageReport(host: ArchiveHost, chatId: string, stage: StageId, hash: string, markdown: string): Promise<string> {
  const path = `reports/${stage}-${hash}.md`;
  await host.files.write(path, markdown, chatScope(chatId));
  return path;
}

export async function readText(host: ArchiveHost, chatId: string, path: string): Promise<string | undefined> {
  return host.files.read(path, chatScope(chatId));
}

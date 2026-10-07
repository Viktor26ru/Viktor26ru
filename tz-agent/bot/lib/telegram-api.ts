import { safeFileStem, scrubSecrets, splitTelegram } from "./logic.js";

export type TelegramFile = {
  fileId: string;
  uniqueId: string;
  name: string;
  mime: string;
  size: number;
};

export type TelegramInbound = {
  updateId: number;
  chatId: string;
  messageId: number;
  userId: string;
  name: string;
  username: string;
  text: string;
  files: TelegramFile[];
};

function record(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberOf(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function fileFrom(value: unknown, fallbackName: string): TelegramFile | undefined {
  const file = record(value);
  if (!file) return undefined;
  const fileId = textOf(file.file_id);
  const uniqueId = textOf(file.file_unique_id);
  if (!fileId || !uniqueId) return undefined;
  return {
    fileId,
    uniqueId,
    name: textOf(file.file_name) || fallbackName,
    mime: textOf(file.mime_type),
    size: numberOf(file.file_size) ?? 0,
  };
}

export function parseInbound(body: unknown): TelegramInbound | undefined {
  const update = record(body);
  if (!update) return undefined;
  const updateId = numberOf(update.update_id);
  if (updateId === undefined) return undefined;
  const message = record(update.message) ?? record(update.edited_message);
  if (!message) return undefined;
  const chat = record(message.chat);
  const from = record(message.from);
  const chatId = chat ? numberOf(chat.id) : undefined;
  const messageId = numberOf(message.message_id);
  if (chatId === undefined || messageId === undefined) return undefined;
  if (from?.is_bot === true) return undefined;
  const files: TelegramFile[] = [];
  const document = fileFrom(message.document, "document");
  if (document) files.push(document);
  const photos = Array.isArray(message.photo) ? message.photo : [];
  const largest = photos.map((item) => fileFrom(item, "photo.jpg")).filter((item): item is TelegramFile => item !== undefined).sort((a, b) => a.size - b.size).at(-1);
  if (largest) files.push({ ...largest, name: largest.name || "photo.jpg", mime: largest.mime || "image/jpeg" });
  for (const kind of ["voice", "audio", "video", "video_note"] as const) {
    const media = fileFrom(message[kind], kind);
    if (media) files.push(media);
  }
  const caption = textOf(message.caption);
  const text = textOf(message.text) || caption;
  const name = [textOf(from?.first_name), textOf(from?.last_name)].filter(Boolean).join(" ");
  return {
    updateId,
    chatId: String(chatId),
    messageId,
    userId: from ? String(numberOf(from.id) ?? "") : "",
    name,
    username: textOf(from?.username),
    text,
    files,
  };
}

function botToken(): string {
  return process.env.TELEGRAM_BOT_TOKEN?.trim() ?? "";
}

async function callApi(method: string, body: Record<string, unknown>): Promise<{ ok: true; result: unknown } | { ok: false; error: string }> {
  const token = botToken();
  if (!token) return { ok: false, error: "telegram_token_missing" };
  try {
    const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json() as { ok?: boolean; description?: string; result?: unknown };
    if (!payload.ok) return { ok: false, error: scrubSecrets(payload.description || `telegram_${response.status}`) };
    return { ok: true, result: payload.result };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, error: scrubSecrets(message).slice(0, 200) };
  }
}

export async function sendTyping(chatId: string): Promise<void> {
  await callApi("sendChatAction", { chat_id: chatId, action: "typing" });
}

export async function sendTelegramText(chatId: string, text: string, replyToMessageId?: number): Promise<{ ok: true } | { ok: false; error: string }> {
  const parts = splitTelegram(text);
  let first = true;
  for (const part of parts) {
    const body: Record<string, unknown> = {
      chat_id: chatId,
      text: part,
      disable_web_page_preview: true,
    };
    if (first && replyToMessageId) body.reply_parameters = { message_id: replyToMessageId };
    const result = await callApi("sendMessage", body);
    if (!result.ok) return result;
    first = false;
  }
  return { ok: true };
}

export async function downloadTelegramFile(fileId: string): Promise<{ ok: true; bytes: Uint8Array } | { ok: false; error: string }> {
  const token = botToken();
  if (!token) return { ok: false, error: "telegram_token_missing" };
  const meta = await callApi("getFile", { file_id: fileId });
  if (!meta.ok) return meta;
  const result = record(meta.result);
  const filePath = result ? textOf(result.file_path) : "";
  const size = result ? numberOf(result.file_size) ?? 0 : 0;
  if (!filePath) return { ok: false, error: "telegram_file_path_missing" };
  if (size > 20 * 1024 * 1024) return { ok: false, error: "file_too_large" };
  try {
    const response = await fetch(`https://api.telegram.org/file/bot${token}/${filePath}`);
    if (!response.ok) return { ok: false, error: `telegram_file_${response.status}` };
    const bytes = new Uint8Array(await response.arrayBuffer());
    return { ok: true, bytes };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, error: scrubSecrets(message).slice(0, 200) };
  }
}

export function storedFilePath(uniqueId: string, name: string): string {
  return `files/${uniqueId}-${safeFileStem(name)}`;
}

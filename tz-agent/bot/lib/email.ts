import { connect, type TLSSocket } from "node:tls";
import type { ArchiveHost } from "./archive.js";
import { asJson, chatScope, mutateJson, readText } from "./archive.js";
import { scrubSecrets } from "./logic.js";

export const DEFAULT_OWNER_EMAIL = "viktor26ru@gmail.com";

export type MailJob = {
  id: string;
  chatId: string;
  subject: string;
  bodyPath: string;
  attempts: number;
  lastError: string;
  createdAt: string;
};

function ownerEmail(): string {
  const configured = process.env.TZ_OWNER_EMAIL?.trim();
  return configured || DEFAULT_OWNER_EMAIL;
}

function smtpConfig(): { host: string; user: string; pass: string } | undefined {
  const user = process.env.SMTP_USER?.trim() ?? "";
  const pass = process.env.SMTP_PASSWORD?.trim() ?? "";
  if (!user || !pass) return undefined;
  return { host: process.env.SMTP_HOST?.trim() || "smtp.gmail.com", user, pass };
}

function encodeSubject(subject: string): string {
  const singleLine = subject.replace(/[\r\n]+/g, " ").slice(0, 180);
  return `=?UTF-8?B?${Buffer.from(singleLine, "utf8").toString("base64")}?=`;
}

function dotStuff(text: string): string {
  return text.replace(/\r?\n/g, "\n").split("\n").map((line) => (line.startsWith(".") ? `.${line}` : line)).join("\r\n");
}

function openMail(host: string): Promise<{ command: (line: string) => Promise<string>; write: (chunk: string) => void; finish: () => Promise<string>; close: () => void }> {
  const socket: TLSSocket = connect({ host, port: 465, servername: host });
  let buffer = "";
  const pending: string[] = [];
  let waiter: ((block: string) => void) | undefined;
  const pump = () => {
    const lines = buffer.split(/\r?\n/);
    let end = -1;
    for (let index = 0; index < lines.length - 1; index += 1) {
      if (/^\d{3} /.test(lines[index] ?? "")) {
        end = index;
        break;
      }
    }
    if (end < 0) return;
    const block = lines.slice(0, end + 1).join("\n");
    buffer = lines.slice(end + 1).join("\n");
    if (waiter) {
      const resolve = waiter;
      waiter = undefined;
      resolve(block);
    } else {
      pending.push(block);
    }
    pump();
  };
  socket.on("data", (chunk: Buffer) => {
    buffer += chunk.toString("utf8");
    pump();
  });
  const nextReply = () => {
    const ready = pending.shift();
    if (ready !== undefined) return Promise.resolve(ready);
    return new Promise<string>((resolve, reject) => {
      waiter = resolve;
      socket.once("error", reject);
    });
  };
  return new Promise((resolve, reject) => {
    socket.once("secureConnect", () => {
      resolve({
        command: async (line: string) => {
          socket.write(`${line}\r\n`);
          return nextReply();
        },
        write: (chunk: string) => {
          socket.write(chunk);
        },
        finish: () => nextReply(),
        close: () => socket.end(),
      });
    });
    socket.once("error", reject);
  });
}

function expectCode(reply: string, code: string): void {
  if (!reply.startsWith(code)) throw new Error(reply.slice(0, 180));
}

export async function sendSmtp(subject: string, text: string): Promise<{ ok: true; to: string } | { ok: false; error: string }> {
  const config = smtpConfig();
  const to = ownerEmail();
  if (!config) return { ok: false, error: "smtp_not_configured" };
  const message = [
    `From: ${config.user}`,
    `To: ${to}`,
    `Subject: ${encodeSubject(subject)}`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
    "",
    dotStuff(text),
    ".",
    "",
  ].join("\r\n");
  let mail: Awaited<ReturnType<typeof openMail>> | undefined;
  try {
    mail = await openMail(config.host);
    expectCode(await mail.finish(), "220");
    expectCode(await mail.command("EHLO tz-agent.local"), "250");
    expectCode(await mail.command("AUTH LOGIN"), "334");
    expectCode(await mail.command(Buffer.from(config.user).toString("base64")), "334");
    expectCode(await mail.command(Buffer.from(config.pass).toString("base64")), "235");
    expectCode(await mail.command(`MAIL FROM:<${config.user}>`), "250");
    expectCode(await mail.command(`RCPT TO:<${to}>`), "250");
    expectCode(await mail.command("DATA"), "354");
    mail.write(message);
    expectCode(await mail.finish(), "250");
    mail.close();
    return { ok: true, to };
  } catch (error) {
    mail?.close();
    const messageText = error instanceof Error ? error.message : String(error);
    return { ok: false, error: scrubSecrets(messageText).slice(0, 300) };
  }
}

type MailIndex = { ids: string[] };

function mailIndex(value: unknown): MailIndex {
  if (!value || typeof value !== "object" || !Array.isArray((value as MailIndex).ids)) return { ids: [] };
  return { ids: (value as MailIndex).ids.filter((id) => typeof id === "string") };
}

function isMailJob(value: unknown): value is MailJob {
  if (!value || typeof value !== "object") return false;
  const job = value as Partial<MailJob>;
  return typeof job.id === "string" && typeof job.chatId === "string" && typeof job.bodyPath === "string";
}

export async function enqueueMail(host: ArchiveHost, job: MailJob, body: string): Promise<void> {
  await host.files.write(job.bodyPath, body, chatScope(job.chatId));
  await host.kv.put(`mail-job:${job.id}`, asJson(job));
  await mutateJson(host.kv, "mail-index", { ids: [] as string[] }, (current) => {
    const index = mailIndex(current);
    if (index.ids.includes(job.id)) return index;
    return { ids: [...index.ids, job.id].slice(-200) };
  });
}

export async function flushPendingMail(host: ArchiveHost): Promise<{ sent: number; waiting: number }> {
  const index = mailIndex(await host.kv.get("mail-index"));
  const kept: string[] = [];
  let sent = 0;
  for (const id of index.ids) {
    const stored = await host.kv.get(`mail-job:${id}`);
    if (!isMailJob(stored)) continue;
    const already = await host.kv.get(`mail-sent:${id}`);
    if (already) {
      await host.kv.delete(`mail-job:${id}`);
      continue;
    }
    const body = await readText(host, stored.chatId, stored.bodyPath);
    if (!body) {
      kept.push(id);
      continue;
    }
    const result = await sendSmtp(stored.subject, body);
    if (result.ok) {
      sent += 1;
      await host.kv.put(`mail-sent:${id}`, asJson({ at: new Date().toISOString(), to: result.to }));
      await host.kv.delete(`mail-job:${id}`);
      continue;
    }
    if (result.error === "smtp_not_configured") {
      kept.push(id);
      continue;
    }
    const attempts = stored.attempts + 1;
    if (attempts < 24) {
      await host.kv.put(`mail-job:${id}`, asJson({ ...stored, attempts, lastError: result.error }));
      kept.push(id);
    } else {
      await host.files.write(`mail-dead/${id}.txt`, body, chatScope(stored.chatId));
      await host.kv.delete(`mail-job:${id}`);
    }
  }
  await host.kv.put("mail-index", asJson({ ids: kept }));
  return { sent, waiting: kept.length };
}

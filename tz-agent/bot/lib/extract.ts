import { inflateRawSync } from "node:zlib";

export type Extracted = {
  kind: "text" | "docx" | "unsupported";
  text: string;
};

const TEXT_EXTENSIONS = new Set([
  "txt",
  "md",
  "csv",
  "json",
  "xml",
  "html",
  "htm",
  "log",
  "yml",
  "yaml",
  "tsv",
]);

function extensionOf(name: string): string {
  const base = name.split(/[/\\]/).pop() ?? "";
  const dot = base.lastIndexOf(".");
  return dot >= 0 ? base.slice(dot + 1).toLowerCase() : "";
}

function decodeXml(text: string): string {
  return text
    .replace(/<w:tab\/>/g, "\t")
    .replace(/<w:br\/>/g, "\n")
    .replace(/<\/w:p>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"")
    .replace(/&#(\d+);/g, (_, code: string) => String.fromCodePoint(Number(code)))
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function unzipEntry(zip: Buffer, wanted: string): Buffer | undefined {
  const min = Math.max(0, zip.length - 22 - 65535);
  let eocd = -1;
  for (let index = zip.length - 22; index >= min; index -= 1) {
    if (zip.readUInt32LE(index) === 0x06054b50) {
      eocd = index;
      break;
    }
  }
  if (eocd < 0) return undefined;
  let cursor = zip.readUInt32LE(eocd + 16);
  const count = zip.readUInt16LE(eocd + 10);
  for (let index = 0; index < count && cursor + 46 <= zip.length; index += 1) {
    if (zip.readUInt32LE(cursor) !== 0x02014b50) return undefined;
    const method = zip.readUInt16LE(cursor + 10);
    const compressedSize = zip.readUInt32LE(cursor + 20);
    const nameLength = zip.readUInt16LE(cursor + 28);
    const extraLength = zip.readUInt16LE(cursor + 30);
    const commentLength = zip.readUInt16LE(cursor + 32);
    const localOffset = zip.readUInt32LE(cursor + 42);
    const name = zip.slice(cursor + 46, cursor + 46 + nameLength).toString("utf8");
    cursor += 46 + nameLength + extraLength + commentLength;
    if (name !== wanted) continue;
    if (localOffset + 30 > zip.length || zip.readUInt32LE(localOffset) !== 0x04034b50) return undefined;
    const localName = zip.readUInt16LE(localOffset + 26);
    const localExtra = zip.readUInt16LE(localOffset + 28);
    const dataStart = localOffset + 30 + localName + localExtra;
    const data = zip.slice(dataStart, dataStart + compressedSize);
    if (method === 0) return data;
    if (method === 8) return inflateRawSync(data);
    return undefined;
  }
  return undefined;
}

function looksBinary(bytes: Buffer): boolean {
  const sample = bytes.subarray(0, 8000);
  for (const byte of sample) {
    if (byte === 0) return true;
  }
  return false;
}

export function extractText(filename: string, mime: string, bytes: Uint8Array): Extracted {
  const buffer = Buffer.from(bytes);
  const extension = extensionOf(filename);
  const normalizedMime = mime.toLowerCase();
  if (extension === "docx" || normalizedMime.includes("wordprocessingml")) {
    const xml = unzipEntry(buffer, "word/document.xml");
    if (!xml) return { kind: "unsupported", text: "" };
    return { kind: "docx", text: decodeXml(xml.toString("utf8")).slice(0, 100_000) };
  }
  const textual = TEXT_EXTENSIONS.has(extension)
    || normalizedMime.startsWith("text/")
    || normalizedMime.includes("json")
    || normalizedMime.includes("xml")
    || normalizedMime.includes("csv");
  if (!textual || looksBinary(buffer)) {
    return { kind: "unsupported", text: "" };
  }
  let text = buffer.toString("utf8").replace(/\u0000/g, "");
  if (extension === "html" || extension === "htm" || normalizedMime.includes("html")) {
    text = text.replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ");
  }
  return { kind: "text", text: text.replace(/[ \t]+\n/g, "\n").trim().slice(0, 100_000) };
}

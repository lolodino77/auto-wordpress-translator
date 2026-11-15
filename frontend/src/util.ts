import type { Article, ArticleStatus } from "./api";

export const STATUS_LABEL: Record<ArticleStatus, string> = {
  pending: "À traduire",
  queued: "Dans la file d'attente",
  running: "Traduction en cours…",
  done: "Brouillon créé",
  error: "Erreur",
};

export const ENGINE_LABEL: Record<string, string> = { gemini: "Gemini (Google)", gpt: "ChatGPT (OpenAI)" };

export const engineName = (e: string) => (ENGINE_LABEL[e] ?? e).replace(/ \(.*\)$/, "");

export const ROLE_LABEL: Record<string, string> = {
  contributor: "Contributeur",
  author: "Auteur",
  editor: "Éditeur",
  administrator: "Administrateur",
  subscriber: "Abonné",
  bbp_blocked: "Forum : bloqué",
  bbp_participant: "Forum : participant",
};

export function formatDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("fr-FR", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m} min ${String(s).padStart(2, "0")} s`;
}

export function sourceLabel(a: Pick<Article, "kind" | "source">): string {
  if (a.kind === "md") return "Fichier .md";
  try {
    return new URL(a.source).hostname.replace(/^www\./, "");
  } catch {
    return a.source;
  }
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n > 1 ? many : one}`;
}

export function splitTags(text: string): string[] {
  return text
    .split(/[,;\n]/)
    .map((t) => t.trim())
    .filter(Boolean);
}

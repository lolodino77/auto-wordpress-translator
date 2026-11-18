import type { Article, ArticleStatus, ResultSummary } from "./api";

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

/** États qui prouvent que le brouillon existe encore dans WordPress. */
export const EXISTS_IN_WP = new Set(["draft", "pending", "future", "private", "publish"]);

/** Brouillon mis à la corbeille ou supprimé dans WordPress. */
export const isGone = (r: Pick<ResultSummary, "mode" | "wp_status">) =>
  r.mode === "brouillon" && (r.wp_status === "trash" || r.wp_status === "missing");

/** Libellés de l'état d'une traduction : court (après le titre, comme « — Brouillon ») et long (colonne Date). */
export function resultState(r: Pick<ResultSummary, "mode" | "wp_status">): { short: string; long: string } {
  if (r.mode === "apercu") return { short: "Essai", long: "Essai (pas dans WordPress)" };
  switch (r.wp_status) {
    case "trash":
      return { short: "Dans la corbeille de WordPress", long: "Mis à la corbeille" };
    case "missing":
      return { short: "Supprimé de WordPress", long: "Supprimé de WordPress" };
    case "publish":
      return { short: "Publié", long: "Publié" };
    case "pending":
      return { short: "En attente de relecture", long: "En attente de relecture" };
    case "future":
      return { short: "Planifié", long: "Planifié" };
    case "private":
      return { short: "Privé", long: "Privé" };
    case "draft":
      return { short: "Brouillon", long: "Brouillon créé" };
    default: // pas (encore) vérifié auprès du site : on ne prétend pas que le brouillon existe
      return { short: "État non vérifié", long: "État non vérifié dans WordPress" };
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

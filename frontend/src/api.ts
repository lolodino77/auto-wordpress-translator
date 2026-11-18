// Accès au serveur local (python -m webapp). Toute requête qui modifie quelque chose porte l'en-tête X-AWT
// exigé par le serveur (protection contre les requêtes envoyées par d'autres sites ouverts dans le navigateur).

export type ArticleStatus = "pending" | "queued" | "running" | "done" | "error";

export interface Article {
  key: string;
  kind: "url" | "md";
  source: string;
  title: string;
  title_fr: string | null;
  tags: string[];
  illustration: string;
  status: ArticleStatus;
  error: string;
  /** Explication affichée sous le titre (ex. ancien brouillon mis à la corbeille dans WordPress). */
  note: string;
  draft_url: string;
  result_id: string | null;
  preview_id: string | null;
}

export interface Status {
  site: string;
  mode: "selfhosted" | "wpcom";
  engines: string[];
  account_configured: boolean;
  templates: { ok: boolean; count: number; error?: string };
  specs: number;
  counts: Record<"pending" | "done" | "error" | "running" | "queued", number>;
  total: number;
  running: boolean;
  /** Le code a changé depuis le lancement (absent : ancienne version du programme) : il faut le relancer. */
  restart_needed?: boolean;
  /** Version de l'interface construite : quand elle change, la page se recharge. */
  ui_version?: string;
  /** Dernière erreur en vérifiant l'état des brouillons dans WordPress ("" si tout va bien). */
  drafts_check_error?: string;
}

export interface RunItem {
  key: string;
  label: string;
  status: "waiting" | "running" | "done" | "error" | "skipped";
  step: "" | "load" | "translate" | "publish" | "done";
  draft_url: string;
  error: string;
  seconds: number;
}

export interface Run {
  id: string;
  mode: "brouillon" | "apercu";
  status: "running" | "done" | "stopped" | "error";
  message: string;
  stop_requested: boolean;
  seconds: number;
  total: number;
  done: number;
  errors: number;
  skipped: number;
  items: RunItem[];
  logs: string[];
}

export interface ResultSummary {
  id: string;
  key: string;
  mode: "brouillon" | "apercu";
  date: string;
  title: string;
  source_title: string;
  source_url: string;
  slug: string;
  draft_url: string;
  engine: string;
  warnings: number;
  /** État du brouillon dans WordPress : draft, publish, trash, missing… (null : essai, ou pas encore vérifié). */
  wp_status: string | null;
}

export interface Result extends Omit<ResultSummary, "warnings"> {
  author: string;
  tags: string[];
  category: string | null;
  html: string;
  warnings: string[];
  fixes: string[];
  to_check: string[];
  manual: string[];
}

export interface Settings {
  site: string;
  mode: "selfhosted" | "wpcom";
  engines: string[];
  max_words?: number;
}

export interface Account {
  mode?: string;
  configured: boolean;
  connected?: boolean | null;
  error?: string;
  username?: string;
  name?: string;
  roles?: string[];
  can_create?: boolean;
  can_publish?: boolean;
  can_edit_others?: boolean;
  can_delete_others?: boolean;
}

export interface AddUrlsResult {
  added: string[];
  duplicates: string[];
  invalid: string[];
  /** Adresses ajoutées qui ont déjà un brouillon (traduites autrefois) : elles ne sont donc pas « à traduire ». */
  already_done: { url: string; draft_url: string }[];
}

export class ApiError extends Error {
  offline: boolean;
  constructor(message: string, offline = false) {
    super(message);
    this.offline = offline;
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined;
  if (method !== "GET") headers["X-AWT"] = "1";
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let r: Response;
  try {
    r = await fetch("/api" + path, { method, headers, body: payload });
  } catch {
    throw new ApiError(
      "Le programme de traduction ne répond pas. Il a peut-être été fermé : relancez-le (double-clic sur « Lancer le traducteur »).",
      true,
    );
  }
  let data: unknown = null;
  try {
    data = await r.json();
  } catch {
    /* réponse vide */
  }
  if (!r.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(typeof detail === "string" ? detail : `Erreur inattendue (code ${r.status}).`);
  }
  return data as T;
}

export const api = {
  status: () => call<Status>("GET", "/status"),
  articles: () => call<Article[]>("GET", "/articles"),
  addUrls: (urls: string[], tags: string[], illustration: string) =>
    call<AddUrlsResult>("POST", "/articles/urls", { urls, tags, illustration }),
  addFiles: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    return call<{ added: string[]; errors: string[] }>("POST", "/articles/files", fd);
  },
  editArticle: (key: string, tags: string[] | null, illustration: string | null) =>
    call<{ ok: boolean }>("PATCH", "/articles", { key, tags, illustration }),
  deleteArticle: (key: string) => call<{ ok: boolean; message: string }>("POST", "/articles/delete", { key }),
  startRun: (opts: { keys?: string[]; mode: "brouillon" | "apercu"; force?: boolean }) =>
    call<Run>("POST", "/runs", { keys: opts.keys ?? [], mode: opts.mode, force: !!opts.force }),
  currentRun: () => call<Run | null>("GET", "/runs/current"),
  stopRun: () => call<{ ok: boolean }>("POST", "/runs/stop"),
  results: () => call<ResultSummary[]>("GET", "/results"),
  result: (id: string) => call<Result>("GET", `/results/${encodeURIComponent(id)}`),
  archiveResult: (id: string) => call<{ ok: boolean; message: string }>("POST", "/results/delete", { key: id }),
  settings: () => call<Settings>("GET", "/settings"),
  saveSettings: (s: Partial<Settings>) => call<Settings>("PUT", "/settings", s),
  account: () => call<Account>("GET", "/account"),
  logout: () => call<{ ok: boolean }>("POST", "/account/logout"),
  saveAccount: (username: string, app_password: string) => call<Account>("POST", "/account", { username, app_password }),
};

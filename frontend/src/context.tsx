import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError, type Account, type Run, type Status } from "./api";
import { plural } from "./util";

export type NoticeKind = "success" | "error" | "warning" | "info";
export interface Notice {
  id: number;
  kind: NoticeKind;
  text: ReactNode;
  at: number;
}

export interface ConfirmOptions {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
}

interface AppState {
  status: Status | null;
  run: Run | null;
  account: Account | null;
  offline: boolean;
  /** Augmente à chaque changement de données (ajout, fin de traduction…) : les pages relisent alors leur liste. */
  version: number;
  notices: Notice[];
  notify: (kind: NoticeKind, text: ReactNode) => void;
  dismiss: (id: number) => void;
  clearOldNotices: () => void;
  refresh: () => void;
  refreshAccount: () => void;
  startRun: (opts: { keys?: string[]; mode: "brouillon" | "apercu"; force?: boolean }) => Promise<boolean>;
  stopRun: () => Promise<void>;
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
}

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp hors de AppProvider");
  return v;
}

export function errorText(e: unknown): ReactNode {
  const msg = e instanceof Error ? e.message : String(e);
  if (/Réglages/.test(msg)) {
    return (
      <>
        {msg} <Link to="/reglages">Ouvrir les réglages</Link>
      </>
    );
  }
  return msg;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [offline, setOffline] = useState(false);
  const [version, setVersion] = useState(0);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null);
  const nextId = useRef(1);
  const wasRunning = useRef(false);
  const runFetched = useRef(false);
  const timer = useRef<number>();

  const notify = useCallback((kind: NoticeKind, text: ReactNode) => {
    const id = nextId.current++;
    setNotices((n) => [...n.filter((x) => x.kind !== kind || x.text !== text), { id, kind, text, at: Date.now() }]);
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (kind === "success") window.setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), 8000);
  }, []);
  const dismiss = useCallback((id: number) => setNotices((n) => n.filter((x) => x.id !== id)), []);
  const clearOldNotices = useCallback(() => setNotices((n) => n.filter((x) => Date.now() - x.at < 1500)), []);

  const poll = useCallback(async () => {
    window.clearTimeout(timer.current);
    let running = false;
    try {
      const st = await api.status();
      setStatus(st);
      setOffline(false);
      running = st.running;
      if (st.running || wasRunning.current || !runFetched.current) {
        const r = await api.currentRun();
        runFetched.current = true;
        setRun(r);
        if (wasRunning.current && !st.running && r) {
          setVersion((v) => v + 1);
          const parts = [];
          if (r.done) parts.push(plural(r.done, r.mode === "apercu" ? "article traduit" : "brouillon créé", r.mode === "apercu" ? "articles traduits" : "brouillons créés"));
          if (r.errors) parts.push(plural(r.errors, "erreur", "erreurs"));
          const kind = r.status === "error" || (r.errors && !r.done) ? "error" : r.errors ? "warning" : "success";
          const head = r.status === "stopped" ? "Traduction arrêtée" : r.status === "error" ? "La traduction s'est interrompue" : "Traduction terminée";
          notify(kind, (
            <>
              <strong>{head}</strong>
              {parts.length ? ` : ${parts.join(", ")}.` : "."} <Link to="/resultats">Voir les traductions</Link>
            </>
          ));
        }
      }
      wasRunning.current = st.running;
    } catch (e) {
      if (e instanceof ApiError && e.offline) setOffline(true);
    }
    timer.current = window.setTimeout(poll, running ? 1500 : 5000);
  }, [notify]);

  useEffect(() => {
    poll();
    return () => window.clearTimeout(timer.current);
  }, [poll]);

  const refreshAccount = useCallback(() => {
    api.account().then(setAccount).catch(() => setAccount(null));
  }, []);
  useEffect(refreshAccount, [refreshAccount]);

  const refresh = useCallback(() => {
    setVersion((v) => v + 1);
    poll();
  }, [poll]);

  const startRun = useCallback(
    async (opts: { keys?: string[]; mode: "brouillon" | "apercu"; force?: boolean }) => {
      try {
        const r = await api.startRun(opts);
        setRun(r);
        wasRunning.current = true;
        setStatus((s) => (s ? { ...s, running: true } : s));
        setVersion((v) => v + 1);
        navigate("/traduction");
        window.setTimeout(poll, 800);
        return true;
      } catch (e) {
        notify("error", errorText(e));
        return false;
      }
    },
    [navigate, notify, poll],
  );

  const stopRun = useCallback(async () => {
    try {
      await api.stopRun();
      setRun((r) => (r ? { ...r, stop_requested: true } : r));
    } catch (e) {
      notify("error", errorText(e));
    }
  }, [notify]);

  const confirm = useCallback(
    (opts: ConfirmOptions) => new Promise<boolean>((resolve) => setPendingConfirm({ ...opts, resolve })),
    [],
  );

  const close = (ok: boolean) => {
    pendingConfirm?.resolve(ok);
    setPendingConfirm(null);
  };

  return (
    <Ctx.Provider
      value={{ status, run, account, offline, version, notices, notify, dismiss, clearOldNotices, refresh, refreshAccount, startRun, stopRun, confirm }}
    >
      {children}
      {pendingConfirm && (
        <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && close(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" onKeyDown={(e) => e.key === "Escape" && close(false)}>
            <h1 id="modal-title">{pendingConfirm.title}</h1>
            <div>{pendingConfirm.body}</div>
            <div className="button-row">
              <button className="button" onClick={() => close(false)}>
                {pendingConfirm.cancelLabel ?? "Annuler"}
              </button>
              <button
                className={"button " + (pendingConfirm.danger ? "button-primary button-danger-primary" : "button-primary")}
                onClick={() => close(true)}
                autoFocus
              >
                {pendingConfirm.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}

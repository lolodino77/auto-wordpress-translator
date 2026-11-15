import { useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Clock, Info, Loader2, X, XCircle, type LucideIcon } from "lucide-react";
import type { ArticleStatus } from "./api";
import { useApp } from "./context";
import { STATUS_LABEL, splitTags } from "./util";

export function Notices() {
  const { notices, dismiss } = useApp();
  return (
    <>
      {notices.map((n) => (
        <div key={n.id} className={`notice notice-${n.kind}`} role={n.kind === "error" ? "alert" : "status"}>
          <p>{n.text}</p>
          <button className="notice-dismiss" onClick={() => dismiss(n.id)} aria-label="Masquer ce message">
            <X size={16} />
          </button>
        </div>
      ))}
    </>
  );
}

const BADGE_ICON: Record<ArticleStatus, LucideIcon> = {
  pending: Clock,
  queued: Clock,
  running: Loader2,
  done: CheckCircle2,
  error: XCircle,
};

export function StatusBadge({ status }: { status: ArticleStatus }) {
  const Icon = BADGE_ICON[status];
  return (
    <span className={`badge badge-${status}`}>
      <Icon className={status === "running" ? "spin" : undefined} />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Postbox(props: { title: ReactNode; icon?: LucideIcon; actions?: ReactNode; children: ReactNode; className?: string }) {
  const Icon = props.icon;
  return (
    <div className={"postbox " + (props.className ?? "")}>
      <div className="postbox-header">
        <h2>
          {Icon && <Icon />}
          {props.title}
        </h2>
        {props.actions && <div className="postbox-actions">{props.actions}</div>}
      </div>
      <div className="inside">{props.children}</div>
    </div>
  );
}

type Kind = "ok" | "bad" | "warn" | "info";
const INLINE_ICON: Record<Kind, LucideIcon> = { ok: CheckCircle2, bad: XCircle, warn: AlertTriangle, info: Info };

export function InlineNotice({ kind, children }: { kind: Kind; children: ReactNode }) {
  const Icon = INLINE_ICON[kind];
  return (
    <div className={`inline-notice ${kind}`}>
      <Icon />
      <div>{children}</div>
    </div>
  );
}

/** Champ d'étiquettes comme la boîte « Étiquettes » de l'éditeur classique : on tape, « Ajouter », on retire avec ⓧ. */
export function TagEditor({ tags, onChange, id }: { tags: string[]; onChange: (t: string[]) => void; id?: string }) {
  const [text, setText] = useState("");
  const add = () => {
    const extra = splitTags(text).filter((t) => !tags.includes(t));
    if (extra.length) onChange([...tags, ...extra]);
    setText("");
  };
  return (
    <div>
      <div className="tag-input">
        <input
          id={id}
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          onBlur={() => text.trim() && add()}
          autoComplete="off"
        />
        <button type="button" className="button" onClick={add}>
          Ajouter
        </button>
      </div>
      <p className="description">Séparez les étiquettes par des virgules.</p>
      {tags.length > 0 && (
        <ul className="tagchecklist">
          {tags.map((t) => (
            <li key={t}>
              <button type="button" onClick={() => onChange(tags.filter((x) => x !== t))} aria-label={`Retirer l'étiquette ${t}`}>
                <XCircle />
              </button>
              {t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

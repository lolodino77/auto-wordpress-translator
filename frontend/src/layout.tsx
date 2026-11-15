import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  CheckSquare,
  ExternalLink,
  FileText,
  Gauge,
  HelpCircle,
  Home,
  Languages,
  Loader2,
  Menu,
  Plus,
  Settings,
  Sparkles,
} from "lucide-react";
import { useApp } from "./context";
import { Notices } from "./components";

function siteUrl(site: string) {
  return /^https?:\/\//.test(site) ? site : `https://${site}`;
}

export function AdminBar({ onMenu }: { onMenu: () => void }) {
  const { status, account } = useApp();
  const name = account?.name || account?.username;
  return (
    <div id="adminbar">
      <button className="ab-menu-toggle" onClick={onMenu} aria-label="Afficher le menu">
        <Menu size={20} />
      </button>
      <Link to="/" className="ab-logo" title="Tableau de bord">
        <Languages size={20} />
        <span className="ab-hide-mobile">Traducteur</span>
      </Link>
      {status && (
        <a href={siteUrl(status.site)} target="_blank" rel="noreferrer" className="ab-site" title="Ouvrir le site dans un nouvel onglet">
          <Home size={16} />
          <span>{status.site}</span>
          <ExternalLink size={12} className="ab-hide-mobile" />
        </a>
      )}
      <Link to="/ajouter" className="ab-hide-mobile">
        <Plus size={18} /> Ajouter
      </Link>
      {status?.running && (
        <Link to="/traduction" className="ab-running">
          <Loader2 size={16} className="spin" /> <span className="ab-hide-mobile">Traduction en cours…</span>
        </Link>
      )}
      <div className="ab-right">
        {name && (
          <Link to="/reglages" title="Compte WordPress utilisé">
            <span className="ab-hide-mobile">Connecté en tant que {name}</span>
            <span className="ab-avatar">{name.slice(0, 1).toUpperCase()}</span>
          </Link>
        )}
      </div>
    </div>
  );
}

function MenuItem(props: { to: string; icon: typeof Gauge; label: string; extra?: ReactNode; current: boolean; children?: ReactNode }) {
  const Icon = props.icon;
  return (
    <li className={"menu-top" + (props.current ? " current" : "")}>
      <Link to={props.to} aria-current={props.current ? "page" : undefined}>
        <Icon />
        <span>{props.label}</span>
        {props.extra}
      </Link>
      {props.current && props.children}
    </li>
  );
}

export function AdminMenu() {
  const { pathname } = useLocation();
  const { status } = useApp();
  const pending = status ? status.counts.pending + status.counts.error : 0;
  const inArticles = pathname.startsWith("/articles") || pathname.startsWith("/ajouter");
  return (
    <nav id="adminmenu" aria-label="Menu principal">
      <ul>
        <MenuItem to="/" icon={Gauge} label="Tableau de bord" current={pathname === "/"} />
        <li className="menu-sep" aria-hidden />
        <MenuItem
          to="/articles"
          icon={FileText}
          label="Articles à traduire"
          current={inArticles}
          extra={pending > 0 ? <span className="count-bubble" title={`${pending} à traduire`}>{pending}</span> : undefined}
        >
          <ul className="submenu">
            <li>
              <NavLink to="/articles" end className={({ isActive }) => (isActive ? "current" : "")}>
                Tous les articles
              </NavLink>
            </li>
            <li>
              <NavLink to="/ajouter" className={({ isActive }) => (isActive ? "current" : "")}>
                Ajouter
              </NavLink>
            </li>
          </ul>
        </MenuItem>
        <MenuItem
          to="/traduction"
          icon={Sparkles}
          label="Traduction"
          current={pathname.startsWith("/traduction")}
          extra={status?.running ? <span className="live-dot" title="Traduction en cours" /> : undefined}
        />
        <MenuItem to="/resultats" icon={CheckSquare} label="Traductions faites" current={pathname.startsWith("/resultats")} />
        <li className="menu-sep" aria-hidden />
        <MenuItem to="/reglages" icon={Settings} label="Réglages" current={pathname.startsWith("/reglages")} />
        <MenuItem to="/aide" icon={HelpCircle} label="Aide" current={pathname.startsWith("/aide")} />
      </ul>
    </nav>
  );
}

export function AdminLayout() {
  const { pathname } = useLocation();
  const { offline, clearOldNotices } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
    clearOldNotices();
    window.scrollTo(0, 0);
  }, [pathname, clearOldNotices]);

  useEffect(() => {
    document.body.classList.toggle("menu-open", menuOpen);
  }, [menuOpen]);

  return (
    <>
      <AdminBar onMenu={() => setMenuOpen((o) => !o)} />
      <AdminMenu />
      {offline && (
        <div className="offline-banner" role="alert">
          Le programme de traduction ne répond plus. Relancez-le (double-clic sur « Lancer le traducteur »), puis rechargez cette page.
        </div>
      )}
      <main id="content" onClick={() => menuOpen && setMenuOpen(false)}>
        <div className="wrap">
          <Notices />
          <Outlet />
        </div>
      </main>
    </>
  );
}

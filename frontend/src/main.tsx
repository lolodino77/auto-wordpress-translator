import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import "./wp.css";
import { AppProvider } from "./context";
import { AdminLayout } from "./layout";
import Dashboard from "./pages/Dashboard";
import Articles from "./pages/Articles";
import Running from "./pages/Running";
import Results from "./pages/Results";
import SettingsPage from "./pages/Settings";
import Help from "./pages/Help";
import AddArticles from "./pages/AddArticles";
import Login from "./pages/Login";
import Closed from "./pages/Closed";
import LoginGate from "./pages/LoginGate";
import type { LoginProvider } from "./api";
import { useApp } from "./context";
import type { ReactNode } from "react";

/** Les rappels de connexion (Gemini, puis ChatGPT) ne sont montrés qu'une fois par ouverture du programme (l'onglet) :
 *  un rechargement de page ne les repose pas. */
const LOGIN_ORDER: LoginProvider[] = ["gemini", "chatgpt"];
const seenKey = (p: LoginProvider) => `${p}_gate_seen`;
function seen(p: LoginProvider): boolean {
  try {
    return sessionStorage.getItem(seenKey(p)) === "1";
  } catch {
    return false;
  }
}

/** Portail : tant que le compte WordPress n'est pas connecté et vérifié, seule la page de connexion est accessible.
 *  Ensuite, rappel (facultatif) de se connecter à Gemini puis à ChatGPT à chaque ouverture du programme. */
function Gate({ children }: { children: ReactNode }) {
  const { account, accountReady, closed } = useApp();
  const [done, setDone] = useState<Record<string, boolean>>(() => Object.fromEntries(LOGIN_ORDER.map((p) => [p, seen(p)])));
  if (closed) return <Closed />;
  if (!accountReady) return <div className="login-splash" aria-busy="true" />;
  if (!account?.connected) return <Login />;
  const pending = LOGIN_ORDER.find((p) => !done[p]);
  if (pending) {
    return (
      <LoginGate
        key={pending}
        provider={pending}
        onDone={() => {
          try {
            sessionStorage.setItem(seenKey(pending), "1");
          } catch {
            /* stockage indisponible : le rappel reviendra au prochain chargement */
          }
          setDone((d) => ({ ...d, [pending]: true }));
        }}
      />
    );
  }
  return <>{children}</>;
}

function NotFound() {
  return (
    <>
      <h1 className="page-title">Page introuvable</h1>
      <p>
        <Link to="/">Retour au tableau de bord</Link>
      </p>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AppProvider>
        <Gate>
        <Routes>
          <Route element={<AdminLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="articles" element={<Articles />} />
            <Route path="traduction" element={<Running />} />
            <Route path="resultats" element={<Results />} />
            <Route path="reglages" element={<SettingsPage />} />
            <Route path="ajouter" element={<AddArticles />} />
            <Route path="aide" element={<Help />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
        </Gate>
      </AppProvider>
    </BrowserRouter>
  </StrictMode>,
);

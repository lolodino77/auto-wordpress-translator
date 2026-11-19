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
import GeminiGate from "./pages/GeminiGate";
import { useApp } from "./context";
import type { ReactNode } from "react";

/** Le rappel Gemini n'est montré qu'une fois par ouverture du programme (l'onglet) : un rechargement de page ne le repose pas. */
const GEMINI_SEEN = "gemini_gate_seen";
function geminiSeen(): boolean {
  try {
    return sessionStorage.getItem(GEMINI_SEEN) === "1";
  } catch {
    return false;
  }
}

/** Portail : tant que le compte WordPress n'est pas connecté et vérifié, seule la page de connexion est accessible.
 *  Ensuite, rappel (facultatif) de se connecter à Gemini à chaque ouverture du programme. */
function Gate({ children }: { children: ReactNode }) {
  const { account, accountReady, closed } = useApp();
  const [geminiDone, setGeminiDone] = useState(geminiSeen);
  if (closed) return <Closed />;
  if (!accountReady) return <div className="login-splash" aria-busy="true" />;
  if (!account?.connected) return <Login />;
  if (!geminiDone) {
    return (
      <GeminiGate
        onDone={() => {
          try {
            sessionStorage.setItem(GEMINI_SEEN, "1");
          } catch {
            /* stockage indisponible : le rappel reviendra au prochain chargement */
          }
          setGeminiDone(true);
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

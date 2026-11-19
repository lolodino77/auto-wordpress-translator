import { StrictMode } from "react";
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
import { useApp } from "./context";
import type { ReactNode } from "react";

/** Portail : tant que le compte WordPress n'est pas connecté et vérifié, seule la page de connexion est accessible. */
function Gate({ children }: { children: ReactNode }) {
  const { account, accountReady, closed } = useApp();
  if (closed) return <Closed />;
  if (!accountReady) return <div className="login-splash" aria-busy="true" />;
  if (!account?.connected) return <Login />;
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

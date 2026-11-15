import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import "./wp.css";
import { AppProvider } from "./context";
import { AdminLayout } from "./layout";
import Dashboard from "./pages/Dashboard";
import Articles from "./pages/Articles";
import AddArticles from "./pages/AddArticles";
import Running from "./pages/Running";
import Results from "./pages/Results";
import Editor from "./pages/Editor";
import SettingsPage from "./pages/Settings";
import Help from "./pages/Help";

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
        <Routes>
          <Route path="/resultats/:id" element={<Editor />} />
          <Route element={<AdminLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="articles" element={<Articles />} />
            <Route path="ajouter" element={<AddArticles />} />
            <Route path="traduction" element={<Running />} />
            <Route path="resultats" element={<Results />} />
            <Route path="reglages" element={<SettingsPage />} />
            <Route path="aide" element={<Help />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  </StrictMode>,
);

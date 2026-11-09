import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import "./index.css";
import Shell from "./components/Shell";
import { Spinner } from "./components/ui";
import { MetaProvider } from "./lib/meta";
import { PrefsProvider } from "./lib/prefs";
import Train from "./pages/Train";

// Train is the screen used most, so it ships in the main bundle; the others load on first visit.
const Home = lazy(() => import("./pages/Home"));
const Games = lazy(() => import("./pages/Games"));
const Analysis = lazy(() => import("./pages/Analysis"));
const Openings = lazy(() => import("./pages/Openings"));
const Endgames = lazy(() => import("./pages/Endgames"));
const Plan = lazy(() => import("./pages/Plan"));
const Diagnosis = lazy(() => import("./pages/Diagnosis"));
const Guide = lazy(() => import("./pages/Guide"));
const Settings = lazy(() => import("./pages/Settings"));

function NotFound() {
  return (
    <div className="max-w-prose">
      <h1>Página não encontrada</h1>
      <p className="mt-2 text-muted">Este endereço não existe no AURA.</p>
      <Link className="btn-primary mt-4" to="/">Ir para o início</Link>
    </div>
  );
}

class Boundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="max-w-prose">
        <h1>Esta tela travou</h1>
        <p className="mt-2 text-muted">Algo deu errado ao mostrar esta tela. O seu progresso está salvo.</p>
        <p className="mt-2 break-words text-sm text-faint">{String(this.state.error.message || this.state.error)}</p>
        <button className="btn-primary mt-4" onClick={() => window.location.reload()}>Recarregar</button>
      </div>
    );
  }
}

function App() {
  return (
    <PrefsProvider>
      <MetaProvider>
        <Shell>
          <Pages />
        </Shell>
      </MetaProvider>
    </PrefsProvider>
  );
}

/** A crash in one screen stays in that screen: going to another one renders it fresh. */
function Pages() {
  const loc = useLocation();
  return (
    <Boundary key={loc.pathname}>
      <Suspense fallback={<Spinner label="Carregando…" />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/treinar" element={<Train />} />
          <Route path="/partidas" element={<Games />} />
          <Route path="/partidas/:id" element={<Games />} />
          <Route path="/analise" element={<Analysis />} />
          <Route path="/aberturas" element={<Openings />} />
          <Route path="/finais" element={<Endgames />} />
          <Route path="/plano" element={<Plan />} />
          <Route path="/diagnostico" element={<Diagnosis />} />
          <Route path="/guia" element={<Guide />} />
          <Route path="/configuracoes" element={<Settings />} />
          {/* 0.3.0 addresses */}
          <Route path="/train" element={<Navigate to="/treinar" replace />} />
          <Route path="/games" element={<Navigate to="/partidas" replace />} />
          <Route path="/analysis" element={<Navigate to="/analise" replace />} />
          <Route path="/openings" element={<Navigate to="/aberturas" replace />} />
          <Route path="/endgames" element={<Navigate to="/finais" replace />} />
          <Route path="/plan" element={<Navigate to="/plano" replace />} />
          <Route path="/cognitive" element={<Navigate to="/diagnostico" replace />} />
          <Route path="/setup" element={<Navigate to="/configuracoes" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </Boundary>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter><App /></BrowserRouter>
  </React.StrictMode>,
);

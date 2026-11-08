import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import "./index.css";
import { api } from "./lib/api";
import Analysis from "./pages/Analysis";
import Cognitive from "./pages/Cognitive";
import Dashboard from "./pages/Dashboard";
import Endgames from "./pages/Endgames";
import Games from "./pages/Games";
import Openings from "./pages/Openings";
import Plan from "./pages/Plan";
import Train from "./pages/Train";

const NAV = [
  ["/", "Dashboard"], ["/train", "Train"], ["/cognitive", "Cognitive"], ["/analysis", "Analysis"],
  ["/games", "Games"], ["/openings", "Openings"], ["/endgames", "Endgames"], ["/plan", "Plan"],
] as const;

function Shell() {
  const [health, setHealth] = useState<any>(null);
  const [puzzles, setPuzzles] = useState<number | null>(null);
  useEffect(() => {
    api.get("/api/health").then(setHealth).catch(() => setHealth({ ok: false }));
    api.get("/api/puzzles/stats").then((s) => setPuzzles(s.count)).catch(() => {});
  }, []);
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-ink-700 bg-ink-900 md:sticky md:top-0 md:h-screen md:w-52 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-4 py-3 md:block">
          <div className="font-semibold tracking-tight">Chess<span className="text-accent">Lab</span> 1800</div>
          <div className="text-xs text-ink-400 md:mt-1">
            <span className={health == null ? "text-ink-400" : health?.engine?.ok ? "text-good" : "text-bad"}>●</span>{" "}
            {health == null ? "checking engine…" : health?.engine?.ok ? health.engine.name : "engine offline"}
            {puzzles != null && <span className="ml-2 md:ml-0 md:block">{puzzles.toLocaleString()} puzzles</span>}
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `whitespace-nowrap rounded px-3 py-1.5 text-sm ${isActive ? "bg-ink-700 text-accent" : "text-ink-300 hover:bg-ink-800"}`}>{label}</NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">
        {health && !health.ok && <div className="card mb-4 text-bad">Backend not reachable. Start it with <code>uvicorn app.main:app</code> in backend/.</div>}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/train" element={<Train />} />
          <Route path="/cognitive" element={<Cognitive />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/games" element={<Games />} />
          <Route path="/openings" element={<Openings />} />
          <Route path="/endgames" element={<Endgames />} />
          <Route path="/plan" element={<Plan />} />
        </Routes>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter><Shell /></BrowserRouter>
  </React.StrictMode>,
);

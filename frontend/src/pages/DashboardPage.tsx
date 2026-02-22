import { useState, useEffect, useRef } from "react";
import type { User, BrokerSession, ExecutionBatch, WsMessage } from "../types";
import { brokerApi, systemApi, createWebSocket } from "../api/client";
import BrokerConnectPanel from "../components/BrokerConnectPanel";
import ExecutionPanel from "../components/ExecutionPanel";
import ResultsPanel from "../components/ResultsPanel";
import HistoryPanel from "../components/HistoryPanel";
import toast from "react-hot-toast";

interface Props {
  user: User;
  onLogout: () => void;
}

type Tab = "execute" | "history";

export default function DashboardPage({ user, onLogout }: Props) {
  const [tab, setTab] = useState<Tab>("execute");
  const [sessions, setSessions] = useState<BrokerSession[]>([]);
  const [activeBroker, setActiveBroker] = useState<string>("");
  const [wsMessages, setWsMessages] = useState<WsMessage[]>([]);
  const [lastBatch, setLastBatch] = useState<ExecutionBatch | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [paperTrading, setPaperTrading] = useState<boolean | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Load broker sessions on mount
  useEffect(() => {
    loadSessions();
    connectWebSocket();
    // Fetch live mode from backend
    systemApi.health().then((r) => setPaperTrading(r.data.paper_trading)).catch(() => {});
    return () => wsRef.current?.close();
  }, []);

  const loadSessions = async () => {
    try {
      const res = await brokerApi.sessions();
      const active = res.data.filter((s: BrokerSession) => s.is_active);
      setSessions(active);
      if (active.length > 0 && !activeBroker) {
        setActiveBroker(active[0].broker);
      }
    } catch {
      // silent
    }
  };

  const connectWebSocket = () => {
    const ws = createWebSocket(user.id);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected");
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        setWsMessages((prev) => [...prev.slice(-50), msg]);

        if (msg.type === "EXECUTION_COMPLETE") {
          setIsExecuting(false);
          toast.success("Execution complete! Check results below.");
        }
        if (msg.type === "ORDER_PROGRESS") {
          const d = msg.data as Record<string, unknown>;
          const symbol = d.symbol as string;
          const status = d.status as string;
          const progress = d.progress as { current: number; total: number };
          toast(`${symbol}: ${status} (${progress?.current}/${progress?.total})`, {
            icon: status === "FILLED" ? "✅" : status === "REJECTED" ? "❌" : "⏳",
            duration: 2000,
          });
        }
      } catch {}
    };

    ws.onerror = () => {
      console.warn("WebSocket error — reconnecting in 3s");
      setTimeout(connectWebSocket, 3000);
    };
  };

  const handleBrokerConnected = (session: BrokerSession) => {
    setSessions((prev) => {
      const filtered = prev.filter((s) => s.broker !== session.broker);
      return [...filtered, session];
    });
    setActiveBroker(session.broker);
  };

  const handleExecutionComplete = (batch: ExecutionBatch) => {
    setLastBatch(batch);
    setIsExecuting(false);
  };

  const handleExecutionStart = () => {
    setIsExecuting(true);
    setWsMessages([]);
  };

  const activeSessions = sessions.filter((s) => s.is_active);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* ── Top Nav ─────────────────────────────────────────────────────── */}
      <nav className="bg-slate-900 border-b border-slate-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <span className="font-bold text-lg">Kalpi Execution Engine</span>
            {paperTrading === true && (
              <span className="text-xs bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full border border-amber-500/30 font-semibold tracking-wide">
                ⚠ PAPER TRADING
              </span>
            )}
            {paperTrading === false && (
              <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full border border-green-500/30 font-semibold tracking-wide">
                ● LIVE
              </span>
            )}
          </div>

          <div className="flex items-center gap-4">
            {/* Connected brokers */}
            <div className="flex gap-2">
              {activeSessions.map((s) => (
                <span
                  key={s.broker}
                  className="text-xs bg-green-500/20 text-green-400 px-2 py-1 rounded-full border border-green-500/30"
                >
                  ● {s.broker}
                </span>
              ))}
            </div>
            <span className="text-slate-400 text-sm">{user.username}</span>
            <button
              onClick={onLogout}
              className="text-sm text-slate-400 hover:text-white transition"
            >
              Logout
            </button>
          </div>
        </div>
      </nav>

      {/* ── Tab Bar ─────────────────────────────────────────────────────── */}
      <div className="bg-slate-900 border-b border-slate-800 px-6">
        <div className="max-w-7xl mx-auto flex gap-6">
          {(["execute", "history"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`py-3 text-sm font-medium border-b-2 transition-all ${
                tab === t
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-slate-400 hover:text-white"
              }`}
            >
              {t === "execute" ? "🚀 Execute Portfolio" : "📋 Execution History"}
            </button>
          ))}
        </div>
      </div>

      {/* ── Main Content ─────────────────────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {tab === "execute" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left column: Broker + Upload */}
            <div className="lg:col-span-1 space-y-6">
              <BrokerConnectPanel
                sessions={activeSessions}
                activeBroker={activeBroker}
                onBrokerConnected={handleBrokerConnected}
                onBrokerSelect={setActiveBroker}
                onSessionsRefresh={loadSessions}
              />
            </div>

            {/* Right column: Portfolio + Execute + Results */}
            <div className="lg:col-span-2 space-y-6">
              <ExecutionPanel
                activeBroker={activeBroker}
                sessions={activeSessions}
                isExecuting={isExecuting}
                wsMessages={wsMessages}
                onExecutionStart={handleExecutionStart}
                onExecutionComplete={handleExecutionComplete}
              />

              {lastBatch && (
                <ResultsPanel batch={lastBatch} />
              )}
            </div>
          </div>
        )}

        {tab === "history" && (
          <HistoryPanel userId={user.id} />
        )}
      </main>
    </div>
  );
}


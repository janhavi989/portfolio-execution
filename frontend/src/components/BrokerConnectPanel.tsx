import { useState, useRef } from "react";
import toast from "react-hot-toast";
import { brokerApi } from "../api/client";
import type { BrokerSession, BrokerName } from "../types";
import { BROKER_DISPLAY } from "../types";
import BrokerFundsWidget from "./BrokerFundsWidget";
import BrokerCredentialsPanel from "./BrokerCredentialsPanel";

interface Props {
  sessions: BrokerSession[];
  activeBroker: string;
  onBrokerConnected: (session: BrokerSession) => void;
  onBrokerSelect: (broker: string) => void;
  onSessionsRefresh: () => void;
}

const BROKERS: { name: BrokerName; auth: string }[] = [
  { name: "zerodha", auth: "oauth" },
  { name: "fyers", auth: "oauth" },
  { name: "angelone", auth: "totp" },
  { name: "upstox", auth: "oauth" },
  { name: "groww", auth: "api_key" },
];

const BROKER_ICONS: Record<BrokerName, string> = {
  zerodha: "🔵",
  fyers: "🔴",
  angelone: "🟠",
  upstox: "🟣",
  groww: "🟢",
};

export default function BrokerConnectPanel({
  sessions,
  activeBroker,
  onBrokerConnected,
  onBrokerSelect,
  onSessionsRefresh,
}: Props) {
  const [selectedBroker, setSelectedBroker] = useState<BrokerName>("zerodha");
  const [form, setForm] = useState({
    api_key: "",
    api_secret: "",
    client_id: "",
    request_token: "",
    totp_secret: "",
    password: "",
  });
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);

  // Zerodha semi-auto token fetch state
  const [tokenFetchStatus, setTokenFetchStatus] = useState<
    "idle" | "opening" | "waiting" | "success" | "error"
  >("idle");
  const [tokenFetchMessage, setTokenFetchMessage] = useState("");
  const esRef = useRef<EventSource | null>(null);

  const isConnected = (broker: string) => sessions.some((s) => s.broker === broker && s.is_active);

  const handleFetchZerodhaToken = () => {
    if (!form.api_key) {
      toast.error("Enter your API Key first");
      return;
    }
    // Close any existing stream
    if (esRef.current) esRef.current.close();

    setTokenFetchStatus("opening");
    setTokenFetchMessage("Launching browser...");
    setForm((f) => ({ ...f, request_token: "" }));

    const es = brokerApi.fetchZerodhaToken(form.api_key);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as {
          status: string;
          message: string;
          request_token?: string;
        };

        setTokenFetchStatus(event.status as typeof tokenFetchStatus);
        setTokenFetchMessage(event.message);

        if (event.status === "success" && event.request_token) {
          setForm((f) => ({ ...f, request_token: event.request_token! }));
          toast.success("Request token captured automatically!");
          es.close();
        } else if (event.status === "error") {
          toast.error(event.message);
          es.close();
        } else if (event.status === "done") {
          es.close();
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setTokenFetchStatus("error");
      setTokenFetchMessage("Connection to server lost. Please try again.");
      es.close();
    };
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload: Record<string, string> = {
        broker: selectedBroker,
        api_key: form.api_key || `PAPER_KEY_${selectedBroker.toUpperCase()}`,
      };
      if (form.api_secret) payload.api_secret = form.api_secret;
      if (form.client_id) payload.client_id = form.client_id;
      if (form.request_token) payload.request_token = form.request_token;
      if (form.totp_secret) payload.totp_secret = form.totp_secret;
      if (form.password) payload.password = form.password;

      const res = await brokerApi.connect(payload);
      onBrokerConnected(res.data);
      onBrokerSelect(selectedBroker);
      toast.success(`Connected to ${BROKER_DISPLAY[selectedBroker]}!`);
      setShowForm(false);
      setForm({ api_key: "", api_secret: "", client_id: "", request_token: "", totp_secret: "", password: "" });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Connection failed";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnect = async (broker: string) => {
    try {
      await brokerApi.disconnect(broker);
      onSessionsRefresh();
      toast.success(`Disconnected from ${broker}`);
    } catch {
      toast.error("Failed to disconnect");
    }
  };

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-800">
        <h2 className="font-semibold text-white flex items-center gap-2">
          <span>🔗</span> Broker Connection
        </h2>
        <p className="text-xs text-slate-500 mt-1">Connect your broker to enable trading</p>
      </div>

      {/* Broker list */}
      <div className="p-4 space-y-2">
        {BROKERS.map(({ name }) => {
          const connected = isConnected(name);
          return (
            <div
              key={name}
              onClick={() => connected && onBrokerSelect(name)}
              className={`flex items-center justify-between p-3 rounded-xl border transition-all cursor-pointer ${
                activeBroker === name && connected
                  ? "border-indigo-500 bg-indigo-500/10"
                  : connected
                  ? "border-green-500/30 bg-green-500/5 hover:border-green-500/50"
                  : "border-slate-700 bg-slate-800/50"
              }`}
            >
              <div className="flex items-center gap-3">
                <span className="text-lg">{BROKER_ICONS[name]}</span>
                <div>
                  <p className="text-sm font-medium text-white">{BROKER_DISPLAY[name]}</p>
                  {connected && (
                    <p className="text-xs text-green-400">● Connected</p>
                  )}
                </div>
              </div>
              <div className="flex gap-2">
                {connected ? (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDisconnect(name); }}
                    className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded-lg border border-red-500/30 hover:border-red-400/50 transition"
                  >
                    Disconnect
                  </button>
                ) : (
                  <button
                    onClick={(e) => { e.stopPropagation(); setSelectedBroker(name); setShowForm(true); }}
                    className="text-xs text-indigo-400 hover:text-indigo-300 px-2 py-1 rounded-lg border border-indigo-500/30 hover:border-indigo-400/50 transition"
                  >
                    Connect
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Live Funds Widget — shown when a connected broker is selected */}
      <BrokerFundsWidget
        broker={activeBroker}
        isConnected={isConnected(activeBroker)}
      />

      {/* Saved Credentials Panel — collapsible, masked by default */}
      <BrokerCredentialsPanel
        broker={activeBroker}
        isConnected={isConnected(activeBroker)}
      />

      {/* Connection form */}
      {showForm && (
        <div className="border-t border-slate-800 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-white">
              Connect {BROKER_DISPLAY[selectedBroker]}
            </h3>
            <button onClick={() => setShowForm(false)} className="text-slate-500 hover:text-white">✕</button>
          </div>

          <div className="mb-3 p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <p className="text-xs text-amber-400">
              📝 Paper Trading Mode: Any API key will work for simulation.
            </p>
          </div>

          <form onSubmit={handleConnect} className="space-y-3">
            <input
              type="text"
              placeholder="API Key (or leave blank for paper trading)"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
            <input
              type="text"
              placeholder="API Secret (optional)"
              value={form.api_secret}
              onChange={(e) => setForm({ ...form, api_secret: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
            <input
              type="text"
              placeholder="Client ID (optional)"
              value={form.client_id}
              onChange={(e) => setForm({ ...form, client_id: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
            {/* Zerodha: semi-automated token fetch via Selenium */}
            {selectedBroker === "zerodha" && (
              <div className="space-y-2">
                {/* Auto-fetch button */}
                <button
                  type="button"
                  onClick={handleFetchZerodhaToken}
                  disabled={tokenFetchStatus === "opening" || tokenFetchStatus === "waiting"}
                  className="w-full flex items-center justify-center gap-2 bg-blue-600/20 hover:bg-blue-600/30 disabled:opacity-50 border border-blue-500/40 text-blue-300 text-sm font-medium py-2.5 rounded-lg transition"
                >
                  {tokenFetchStatus === "opening" || tokenFetchStatus === "waiting" ? (
                    <>
                      <span className="animate-spin">⟳</span>
                      {tokenFetchStatus === "opening" ? "Opening browser..." : "Waiting for login..."}
                    </>
                  ) : tokenFetchStatus === "success" ? (
                    <><span>✓</span> Token Captured — Click to Re-fetch</>
                  ) : (
                    <><span>🤖</span> Auto-Fetch Request Token (Opens Browser)</>
                  )}
                </button>

                {/* Status message */}
                {tokenFetchStatus !== "idle" && (
                  <div className={`rounded-lg px-3 py-2 text-xs flex items-start gap-2 ${
                    tokenFetchStatus === "success"
                      ? "bg-green-500/10 border border-green-500/30 text-green-400"
                      : tokenFetchStatus === "error"
                      ? "bg-red-500/10 border border-red-500/30 text-red-400"
                      : "bg-blue-500/10 border border-blue-500/30 text-blue-300"
                  }`}>
                    <span className="mt-0.5 shrink-0">
                      {tokenFetchStatus === "success" ? "✓" : tokenFetchStatus === "error" ? "⚠️" : "ℹ"}
                    </span>
                    <div>
                      <p>{tokenFetchMessage}</p>
                      {(tokenFetchStatus === "opening" || tokenFetchStatus === "waiting") && (
                        <p className="mt-1 text-blue-400/70">
                          A Chrome window will open. Type your Zerodha <strong>password</strong> and <strong>TOTP</strong> — we'll capture the token automatically.
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Captured token display (read-only) */}
                {form.request_token && (
                  <div className="relative">
                    <input
                      type="text"
                      readOnly
                      value={form.request_token}
                      className="w-full bg-green-500/5 border border-green-500/30 rounded-lg px-3 py-2 text-xs text-green-300 font-mono focus:outline-none cursor-default"
                    />
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-green-500">✓ captured</span>
                  </div>
                )}

                {/* Fallback: manual entry */}
                <details className="group">
                  <summary className="text-xs text-slate-500 hover:text-slate-400 cursor-pointer select-none">
                    ↳ Enter request token manually instead
                  </summary>
                  <input
                    type="text"
                    placeholder="Paste request_token from redirect URL"
                    value={form.request_token}
                    onChange={(e) => {
                      setForm({ ...form, request_token: e.target.value });
                      setTokenFetchStatus("idle");
                    }}
                    className="mt-2 w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </details>
              </div>
            )}

            {/* Fyers / Upstox: still manual (no Selenium flow for these yet) */}
            {["fyers", "upstox"].includes(selectedBroker) && (
              <input
                type="text"
                placeholder="Request Token / Auth Code (from OAuth redirect)"
                value={form.request_token}
                onChange={(e) => setForm({ ...form, request_token: e.target.value })}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            )}
            {selectedBroker === "angelone" && (
              <>
                <input
                  type="password"
                  placeholder="Password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
                <input
                  type="text"
                  placeholder="TOTP Secret"
                  value={form.totp_secret}
                  onChange={(e) => setForm({ ...form, totp_secret: e.target.value })}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium py-2 rounded-lg transition"
            >
              {loading ? "Connecting..." : `Connect ${BROKER_DISPLAY[selectedBroker]}`}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}


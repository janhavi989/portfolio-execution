import { useState } from "react";
import toast from "react-hot-toast";
import { executionApi } from "../api/client";
import type { BrokerSession, ExecutionBatch, TargetHolding, WsMessage } from "../types";

interface Props {
  activeBroker: string;
  sessions: BrokerSession[];
  isExecuting: boolean;
  wsMessages: WsMessage[];
  onExecutionStart: () => void;
  onExecutionComplete: (batch: ExecutionBatch) => void;
}

const SAMPLE_PORTFOLIO: TargetHolding[] = [
  { symbol: "RELIANCE", exchange: "NSE", quantity: 10 },
  { symbol: "TCS", exchange: "NSE", quantity: 5 },
  { symbol: "INFY", exchange: "NSE", quantity: 20 },
  { symbol: "HDFCBANK", exchange: "NSE", quantity: 15 },
  { symbol: "WIPRO", exchange: "NSE", quantity: 25 },
];

const SAMPLE_REBALANCE: TargetHolding[] = [
  { symbol: "RELIANCE", exchange: "NSE", quantity: 5, instruction: "REBALANCE_SELL" },
  { symbol: "SBIN", exchange: "NSE", quantity: 50, instruction: "BUY_NEW" },
  { symbol: "TCS", exchange: "NSE", quantity: 0, instruction: "SELL_EXIT" },
];

export default function ExecutionPanel({
  activeBroker,
  sessions,
  isExecuting,
  wsMessages,
  onExecutionStart,
  onExecutionComplete,
}: Props) {
  const [portfolioText, setPortfolioText] = useState(JSON.stringify(SAMPLE_PORTFOLIO, null, 2));
  const [executionType, setExecutionType] = useState<"AUTO" | "FIRST_TIME" | "REBALANCE">("AUTO");
  const [deltaPreview, setDeltaPreview] = useState<unknown[] | null>(null);
  const [validating, setValidating] = useState(false);

  const isConnected = sessions.some((s) => s.broker === activeBroker && s.is_active);

  const parsePortfolio = (): TargetHolding[] | null => {
    try {
      return JSON.parse(portfolioText);
    } catch {
      toast.error("Invalid JSON in portfolio");
      return null;
    }
  };

  const handleValidate = async () => {
    if (!activeBroker || !isConnected) {
      toast.error("Please connect a broker first");
      return;
    }
    const holdings = parsePortfolio();
    if (!holdings) return;

    setValidating(true);
    try {
      const res = await executionApi.validate({
        broker: activeBroker,
        portfolio: { holdings, execution_type: executionType },
      });
      setDeltaPreview(res.data);
      toast.success(`Preview: ${res.data.length} orders computed`);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Validation failed";
      toast.error(msg);
    } finally {
      setValidating(false);
    }
  };

  const handleExecute = async () => {
    if (!activeBroker || !isConnected) {
      toast.error("Please connect a broker first");
      return;
    }
    const holdings = parsePortfolio();
    if (!holdings) return;

    onExecutionStart();
    try {
      const res = await executionApi.execute({
        broker: activeBroker,
        portfolio: { holdings, execution_type: executionType },
      });
      onExecutionComplete(res.data);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Execution failed";
      toast.error(msg);
      onExecutionComplete({ status: "FAILED" } as ExecutionBatch);
    }
  };

  const progressMessages = wsMessages.filter((m) => m.type === "ORDER_PROGRESS");

  return (
    <div className="space-y-6">
      {/* Portfolio Input */}
      <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-white flex items-center gap-2">
              <span>📊</span> Target Portfolio
            </h2>
            <p className="text-xs text-slate-500 mt-1">Define your target holdings as JSON</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPortfolioText(JSON.stringify(SAMPLE_PORTFOLIO, null, 2))}
              className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded border border-slate-700 hover:border-slate-500 transition"
            >
              Load Sample
            </button>
            <button
              onClick={() => setPortfolioText(JSON.stringify(SAMPLE_REBALANCE, null, 2))}
              className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded border border-slate-700 hover:border-slate-500 transition"
            >
              Load Rebalance
            </button>
          </div>
        </div>

        <div className="p-4 space-y-4">
          {/* Execution type selector */}
          <div className="flex gap-2">
            {(["AUTO", "FIRST_TIME", "REBALANCE"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setExecutionType(t)}
                className={`flex-1 py-2 text-xs font-medium rounded-lg border transition-all ${
                  executionType === t
                    ? "bg-indigo-600 border-indigo-500 text-white"
                    : "bg-slate-800 border-slate-700 text-slate-400 hover:text-white"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* JSON editor */}
          <textarea
            value={portfolioText}
            onChange={(e) => setPortfolioText(e.target.value)}
            rows={12}
            className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm text-green-400 font-mono focus:outline-none focus:border-indigo-500 resize-none"
            placeholder='[{"symbol": "RELIANCE", "exchange": "NSE", "quantity": 10}]'
          />

          {/* Schema hint */}
          <div className="text-xs text-slate-500 bg-slate-800/50 rounded-lg p-3">
            <p className="font-medium text-slate-400 mb-1">Schema:</p>
            <code className="text-slate-500">
              {`[{ "symbol": "NSE_SYMBOL", "exchange": "NSE|BSE", "quantity": N, "instruction"?: "BUY_NEW|SELL_EXIT|REBALANCE_BUY|REBALANCE_SELL" }]`}
            </code>
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleValidate}
              disabled={validating || isExecuting || !isConnected}
              className="flex-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-sm font-medium py-3 rounded-xl transition"
            >
              {validating ? "Computing..." : "🔍 Preview Delta"}
            </button>
            <button
              onClick={handleExecute}
              disabled={isExecuting || !isConnected}
              className="flex-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-semibold py-3 px-8 rounded-xl transition-all shadow-lg shadow-indigo-500/20"
            >
              {isExecuting ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Executing...
                </span>
              ) : (
                "🚀 Execute Now"
              )}
            </button>
          </div>

          {!isConnected && (
            <p className="text-xs text-amber-400 text-center">
              ⚠️ Connect a broker to enable execution
            </p>
          )}
        </div>
      </div>

      {/* Delta Preview */}
      {deltaPreview && deltaPreview.length > 0 && (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-800">
            <h2 className="font-semibold text-white">🔍 Delta Preview ({deltaPreview.length} orders)</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-800/50">
                <tr>
                  {["Symbol", "Type", "Instruction", "Qty", "Current", "Target"].map((h) => (
                    <th key={h} className="px-4 py-2 text-left text-xs text-slate-400 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(deltaPreview as Record<string, unknown>[]).map((d, i) => (
                  <tr key={i} className="border-t border-slate-800 hover:bg-slate-800/30">
                    <td className="px-4 py-2 font-mono text-white">{String(d.symbol)}</td>
                    <td className="px-4 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        d.order_type === "BUY" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                      }`}>
                        {String(d.order_type)}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-400">{String(d.instruction_type)}</td>
                    <td className="px-4 py-2 text-white font-medium">{String(d.quantity)}</td>
                    <td className="px-4 py-2 text-slate-400">{String(d.current_qty)}</td>
                    <td className="px-4 py-2 text-slate-400">{String(d.target_qty)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Real-time execution progress */}
      {(isExecuting || progressMessages.length > 0) && (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-800 flex items-center gap-2">
            {isExecuting && (
              <svg className="animate-spin w-4 h-4 text-indigo-400" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            <h2 className="font-semibold text-white">⚡ Live Execution Feed</h2>
          </div>
          <div className="p-4 space-y-2 max-h-64 overflow-y-auto">
            {progressMessages.length === 0 && isExecuting && (
              <p className="text-slate-500 text-sm text-center py-4">Connecting to execution stream...</p>
            )}
            {progressMessages.map((msg, i) => {
              const d = msg.data as Record<string, unknown>;
              const progress = d.progress as { current: number; total: number };
              return (
                <div key={i} className="flex items-center justify-between text-sm p-2 rounded-lg bg-slate-800/50">
                  <div className="flex items-center gap-3">
                    <span className={`w-2 h-2 rounded-full ${
                      d.status === "FILLED" ? "bg-green-400" :
                      d.status === "REJECTED" ? "bg-red-400" : "bg-yellow-400 animate-pulse"
                    }`} />
                    <span className="font-mono text-white">{String(d.symbol)}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      d.order_type === "BUY" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                    }`}>{String(d.order_type)}</span>
                    <span className="text-slate-400">×{String(d.quantity)}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span>{String(d.status)}</span>
                    <span>{progress?.current}/{progress?.total}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}


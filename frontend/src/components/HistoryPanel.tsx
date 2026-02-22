import { useState, useEffect } from "react";
import { executionApi } from "../api/client";
import type { ExecutionBatch } from "../types";
import ResultsPanel from "./ResultsPanel";

interface Props {
  userId: string;
}

export default function HistoryPanel({ userId: _userId }: Props) {
  const [batches, setBatches] = useState<ExecutionBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ExecutionBatch | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const res = await executionApi.batches();
      setBatches(res.data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  const STATUS_COLORS: Record<string, string> = {
    COMPLETED: "text-green-400",
    PARTIAL: "text-orange-400",
    FAILED: "text-red-400",
    IN_PROGRESS: "text-blue-400",
    PENDING: "text-yellow-400",
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {batches.length === 0 ? (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 p-12 text-center">
          <p className="text-4xl mb-4">📋</p>
          <p className="text-slate-400">No execution history yet.</p>
          <p className="text-slate-500 text-sm mt-1">Execute a portfolio to see results here.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Batch list */}
          <div className="lg:col-span-1">
            <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-800">
                <h2 className="font-semibold text-white">Execution Batches</h2>
                <p className="text-xs text-slate-500 mt-1">{batches.length} total</p>
              </div>
              <div className="divide-y divide-slate-800 max-h-[600px] overflow-y-auto">
                {batches.map((batch) => (
                  <div
                    key={batch.id}
                    onClick={() => setSelected(batch)}
                    className={`p-4 cursor-pointer hover:bg-slate-800/50 transition ${
                      selected?.id === batch.id ? "bg-indigo-500/10 border-l-2 border-indigo-500" : ""
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-white capitalize">{batch.broker}</span>
                      <span className={`text-xs font-medium ${STATUS_COLORS[batch.status] || "text-slate-400"}`}>
                        {batch.status}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>{batch.execution_type}</span>
                      <span>{new Date(batch.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="mt-2 text-xs text-slate-400">
                      {batch.summary?.total_orders ?? 0} orders •{" "}
                      {batch.summary?.filled ?? 0} filled •{" "}
                      {batch.summary?.failed ?? 0} failed
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Batch detail */}
          <div className="lg:col-span-2">
            {selected ? (
              <ResultsPanel batch={selected} />
            ) : (
              <div className="bg-slate-900 rounded-2xl border border-slate-800 p-12 text-center">
                <p className="text-slate-500">Select a batch to view details</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


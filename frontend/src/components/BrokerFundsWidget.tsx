import { useEffect, useState, useCallback } from "react";
import { brokerApi } from "../api/client";
import type { BrokerFunds, FundsSegment } from "../types";

interface Props {
  broker: string;
  isConnected: boolean;
}

function fmt(val: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

function SegmentCard({
  label,
  seg,
}: {
  label: string;
  seg: FundsSegment;
}) {
  const utilised = seg.debits + seg.span + seg.exposure;

  return (
    <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {label}
        </span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            seg.enabled
              ? "bg-green-500/15 text-green-400 border border-green-500/30"
              : "bg-slate-700 text-slate-500"
          }`}
        >
          {seg.enabled ? "Active" : "Disabled"}
        </span>
      </div>

      {/* Net Available — big number */}
      <div className="mb-3">
        <p className="text-xs text-slate-500 mb-0.5">Available (Net)</p>
        <p className="text-2xl font-bold text-green-400">{fmt(seg.net)}</p>
      </div>

      {/* Grid of sub-fields */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-slate-500">Cash</p>
          <p className="text-white font-medium">{fmt(seg.cash)}</p>
        </div>
        <div>
          <p className="text-slate-500">Opening Balance</p>
          <p className="text-white font-medium">{fmt(seg.opening_balance)}</p>
        </div>
        <div>
          <p className="text-slate-500">Live Balance</p>
          <p className="text-white font-medium">{fmt(seg.live_balance)}</p>
        </div>
        <div>
          <p className="text-slate-500">Collateral</p>
          <p className="text-white font-medium">{fmt(seg.collateral)}</p>
        </div>
      </div>

      {/* Utilised section */}
      {utilised > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-700">
          <p className="text-xs text-slate-500 mb-2">Utilised</p>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <p className="text-slate-500">Debits</p>
              <p className="text-red-400 font-medium">{fmt(seg.debits)}</p>
            </div>
            <div>
              <p className="text-slate-500">SPAN</p>
              <p className="text-red-400 font-medium">{fmt(seg.span)}</p>
            </div>
            <div>
              <p className="text-slate-500">Exposure</p>
              <p className="text-red-400 font-medium">{fmt(seg.exposure)}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function BrokerFundsWidget({ broker, isConnected }: Props) {
  const [funds, setFunds] = useState<BrokerFunds | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFunds = useCallback(async () => {
    if (!isConnected || !broker) return;
    setLoading(true);
    setError(null);
    try {
      const res = await brokerApi.funds(broker);
      setFunds(res.data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to fetch funds";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [broker, isConnected]);

  useEffect(() => {
    fetchFunds();
  }, [fetchFunds]);

  if (!isConnected) return null;

  return (
    <div className="border-t border-slate-800 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-base">💰</span>
          <h3 className="text-sm font-semibold text-white">Live Funds & Margin</h3>
          {funds?.paper_trading && (
            <span className="text-xs bg-amber-500/15 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full">
              Paper Trading
            </span>
          )}
        </div>
        <button
          onClick={fetchFunds}
          disabled={loading}
          className="text-xs text-indigo-400 hover:text-indigo-300 disabled:opacity-40 flex items-center gap-1 transition"
        >
          <span className={loading ? "animate-spin" : ""}>↻</span>
          Refresh
        </button>
      </div>

      {/* Loading skeleton */}
      {loading && !funds && (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="h-28 bg-slate-800/60 rounded-xl border border-slate-700 animate-pulse"
            />
          ))}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-3 text-xs text-red-400 flex items-start gap-2">
          <span>⚠️</span>
          <div>
            <p className="font-medium">Could not fetch funds</p>
            <p className="text-red-400/70 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Funds data */}
      {funds && !loading && (
        <>
          {/* Connection verified badge */}
          <div className="mb-3 flex items-center gap-2 bg-green-500/10 border border-green-500/30 rounded-lg px-3 py-2">
            <span className="text-green-400 text-sm">✓</span>
            <p className="text-xs text-green-400 font-medium">
              Broker connection verified — live data received
            </p>
          </div>

          <div className="space-y-3">
            {funds.equity && (
              <SegmentCard label="Equity Segment" seg={funds.equity} />
            )}
            {funds.commodity && (
              <SegmentCard label="Commodity Segment" seg={funds.commodity} />
            )}
          </div>
        </>
      )}
    </div>
  );
}



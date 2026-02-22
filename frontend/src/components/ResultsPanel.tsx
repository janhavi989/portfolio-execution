import type { ExecutionBatch, Order } from "../types";

interface Props {
  batch: ExecutionBatch;
}

const STATUS_COLORS: Record<string, string> = {
  FILLED: "bg-green-500/20 text-green-400",
  REJECTED: "bg-red-500/20 text-red-400",
  FAILED: "bg-red-500/20 text-red-400",
  PLACED: "bg-blue-500/20 text-blue-400",
  PENDING: "bg-yellow-500/20 text-yellow-400",
  PARTIALLY_FILLED: "bg-orange-500/20 text-orange-400",
};

const BATCH_STATUS_COLORS: Record<string, string> = {
  COMPLETED: "bg-green-500/20 text-green-400 border-green-500/30",
  PARTIAL: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  FAILED: "bg-red-500/20 text-red-400 border-red-500/30",
  IN_PROGRESS: "bg-blue-500/20 text-blue-400 border-blue-500/30",
};

export default function ResultsPanel({ batch }: Props) {
  const summary = batch.summary || {};
  const orders: Order[] = batch.orders || [];

  const filled = summary.filled ?? 0;
  const failed = summary.failed ?? 0;
  const total = summary.total_orders ?? orders.length;
  const fillRate = total > 0 ? Math.round((filled / total) * 100) : 0;

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
        <h2 className="font-semibold text-white flex items-center gap-2">
          <span>📈</span> Execution Results
        </h2>
        <div className="flex items-center gap-2">
          {summary.paper_trading && (
            <span className="text-xs bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full border border-amber-500/30">
              PAPER
            </span>
          )}
          <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${
            BATCH_STATUS_COLORS[batch.status] || "bg-slate-700 text-slate-300 border-slate-600"
          }`}>
            {batch.status}
          </span>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-4 divide-x divide-slate-800 border-b border-slate-800">
        {[
          { label: "Total Orders", value: total, color: "text-white" },
          { label: "Filled", value: filled, color: "text-green-400" },
          { label: "Failed", value: failed, color: "text-red-400" },
          { label: "Fill Rate", value: `${fillRate}%`, color: fillRate === 100 ? "text-green-400" : "text-orange-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="p-4 text-center">
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
            <p className="text-xs text-slate-500 mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Execution type + broker info */}
      <div className="px-5 py-3 bg-slate-800/30 border-b border-slate-800 flex items-center gap-4 text-xs text-slate-400">
        <span>Broker: <span className="text-white capitalize">{batch.broker}</span></span>
        <span>Type: <span className="text-white">{batch.execution_type}</span></span>
        <span>
          Time: <span className="text-white">
            {batch.completed_at
              ? new Date(batch.completed_at).toLocaleTimeString()
              : "—"}
          </span>
        </span>
        <span>ID: <span className="font-mono text-slate-300">{batch.id?.slice(0, 8)}...</span></span>
      </div>

      {/* Orders table */}
      {orders.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/50">
              <tr>
                {["Symbol", "Side", "Instruction", "Qty", "Filled", "Avg Price", "Status", "Order ID"].map((h) => (
                  <th key={h} className="px-4 py-2 text-left text-xs text-slate-400 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id} className="border-t border-slate-800 hover:bg-slate-800/30">
                  <td className="px-4 py-2.5 font-mono font-medium text-white">{order.symbol}</td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      order.order_type === "BUY"
                        ? "bg-green-500/20 text-green-400"
                        : "bg-red-500/20 text-red-400"
                    }`}>
                      {order.order_type}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-400">{order.instruction_type}</td>
                  <td className="px-4 py-2.5 text-white">{order.quantity}</td>
                  <td className="px-4 py-2.5 text-slate-300">{order.filled_quantity}</td>
                  <td className="px-4 py-2.5 text-slate-300">
                    {order.avg_fill_price ? `₹${order.avg_fill_price.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      STATUS_COLORS[order.order_status] || "bg-slate-700 text-slate-300"
                    }`}>
                      {order.order_status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-slate-500">
                    {order.broker_order_id ? order.broker_order_id.slice(0, 16) + "..." : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="p-8 text-center text-slate-500">
          {batch.status === "COMPLETED" && summary.message
            ? summary.message
            : "No orders in this batch"}
        </div>
      )}

      {/* Error message if failed */}
      {summary.error && (
        <div className="mx-4 mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl">
          <p className="text-xs text-red-400">Error: {summary.error}</p>
        </div>
      )}
    </div>
  );
}


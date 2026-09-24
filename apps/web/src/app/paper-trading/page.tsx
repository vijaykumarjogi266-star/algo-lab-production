"use client";

import { useState } from "react";
import {
  Briefcase,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  ShieldCheck,
  Power,
  AlertTriangle,
  Receipt,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";

export default function PaperTradingPage() {
  const [killSwitchEngaged, setKillSwitchEngaged] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<"MIS" | "CNC">("MIS");
  const [orderSymbol, setOrderSymbol] = useState("SBIN.NS");
  const [orderQty, setOrderQty] = useState(15);
  const [orderPrice, setOrderPrice] = useState("978.50");
  const [orderSL, setOrderSL] = useState("957.00");
  const [orderPlaced, setOrderPlaced] = useState(false);

  const samplePositions = [
    {
      product: "MIS",
      symbol: "HAL.NS",
      qty: 0,
      buyAvg: "₹4,625.50",
      sellAvg: "₹4,538.50",
      ltp: "₹4,530.00",
      grossPnl: "-₹980.00",
      taxes: "₹64.10",
      netPnl: "-₹1,044.10",
      status: "SQUARED_OFF",
      exitReason: "Stop-Loss Triggered (14:54 IST)",
    },
    {
      product: "MIS",
      symbol: "SBIN.NS",
      qty: 13,
      buyAvg: "₹978.50",
      sellAvg: "—",
      ltp: "₹984.20",
      grossPnl: "+₹74.10",
      taxes: "₹18.40",
      netPnl: "+₹55.70",
      status: "OPEN (PAPER)",
      exitReason: "Trailing SL @ ₹957.07",
    },
  ];

  const orderBook = [
    { id: "ORD-88419", time: "14:54:21", symbol: "HAL.NS", type: "SL-M", qty: 11, price: "₹4,538.50", status: "TRIGGERED", note: "Disciplined Stop Loss Execution" },
    { id: "ORD-88301", time: "11:15:02", symbol: "HAL.NS", type: "LIMIT", qty: 11, price: "₹4,625.50", status: "COMPLETE", note: "Ensemble Alpha Voter Entry" },
    { id: "ORD-88120", time: "10:30:15", symbol: "ZOMATO.NS", type: "MARKET", qty: 500, price: "₹298.00", status: "REJECTED", note: "Risk Gateway: Max single trade cap exceeded" },
  ];

  const handlePlaceOrder = (e: React.FormEvent) => {
    e.preventDefault();
    if (killSwitchEngaged) {
      alert("Execution blocked: Zerodha Kill Switch is active!");
      return;
    }
    setOrderPlaced(true);
    setTimeout(() => setOrderPlaced(false), 3000);
  };

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Title & Kill Switch Status Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-surface-border gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              ZERODHA KITE SIMULATOR
            </span>
            <span className="text-xs text-slate-400 font-mono">Stage 1 In-Memory Sandbox</span>
          </div>
          <h2 className="text-xl md:text-2xl font-bold text-white mt-1">Positions &amp; Simulated Orders</h2>
        </div>

        {/* Interactive Kill Switch Toggle */}
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setKillSwitchEngaged(!killSwitchEngaged)}
            className={`flex items-center space-x-2 px-4 py-2 rounded text-xs font-mono font-bold transition-all shadow-md ${
              killSwitchEngaged
                ? "bg-rose-600 text-white hover:bg-rose-500 animate-pulse"
                : "bg-slate-800 text-slate-300 border border-slate-700 hover:border-rose-500 hover:text-white"
            }`}
          >
            <Power className="w-4 h-4" />
            <span>{killSwitchEngaged ? "KILL SWITCH ENGAGED (LOCKED)" : "ENGAGE KILL SWITCH"}</span>
          </button>
        </div>
      </div>

      {/* Kill Switch Active Warning Banner */}
      {killSwitchEngaged && (
        <div className="p-4 rounded-lg bg-rose-500/15 border border-rose-500/30 flex items-center space-x-3 text-rose-200 text-xs">
          <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0" />
          <div>
            <span className="font-bold">Zerodha Kill Switch Activated:</span> All simulated order placement is locked out for 12 hours. Existing positions remain protected by in-memory stop-loss triggers.
          </div>
        </div>
      )}

      {/* Account Balance & Capital Allocation (Kite Style) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <span className="text-xs text-slate-400 font-mono">AVAILABLE MARGIN</span>
          <div className="text-xl font-bold text-white mt-1 font-mono">₹86,220.00</div>
          <span className="text-[10px] text-slate-500">Unencumbered Cash (₹1L Base)</span>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <span className="text-xs text-slate-400 font-mono">MARGIN USED (MIS)</span>
          <div className="text-xl font-bold text-sky-400 mt-1 font-mono">₹12,735.90</div>
          <span className="text-[10px] text-slate-500">Intraday 1.0x (No Leverage)</span>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <span className="text-xs text-slate-400 font-mono">REALIZED P&amp;L (NET)</span>
          <div className="text-xl font-bold text-rose-400 mt-1 font-mono">-₹1,044.10</div>
          <span className="text-[10px] text-slate-500">Post-STT / Charges</span>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <span className="text-xs text-slate-400 font-mono">UNREALIZED P&amp;L</span>
          <div className="text-xl font-bold text-emerald-400 mt-1 font-mono">+₹55.70</div>
          <span className="text-[10px] text-emerald-500">1 Open Position</span>
        </div>
      </div>

      {/* Active Positions Table */}
      <div className="rounded-lg bg-surface border border-surface-border overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-border flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Briefcase className="w-4 h-4 text-sky-400" />
            <h3 className="text-sm font-semibold text-white">Positions (Paper Sandbox)</h3>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            Mandatory EOD Square-Off at 15:15 IST
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-black/40 text-slate-400 border-b border-surface-border">
              <tr>
                <th className="p-3">Product</th>
                <th className="p-3">Instrument</th>
                <th className="p-3">Qty</th>
                <th className="p-3">Avg Buy</th>
                <th className="p-3">LTP</th>
                <th className="p-3">Gross P&amp;L</th>
                <th className="p-3">Taxes / Fees</th>
                <th className="p-3">Net P&amp;L</th>
                <th className="p-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border text-slate-300">
              {samplePositions.map((pos) => (
                <tr key={pos.symbol} className="hover:bg-slate-800/30 transition-colors">
                  <td className="p-3">
                    <span className="px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20 text-[10px] font-bold">
                      {pos.product}
                    </span>
                  </td>
                  <td className="p-3 font-bold text-white">{pos.symbol}</td>
                  <td className="p-3">{pos.qty}</td>
                  <td className="p-3">{pos.buyAvg}</td>
                  <td className="p-3 text-white font-medium">{pos.ltp}</td>
                  <td className={`p-3 font-bold ${pos.grossPnl.startsWith("+") ? "text-emerald-400" : "text-rose-400"}`}>
                    {pos.grossPnl}
                  </td>
                  <td className="p-3 text-slate-400">{pos.taxes}</td>
                  <td className={`p-3 font-bold ${pos.netPnl.startsWith("+") ? "text-emerald-400" : "text-rose-400"}`}>
                    {pos.netPnl}
                  </td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] ${
                      pos.status.includes("OPEN")
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-slate-800 text-slate-400 border border-slate-700"
                    }`}>
                      {pos.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Grid: Order Window Simulator + Order Book */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Kite-Style Order Placement Window */}
        <div className="p-5 rounded-lg bg-surface border border-surface-border space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-surface-border">
            <span className="text-sm font-semibold text-white">Simulate Order Entry</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              PAPER ONLY
            </span>
          </div>

          <form onSubmit={handlePlaceOrder} className="space-y-3.5 text-xs">
            {/* Product Toggle (MIS vs CNC) */}
            <div>
              <label className="text-slate-400 font-mono text-[11px] block mb-1">Product Type</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedProduct("MIS")}
                  className={`py-1.5 rounded font-mono text-xs font-semibold border transition-all ${
                    selectedProduct === "MIS"
                      ? "bg-sky-500/20 border-sky-400 text-sky-300"
                      : "bg-black/30 border-surface-border text-slate-400 hover:text-white"
                  }`}
                >
                  MIS (Intraday)
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedProduct("CNC")}
                  className={`py-1.5 rounded font-mono text-xs font-semibold border transition-all ${
                    selectedProduct === "CNC"
                      ? "bg-sky-500/20 border-sky-400 text-sky-300"
                      : "bg-black/30 border-surface-border text-slate-400 hover:text-white"
                  }`}
                >
                  CNC (Delivery)
                </button>
              </div>
            </div>

            {/* Symbol & Quantity */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 font-mono text-[11px] block mb-1">Instrument</label>
                <input
                  type="text"
                  value={orderSymbol}
                  onChange={(e) => setOrderSymbol(e.target.value)}
                  className="w-full bg-black/40 border border-surface-border rounded p-2 text-white font-mono text-xs focus:border-accent outline-none"
                />
              </div>
              <div>
                <label className="text-slate-400 font-mono text-[11px] block mb-1">Quantity</label>
                <input
                  type="number"
                  value={orderQty}
                  onChange={(e) => setOrderQty(Number(e.target.value))}
                  className="w-full bg-black/40 border border-surface-border rounded p-2 text-white font-mono text-xs focus:border-accent outline-none"
                />
              </div>
            </div>

            {/* Limit Price & Mandatory SL */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 font-mono text-[11px] block mb-1">Price (₹)</label>
                <input
                  type="text"
                  value={orderPrice}
                  onChange={(e) => setOrderPrice(e.target.value)}
                  className="w-full bg-black/40 border border-surface-border rounded p-2 text-white font-mono text-xs focus:border-accent outline-none"
                />
              </div>
              <div>
                <label className="text-slate-400 font-mono text-[11px] block mb-1">
                  Mandatory Stop-Loss <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={orderSL}
                  onChange={(e) => setOrderSL(e.target.value)}
                  className="w-full bg-black/40 border border-rose-500/30 rounded p-2 text-white font-mono text-xs focus:border-rose-400 outline-none"
                />
              </div>
            </div>

            {/* Estimated Friction / Brokerage Nudge */}
            <div className="p-2.5 rounded bg-black/50 border border-surface-border text-[11px] font-mono text-slate-400 space-y-1">
              <div className="flex justify-between">
                <span>Margin Required:</span>
                <span className="text-white font-bold">₹{(orderQty * Number(orderPrice || 0)).toLocaleString("en-IN")}</span>
              </div>
              <div className="flex justify-between text-[10px]">
                <span>Est. STT + Charges:</span>
                <span className="text-amber-400">~₹14.80 (SEBI / NSE)</span>
              </div>
            </div>

            {/* Action Buttons */}
            <button
              type="submit"
              disabled={killSwitchEngaged}
              className={`w-full py-2.5 rounded font-mono font-bold text-xs transition-all ${
                killSwitchEngaged
                  ? "bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700"
                  : "bg-sky-500 hover:bg-sky-400 text-black shadow-lg"
              }`}
            >
              {killSwitchEngaged ? "BLOCKED BY KILL SWITCH" : "SUBMIT SIMULATED BUY (MIS)"}
            </button>

            {orderPlaced && (
              <div className="p-2 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-mono text-center">
                ✓ Order placed in memory sandbox with SL-M guard.
              </div>
            )}
          </form>
        </div>

        {/* Right 2 Cols: Order Audit Trail & Rejections */}
        <div className="lg:col-span-2 p-5 rounded-lg bg-surface border border-surface-border space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-surface-border">
            <h3 className="text-sm font-semibold text-white">Order Audit Trail &amp; Gateway Rejections</h3>
            <span className="text-[11px] font-mono text-slate-400">SEBI Order Tagging Active</span>
          </div>

          <div className="space-y-2.5">
            {orderBook.map((ord) => (
              <div
                key={ord.id}
                className="p-3 rounded bg-black/40 border border-surface-border flex items-center justify-between text-xs font-mono"
              >
                <div className="space-y-0.5">
                  <div className="flex items-center space-x-2">
                    <span className="text-slate-400">{ord.time}</span>
                    <span className="font-bold text-white">{ord.symbol}</span>
                    <span className="text-[10px] px-1 rounded bg-slate-800 text-slate-300">{ord.type}</span>
                    <span className="text-slate-300">{ord.qty} @ {ord.price}</span>
                  </div>
                  <div className="text-[11px] text-slate-400">{ord.note}</div>
                </div>

                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  ord.status === "COMPLETE"
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : ord.status === "TRIGGERED"
                    ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                    : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                }`}>
                  {ord.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

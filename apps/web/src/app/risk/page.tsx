"use client";

import { useState } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Power,
  AlertTriangle,
  Lock,
  Activity,
  CheckCircle2,
  XCircle,
  FileText,
  Sliders,
  Percent,
} from "lucide-react";

export default function RiskPage() {
  const [killSwitchState, setKillSwitchState] = useState(false);

  const rmsRules = [
    {
      name: "Zerodha Kill Switch Protocol",
      value: killSwitchState ? "ACTIVATED" : "ARMED (STANDBY)",
      type: "Hard Process Lock",
      desc: "Instantly terminates all order routing and locks trader out of placing orders for 12 hours. Existing trailing stops remain active.",
      status: killSwitchState ? "TRIPPED" : "HEALTHY",
    },
    {
      name: "Daily Loss Circuit Breaker",
      value: "₹3,000 (3.0% of Capital)",
      type: "Capital Preservation",
      desc: "Mandatory session halt when daily realized/unrealized loss crosses ₹3,000. Prevents revenge trading and tilt.",
      status: "HEALTHY (₹1,044 Used)",
    },
    {
      name: "Fat-Finger Single Order Cap",
      value: "₹45,000 per Order",
      type: "Execution Guard",
      desc: "Rejects any algorithmic order whose gross notional exposure exceeds ₹45,000, preventing decimal point fat-finger disasters.",
      status: "ENFORCED",
    },
    {
      name: "Order Velocity Throttler",
      value: "Max 6 Orders / Minute",
      type: "Loop Guard",
      desc: "Blocks runaway infinite while-loops in automated strategy code from flooding the broker API or triggering exchange penalties.",
      status: "ENFORCED",
    },
    {
      name: "Mandatory Stop-Loss Guard",
      value: "SL-M Tag Compulsory",
      type: "Pre-Trade Validation",
      desc: "Every BUY/SELL order MUST include an explicit, verified stop-loss price. Naked directional positions are rejected pre-trade.",
      status: "ENFORCED",
    },
    {
      name: "Zero Margin Leverage (1.0x)",
      value: "1.0x Hard Ceiling",
      type: "SEBI Peak Margin",
      desc: "Principle 20: No hidden multiplier, no margin debt. You only trade what you have in unencumbered cash.",
      status: "ENFORCED",
    },
  ];

  const taxBreakdown = [
    { segment: "Equity Delivery (CNC)", stt: "0.1% on Buy & Sell", exchange: "0.00297%", gst: "18% on charges", stamp: "0.015% on Buy" },
    { segment: "Equity Intraday (MIS)", stt: "0.025% on Sell only", exchange: "0.00297%", gst: "18% on charges", stamp: "0.003% on Buy" },
    { segment: "Futures (Equity/Index)", stt: "0.02% on Sell (Budget 2024)", exchange: "0.00173%", gst: "18% on charges", stamp: "0.002% on Buy" },
    { segment: "Options (Premium)", stt: "0.1% on Sell (Budget 2024)", exchange: "0.03503%", gst: "18% on charges", stamp: "0.003% on Buy" },
  ];

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Risk Architecture Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-surface-border gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono font-bold text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
              ZERODHA RISK MANAGEMENT SYSTEM (RMS)
            </span>
            <span className="text-xs text-slate-400 font-mono">Independent Pre-Trade Gateway</span>
          </div>
          <h2 className="text-xl md:text-2xl font-bold text-white mt-1">Hard Risk Engine &amp; Kill Switch</h2>
          <p className="text-xs text-slate-400 mt-1">
            Principle 14: Risk Engine is decoupled from Alpha. Strategy logic cannot override mathematical limits.
          </p>
        </div>

        <button
          onClick={() => setKillSwitchState(!killSwitchState)}
          className={`flex items-center space-x-2 px-5 py-2.5 rounded font-mono font-bold text-xs transition-all shadow-lg ${
            killSwitchState
              ? "bg-rose-600 text-white hover:bg-rose-500 animate-pulse"
              : "bg-slate-800 text-slate-300 border border-slate-700 hover:border-rose-400 hover:text-white"
          }`}
        >
          <Power className="w-4 h-4 text-rose-400" />
          <span>{killSwitchState ? "KILL SWITCH ENGAGED (RESET)" : "ACTIVATE KILL SWITCH"}</span>
        </button>
      </div>

      {/* 6 Hard Risk Gates */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {rmsRules.map((rule) => (
          <div key={rule.name} className="p-4 rounded-lg bg-surface border border-surface-border space-y-2.5 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">{rule.type}</span>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                  rule.status.includes("TRIPPED")
                    ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                    : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                }`}>
                  {rule.status}
                </span>
              </div>
              <h3 className="text-xs font-bold text-white mt-2">{rule.name}</h3>
              <div className="text-sm font-mono font-bold text-accent mt-1">{rule.value}</div>
              <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">{rule.desc}</p>
            </div>

            <div className="pt-2 border-t border-surface-border flex items-center justify-between text-[10px] font-mono text-slate-500">
              <span>SEBI RMS Compliance</span>
              <span className="text-emerald-400">PASSED</span>
            </div>
          </div>
        ))}
      </div>

      {/* Indian Market Statutory Friction Matrix (The Zerodha Reality Table) */}
      <div className="rounded-lg bg-surface border border-surface-border overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-border flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">NSE / SEBI Statutory Friction &amp; Tax Matrix</h3>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Accurate tax rates updated post-Finance Act 2024. Your algorithm must generate enough alpha to overcome these hurdle rates.
            </p>
          </div>
          <span className="text-xs font-mono text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
            HURDLE RATE GUARD
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-black/40 text-slate-400 border-b border-surface-border">
              <tr>
                <th className="p-3">Market Segment</th>
                <th className="p-3">STT / CTT Rate</th>
                <th className="p-3">NSE Turnover Charge</th>
                <th className="p-3">GST (18%)</th>
                <th className="p-3">Stamp Duty</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border text-slate-300">
              {taxBreakdown.map((row) => (
                <tr key={row.segment} className="hover:bg-slate-800/30 transition-colors">
                  <td className="p-3 font-bold text-white">{row.segment}</td>
                  <td className="p-3 text-amber-400">{row.stt}</td>
                  <td className="p-3">{row.exchange}</td>
                  <td className="p-3">{row.gst}</td>
                  <td className="p-3 text-slate-400">{row.stamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

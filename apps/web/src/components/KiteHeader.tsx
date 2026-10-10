"use client";

import { useState, useEffect } from "react";
import { ShieldAlert, ShieldCheck, Power, AlertTriangle, Clock } from "lucide-react";

export function KiteHeader() {
  const [killSwitchActive, setKillSwitchActive] = useState(false);
  const [istTime, setIstTime] = useState("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      // Format to IST
      const options: Intl.DateTimeFormatOptions = {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      };
      setIstTime(new Intl.DateTimeFormat("en-IN", options).format(now));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="h-14 border-b border-surface-border bg-surface/80 backdrop-blur px-6 flex items-center justify-between sticky top-0 z-20">
      {/* Left: Market Indices Ticker (Kite Style) */}
      <div className="flex items-center space-x-6 text-xs font-mono">
        <div className="flex items-center space-x-2">
          <span className="text-slate-400 font-semibold">NIFTY 50</span>
          <span className="text-white font-bold">25,790.65</span>
          <span className="text-emerald-400 font-medium">+36.20 (+0.14%)</span>
        </div>

        <div className="hidden md:flex items-center space-x-2">
          <span className="text-slate-400 font-semibold">SENSEX</span>
          <span className="text-white font-bold">84,266.29</span>
          <span className="text-emerald-400 font-medium">+98.15 (+0.12%)</span>
        </div>

        <div className="hidden lg:flex items-center space-x-2">
          <span className="text-slate-400 font-semibold">INDIA VIX</span>
          <span className="text-white font-bold">12.84</span>
          <span className="text-emerald-400 font-medium">-0.28 (-2.13%)</span>
          <span className="text-[10px] text-slate-500 bg-slate-800/80 px-1.5 py-0.5 rounded">Low Vol</span>
        </div>
      </div>

      {/* Right: Clock & Zerodha Kill Switch */}
      <div className="flex items-center space-x-4">
        {/* IST Clock */}
        <div className="hidden sm:flex items-center space-x-1.5 text-xs font-mono text-slate-400 bg-black/40 px-2.5 py-1 rounded border border-surface-border">
          <Clock className="w-3.5 h-3.5 text-sky-400" />
          <span>{istTime || "18:30:00 IST"}</span>
          <span className="text-[10px] text-emerald-400 ml-1">● EOD PREP</span>
        </div>

        {/* Nithin's Zerodha Kill Switch */}
        <button
          onClick={() => setKillSwitchActive(!killSwitchActive)}
          className={`flex items-center space-x-1.5 px-3 py-1 rounded text-xs font-mono font-medium transition-all ${
            killSwitchActive
              ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse"
              : "bg-slate-800/80 text-slate-300 border border-slate-700 hover:border-accent hover:text-white"
          }`}
          title="Zerodha Kill Switch: Locks order execution for the remainder of the session"
        >
          <Power className={`w-3.5 h-3.5 ${killSwitchActive ? "text-rose-400" : "text-emerald-400"}`} />
          <span>{killSwitchActive ? "KILL SWITCH: ENGAGED" : "KILL SWITCH: ARMED"}</span>
        </button>

        {/* Safety Lock Badge */}
        <div className="flex items-center space-x-1 text-xs font-mono px-2 py-1 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span className="hidden md:inline">PAPER SANDBOX</span>
        </div>
      </div>
    </header>
  );
}

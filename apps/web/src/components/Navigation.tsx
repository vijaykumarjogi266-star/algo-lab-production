"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  LineChart,
  FlaskConical,
  Briefcase,
  ShieldAlert,
  Layers,
  Bot,
  Activity,
  AlertTriangle,
  Receipt,
  Lock,
} from "lucide-react";

export function Navigation() {
  const pathname = usePathname();

  const navItems = [
    { label: "Dashboard", href: "/", icon: LayoutDashboard },
    { label: "Swing Desk (Live EOD)", href: "/dashboard", icon: Activity },
    { label: "Positions & Orders", href: "/paper-trading", icon: Briefcase },
    { label: "Strategies & Alphas", href: "/strategies", icon: Layers },
    { label: "Backtests & Friction", href: "/backtests", icon: Receipt },
    { label: "Market & Watchlist", href: "/market", icon: LineChart },
    { label: "Risk & Kill Switch", href: "/risk", icon: ShieldAlert },
    { label: "Portfolio Allocation", href: "/portfolio", icon: Briefcase },
    { label: "Varsity & Research", href: "/research", icon: FlaskConical },
    { label: "AI Quantitative Council", href: "/ai-analyst", icon: Bot },
    { label: "System Diagnostics", href: "/system", icon: Activity },
  ];

  return (
    <aside className="w-64 border-r border-surface-border bg-surface flex flex-col justify-between shrink-0 h-screen sticky top-0">
      <div>
        {/* Brand Header */}
        <div className="p-5 border-b border-surface-border">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded bg-gradient-to-tr from-sky-500 to-emerald-400 flex items-center justify-center font-bold text-black text-sm tracking-wider shadow-sm">
              ZK
            </div>
            <div>
              <div className="flex items-center space-x-1.5">
                <h1 className="font-bold text-sm tracking-wide text-white">ALGO LAB</h1>
                <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  KITE OS
                </span>
              </div>
              <p className="text-[10px] text-slate-400 font-mono">NITHIN KAMATH EDITION</p>
            </div>
          </div>
        </div>

        {/* Navigation Items */}
        <div className="px-3 py-4">
          <div className="px-3 pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider font-mono">
            Menu
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center space-x-3 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                    isActive
                      ? "bg-accent/10 text-accent border border-accent/20"
                      : "text-slate-300 hover:text-white hover:bg-slate-800/60"
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? "text-accent" : "text-slate-400"}`} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Footer: Nithin Kamath's Survival Nudge */}
      <div className="p-4 border-t border-surface-border bg-black/30">
        <div className="rounded border border-amber-500/25 bg-amber-500/5 p-3">
          <div className="flex items-center space-x-1.5 text-amber-400 text-xs font-semibold">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>Nithin&apos;s Nudge</span>
          </div>
          <p className="text-[11px] text-slate-300 mt-1 leading-relaxed">
            &ldquo;Rule #1: Survival. 90% lose money by overtrading. Return OF capital is far more important than return ON capital.&rdquo;
          </p>
          <div className="mt-2 pt-2 border-t border-amber-500/15 flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>SEBI Reality Guard</span>
            <span className="text-emerald-400">ACTIVE</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

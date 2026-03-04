"use client";

import { useQuery } from "@tanstack/react-query";
import { dashboardApi, brokerageApi } from "@/lib/api";
import { formatCurrency, formatPercent, formatPnL } from "@/lib/utils";
import {
  TrendingUp, TrendingDown, AlertTriangle, Activity,
  BookOpen, Zap, BarChart2, Plug,
} from "lucide-react";
import Link from "next/link";

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  valueClass = "text-white",
}: {
  title: string;
  value: string;
  subtitle?: string;
  icon?: React.ElementType;
  valueClass?: string;
}) {
  return (
    <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-400">{title}</p>
          <p className={`text-2xl font-bold mt-1 font-mono ${valueClass}`}>{value}</p>
          {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
        </div>
        {Icon && (
          <div className="bg-[#334155] rounded-lg p-2">
            <Icon className="w-5 h-5 text-slate-400" />
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data: dash, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => dashboardApi.get().then((r) => r.data),
  });

  const { data: brokerageStatus } = useQuery({
    queryKey: ["brokerage-status"],
    queryFn: () => brokerageApi.status().then((r) => r.data),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">Loading dashboard...</div>
      </div>
    );
  }

  if (!dash) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
        <div className="bg-[#1e293b] border border-[#334155] rounded-2xl p-12 max-w-md">
          <Activity className="w-16 h-16 text-blue-400 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-white mb-2">Welcome to TradeOS</h1>
          <p className="text-slate-400 mb-6">Sign in to access your trading dashboard.</p>
          <Link
            href="/connect"
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-6 py-3 rounded-lg font-medium transition-colors"
          >
            Sign In
          </Link>
        </div>
      </div>
    );
  }

  const pnl = formatPnL(dash.portfolio.total_realized_pnl);
  const winRate = dash.trades_summary.win_rate_30d_pct;
  const avgR = dash.trades_summary.avg_r_multiple_30d;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        {brokerageStatus?.is_connected ? (
          <span className="flex items-center gap-2 text-sm text-green-400">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Questrade connected
          </span>
        ) : (
          <Link
            href="/connect"
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white border border-[#334155] rounded-lg px-3 py-1.5 transition-colors"
          >
            <Plug className="w-3.5 h-3.5" />
            Connect Questrade
          </Link>
        )}
      </div>

      {/* Circuit Breaker Warning */}
      {dash.risk.circuit_breaker_active && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="text-red-400 w-5 h-5 flex-shrink-0" />
          <div>
            <p className="text-red-400 font-medium">Circuit Breaker Active</p>
            <p className="text-sm text-slate-400">Trading is halted. Go to Settings to reset.</p>
          </div>
        </div>
      )}

      {/* Key metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Open Positions"
          value={String(dash.portfolio.open_positions)}
          subtitle="in database"
          icon={Activity}
        />
        <StatCard
          title="Realized P&L"
          value={pnl.text}
          valueClass={pnl.className}
          subtitle="all time"
          icon={dash.portfolio.total_realized_pnl >= 0 ? TrendingUp : TrendingDown}
        />
        <StatCard
          title="Win Rate (30d)"
          value={winRate !== null ? `${winRate}%` : "—"}
          subtitle={`${dash.trades_summary.closed_30d} closed trades`}
          icon={BarChart2}
        />
        <StatCard
          title="Avg R (30d)"
          value={avgR !== null ? `${avgR}R` : "—"}
          subtitle="risk-reward ratio"
          icon={TrendingUp}
        />
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5">
          <p className="text-sm text-slate-400">Strategies</p>
          <p className="text-2xl font-bold text-white mt-1">{dash.strategies.total}</p>
          <p className="text-xs text-slate-500 mt-1">{dash.strategies.active_auto} auto-active</p>
        </div>
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm text-slate-400">Signals (24h)</p>
              <p className="text-2xl font-bold text-white mt-1">
                {dash.signals_24h.pending + dash.signals_24h.executed + dash.signals_24h.rejected}
              </p>
              <p className="text-xs text-slate-500 mt-1">{dash.signals_24h.pending} pending</p>
            </div>
            <div className="bg-[#334155] rounded-lg p-2">
              <Zap className="w-5 h-5 text-slate-400" />
            </div>
          </div>
        </div>
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm text-slate-400">Journal</p>
              <p className="text-2xl font-bold text-white mt-1">{dash.journal.total_entries}</p>
              <p className="text-xs text-slate-500 mt-1">{dash.journal.entries_last_7d} this week</p>
            </div>
            <div className="bg-[#334155] rounded-lg p-2">
              <BookOpen className="w-5 h-5 text-slate-400" />
            </div>
          </div>
        </div>
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5">
          <p className="text-sm text-slate-400">Backtests</p>
          <p className="text-2xl font-bold text-white mt-1">{dash.backtests.total_completed}</p>
          <p className="text-xs text-slate-500 mt-1">completed</p>
        </div>
      </div>

      {/* Recent trades + signals side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Trades */}
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl">
          <div className="px-5 py-4 border-b border-[#334155]">
            <h2 className="font-semibold text-white">Recent Trades</h2>
          </div>
          {dash.recent_trades.length === 0 ? (
            <div className="px-5 py-8 text-center text-slate-400 text-sm">No trades yet</div>
          ) : (
            <div className="divide-y divide-[#334155]">
              {dash.recent_trades.map((t: { id: string; symbol: string; side: string; status: string; pnl: number | null; created_at: string }) => {
                const tradePnl = formatPnL(t.pnl);
                return (
                  <div key={t.id} className="px-5 py-3 flex items-center justify-between">
                    <div>
                      <span className="text-white font-medium">{t.symbol}</span>
                      <span className="ml-2 text-xs text-slate-500 uppercase">{t.side}</span>
                    </div>
                    <div className="text-right">
                      {t.pnl !== null ? (
                        <span className={`font-mono text-sm ${tradePnl.className}`}>{tradePnl.text}</span>
                      ) : (
                        <span className="text-xs text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded">open</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Recent Signals */}
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl">
          <div className="px-5 py-4 border-b border-[#334155]">
            <h2 className="font-semibold text-white">Recent Signals</h2>
          </div>
          {dash.recent_signals.length === 0 ? (
            <div className="px-5 py-8 text-center text-slate-400 text-sm">No signals yet</div>
          ) : (
            <div className="divide-y divide-[#334155]">
              {dash.recent_signals.map((s: { id: string; symbol: string; pattern_name: string; direction: string; status: string; confidence_score: number }) => (
                <div key={s.id} className="px-5 py-3 flex items-center justify-between">
                  <div>
                    <span className="text-white font-medium">{s.symbol}</span>
                    <span className="ml-2 text-xs text-slate-500">{s.pattern_name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs ${s.direction === "bullish" ? "text-green-400" : "text-red-400"}`}>
                      {s.direction}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      s.status === "pending" ? "bg-yellow-400/10 text-yellow-400" :
                      s.status === "executed" ? "bg-green-400/10 text-green-400" :
                      "bg-slate-400/10 text-slate-400"
                    }`}>
                      {s.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

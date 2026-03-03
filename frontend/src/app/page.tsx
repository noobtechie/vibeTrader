"use client";

import { useQuery } from "@tanstack/react-query";
import { brokerageApi, riskApi } from "@/lib/api";
import { formatCurrency, formatPercent, formatPnL } from "@/lib/utils";
import { TrendingUp, TrendingDown, AlertTriangle, Activity } from "lucide-react";
import type { Account, Balance, Position, RiskSettings } from "@/types";
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
  const { data: connectionStatus } = useQuery({
    queryKey: ["brokerage-status"],
    queryFn: () => brokerageApi.status().then((r) => r.data),
  });

  const isConnected = connectionStatus?.is_connected;

  const { data: accountsData } = useQuery({
    queryKey: ["accounts"],
    queryFn: () => brokerageApi.accounts().then((r) => r.data),
    enabled: isConnected,
  });

  const primaryAccount: Account | undefined = accountsData?.accounts?.[0];

  const { data: balancesData } = useQuery({
    queryKey: ["balances", primaryAccount?.account_id],
    queryFn: () =>
      brokerageApi
        .balances(primaryAccount!.account_id)
        .then((r) => r.data),
    enabled: !!primaryAccount,
  });

  const { data: positionsData } = useQuery({
    queryKey: ["positions", primaryAccount?.account_id],
    queryFn: () =>
      brokerageApi
        .positions(primaryAccount!.account_id)
        .then((r) => r.data),
    enabled: !!primaryAccount,
  });

  const { data: riskData } = useQuery({
    queryKey: ["risk-settings"],
    queryFn: () => riskApi.getSettings().then((r) => r.data),
  });

  const cad: Balance | undefined = balancesData?.balances?.find(
    (b: Balance) => b.currency === "CAD"
  );
  const positions: Position[] = positionsData?.positions || [];
  const totalPnL = positions.reduce((acc: number, p: Position) => acc + (p.pnl || 0), 0);
  const risk: RiskSettings | undefined = riskData;

  if (!isConnected) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
        <div className="bg-[#1e293b] border border-[#334155] rounded-2xl p-12 max-w-md">
          <Activity className="w-16 h-16 text-blue-400 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-white mb-2">Welcome to TradeOS</h1>
          <p className="text-slate-400 mb-6">
            Connect your Questrade account to start trading with automation.
          </p>
          <Link
            href="/connect"
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-6 py-3 rounded-lg font-medium transition-colors"
          >
            Connect Brokerage
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <span className="flex items-center gap-2 text-sm text-profit">
          <span className="w-2 h-2 rounded-full bg-profit animate-pulse" />
          {primaryAccount?.account_type} · {primaryAccount?.account_id}
        </span>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Equity"
          value={formatCurrency(cad?.total_equity)}
          subtitle={primaryAccount?.currency}
          icon={TrendingUp}
        />
        <StatCard
          title="Buying Power"
          value={formatCurrency(cad?.buying_power)}
          icon={Activity}
        />
        <StatCard
          title="Open P&L"
          value={formatPnL(totalPnL).text}
          valueClass={formatPnL(totalPnL).className}
          subtitle={`${positions.length} positions`}
          icon={totalPnL >= 0 ? TrendingUp : TrendingDown}
        />
        <StatCard
          title="Daily Risk"
          value={
            risk?.circuit_breaker_active
              ? "HALTED"
              : formatCurrency(risk?.max_risk_daily)
          }
          valueClass={risk?.circuit_breaker_active ? "text-loss" : "text-white"}
          subtitle="max daily loss"
          icon={AlertTriangle}
        />
      </div>

      {/* Circuit Breaker Warning */}
      {risk?.circuit_breaker_active && (
        <div className="bg-loss/10 border border-loss/30 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="text-loss w-5 h-5 flex-shrink-0" />
          <div>
            <p className="text-loss font-medium">Circuit Breaker Active</p>
            <p className="text-sm text-slate-400">
              Trading is halted. Go to Settings to reset.
            </p>
          </div>
        </div>
      )}

      {/* Open positions */}
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl">
        <div className="px-5 py-4 border-b border-[#334155] flex items-center justify-between">
          <h2 className="font-semibold text-white">Open Positions</h2>
          <span className="text-sm text-slate-400">{positions.length} positions</span>
        </div>
        {positions.length === 0 ? (
          <div className="px-5 py-8 text-center text-slate-400">
            No open positions
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 border-b border-[#334155]">
                  <th className="px-5 py-3 text-left">Symbol</th>
                  <th className="px-5 py-3 text-right">Qty</th>
                  <th className="px-5 py-3 text-right">Avg Cost</th>
                  <th className="px-5 py-3 text-right">Current</th>
                  <th className="px-5 py-3 text-right">P&L</th>
                  <th className="px-5 py-3 text-right">P&L %</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => {
                  const pnl = formatPnL(pos.pnl);
                  return (
                    <tr
                      key={pos.symbol}
                      className="border-b border-[#334155] last:border-0 hover:bg-[#334155]/30"
                    >
                      <td className="px-5 py-3 font-medium text-white">{pos.symbol}</td>
                      <td className="px-5 py-3 text-right text-slate-300 font-mono">
                        {pos.quantity}
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-slate-300">
                        {formatCurrency(pos.average_cost)}
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-slate-300">
                        {formatCurrency(pos.current_price)}
                      </td>
                      <td className={`px-5 py-3 text-right font-mono ${pnl.className}`}>
                        {pnl.text}
                      </td>
                      <td className={`px-5 py-3 text-right font-mono ${pnl.className}`}>
                        {formatPercent(pos.pnl_pct / 100)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

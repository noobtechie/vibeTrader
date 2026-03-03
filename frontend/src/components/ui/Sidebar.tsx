"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BookOpen,
  ScrollText,
  FlaskConical,
  Settings,
  Plug,
  Zap,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/connect", icon: Plug, label: "Connect" },
  { href: "/playbook", icon: BookOpen, label: "Playbook" },
  { href: "/journal", icon: ScrollText, label: "Journal" },
  { href: "/backtest", icon: FlaskConical, label: "Backtest" },
  { href: "/automation", icon: Zap, label: "Automation" },
  { href: "/settings", icon: Settings, label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-16 lg:w-56 bg-[#1e293b] border-r border-[#334155] flex flex-col flex-shrink-0">
      {/* Logo */}
      <div className="h-16 flex items-center px-4 border-b border-[#334155]">
        <TrendingUp className="text-blue-400 w-6 h-6 flex-shrink-0" />
        <span className="ml-3 font-bold text-white hidden lg:block">
          TradeOS
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-1">
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm",
                active
                  ? "bg-blue-600/20 text-blue-400 font-medium"
                  : "text-slate-400 hover:bg-[#334155] hover:text-white"
              )}
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              <span className="hidden lg:block">{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Version */}
      <div className="p-4 border-t border-[#334155] hidden lg:block">
        <p className="text-xs text-slate-500">TradeOS v1.0</p>
      </div>
    </aside>
  );
}

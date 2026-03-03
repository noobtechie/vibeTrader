"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { brokerageApi, authApi } from "@/lib/api";
import { AlertCircle, CheckCircle, ExternalLink, Plug, Unplug } from "lucide-react";
import toast from "react-hot-toast";

function TickerSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await brokerageApi.searchSymbols(query);
      setResults(res.data.symbols || []);
    } catch {
      toast.error("Symbol search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5">
      <h3 className="font-semibold text-white mb-4">Symbol Search</h3>
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="Search symbol (e.g. AAPL, SPY)"
          className="flex-1 bg-[#0f172a] border border-[#475569] rounded-lg px-4 py-2 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? "..." : "Search"}
        </button>
      </div>
      {results.length > 0 && (
        <div className="mt-3 space-y-1 max-h-48 overflow-y-auto">
          {(results as Array<{ symbol: string; symbolId: number; description: string; securityType: string; currency?: string }>).map((sym) => (
            <div
              key={sym.symbolId}
              className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-[#334155] cursor-pointer"
            >
              <div>
                <span className="text-white font-medium text-sm">{sym.symbol}</span>
                <span className="ml-2 text-xs text-slate-400">{sym.description}</span>
              </div>
              <span className="text-xs text-slate-500 font-mono">
                {sym.securityType} · {sym.currency}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ConnectPage() {
  const [refreshToken, setRefreshToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLogin, setIsLogin] = useState(true);
  const queryClient = useQueryClient();

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["brokerage-status"],
    queryFn: () => brokerageApi.status().then((r) => r.data),
  });

  const connectMutation = useMutation({
    mutationFn: (token: string) => brokerageApi.connectQuestrade(token),
    onSuccess: () => {
      toast.success("Questrade connected!");
      queryClient.invalidateQueries({ queryKey: ["brokerage-status"] });
      setRefreshToken("");
    },
    onError: () => toast.error("Failed to connect. Check your token."),
  });

  const disconnectMutation = useMutation({
    mutationFn: () => brokerageApi.disconnect(),
    onSuccess: () => {
      toast.success("Disconnected");
      queryClient.invalidateQueries({ queryKey: ["brokerage-status"] });
    },
  });

  const authMutation = useMutation({
    mutationFn: async () => {
      const endpoint = isLogin ? authApi.login : authApi.register;
      const res = await endpoint(email, password);
      localStorage.setItem("access_token", res.data.access_token);
      return res.data;
    },
    onSuccess: () => {
      toast.success(isLogin ? "Logged in!" : "Account created!");
      queryClient.invalidateQueries();
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Auth failed";
      toast.error(msg);
    },
  });

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-white">Connect & Setup</h1>

      {/* Auth section */}
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5">
        <h3 className="font-semibold text-white mb-4">
          {isLogin ? "Sign In" : "Create Account"}
        </h3>
        <div className="space-y-3">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            className="w-full bg-[#0f172a] border border-[#475569] rounded-lg px-4 py-2 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && authMutation.mutate()}
            placeholder="Password"
            className="w-full bg-[#0f172a] border border-[#475569] rounded-lg px-4 py-2 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={() => authMutation.mutate()}
            disabled={authMutation.isPending}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-2 rounded-lg font-medium transition-colors"
          >
            {authMutation.isPending ? "..." : isLogin ? "Sign In" : "Register"}
          </button>
          <button
            onClick={() => setIsLogin(!isLogin)}
            className="w-full text-sm text-slate-400 hover:text-white"
          >
            {isLogin ? "Need an account? Register" : "Already have an account? Sign in"}
          </button>
        </div>
      </div>

      {/* Questrade connection */}
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-white">Questrade</h3>
          {status?.is_connected ? (
            <span className="flex items-center gap-1.5 text-sm text-profit">
              <CheckCircle className="w-4 h-4" />
              Connected
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-sm text-slate-400">
              <AlertCircle className="w-4 h-4" />
              Not connected
            </span>
          )}
        </div>

        {status?.is_connected ? (
          <div className="space-y-3">
            <div className="bg-[#0f172a] rounded-lg p-3 text-sm text-slate-400 font-mono">
              <div>Server: {status.api_server}</div>
              <div>Expires: {status.expires_at ? new Date(status.expires_at).toLocaleString() : "N/A"}</div>
            </div>
            <button
              onClick={() => disconnectMutation.mutate()}
              disabled={disconnectMutation.isPending}
              className="flex items-center gap-2 text-loss hover:text-red-400 text-sm"
            >
              <Unplug className="w-4 h-4" />
              Disconnect
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">
              Get your refresh token from the{" "}
              <a
                href="https://login.questrade.com/APIhub"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:underline inline-flex items-center gap-1"
              >
                Questrade API Hub <ExternalLink className="w-3 h-3" />
              </a>
            </p>
            <input
              type="password"
              value={refreshToken}
              onChange={(e) => setRefreshToken(e.target.value)}
              placeholder="Paste your refresh token here"
              className="w-full bg-[#0f172a] border border-[#475569] rounded-lg px-4 py-2 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => connectMutation.mutate(refreshToken)}
              disabled={connectMutation.isPending || !refreshToken}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Plug className="w-4 h-4" />
              {connectMutation.isPending ? "Connecting..." : "Connect Questrade"}
            </button>
          </div>
        )}
      </div>

      {/* Symbol search (only when connected) */}
      {status?.is_connected && <TickerSearch />}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MacroDashboard } from "@/lib/types";
import { formatPrice } from "@/lib/format";
import { EarningsList, MacroEventList, SectorHeatmap } from "@/components/MacroWidgets";

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-xl font-bold ${accent ?? "text-slate-100"}`}>{value}</div>
    </div>
  );
}

export default function MacroPage() {
  const [data, setData] = useState<MacroDashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .macroDashboard()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load macro data"));
  }, []);

  if (error) return <p className="text-sm text-red-400">{error}</p>;
  if (!data) return <p className="text-sm text-slate-400">Loading macro data…</p>;

  const snap = data.snapshot;
  const regimeColor =
    snap?.regime === "bullish" ? "text-emerald-400" : snap?.regime === "bearish" ? "text-red-400" : "text-amber-400";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold sm:text-2xl">Macro Dashboard</h1>
        <p className="text-sm text-slate-400">Market regime, volatility, rates, and the event calendar.</p>
      </div>

      {snap && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Regime" value={snap.regime} accent={regimeColor} />
          <Stat label="SPY" value={formatPrice(snap.spy_close)} />
          <Stat label="SPY 200d MA" value={formatPrice(snap.spy_ma200)} />
          <Stat label="VIX" value={formatPrice(snap.vix)} />
          <Stat label="10Y Yield" value={snap.ten_year_yield ? `${snap.ten_year_yield.toFixed(2)}%` : "—"} />
          <Stat label="Fed Funds" value={snap.fed_funds_rate ? `${snap.fed_funds_rate.toFixed(2)}%` : "—"} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="mb-3 text-sm font-semibold">Sector Relative Strength</h3>
          <SectorHeatmap data={data.sector_heatmap} />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="mb-3 text-sm font-semibold">Economic Calendar</h3>
          <MacroEventList events={data.macro_events} />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="mb-3 text-sm font-semibold">Upcoming Earnings</h3>
          <EarningsList earnings={data.earnings} />
        </div>
      </div>
    </div>
  );
}

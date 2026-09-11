"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { MacroDashboard, SignalListResponse, Summary } from "@/lib/types";
import { SummaryCards } from "@/components/SummaryCards";
import { SignalTable } from "@/components/SignalTable";
import { SignalCard } from "@/components/SignalCard";
import { EMPTY_FILTERS, Filters, type FilterState } from "@/components/Filters";
import { EarningsList, MacroEventList, SectorHeatmap } from "@/components/MacroWidgets";
import { RefreshButton } from "@/components/RefreshButton";
import { Collapsible } from "@/components/Collapsible";

export default function HomePage() {
  const { token } = useAuth();
  const [data, setData] = useState<SignalListResponse | null>(null);
  const [macro, setMacro] = useState<MacroDashboard | null>(null);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  // Debounce filter changes into a single fetch.
  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      const params: Record<string, string | number | boolean | undefined> = {
        all: showAll,
        type: filters.type,
        sector: filters.sector,
        min_confidence: filters.min_confidence ? Number(filters.min_confidence) : undefined,
        min_price: filters.min_price ? Number(filters.min_price) : undefined,
        max_price: filters.max_price ? Number(filters.max_price) : undefined,
        exclude_earnings_week: filters.exclude_earnings_week,
        exclude_macro_risk: filters.exclude_macro_risk,
      };
      api
        .dailySignals(params)
        .then(setData)
        .catch((e) => setError(e instanceof Error ? e.message : "Failed to load signals"))
        .finally(() => setLoading(false));
    }, 350);
    return () => clearTimeout(t);
  }, [filters, showAll, reload]);

  useEffect(() => {
    api
      .macroDashboard()
      .then(setMacro)
      .catch(() => setMacro(null));
  }, [reload]);

  const summary = (data?.summary as unknown as Summary) ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold sm:text-2xl">Daily Signals</h1>
          <p className="text-sm text-slate-400">
            Top swing-trading setups for liquid US equities · {summary?.generated_at ?? "—"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setShowAll(false)}
            className={`min-h-[44px] rounded-lg px-4 text-sm font-medium ${
              !showAll ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-300"
            }`}
          >
            Top 20
          </button>
          <button
            onClick={() => setShowAll(true)}
            className={`min-h-[44px] rounded-lg px-4 text-sm font-medium ${
              showAll ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-300"
            }`}
          >
            All
          </button>
          {token && <RefreshButton onDone={() => setReload((r) => r + 1)} />}
        </div>
      </div>

      <SummaryCards summary={summary} />

      <Filters
        filters={filters}
        onChange={(patch) => setFilters((f) => ({ ...f, ...patch }))}
        onReset={() => setFilters(EMPTY_FILTERS)}
      />

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-sm text-slate-400">Loading signals…</p>}
      {!loading && data && data.signals.length === 0 && (
        <p className="text-sm text-slate-400">No signals match the current filters.</p>
      )}

      {data && data.signals.length > 0 && (
        <>
          <SignalTable signals={data.signals} />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:hidden">
            {data.signals.map((s) => (
              <SignalCard key={s.id} signal={s} />
            ))}
          </div>
        </>
      )}

      {macro && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            Macro &amp; Events
          </h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Collapsible title="Upcoming Macro Events" subtitle={`${macro.macro_events.length}`}>
              <MacroEventList events={macro.macro_events} />
            </Collapsible>
            <Collapsible title="Upcoming Earnings" subtitle={`${macro.earnings.length}`}>
              <EarningsList earnings={macro.earnings} />
            </Collapsible>
            <Collapsible title="Sector Heatmap" subtitle="relative strength">
              <SectorHeatmap data={macro.sector_heatmap} />
            </Collapsible>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AccuracyResponse, SignalListResponse, Timeframe } from "@/lib/types";
import { TIMEFRAME_DESCRIPTIONS, TIMEFRAME_LABELS } from "@/lib/types";
import { SignalTable } from "@/components/SignalTable";
import { SignalCard } from "@/components/SignalCard";
import { EMPTY_FILTERS, Filters, type FilterState } from "@/components/Filters";
import { TimeframeTabs } from "@/components/TimeframeTabs";
import { AccuracyPanel } from "@/components/AccuracyPanel";

const PAGE_SIZE = 50;

export default function HistoryPage() {
  const [timeframe, setTimeframe] = useState<Timeframe>("DAILY");
  const [data, setData] = useState<SignalListResponse | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracyResponse | null>(null);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      const params: Record<string, string | number | boolean | undefined> = {
        limit: PAGE_SIZE,
        offset,
        timeframe,
        type: filters.type,
        setup: filters.setup,
        sector: filters.sector,
        min_confidence: filters.min_confidence ? Number(filters.min_confidence) : undefined,
        min_price: filters.min_price ? Number(filters.min_price) : undefined,
        max_price: filters.max_price ? Number(filters.max_price) : undefined,
        exclude_earnings_week: filters.exclude_earnings_week,
        exclude_macro_risk: filters.exclude_macro_risk,
      };
      api
        .signals(params)
        .then(setData)
        .catch((e) => setError(e instanceof Error ? e.message : "Failed to load history"))
        .finally(() => setLoading(false));
    }, 350);
    return () => clearTimeout(t);
  }, [filters, offset, timeframe]);

  useEffect(() => {
    api
      .accuracy(timeframe)
      .then(setAccuracy)
      .catch(() => setAccuracy(null));
  }, [timeframe, data]);

  const total = data?.total ?? 0;
  const decided = accuracy?.decided ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold sm:text-2xl">Signal History</h1>
        <p className="text-sm text-slate-400">
          Every stored pick for the selected interval, with its result once it has resolved.
        </p>
      </div>

      <div className="space-y-2">
        <TimeframeTabs
          value={timeframe}
          onChange={(next) => {
            setTimeframe(next);
            setOffset(0);
          }}
        />
        <p className="text-xs text-slate-500">{TIMEFRAME_DESCRIPTIONS[timeframe]}</p>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
          How {TIMEFRAME_LABELS[timeframe].toLowerCase()} picks have performed
        </h2>
        <AccuracyPanel accuracy={accuracy} timeframe={timeframe} />
      </div>

      <Filters
        filters={filters}
        onChange={(patch) => {
          setFilters((f) => ({ ...f, ...patch }));
          setOffset(0);
        }}
        onReset={() => {
          setFilters(EMPTY_FILTERS);
          setOffset(0);
        }}
      />

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-sm text-slate-400">Loading…</p>}

      {!loading && data && data.signals.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
          <p className="font-medium text-slate-300">
            No {TIMEFRAME_LABELS[timeframe].toLowerCase()} picks match these filters.
          </p>
          <p className="mt-1 text-xs">
            The rules are strict, so a quieter interval can legitimately produce nothing. A monthly
            list needs several years of price history — run a data refresh if the higher intervals
            look empty.
          </p>
        </div>
      )}

      {data && data.signals.length > 0 && (
        <>
          <SignalTable signals={data.signals} showOutcome />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:hidden">
            {data.signals.map((s) => (
              <SignalCard key={s.id} signal={s} />
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              className="min-h-[44px] rounded-lg border border-slate-700 px-4 text-sm disabled:opacity-40"
            >
              ← Previous
            </button>
            <span className="text-xs text-slate-400">
              {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              {decided > 0 ? ` · ${decided} resolved` : ""}
            </span>
            <button
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              className="min-h-[44px] rounded-lg border border-slate-700 px-4 text-sm disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}

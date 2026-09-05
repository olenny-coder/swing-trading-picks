"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import type { SignalDetail } from "@/lib/types";
import { ConfidenceBadge, TypeBadge } from "@/components/Badges";
import { formatDate, formatPrice } from "@/lib/format";

const PriceChart = dynamic(() => import("@/components/PriceChart"), { ssr: false });

const COMPONENT_LABELS: Record<string, string> = {
  technical: "Technical confluence",
  backtest: "Backtest performance",
  regime: "Regime alignment",
  sector: "Sector strength",
  volume: "Volume confirmation",
  macro: "Macro / earnings risk",
};

function Level({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-lg bg-slate-800/50 p-3">
      <div className="text-[11px] uppercase text-slate-400">{label}</div>
      <div className={`font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}

export default function SignalDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [data, setData] = useState<SignalDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .signalDetail(id)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load signal"));
  }, [id]);

  if (error) return <p className="text-sm text-red-400">{error}</p>;
  if (!data) return <p className="text-sm text-slate-400">Loading…</p>;

  const s = data.signal;
  const flags = (s.event_flags ?? {}) as Record<string, unknown>;
  const components = s.confidence_components ?? {};

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-emerald-400">{s.ticker}</h1>
            <TypeBadge type={s.type} />
          </div>
          <p className="text-sm text-slate-400">
            {s.name} · {s.sector ?? "Unknown sector"} · {formatDate(s.date)}
          </p>
        </div>
        <div className="ml-auto">
          <ConfidenceBadge value={s.confidence} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Level label="Entry" value={formatPrice(s.entry)} color="text-slate-100" />
        <Level label="Target" value={formatPrice(s.target)} color="text-emerald-400" />
        <Level label="Stop" value={formatPrice(s.stop)} color="text-red-400" />
      </div>

      {s.type === "PUT" && s.option_recommendation && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="mb-3 text-sm font-semibold">Put option recommendation</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Level label="Strike" value={`P${formatPrice(s.option_recommendation.strike)}`} color="text-slate-100" />
            <Level label="Premium (entry)" value={formatPrice(s.option_recommendation.option_entry)} color="text-slate-100" />
            <Level label="Option target" value={formatPrice(s.option_recommendation.option_target)} color="text-emerald-400" />
            <Level label="Option stop" value={formatPrice(s.option_recommendation.option_stop)} color="text-red-400" />
          </div>
          <p className="mt-3 text-xs text-slate-400">
            {s.option_recommendation.symbol} · OI {s.option_recommendation.open_interest ?? "—"} · IV{" "}
            {s.option_recommendation.implied_volatility
              ? `${(s.option_recommendation.implied_volatility * 100).toFixed(1)}%`
              : "—"}
          </p>
        </div>
      )}

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <h3 className="mb-3 text-sm font-semibold">Price chart & indicators</h3>
        {data.doji_highlight && (
          <p className="mb-2 text-xs text-violet-400">Doji candle detected in this series.</p>
        )}
        <PriceChart bars={data.bars} ema20={data.indicators.ema20} ema50={data.indicators.ema50} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="mb-3 text-sm font-semibold">Triggered rules</h3>
          <ul className="space-y-1">
            {(s.triggered_rules ?? []).map((r) => (
              <li key={r} className="text-sm text-slate-300">
                • {r.replace(/_/g, " ")}
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="mb-3 text-sm font-semibold">Confidence breakdown</h3>
          <ul className="space-y-2">
            {Object.entries(COMPONENT_LABELS).map(([key, label]) => (
              <li key={key}>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="text-slate-400">{label}</span>
                  <span className="text-slate-200">{Math.round(components[key] ?? 0)}</span>
                </div>
                <div className="h-1.5 w-full rounded bg-slate-800">
                  <div
                    className="h-1.5 rounded bg-emerald-500"
                    style={{ width: `${Math.round(components[key] ?? 0)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <h3 className="mb-3 text-sm font-semibold">Event context</h3>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded bg-slate-800 px-2 py-1">Regime: {String(flags.regime ?? "—")}</span>
          <span className="rounded bg-slate-800 px-2 py-1">VIX: {flags.vix ? formatPrice(Number(flags.vix)) : "—"}</span>
          <span className="rounded bg-slate-800 px-2 py-1">
            Earnings:{" "}
            {typeof flags.earnings_in_days === "number" ? `${flags.earnings_in_days}d` : "none near"}
          </span>
          <span className="rounded bg-slate-800 px-2 py-1">
            Macro risk: {flags.macro_risk ? "yes" : "no"}
          </span>
          <span className="rounded bg-slate-800 px-2 py-1">
            Macro sentiment:{" "}
            {typeof flags.macro_sentiment === "number"
              ? flags.macro_sentiment > 0.05
                ? "positive"
                : flags.macro_sentiment < -0.05
                  ? "negative"
                  : "neutral"
              : "—"}
          </span>
          <span className="rounded bg-slate-800 px-2 py-1">Sector rotation: {String(flags.sector_rotation ?? "—")}</span>
        </div>
      </div>
    </div>
  );
}

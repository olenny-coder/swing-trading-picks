"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import type { SignalDetail } from "@/lib/types";
import { ConfidenceBadge, TypeBadge } from "@/components/Badges";
import { Collapsible } from "@/components/Collapsible";
import { confidenceLabel, formatDate, formatPrice } from "@/lib/format";

const PriceChart = dynamic(() => import("@/components/PriceChart"), { ssr: false });

const COMPONENT_LABELS: Record<string, string> = {
  technical: "Technical confluence",
  backtest: "Backtest performance",
  regime: "Regime alignment",
  sector: "Sector strength",
  volume: "Volume confirmation",
  macro: "Macro / earnings risk",
};

const COMPONENT_EXPLANATIONS: Record<string, string> = {
  technical: "How many of the strategy's conditions this setup satisfies (more conditions → higher score).",
  backtest: "Historical win rate for this signal type (from the backtest, or the default prior).",
  regime: "How well the market regime (bullish / neutral / bearish) matches the signal's direction.",
  sector: "Whether the stock's sector is leading or lagging the market (rotation).",
  volume: "Current volume versus its 20-day average — confirms participation.",
  macro: "Upcoming high-impact events, earnings proximity, rate sensitivity, and net economic-calendar sentiment.",
};

// Must match backend/app/core/confidence.py
const WEIGHTS: Record<string, number> = {
  technical: 0.4,
  backtest: 0.2,
  regime: 0.15,
  sector: 0.1,
  volume: 0.05,
  macro: 0.1,
};

function Level({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-lg bg-slate-800/50 p-3">
      <div className="text-[11px] uppercase text-slate-400">{label}</div>
      <div className={`font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}

function ConfidenceDerivation({
  components,
  confidence,
}: {
  components: Record<string, number>;
  confidence: number;
}) {
  const rows = Object.keys(WEIGHTS).map((key) => {
    const raw = components[key] ?? 0;
    const weight = WEIGHTS[key];
    return { key, label: COMPONENT_LABELS[key] ?? key, raw, weight, contribution: raw * weight };
  });
  const total = rows.reduce((acc, r) => acc + r.contribution, 0);

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        Confidence is a <strong className="text-slate-200">weighted sum of six sub-scores</strong> (each
        scored 0–100). The table shows each component&apos;s score, its weight, and how much it
        contributed to the final number.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[440px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="py-2 pr-3">Component</th>
              <th className="py-2 pr-3">Score</th>
              <th className="py-2 pr-3">Weight</th>
              <th className="py-2">Contribution</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-slate-800">
                <td className="py-2 pr-3 text-slate-300">{r.label}</td>
                <td className="py-2 pr-3 font-mono">{Math.round(r.raw)}</td>
                <td className="py-2 pr-3 font-mono text-slate-400">{Math.round(r.weight * 100)}%</td>
                <td className="py-2 font-mono text-emerald-400">{r.contribution.toFixed(1)}</td>
              </tr>
            ))}
            <tr className="border-t border-slate-600 font-semibold">
              <td className="py-2 pr-3">Total</td>
              <td className="py-2 pr-3" />
              <td className="py-2 pr-3 font-mono text-slate-400">100%</td>
              <td className="py-2 font-mono text-emerald-400">{total.toFixed(1)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p className="text-sm text-slate-300">
        Final confidence:{" "}
        <span className="font-mono font-semibold text-emerald-400">{confidence.toFixed(1)}</span> →{" "}
        <span className="font-semibold">{confidenceLabel(confidence)}</span>
      </p>

      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          What each component means
        </h4>
        <ul className="space-y-1 text-xs text-slate-400">
          {Object.keys(WEIGHTS).map((key) => (
            <li key={key}>
              • <span className="text-slate-300">{COMPONENT_LABELS[key]}</span> —{" "}
              {COMPONENT_EXPLANATIONS[key]}
            </li>
          ))}
        </ul>
      </div>

      <p className="text-xs text-slate-500">
        Labels: Low 0–40 · Medium 41–70 · High 71–100. Earnings within 7 days suppresses a signal
        entirely unless confidence is above 80 and earnings plays are enabled.
      </p>
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
  const components = (s.confidence_components ?? {}) as Record<string, number>;

  return (
    <div className="space-y-4">
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

      {s.type === "SELL" && s.option_recommendation && (
        <Collapsible title="Put option recommendation" subtitle={s.option_recommendation.symbol}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Level
              label="Strike"
              value={`P${formatPrice(s.option_recommendation.strike)}`}
              color="text-slate-100"
            />
            <Level
              label="Premium (entry)"
              value={formatPrice(s.option_recommendation.option_entry)}
              color="text-slate-100"
            />
            <Level
              label="Option target"
              value={formatPrice(s.option_recommendation.option_target)}
              color="text-emerald-400"
            />
            <Level
              label="Option stop"
              value={formatPrice(s.option_recommendation.option_stop)}
              color="text-red-400"
            />
          </div>
          <p className="mt-3 text-xs text-slate-400">
            Open interest {s.option_recommendation.open_interest ?? "—"} · IV{" "}
            {s.option_recommendation.implied_volatility
              ? `${(s.option_recommendation.implied_volatility * 100).toFixed(1)}%`
              : "—"}
          </p>
        </Collapsible>
      )}

      {s.type === "SELL" && !s.option_recommendation && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-200">
          No options chain was available for this ticker (an Alpaca options subscription or a
          Polygon.io key is required), so only the underlying price levels are shown.
        </div>
      )}

      <Collapsible title="Price chart & indicators" subtitle="EMA 20 / 50 overlay">
        {data.doji_highlight && (
          <p className="mb-2 text-xs text-violet-400">Doji candle detected in this series.</p>
        )}
        <PriceChart bars={data.bars} ema20={data.indicators.ema20} ema50={data.indicators.ema50} />
      </Collapsible>

      <Collapsible title="Triggered rules" subtitle={`${(s.triggered_rules ?? []).length} matched`}>
        <ul className="space-y-1">
          {(s.triggered_rules ?? []).map((r) => (
            <li key={r} className="text-sm text-slate-300">
              • {r.replace(/_/g, " ")}
            </li>
          ))}
          {(s.triggered_rules ?? []).length === 0 && (
            <li className="text-sm text-slate-500">No individual rules recorded.</li>
          )}
        </ul>
      </Collapsible>

      <Collapsible title="Confidence breakdown" subtitle={`${Math.round(s.confidence)} / 100`}>
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
      </Collapsible>

      <Collapsible title="Event context" subtitle="macro, earnings & regime flags" defaultOpen={false}>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded bg-slate-800 px-2 py-1">Regime: {String(flags.regime ?? "—")}</span>
          <span className="rounded bg-slate-800 px-2 py-1">
            VIX: {flags.vix ? formatPrice(Number(flags.vix)) : "—"}
          </span>
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
          <span className="rounded bg-slate-800 px-2 py-1">
            Sector rotation: {String(flags.sector_rotation ?? "—")}
          </span>
        </div>
      </Collapsible>

      <Collapsible title="How confidence was derived" subtitle="weighted sub-score math">
        <ConfidenceDerivation components={components} confidence={s.confidence} />
      </Collapsible>
    </div>
  );
}

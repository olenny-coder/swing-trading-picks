"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import type { SignalDetail } from "@/lib/types";
import {
  AdjustedConfidence,
  ConfidenceBadge,
  SentimentBadge,
  SetupBadge,
  TypeBadge,
  flagLabel,
} from "@/components/Badges";
import { Collapsible } from "@/components/Collapsible";
import { DemoBanner } from "@/components/DemoBanner";
import { SETUP_LABELS } from "@/lib/types";
import { confidenceLabel, formatDate, formatPrice } from "@/lib/format";

const PriceChart = dynamic(() => import("@/components/PriceChart"), { ssr: false });

// Factor groups behind the blended confidence. Keys must match
// backend/app/core/sma_strategy.py (CONTINUATION_FACTORS / REVERSAL_FACTORS).
const CONTINUATION_FACTORS: Record<string, string> = {
  trend_separation: "Price beyond the 50 SMA, measured in ATRs",
  ma_alignment: "Separation of the 20 and 50 SMA",
  pullback_control: "How shallow and orderly the pullback was",
  structure_clean: "No counter-flush against the trend",
  trigger_strength: "Entry candle quality + how decisively it cleared the LP",
  participation: "Volume versus its 20-day average",
};

const REVERSAL_FACTORS: Record<string, string> = {
  flush_intensity: "Size and aggression of the flush into the level",
  liquidity_sweep: "Whether a prior swing extreme was taken out",
  reversal_trigger: "Recovery candle quality + how far it reclaimed",
  exhaustion: "RSI stretch and distance from the mean",
  structure: "Pattern quality (double top/bottom, retracement depth)",
};

const GROUP_LABELS: Record<string, string> = {
  continuation: "Continuation",
  reversal: "Reversal",
};

function signed(value: number, digits = 1): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function Level({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-lg bg-slate-800/50 p-3">
      <div className="text-[11px] uppercase text-slate-400">{label}</div>
      <div className={`font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}

function FactorList({
  title,
  factors,
  components,
}: {
  title: string;
  factors: Record<string, string>;
  components: Record<string, number>;
}) {
  const rows = Object.entries(factors).filter(([key]) => `factor_${key}` in components);
  if (rows.length === 0) return null;
  return (
    <div>
      <h5 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h5>
      <ul className="space-y-1 text-xs text-slate-400">
        {rows.map(([key, label]) => (
          <li key={key} className="flex items-baseline justify-between gap-3">
            <span>
              • <span className="text-slate-300">{label}</span>
            </span>
            <span className="font-mono text-slate-300">
              {Math.round(components[`factor_${key}`])}
            </span>
          </li>
        ))}
      </ul>
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
  const cont = components.continuation ?? 0;
  const rev = components.reversal ?? 0;
  const cw = components.continuation_weight ?? 50;
  const rw = components.reversal_weight ?? 50;
  const blend = components.blend ?? 0;

  const groups = [
    { key: "continuation", score: cont, weight: cw },
    { key: "reversal", score: rev, weight: rw },
  ];

  const adjustments = [
    {
      key: "regime_adjustment",
      label: "Regime alignment",
      value: components.regime_adjustment ?? 0,
    },
    {
      key: "sector_adjustment",
      label: "Sector rotation",
      value: components.sector_adjustment ?? 0,
    },
    {
      key: "counter_impact",
      label: "Counter impact (macro/media against the trade)",
      value: components.counter_impact ?? 0,
    },
  ];

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-400">
        Confidence is a <strong className="text-slate-200">blended rating</strong> built from two
        factor groups, each scored 0–100:
      </p>
      <ul className="space-y-1 text-sm text-slate-400">
        <li>
          • <span className="text-slate-200">Continuation factors</span> describe the trend the setup
          wants to ride.
        </li>
        <li>
          • <span className="text-slate-200">Reversal factors</span> describe the turn that triggers
          the entry — the end of a pullback for continuation setups, or a genuine change of direction
          for reversal setups.
        </li>
      </ul>
      <p className="text-sm text-slate-400">
        The two are weighted according to the setup family (continuation setups lean on continuation
        evidence; reversal setups lean on reversal evidence), then a small set of context adjustments
        is applied.
      </p>

      {/* Step 1 — the blend */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[460px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="py-2 pr-3">Factor group</th>
              <th className="py-2 pr-3">Score</th>
              <th className="py-2 pr-3">Weight</th>
              <th className="py-2">Contribution</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.key} className="border-t border-slate-800">
                <td className="py-2 pr-3 text-slate-300">{GROUP_LABELS[g.key]}</td>
                <td className="py-2 pr-3 font-mono">{Math.round(g.score)}</td>
                <td className="py-2 pr-3 font-mono text-slate-400">{Math.round(g.weight)}%</td>
                <td className="py-2 font-mono text-emerald-400">
                  {((g.score * g.weight) / 100).toFixed(1)}
                </td>
              </tr>
            ))}
            <tr className="border-t border-slate-600 font-semibold">
              <td className="py-2 pr-3">Blend</td>
              <td className="py-2 pr-3" />
              <td className="py-2 pr-3 font-mono text-slate-400">100%</td>
              <td className="py-2 font-mono text-emerald-400">{blend.toFixed(1)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Step 2 — context adjustments */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[460px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="py-2 pr-3">Context adjustment</th>
              <th className="py-2">Impact</th>
            </tr>
          </thead>
          <tbody>
            {adjustments.map((a) => (
              <tr key={a.key} className="border-t border-slate-800">
                <td className="py-2 pr-3 text-slate-300">{a.label}</td>
                <td
                  className={`py-2 font-mono ${
                    a.value > 0 ? "text-emerald-400" : a.value < 0 ? "text-red-400" : "text-slate-400"
                  }`}
                >
                  {signed(a.value)}
                </td>
              </tr>
            ))}
            <tr className="border-t border-slate-600 font-semibold">
              <td className="py-2 pr-3">
                Blend {blend.toFixed(1)} {adjustments.map((a) => signed(a.value)).join(" ")}
              </td>
              <td className="py-2 font-mono text-emerald-400">{confidence.toFixed(1)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p className="text-sm text-slate-300">
        Blended confidence:{" "}
        <span className="font-mono font-semibold text-emerald-400">{confidence.toFixed(1)}</span> →{" "}
        <span className="font-semibold">{confidenceLabel(confidence)}</span>
      </p>

      <div className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          What each factor measures
        </h4>
        <FactorList title="Continuation factors" factors={CONTINUATION_FACTORS} components={components} />
        <FactorList title="Reversal factors" factors={REVERSAL_FACTORS} components={components} />
      </div>

      <p className="text-xs text-slate-500">
        Labels: Low 0–40 · Medium 41–70 · High 71–100. A structural stop further than 15% from entry
        is rejected as untradeable, and earnings within 7 days suppress the signal entirely unless
        confidence is above 80 and earnings plays are enabled. The blend weights are
        <code className="mx-1 rounded bg-slate-800 px-1">FAMILY_WEIGHTS</code> in
        <code className="mx-1 rounded bg-slate-800 px-1">backend/app/core/sma_strategy.py</code>.
      </p>
    </div>
  );
}

function SignalDetail() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id") ?? "";
  const [data, setData] = useState<SignalDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) {
      setError("No signal selected.");
      return;
    }
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
            <SetupBadge setup={s.setup} type={s.type} />
            <TypeBadge type={s.type} />
          </div>
          <p className="text-sm text-slate-400">
            {s.name} · {s.sector ?? "Unknown sector"} · {formatDate(s.date)}
          </p>
          <p className="text-xs text-slate-500">{SETUP_LABELS[s.setup] ?? s.setup}</p>
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

      {data.demo && <DemoBanner />}

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

      <Collapsible
        title="LLM research"
        subtitle={
          s.annotation
            ? `${s.annotation.sentiment} · ${s.annotation.model ?? "model"}`
            : "not run yet"
        }
        defaultOpen={Boolean(s.annotation)}
      >
        {s.annotation ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <SentimentBadge sentiment={s.annotation.sentiment} />
              <AdjustedConfidence
                base={s.annotation.base_confidence}
                adjusted={s.annotation.adjusted_confidence}
              />
              <span className="text-xs text-slate-500">
                engine score vs LLM-adjusted score (adjustment bounded by the server)
              </span>
            </div>

            {s.annotation.risk_flags.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {s.annotation.risk_flags.map((flag) => (
                  <span
                    key={flag}
                    className="rounded bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300"
                  >
                    {flagLabel(flag)}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500">No risk flags raised.</p>
            )}

            {s.annotation.rationale && (
              <p className="text-sm text-slate-300">{s.annotation.rationale}</p>
            )}

            <p className="text-xs text-slate-500">
              {s.annotation.model}
              {s.annotation.created_at ? ` · ${s.annotation.created_at}` : ""} · generated
              commentary, informational only — not financial advice.
            </p>
          </div>
        ) : (
          <p className="text-sm text-slate-400">
            This signal has not been annotated yet. An admin can run the research agent from the
            Daily View (requires a Groq API key).
          </p>
        )}
      </Collapsible>

      <Collapsible
        title="Counter impact"
        subtitle="macro & media arguing against this trade"
        defaultOpen={
          Boolean((flags.counter_impact_drivers as string[] | undefined)?.length) ||
          Boolean(s.annotation?.counter_impact)
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-slate-400">
            What argues <strong className="text-slate-200">against</strong> this {s.type}{" "}
            recommendation — the &ldquo;counter&rdquo; case. Both rows are penalties: they are
            subtracted inside the blended confidence, and a media figure only exists once the
            research agent has run.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[440px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="py-2 pr-3">Source</th>
                  <th className="py-2 pr-3">Impact</th>
                  <th className="py-2">What it reflects</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-slate-800">
                  <td className="py-2 pr-3 text-slate-300">Macro events</td>
                  <td
                    className={`py-2 pr-3 font-mono ${
                      Number(flags.counter_impact ?? 0) < 0 ? "text-red-400" : "text-slate-400"
                    }`}
                  >
                    {signed(Number(flags.counter_impact ?? 0))}
                  </td>
                  <td className="py-2 text-xs text-slate-400">
                    {((flags.counter_impact_drivers as string[] | undefined) ?? []).length
                      ? (flags.counter_impact_drivers as string[]).join("; ")
                      : "no material macro opposition"}
                  </td>
                </tr>
                <tr className="border-t border-slate-800">
                  <td className="py-2 pr-3 text-slate-300">Media / news</td>
                  <td className="py-2 pr-3 font-mono text-red-400">
                    {s.annotation?.counter_impact
                      ? `−${Number(s.annotation.counter_impact).toFixed(1)}`
                      : "—"}
                  </td>
                  <td className="py-2 text-xs text-slate-400">
                    {s.annotation
                      ? `research agent read (${s.annotation.sentiment}); its net effect is already inside the ${signed(
                          s.annotation.confidence_delta,
                        )} adjustment`
                      : "run the research agent to assess adverse coverage"}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </Collapsible>

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

      <Collapsible
        title="Confidence breakdown"
        subtitle={`blend ${Math.round(components.blend ?? 0)} → ${Math.round(s.confidence)} / 100`}
      >
        <ul className="space-y-3">
          {[
            {
              key: "continuation",
              label: "Continuation factors",
              weight: components.continuation_weight,
            },
            { key: "reversal", label: "Reversal factors", weight: components.reversal_weight },
          ].map(({ key, label, weight }) => (
            <li key={key}>
              <div className="mb-1 flex justify-between text-xs">
                <span className="text-slate-400">
                  {label}
                  {typeof weight === "number" ? ` · weighted ${Math.round(weight)}%` : ""}
                </span>
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

          <li className="space-y-1 border-t border-slate-800 pt-3 text-xs">
            {[
              ["Regime alignment", components.regime_adjustment],
              ["Sector rotation", components.sector_adjustment],
              ["Counter impact", components.counter_impact],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex justify-between">
                <span className="text-slate-400">{label}</span>
                <span
                  className={`font-mono ${
                    Number(value) > 0
                      ? "text-emerald-400"
                      : Number(value) < 0
                        ? "text-red-400"
                        : "text-slate-400"
                  }`}
                >
                  {signed(Number(value ?? 0))}
                </span>
              </div>
            ))}
          </li>
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

// useSearchParams needs a Suspense boundary in a statically exported page.
export default function SignalDetailPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-400">Loading…</p>}>
      <SignalDetail />
    </Suspense>
  );
}

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
} from "@/components/Badges";
import { Collapsible } from "@/components/Collapsible";
import { DemoBanner } from "@/components/DemoBanner";
import { OutcomeBadge } from "@/components/OutcomeBadge";
import { SETUP_LABELS, TIMEFRAME_LABELS } from "@/lib/types";
import { confidenceLabel, formatDate, formatPrice } from "@/lib/format";
import {
  CONFIDENCE_ADJUSTMENT_LABELS,
  CONTINUATION_FACTORS,
  GROUP_LABELS,
  REVERSAL_FACTORS,
  flagLabel,
  ruleLabel,
} from "@/lib/labels";

const PriceChart = dynamic(() => import("@/components/PriceChart"), { ssr: false });

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
      <h5 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h5>
      <ul className="space-y-2 text-xs">
        {rows.map(([key, label]) => (
          <li key={key} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span aria-hidden="true" className="select-none text-slate-600">
              •
            </span>
            {/* basis-full keeps the description on its own line on a phone, so
                the score never squeezes the text into a narrow column. */}
            <span className="min-w-0 flex-1 basis-full leading-relaxed text-slate-400 sm:basis-0">
              {label}
            </span>
            <span className="font-mono font-semibold text-slate-300">
              {Math.round(components[`factor_${key}`])}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The screener's confidence model: a base plus named factors. */
function SmcConfidenceDerivation({
  components,
  confidence,
}: {
  components: Record<string, unknown>;
  confidence: number;
}) {
  const base = Number(components.base ?? 40);
  const parts = (components.parts ?? {}) as Record<string, number>;
  const factors = (components.factors ?? {}) as Record<string, string>;
  const total = Object.values(parts).reduce((sum, value) => sum + (value ?? 0), 0);

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-slate-400">
        This is an <strong className="text-slate-200">SMC</strong> pick, so the score is not a
        continuation/reversal blend. It starts from a base of{" "}
        <span className="font-mono text-slate-200">{base}</span> points and each factor below adds
        to it, up to a maximum of 100.
      </p>

      <ul className="space-y-2 text-xs">
        <li className="flex flex-wrap items-baseline gap-x-2 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
          <span className="min-w-0 flex-1 basis-full leading-relaxed text-slate-400 sm:basis-0">
            Base score — a valid break of structure with a fair value gap behind it
          </span>
          <span className="font-mono font-semibold text-slate-300">{base}</span>
        </li>
        {Object.entries(parts).map(([key, points]) => (
          <li
            key={key}
            className="flex flex-wrap items-baseline gap-x-2 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2"
          >
            <span className="min-w-0 flex-1 basis-full leading-relaxed text-slate-400 sm:basis-0">
              {factors[key] ?? key}
            </span>
            <span
              className={`font-mono font-semibold ${points > 0 ? "text-emerald-300" : "text-slate-500"}`}
            >
              {points > 0 ? `+${points}` : "0"}
            </span>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-sm">
        <span className="text-slate-300">
          Base {base} + factors {total.toFixed(1)}
        </span>
        <span className="font-mono text-lg font-semibold text-emerald-300">{Math.round(confidence)}</span>
      </div>

      <p className="text-xs leading-relaxed text-slate-500">
        A factor scoring zero means that part of the setup was absent or weak — for example a gap
        that price has already traded fully through, or a stop so tight it sits inside a single
        4-hour bar&apos;s range. Nothing here is adjusted after the fact: the score is fixed from
        closed candles when the pick is raised.
      </p>
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
      label: CONFIDENCE_ADJUSTMENT_LABELS.regime_adjustment,
      value: components.regime_adjustment ?? 0,
    },
    {
      key: "sector_adjustment",
      label: CONFIDENCE_ADJUSTMENT_LABELS.sector_adjustment,
      value: components.sector_adjustment ?? 0,
    },
    {
      key: "counter_impact",
      label: CONFIDENCE_ADJUSTMENT_LABELS.counter_impact,
      value: components.counter_impact ?? 0,
    },
    {
      key: "confirmation_boost",
      label: CONFIDENCE_ADJUSTMENT_LABELS.confirmation_boost,
      value: components.confirmation_boost ?? 0,
    },
  ];

  const volumeRatio = components.volume_ratio;
  const atrMultiple = components.atr_multiple;

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-400">
        Confidence is a <strong className="text-slate-200">blended rating</strong> built from two
        factor groups, each scored from 0 to 100:
      </p>
      <ul className="space-y-2 text-sm text-slate-400">
        <li className="flex gap-2">
          <span aria-hidden="true" className="select-none text-slate-600">
            •
          </span>
          <span className="min-w-0 flex-1 leading-relaxed">
            <span className="text-slate-200">Continuation factors</span> describe the trend the
            setup wants to ride.
          </span>
        </li>
        <li className="flex gap-2">
          <span aria-hidden="true" className="select-none text-slate-600">
            •
          </span>
          <span className="min-w-0 flex-1 leading-relaxed">
            <span className="text-slate-200">Reversal factors</span> describe the turn that triggers
            the entry — the end of a pullback for continuation setups, or a genuine change of
            direction for reversal setups.
          </span>
        </li>
      </ul>
      <p className="text-sm leading-relaxed text-slate-400">
        The two groups are weighted according to the setup family (continuation setups lean on
        continuation evidence, reversal setups lean on reversal evidence). A set of context
        adjustments is then applied, including a bonus when the entry candle is confirmed by both
        traded volume and an expanded range.
      </p>

      {(volumeRatio != null || atrMultiple != null) && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm">
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Volume and range confirmation
          </div>
          <div className="mt-1 flex flex-wrap gap-4 text-slate-300">
            <span>
              Volume:{" "}
              <span className="font-mono">
                {volumeRatio != null ? `${volumeRatio.toFixed(2)}× its 20-period average` : "—"}
              </span>
            </span>
            <span>
              Entry candle range:{" "}
              <span className="font-mono">
                {atrMultiple != null
                  ? `${atrMultiple.toFixed(2)}× the Average True Range`
                  : "—"}
              </span>
            </span>
            <span>
              Bonus awarded:{" "}
              <span className="font-mono text-emerald-400">
                {signed(components.confirmation_boost ?? 0)}
              </span>
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            A setup earns the bonus once volume is above its 20-period average and the entry candle
            is at least 0.8 of an Average True Range. It is never a penalty, so a quiet candle simply
            earns nothing.
          </p>
        </div>
      )}

      {/* Step 1 — the blend. Stacked rows rather than a table: a four-column
          table needs horizontal scrolling on a phone. */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Step 1 — blend the two factor groups
        </h4>
        {groups.map((g) => (
          <div
            key={g.key}
            className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2.5"
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-medium text-slate-200">{GROUP_LABELS[g.key]}</span>
              <span className="font-mono text-slate-100">{Math.round(g.score)}</span>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-slate-400">
              Weighted {Math.round(g.weight)}% → contributes{" "}
              <span className="font-mono text-emerald-400">
                {((g.score * g.weight) / 100).toFixed(1)}
              </span>{" "}
              points
            </p>
          </div>
        ))}
        <div className="flex items-baseline justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2.5 font-semibold">
          <span>Blend</span>
          <span className="font-mono text-emerald-400">{blend.toFixed(1)}</span>
        </div>
      </div>

      {/* Step 2 — context adjustments */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Step 2 — apply the context adjustments
        </h4>
        <ul className="space-y-2">
          {adjustments.map((a) => (
            <li
              key={a.key}
              className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2.5"
            >
              <span className="min-w-0 flex-1 basis-full leading-relaxed text-slate-300 sm:basis-0">
                {a.label}
              </span>
              <span
                className={`font-mono font-semibold ${
                  a.value > 0
                    ? "text-emerald-400"
                    : a.value < 0
                      ? "text-red-400"
                      : "text-slate-400"
                }`}
              >
                {signed(a.value)}
              </span>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2.5 font-semibold">
          <span className="leading-relaxed">
            Blend {blend.toFixed(1)} {adjustments.map((a) => signed(a.value)).join(" ")}
          </span>
          <span className="font-mono text-emerald-400">{confidence.toFixed(1)}</span>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-slate-300">
        Blended confidence:{" "}
        <span className="font-mono font-semibold text-emerald-400">{confidence.toFixed(1)}</span> →{" "}
        <span className="font-semibold">{confidenceLabel(confidence)}</span>
      </p>

      <div className="space-y-4">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          What each factor measures
        </h4>
        <FactorList
          title="Continuation factors"
          factors={CONTINUATION_FACTORS}
          components={components}
        />
        <FactorList title="Reversal factors" factors={REVERSAL_FACTORS} components={components} />
      </div>

      <p className="text-xs leading-relaxed text-slate-500">
        Labels: Low 0–40 · Medium 41–70 · High 71–100. A structural stop further than the timeframe's
        limit is rejected as untradeable, and earnings within 7 days suppress the signal entirely
        unless confidence is above 80 and earnings plays are enabled. The blend weights are
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
  const rawComponents = (s.confidence_components ?? {}) as Record<string, unknown>;
  // SMC picks store {model, base, parts, factors}; the retired engine stored a flat
  // set of factor_* keys. The panel must follow whichever produced the pick.
  const isSmc = s.setup === "SMC" || rawComponents.model === "SMC";

  // ``annotation`` holds two different things: the LLM research note (which has a
  // sentiment) or the screener's own verdict (which has text/reasoning). Reading
  // one as the other is what crashed this page for SMC picks.
  const annotation = (s.annotation ?? null) as Record<string, unknown> | null;
  const research =
    annotation && typeof annotation.sentiment === "string"
      ? (annotation as unknown as {
          sentiment: string;
          model?: string;
          base_confidence: number;
          adjusted_confidence: number;
          confidence_delta: number;
          risk_flags?: string[];
          rationale?: string;
          created_at?: string;
          counter_impact?: number;
        })
      : null;
  const smcVerdict =
    annotation && (annotation.text || annotation.reasoning)
      ? (annotation as { text?: string; reasoning?: string; trend?: string })
      : null;

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
            {s.name} · {s.sector ?? "Unknown sector"} · {formatDate(s.date)} ·{" "}
            {TIMEFRAME_LABELS[s.timeframe] ?? "Daily"} interval
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

      {s.outcome && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
          <span className="text-xs uppercase tracking-wide text-slate-400">Result</span>
          <OutcomeBadge outcome={s.outcome} />
          <span className="text-xs text-slate-500">
            {s.outcome.exit_date ? `closed ${formatDate(s.outcome.exit_date)}` : ""}
            {s.outcome.bars_held ? ` · held ${s.outcome.bars_held} session(s)` : ""}
            {s.outcome.max_favourable_pct != null
              ? ` · best ${signed(s.outcome.max_favourable_pct)}% · worst ${signed(
                  s.outcome.max_adverse_pct,
                )}%`
              : ""}
          </span>
        </div>
      )}

      {data.demo && <DemoBanner />}

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs leading-relaxed text-slate-400">
        Levels are quoted on the underlying itself. This app reads stock prices only — there is no
        options leg, so a bearish setup is traded by selling the underlying (or, for an index future
        such as MES, the contract).
      </div>

      {/* The SMC verdict, when the pick came from the screener. */}
      {smcVerdict && (
        <Collapsible
          title="SMC analysis"
          subtitle={`${smcVerdict.trend ?? ""} · entry ${formatPrice(s.entry)}`}
          defaultOpen
        >
          <div className="space-y-3">
            {smcVerdict.text ? (
              <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950/60 p-3 font-mono text-[12px] leading-relaxed text-slate-200">
                {smcVerdict.text}
              </pre>
            ) : (
              <p className="text-sm text-slate-300">{smcVerdict.reasoning}</p>
            )}
            <p className="text-xs text-slate-500">
              Generated by the screener from closed candles only. Informational, not financial
              advice.
            </p>
          </div>
        </Collapsible>
      )}

      <Collapsible
        title="LLM research"
        subtitle={
          research
            ? `${research.sentiment} · ${research.model ?? "model"}`
            : "not run yet"
        }
        defaultOpen={Boolean(research)}
      >
        {research ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <SentimentBadge sentiment={research.sentiment} />
              <AdjustedConfidence
                base={research.base_confidence}
                adjusted={research.adjusted_confidence}
              />
              <span className="text-xs text-slate-500">
                engine score vs LLM-adjusted score (adjustment bounded by the server)
              </span>
            </div>

            {research.risk_flags && research.risk_flags.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {research.risk_flags.map((flag) => (
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

            {research.rationale && (
              <p className="text-sm text-slate-300">{research.rationale}</p>
            )}

            <p className="text-xs text-slate-500">
              {research.model}
              {research.created_at ? ` · ${research.created_at}` : ""} · generated commentary,
              informational only — not financial advice.
            </p>
          </div>
        ) : (
          <p className="text-sm text-slate-400">
            This pick has not been annotated yet. An admin can run the research agent from the Daily
            View (requires a Groq API key).
          </p>
        )}
      </Collapsible>

      <Collapsible
        title="Counter impact"
        subtitle="macro & media arguing against this trade"
        defaultOpen={
          Boolean((flags.counter_impact_drivers as string[] | undefined)?.length) ||
          Boolean(research?.counter_impact)
        }
      >
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-slate-400">
            What argues <strong className="text-slate-200">against</strong> this {s.type}{" "}
            recommendation — the &ldquo;counter&rdquo; case. Both entries are penalties: they are
            subtracted inside the blended confidence, and a media figure only exists once the
            research agent has run.
          </p>
          <ul className="space-y-2">
            <li className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium text-slate-200">Macro events</span>
                <span
                  className={`font-mono font-semibold ${
                    Number(flags.counter_impact ?? 0) < 0 ? "text-red-400" : "text-slate-400"
                  }`}
                >
                  {signed(Number(flags.counter_impact ?? 0))}
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">
                {((flags.counter_impact_drivers as string[] | undefined) ?? []).length
                  ? (flags.counter_impact_drivers as string[]).join("; ")
                  : "No material macro opposition."}
              </p>
            </li>
            <li className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium text-slate-200">Media and news</span>
                <span className="font-mono font-semibold text-red-400">
                  {research?.counter_impact
                    ? `−${Number(research.counter_impact).toFixed(1)}`
                    : "—"}
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">
                {research
                  ? `Research agent read: ${research.sentiment}. Its net effect is already inside the ${signed(
                      research.confidence_delta,
                    )} adjustment`
                  : "Run the research agent to assess adverse coverage."}
              </p>
            </li>
          </ul>
        </div>
      </Collapsible>

      <Collapsible
        title="Price chart and indicators"
        subtitle="20-period and 50-period exponential moving averages"
      >
        {data.doji_highlight && (
          <p className="mb-2 text-xs text-violet-400">Doji candle detected in this series.</p>
        )}
        <PriceChart bars={data.bars} ema20={data.indicators.ema20} ema50={data.indicators.ema50} />
      </Collapsible>

      <Collapsible title="Triggered rules" subtitle={`${(s.triggered_rules ?? []).length} matched`}>
        <ul className="space-y-2">
          {(s.triggered_rules ?? []).map((rule) => (
            <li key={rule} className="flex gap-2 text-sm text-slate-300">
              <span aria-hidden="true" className="select-none text-slate-600">
                •
              </span>
              {/* Hanging indent: wrapped lines stay aligned under the text
                  rather than under the bullet. */}
              <span className="min-w-0 flex-1 leading-relaxed">{ruleLabel(rule)}</span>
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

      {/* The screener and the retired SMA engine scored confidence differently, so
          the explanation has to follow the model that actually produced the pick. */}
      <Collapsible
        title="How confidence was derived"
        subtitle={isSmc ? "base score plus SMC factors" : "weighted sub-score math"}
        defaultOpen={isSmc}
      >
        {isSmc ? (
          <SmcConfidenceDerivation components={rawComponents} confidence={s.confidence} />
        ) : (
          <ConfidenceDerivation components={components} confidence={s.confidence} />
        )}
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

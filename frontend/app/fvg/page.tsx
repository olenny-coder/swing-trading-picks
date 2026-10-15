"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import type { FvgDrilldown, FvgRow, FvgShortlist, Timeframe } from "@/lib/types";
import { TIMEFRAME_LABELS } from "@/lib/types";
import { TimeframeTabs } from "@/components/TimeframeTabs";
import { DemoBanner } from "@/components/DemoBanner";

const PriceChart = dynamic(() => import("@/components/PriceChart"), { ssr: false });

const STATUS_STYLES: Record<string, string> = {
  BUY: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  SELL: "bg-red-500/15 text-red-300 border-red-500/40",
  WAIT: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  NO_TRADE: "bg-slate-500/15 text-slate-400 border-slate-500/40",
};

const STATUS_LABELS: Record<string, string> = {
  BUY: "BUY",
  SELL: "SELL",
  WAIT: "WAIT",
  NO_TRADE: "NO TRADE",
};

function money(value: number | null | undefined): string {
  if (value == null) return "—";
  return value >= 1000 ? value.toFixed(2) : value.toFixed(value < 10 ? 3 : 2);
}

function StatusBadge({ status, direction }: { status: string; direction: string | null }) {
  const arrow = direction === "BUY" ? "▲" : direction === "SELL" ? "▼" : "";
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-[11px] font-semibold ${
        STATUS_STYLES[status] ?? STATUS_STYLES.NO_TRADE
      }`}
    >
      {arrow} {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const colour = value >= 75 ? "bg-emerald-500" : value >= 55 ? "bg-amber-500" : "bg-slate-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full ${colour}`} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
      <span className="font-mono text-xs text-slate-300">{value.toFixed(0)}</span>
    </div>
  );
}

/** Phone layout: one card per candidate, all twelve columns as labelled rows. */
function RowCard({ row, onSelect }: { row: FvgRow; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-left transition hover:border-slate-700"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-emerald-400">{row.ticker}</span>
            <StatusBadge status={row.status} direction={row.direction} />
          </div>
          <div className="text-[11px] text-slate-500">{row.name}</div>
        </div>
        <ConfidenceBar value={row.confidence} />
      </div>
      <div className="mt-2 text-xs text-slate-300">{row.setup_type}</div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <div>
          <dt className="text-slate-500">Breakout level</dt>
          <dd className="font-mono text-slate-200">{money(row.breakout_level)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">FVG zone</dt>
          <dd className="font-mono text-slate-200">
            {row.fvg_bottom != null && row.fvg_top != null
              ? `${money(row.fvg_bottom)} – ${money(row.fvg_top)}`
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Entry zone</dt>
          <dd className="font-mono text-slate-200">{money(row.entry)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Stop</dt>
          <dd className="font-mono text-red-300">{money(row.stop)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Target 1 / 2</dt>
          <dd className="font-mono text-emerald-300">
            {money(row.target1)} / {money(row.target2)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">R:R</dt>
          <dd className="font-mono text-slate-200">
            {row.rr1 != null ? row.rr1.toFixed(2) : "—"}
            {row.rr2 != null ? ` / ${row.rr2.toFixed(2)}` : ""}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-[11px] leading-relaxed text-slate-400">{row.why}</p>
    </button>
  );
}

export default function FvgPage() {
  const [timeframe, setTimeframe] = useState<Timeframe>("DAILY");
  const [shortlist, setShortlist] = useState<FvgShortlist | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  // The drill-down is deliberately keyed on an explicit selection. Nothing is
  // fetched — and no annotated chart is rendered — until the user picks a ticker.
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<FvgDrilldown | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [showMarkup, setShowMarkup] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError("");
    api
      .fvgShortlist({ timeframe })
      .then(setShortlist)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the screener"))
      .finally(() => setLoading(false));
  }, [timeframe, reload]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setDetailError("");
    api
      .fvgDrilldown(selected, timeframe)
      .then(setDetail)
      .catch((e) => setDetailError(e instanceof Error ? e.message : "Failed to load the chart"))
      .finally(() => setDetailLoading(false));
  }, [selected, timeframe]);

  const rows = shortlist?.rows ?? [];
  const card = detail?.signal_card;

  const markupText = useMemo(
    () => (detail ? JSON.stringify(detail.chart_markup, null, 2) : ""),
    [detail],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold sm:text-2xl">FVG Screener</h1>
          <p className="text-sm text-slate-400">
            Breakout structure plus the Fair Value Gap it left behind. Pick a ticker to open the
            annotated chart and exact levels.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setReload((r) => r + 1)}
          className="min-h-[44px] self-start rounded-lg border border-slate-700 px-4 text-sm hover:border-slate-600"
        >
          ↻ Re-screen
        </button>
      </div>

      {shortlist?.demo && <DemoBanner />}

      <div className="space-y-2">
        <TimeframeTabs
          value={timeframe}
          onChange={(next) => {
            setTimeframe(next);
            setSelected(null);
          }}
        />
        {shortlist && (
          <p className="text-xs leading-relaxed text-slate-500">
            Screened {shortlist.screened} instruments · {shortlist.matched} left a usable structure
            and gap · showing the top {shortlist.max_watchlist}. {shortlist.method}
          </p>
        )}
      </div>

      {shortlist && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-xs leading-relaxed text-slate-400">
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            <span>
              Minimum reward-to-risk{" "}
              <span className="font-mono text-slate-200">{shortlist.settings.min_rr}</span>
            </span>
            <span>
              Risk per trade{" "}
              <span className="font-mono text-slate-200">
                {shortlist.settings.risk_per_trade_pct}%
              </span>
            </span>
            <span>
              Earnings buffer{" "}
              <span className="font-mono text-slate-200">
                {shortlist.settings.earnings_buffer_days} days
              </span>
            </span>
            <span>
              Minimum price{" "}
              <span className="font-mono text-slate-200">{shortlist.settings.min_price}</span>
            </span>
            <span>
              Minimum volume{" "}
              <span className="font-mono text-slate-200">
                {shortlist.settings.min_volume.toLocaleString()}
              </span>
            </span>
          </div>
          {shortlist.settings.market_cap_note && (
            <p className="mt-2 text-amber-300/80">{shortlist.settings.market_cap_note}</p>
          )}
          {shortlist.intraday && !shortlist.intraday.available && (
            <p className="mt-2 text-slate-500">{shortlist.intraday.note}</p>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-sm text-slate-400">Screening…</p>}

      {!loading && shortlist && rows.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
          <p className="font-medium text-slate-300">
            No valid signal on {TIMEFRAME_LABELS[timeframe].toLowerCase()} candles.
          </p>
          <p className="mt-1 text-xs">
            Nothing currently has a confirmed breakout structure with an unmitigated Fair Value Gap
            behind it. That is a legitimate answer — the screener does not force a setup.
          </p>
        </div>
      )}

      {rows.length > 0 && (
        <>
          {/* Desktop: the full shortlist table. */}
          <div className="hidden overflow-x-auto rounded-xl border border-slate-800 lg:block">
            <table className="w-full min-w-[1100px] text-left text-sm">
              <thead className="border-b border-slate-800 bg-slate-900/80 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-3 py-3">Ticker</th>
                  <th className="px-3 py-3">Dir</th>
                  <th className="px-3 py-3">Setup type</th>
                  <th className="px-3 py-3">Breakout</th>
                  <th className="px-3 py-3">FVG zone</th>
                  <th className="px-3 py-3">Entry zone</th>
                  <th className="px-3 py-3">Stop</th>
                  <th className="px-3 py-3">Target 1</th>
                  <th className="px-3 py-3">Target 2</th>
                  <th className="px-3 py-3">R:R</th>
                  <th className="px-3 py-3">Confidence</th>
                  <th className="px-3 py-3">Why</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.ticker}
                    onClick={() => setSelected(row.ticker)}
                    className={`cursor-pointer border-b border-slate-800/60 hover:bg-slate-900/50 ${
                      selected === row.ticker ? "bg-slate-800/50" : ""
                    }`}
                  >
                    <td className="px-3 py-3">
                      <div className="font-semibold text-emerald-400">{row.ticker}</div>
                      <div className="text-[11px] text-slate-500">{row.name}</div>
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge status={row.status} direction={row.direction} />
                    </td>
                    <td className="px-3 py-3 text-xs text-slate-300">{row.setup_type}</td>
                    <td className="px-3 py-3 font-mono text-xs">{money(row.breakout_level)}</td>
                    <td className="px-3 py-3 font-mono text-xs">
                      {row.fvg_bottom != null && row.fvg_top != null
                        ? `${money(row.fvg_bottom)}–${money(row.fvg_top)}`
                        : "—"}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">{money(row.entry)}</td>
                    <td className="px-3 py-3 font-mono text-xs text-red-300">{money(row.stop)}</td>
                    <td className="px-3 py-3 font-mono text-xs text-emerald-300">
                      {money(row.target1)}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs text-emerald-300">
                      {money(row.target2)}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">
                      {row.rr1 != null ? row.rr1.toFixed(2) : "—"}
                      {row.rr2 != null ? ` / ${row.rr2.toFixed(2)}` : ""}
                    </td>
                    <td className="px-3 py-3">
                      <ConfidenceBar value={row.confidence} />
                    </td>
                    <td className="max-w-[260px] px-3 py-3 text-[11px] leading-relaxed text-slate-400">
                      {row.why}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Phones and tablets: one card per candidate. */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
            {rows.map((row) => (
              <RowCard key={row.ticker} row={row} onSelect={() => setSelected(row.ticker)} />
            ))}
          </div>
        </>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Step 2 — only rendered once a ticker has been chosen.               */}
      {/* ------------------------------------------------------------------ */}
      {selected && (
        <section className="space-y-4 rounded-2xl border border-slate-700 bg-slate-900/40 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">
                {selected}
                <span className="ml-2 text-sm font-normal text-slate-400">
                  {TIMEFRAME_LABELS[timeframe]} candles
                  {detail?.as_of ? ` · closed through ${detail.as_of}` : ""}
                </span>
              </h2>
              <p className="text-xs text-slate-500">
                {detail?.name}
                {detail?.sector ? ` · ${detail.sector}` : ""}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="min-h-[40px] rounded-lg border border-slate-700 px-3 text-xs hover:border-slate-600"
            >
              Close drill-down
            </button>
          </div>

          {detailError && <p className="text-sm text-red-400">{detailError}</p>}
          {detailLoading && <p className="text-sm text-slate-400">Loading chart and levels…</p>}

          {detail && card && (
            <>
              {detail.demo && <DemoBanner />}

              {/* Signal card */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge status={card.signal} direction={card.direction} />
                  <span className="text-sm text-slate-300">{card.setup_type}</span>
                  <span className="ml-auto text-xs text-slate-400">
                    Confidence{" "}
                    <span className="font-mono text-slate-200">{card.confidence.toFixed(1)}</span>
                    /100
                  </span>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    { label: "Entry", value: money(card.entry), tone: "text-amber-300" },
                    {
                      label: "Entry zone",
                      value:
                        card.entry_zone?.[0] != null && card.entry_zone?.[1] != null
                          ? `${money(card.entry_zone[0])}–${money(card.entry_zone[1])}`
                          : "—",
                      tone: "text-slate-200",
                    },
                    { label: "Stop", value: money(card.stop), tone: "text-red-300" },
                    { label: "Target 1", value: money(card.target1), tone: "text-emerald-300" },
                    { label: "Target 2", value: money(card.target2), tone: "text-emerald-300" },
                    {
                      label: "R:R (1 / 2)",
                      value: `${card.rr1 != null ? card.rr1.toFixed(2) : "—"} / ${
                        card.rr2 != null ? card.rr2.toFixed(2) : "—"
                      }`,
                      tone: "text-slate-200",
                    },
                  ].map((cell) => (
                    <div key={cell.label} className="rounded-lg border border-slate-800 px-3 py-2">
                      <div className="text-[11px] uppercase tracking-wide text-slate-500">
                        {cell.label}
                      </div>
                      <div className={`font-mono text-sm ${cell.tone}`}>{cell.value}</div>
                    </div>
                  ))}
                </div>

                <p className="mt-3 text-xs leading-relaxed text-slate-400">
                  Risk per share{" "}
                  <span className="font-mono text-slate-200">{money(card.risk_per_share)}</span> ·
                  risking{" "}
                  <span className="font-mono text-slate-200">{card.risk_per_trade_pct}%</span> of
                  the account per trade. {card.invalidation}
                </p>

                {card.reasons.length > 0 && (
                  <ul className="mt-3 space-y-1.5">
                    {card.reasons.map((reason) => (
                      <li key={reason} className="flex gap-2 text-xs text-slate-300">
                        <span aria-hidden="true" className="select-none text-emerald-500">
                          •
                        </span>
                        <span className="min-w-0 flex-1 leading-relaxed">{reason}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {card.blockers.length > 0 && (
                  <ul className="mt-3 space-y-1.5">
                    {card.blockers.map((blocker) => (
                      <li key={blocker} className="flex gap-2 text-xs text-amber-300/90">
                        <span aria-hidden="true" className="select-none">
                          !
                        </span>
                        <span className="min-w-0 flex-1 leading-relaxed">{blocker}</span>
                      </li>
                    ))}
                  </ul>
                )}

                <p className="mt-3 text-[11px] text-slate-500">{card.disclaimer}</p>
              </div>

              {/* Annotated chart */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <PriceChart
                  bars={detail.bars}
                  ema20={detail.indicators.ema20}
                  ema50={detail.indicators.ema50}
                  annotations={detail.annotations}
                />
                <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                  Shaded bands are Fair Value Gaps; the emphasised one is the gap being traded.
                  Dashed lines carry the entry, target and stop levels on the price axis. All
                  candles are closed, so nothing here repaints.
                </p>
              </div>

              {/* Annotation list */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <h3 className="text-sm font-semibold">Chart annotations</h3>
                <ul className="mt-2 space-y-2">
                  {detail.annotations.map((annotation, index) => (
                    <li
                      key={`${annotation.kind}-${annotation.label}-${index}`}
                      className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs"
                    >
                      <span
                        aria-hidden="true"
                        className="mt-1 inline-block h-2 w-2 shrink-0 rounded-sm"
                        style={{ backgroundColor: annotation.color ?? "#38bdf8" }}
                      />
                      <span className="font-medium text-slate-200">{annotation.kind}</span>
                      <span className="min-w-0 flex-1 basis-full leading-relaxed text-slate-400 sm:basis-0">
                        {annotation.label}
                        {annotation.top != null && annotation.bottom != null
                          ? ` · ${money(annotation.bottom)} – ${money(annotation.top)}`
                          : ""}
                        {annotation.price != null ? ` · ${money(annotation.price)}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Structures and open gaps */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                  <h3 className="text-sm font-semibold">Breakout structures detected</h3>
                  <ul className="mt-2 space-y-2">
                    {detail.structures.length === 0 && (
                      <li className="text-xs text-slate-500">None confirmed on this interval.</li>
                    )}
                    {detail.structures.map((structure, index) => (
                      <li
                        key={`${String(structure.kind)}-${index}`}
                        className="text-xs leading-relaxed text-slate-400"
                      >
                        <span className="font-medium text-slate-200">
                          {String(structure.label)}
                        </span>{" "}
                        at <span className="font-mono">{money(Number(structure.level))}</span> ·{" "}
                        {String(structure.detail)}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                  <h3 className="text-sm font-semibold">
                    Open Fair Value Gaps
                    <span className="ml-2 font-normal text-slate-500">
                      {detail.open_gap_count} unmitigated
                    </span>
                  </h3>
                  <ul className="mt-2 space-y-2">
                    {detail.fvg_gaps.length === 0 && (
                      <li className="text-xs text-slate-500">No open gaps on this interval.</li>
                    )}
                    {detail.fvg_gaps.map((gap, index) => (
                      <li
                        key={`${String(gap.formed_date)}-${index}`}
                        className="text-xs leading-relaxed text-slate-400"
                      >
                        <span className="font-medium text-slate-200">{String(gap.label)}</span>{" "}
                        {money(Number(gap.bottom))} – {money(Number(gap.top))} (midpoint{" "}
                        {money(Number(gap.midpoint))}) · formed {String(gap.formed_date)} ·{" "}
                        {Math.round(Number(gap.mitigation) * 100)}% mitigated ·{" "}
                        {Number(gap.displacement_atr).toFixed(1)}× Average True Range
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Chart markup */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold">Chart markup</h3>
                  <button
                    type="button"
                    onClick={() => setShowMarkup((v) => !v)}
                    className="min-h-[36px] rounded-lg border border-slate-700 px-3 text-xs hover:border-slate-600"
                  >
                    {showMarkup ? "Hide" : "Show"} JSON
                  </button>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  A portable description of every marking on the chart, so the same view can be
                  redrawn or shared.
                </p>
                {showMarkup && (
                  <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-slate-950/70 p-3 text-[11px] leading-relaxed text-slate-300">
                    {markupText}
                  </pre>
                )}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}

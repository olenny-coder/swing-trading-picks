"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import type { ChartAnnotation, SmcResult, SmcScan, SmcSymbol } from "@/lib/types";
import { DemoBanner } from "@/components/DemoBanner";

const PriceChart = dynamic(() => import("@/components/PriceChart"), { ssr: false });

function money(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toFixed(2);
}

function TrendBadge({ trend }: { trend: string }) {
  const style =
    trend === "Bullish"
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
      : trend === "Bearish"
        ? "bg-red-500/15 text-red-300 border-red-500/40"
        : "bg-slate-500/15 text-slate-300 border-slate-500/40";
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-semibold ${style}`}>
      {trend}
    </span>
  );
}

function Confidence({ value }: { value: number }) {
  const colour = value >= 70 ? "bg-emerald-500" : value >= 40 ? "bg-amber-500" : "bg-slate-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full ${colour}`} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
      <span className="font-mono text-xs text-slate-300">{value.toFixed(0)}</span>
    </div>
  );
}

/** Chart markup for the structure chart, built from the analysis levels. */
function annotationsFor(detail: SmcSymbol): ChartAnnotation[] {
  const out: ChartAnnotation[] = [];
  const gap = detail.gap as
    | { bottom?: number; top?: number; formed_date?: string; label?: string }
    | null;
  const last = detail.daily_bars[detail.daily_bars.length - 1]?.date;

  if (gap?.bottom != null && gap?.top != null && gap.formed_date && last) {
    out.push({
      kind: "fvg",
      label: gap.label ?? "1D FVG",
      color: detail.trend === "Bullish" ? "#16a34a" : "#dc2626",
      top: gap.top,
      bottom: gap.bottom,
      from_date: gap.formed_date,
      to_date: last,
      emphasis: true,
    });
  }
  if (detail.entry != null) {
    out.push({
      kind: "level",
      label: `Entry ${money(detail.entry)}`,
      color: "#f59e0b",
      price: detail.entry,
      style: "dashed",
    });
  }
  if (detail.stop != null) {
    out.push({
      kind: "level",
      label: `Stop ${money(detail.stop)}`,
      color: "#dc2626",
      price: detail.stop,
    });
  }
  if (detail.target != null) {
    out.push({
      kind: "level",
      label: `Target ${money(detail.target)}`,
      color: "#22c55e",
      price: detail.target,
      style: "dashed",
    });
  }
  return out;
}

function ResultCard({ row, onSelect }: { row: SmcResult; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-left transition hover:border-slate-700"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-emerald-400">{row.symbol}</span>
            <TrendBadge trend={row.trend} />
            {!row.tradeable && (
              <span className="rounded border border-slate-600 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                No trade
              </span>
            )}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            1D BOS {row.bos_confirmed ? "confirmed" : "not confirmed"}
          </div>
        </div>
        <Confidence value={row.confidence} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <div>
          <dt className="text-slate-500">1D FVG zone</dt>
          <dd className="font-mono text-slate-200">
            {row.fvg_low != null && row.fvg_high != null
              ? `${money(row.fvg_low)} – ${money(row.fvg_high)}`
              : "n/a"}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Entry</dt>
          <dd className="font-mono text-amber-300">{money(row.entry)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Stop</dt>
          <dd className="font-mono text-red-300">{money(row.stop)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Take profit</dt>
          <dd className="font-mono text-emerald-300">{money(row.target)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Risk / reward</dt>
          <dd className="font-mono text-slate-200">
            {row.risk_reward != null ? `1:${row.risk_reward.toFixed(2)}` : "n/a"}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-[11px] leading-relaxed text-slate-400">{row.reasoning}</p>
    </button>
  );
}

/** 4-hour candles come back as ISO timestamps; the chart wants epoch seconds. */
function refinementSeries(detail: SmcSymbol) {
  return detail.refinement_bars.map((b) => ({
    date: Math.floor(new Date(`${b.time}Z`).getTime() / 1000),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }));
}

/** Level-only markup — price lines need no date, so they work on either chart. */
function levelsFor(detail: SmcSymbol): ChartAnnotation[] {
  return annotationsFor(detail).filter((a) => a.kind === "level");
}

export default function HomePage() {
  const [scan, setScan] = useState<SmcScan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<SmcSymbol | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api
      .smcScan()
      .then(setScan)
      .catch((e) => setError(e instanceof Error ? e.message : "Analysis failed"))
      .finally(() => setLoading(false));
  }, [reload]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setDetailError("");
    api
      .smcSymbol(selected)
      .then(setDetail)
      .catch((e) => setDetailError(e instanceof Error ? e.message : "Could not load the chart"))
      .finally(() => setDetailLoading(false));
  }, [selected]);

  const rows = scan?.results ?? [];
  const annotations = useMemo(() => (detail ? annotationsFor(detail) : []), [detail]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold sm:text-2xl">SMC Analysis</h1>
          <p className="text-sm text-slate-400">
            Daily structure, break of structure and the fair value gap behind it — refined on the
            4-hour chart for the entry, stop and target.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setReload((r) => r + 1)}
          className="min-h-[44px] self-start rounded-lg border border-slate-700 px-4 text-sm hover:border-slate-600"
        >
          ↻ Re-analyse
        </button>
      </div>

      {scan?.demo && <DemoBanner />}

      {scan && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs leading-relaxed text-slate-400">
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            <span>
              Screened <span className="font-mono text-slate-200">{scan.scanned}</span>
            </span>
            <span>
              Tradeable <span className="font-mono text-emerald-300">{scan.tradeable}</span>
            </span>
            <span>
              Minimum R:R{" "}
              <span className="font-mono text-slate-200">1:{scan.min_risk_reward.toFixed(1)}</span>
            </span>
            <span>
              Refinement <span className="font-mono text-slate-200">{scan.refinement_interval}</span>
            </span>
            <span>
              4H data{" "}
              <span className={scan.intraday_available ? "text-emerald-300" : "text-amber-300"}>
                {scan.intraday_available ? "available" : "unavailable"}
              </span>
            </span>
          </div>

          {/* Say why the screen is empty instead of leaving it a mystery. */}
          {scan.data_status && (
            <p
              className={`mt-2 rounded-lg border px-3 py-2 ${
                scan.data_status.ready
                  ? "border-slate-700 bg-slate-950/40 text-slate-400"
                  : "border-amber-500/40 bg-amber-500/5 text-amber-200"
              }`}
            >
              {scan.data_status.message}
            </p>
          )}

          <p className="mt-2 text-[11px] text-slate-500">
            A setup is only raised when the 1D break of structure left a valid, unmitigated fair
            value gap and the 4H refinement clears the minimum risk-to-reward. Everything else is
            reported as No Trade with the reason.
          </p>
        </div>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-sm text-slate-400">Analysing…</p>}

      {!loading && scan && rows.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
          <p className="font-medium text-slate-300">No valid signal.</p>
          <p className="mt-1 text-xs">
            {scan.data_status && !scan.data_status.ready
              ? scan.data_status.message
              : "Nothing currently has a confirmed break of structure with a valid fair value gap behind it. Press Re-analyse, or refresh the data, and look again after the next session."}
          </p>
          {scan.data_status?.market_day_note && (
            <p className="mt-2 text-[11px] text-slate-500">{scan.data_status.market_day_note}</p>
          )}
        </div>
      )}

      {rows.length > 0 && (
        <>
          <div className="hidden overflow-x-auto rounded-xl border border-slate-800 lg:block">
            <table className="w-full min-w-[980px] text-left text-sm">
              <thead className="border-b border-slate-800 bg-slate-900/80 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-3 py-3">Symbol</th>
                  <th className="px-3 py-3">Confidence</th>
                  <th className="px-3 py-3">Trend</th>
                  <th className="px-3 py-3">1D BOS</th>
                  <th className="px-3 py-3">1D FVG zone</th>
                  <th className="px-3 py-3">Entry</th>
                  <th className="px-3 py-3">Stop</th>
                  <th className="px-3 py-3">Take profit</th>
                  <th className="px-3 py-3">R:R</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.symbol}
                    onClick={() => setSelected(row.symbol)}
                    className={`cursor-pointer border-b border-slate-800/60 hover:bg-slate-900/50 ${
                      selected === row.symbol ? "bg-slate-800/50" : ""
                    }`}
                  >
                    <td className="px-3 py-3">
                      <div className="font-semibold text-emerald-400">{row.symbol}</div>
                      {!row.tradeable && (
                        <div className="text-[10px] uppercase text-slate-500">No trade</div>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <Confidence value={row.confidence} />
                    </td>
                    <td className="px-3 py-3">
                      <TrendBadge trend={row.trend} />
                    </td>
                    <td className="px-3 py-3 text-xs text-slate-300">
                      {row.bos_confirmed ? "Yes" : "No"}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">
                      {row.fvg_low != null && row.fvg_high != null
                        ? `${money(row.fvg_low)}–${money(row.fvg_high)}`
                        : "n/a"}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs text-amber-300">
                      {money(row.entry)}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs text-red-300">{money(row.stop)}</td>
                    <td className="px-3 py-3 font-mono text-xs text-emerald-300">
                      {money(row.target)}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">
                      {row.risk_reward != null ? `1:${row.risk_reward.toFixed(2)}` : "n/a"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
            {rows.map((row) => (
              <ResultCard key={row.symbol} row={row} onSelect={() => setSelected(row.symbol)} />
            ))}
          </div>
        </>
      )}

      {selected && (
        <section className="space-y-4 rounded-2xl border border-slate-700 bg-slate-900/40 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">
                {selected}
                <span className="ml-2 text-sm font-normal text-slate-400">
                  {detail?.as_of ? `closed through ${detail.as_of}` : ""}
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
              Close
            </button>
          </div>

          {detailError && <p className="text-sm text-red-400">{detailError}</p>}
          {detailLoading && <p className="text-sm text-slate-400">Loading the chart…</p>}

          {detail && (
            <>
              {detail.demo && <DemoBanner />}

              {/* The plain-text verdict — the exact block from the brief. */}
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
                  Analysis output
                </div>
                <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[13px] leading-relaxed text-slate-200">
                  {detail.text}
                </pre>
              </div>

              {/* Live price versus the entry. Display only: the levels never move. */}
              {detail.live?.available && (
                <div
                  className={`rounded-xl border px-4 py-3 text-xs leading-relaxed ${
                    detail.live.in_zone
                      ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-200"
                      : "border-slate-800 bg-slate-900/60 text-slate-300"
                  }`}
                >
                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                    <span className="text-[11px] uppercase tracking-wide text-slate-500">
                      Live price
                    </span>
                    <span className="font-mono text-base font-semibold">
                      {detail.live.price?.toFixed(2)}
                    </span>
                    {typeof detail.live.change_pct === "number" && (
                      <span
                        className={
                          detail.live.change_pct >= 0 ? "text-emerald-300" : "text-red-300"
                        }
                      >
                        {detail.live.change_pct >= 0 ? "+" : ""}
                        {detail.live.change_pct.toFixed(2)}%
                      </span>
                    )}
                    {detail.live.feed && (
                      <span className="text-[11px] text-slate-500">feed {detail.live.feed}</span>
                    )}
                    {typeof detail.live.distance_pct === "number" && (
                      <span className="text-[11px] text-slate-400">
                        {detail.live.distance_pct >= 0 ? "+" : ""}
                        {detail.live.distance_pct.toFixed(2)}% vs entry
                      </span>
                    )}
                  </div>
                  {detail.live.status && <p className="mt-1">{detail.live.status}</p>}
                  <p className="mt-1 text-[11px] text-slate-500">
                    The entry, stop and target above are fixed from closed candles — this price
                    only tells you how far the market is from the entry.
                  </p>
                </div>
              )}

              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <div className="mb-2 flex items-baseline justify-between gap-2">
                  <h3 className="text-sm font-semibold">Daily structure (1D)</h3>
                  <span className="text-[11px] text-slate-500">break of structure + gap</span>
                </div>
                <PriceChart bars={detail.daily_bars} annotations={annotations} />
                <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                  The shaded band is the 1D fair value gap behind the break; the dashed lines are
                  the entry and take-profit, the solid red line the stop. All candles are closed, so
                  nothing here repaints.
                </p>
              </div>

              {/* The refinement chart — the clock the levels were actually read on. */}
              {detail.refinement_bars.length > 0 ? (
                <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                  <div className="mb-2 flex items-baseline justify-between gap-2">
                    <h3 className="text-sm font-semibold">
                      Refinement ({detail.refinement_timeframe ?? "4H"})
                    </h3>
                    <span className="text-[11px] text-slate-500">
                      {detail.refinement_bars.length} candles · entry, stop and target
                    </span>
                  </div>
                  <PriceChart
                    bars={refinementSeries(detail)}
                    annotations={levelsFor(detail)}
                  />
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                    The entry, stop and target on the refinement clock. The entry sits at the gap&apos;s
                    50% mean threshold, the stop beyond the structural swing that created the gap.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-xs leading-relaxed text-amber-200">
                  <strong>No trade.</strong> No 4-hour candles are stored, and the entry, stop
                  and target are only accurate when placed off the 4-hour refinement chart. Rather
                  than approximate them off the daily chart, the setup is refused. Press{" "}
                  <strong>Refresh</strong> once the 4-hour data can load.
                </div>
              )}

              {detail.reasons.length > 0 && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                  <h3 className="text-sm font-semibold">What the analysis saw</h3>
                  <ul className="mt-2 space-y-1.5">
                    {detail.reasons.map((reason) => (
                      <li key={reason} className="flex gap-2 text-xs text-slate-300">
                        <span aria-hidden="true" className="select-none text-emerald-500">
                          •
                        </span>
                        <span className="min-w-0 flex-1 leading-relaxed">{reason}</span>
                      </li>
                    ))}
                  </ul>
                  {detail.blockers.length > 0 && (
                    <ul className="mt-3 space-y-1.5">
                      {detail.blockers.map((blocker) => (
                        <li key={blocker} className="flex gap-2 text-xs text-amber-300/90">
                          <span aria-hidden="true" className="select-none">
                            !
                          </span>
                          <span className="min-w-0 flex-1 leading-relaxed">{blocker}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}

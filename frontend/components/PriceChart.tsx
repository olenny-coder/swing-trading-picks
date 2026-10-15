"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  ColorType,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { BarOut, FvgAnnotation } from "@/lib/types";

type Line = (number | null)[];

/** "#16a34a" + 0.2 -> "rgba(22,163,74,0.2)". */
function withAlpha(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  const full =
    clean.length === 3
      ? clean
          .split("")
          .map((c) => c + c)
          .join("")
      : clean;
  const value = Number.parseInt(full.slice(0, 6), 16);
  if (Number.isNaN(value)) return hex;
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
 * Candlestick chart with optional FVG / breakout markup.
 *
 * Levels (breakout, entry, stop, targets) are drawn as price lines so they get
 * axis labels. Zones — Fair Value Gaps, consolidation boxes and the entry band —
 * are painted on a transparent canvas layered over the chart, because
 * lightweight-charts has no rectangle primitive. The canvas is repainted on every
 * pan, zoom and resize so the shading stays locked to the candles.
 */
export default function PriceChart({
  bars,
  ema20,
  ema50,
  annotations = [],
}: {
  bars: BarOut[];
  ema20?: Line;
  ema50?: Line;
  annotations?: FvgAnnotation[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const annotationsRef = useRef<FvgAnnotation[]>(annotations);
  annotationsRef.current = annotations;

  const paint = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!canvas || !container || !chart || !series) return;

    const dpr = window.devicePixelRatio || 1;
    const width = container.clientWidth;
    const height = container.clientHeight;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const scale = chart.timeScale();

    /** x for a date, or null when it cannot be placed on the current scale. */
    const xOf = (iso?: string): number | null => {
      if (!iso) return null;
      const x = scale.timeToCoordinate(iso as Time);
      return x == null ? null : x;
    };

    const zones = annotationsRef.current.filter((a) =>
      ["fvg", "zone", "box"].includes(a.kind),
    );
    for (const zone of zones) {
      if (zone.top == null || zone.bottom == null) continue;
      let x1 = xOf(zone.from_date);
      let x2 = xOf(zone.to_date);
      if (x1 == null) x1 = 0;
      // Zones are drawn to the right edge when they extend to the latest candle.
      if (x2 == null) x2 = zone.to_date ? width : x1;
      const y1 = series.priceToCoordinate(zone.top);
      const y2 = series.priceToCoordinate(zone.bottom);
      if (y1 == null || y2 == null) continue;
      const left = Math.min(x1, x2);
      const right = Math.max(x1, x2) + 6;
      const top = Math.min(y1, y2);
      const zoneHeight = Math.max(2, Math.abs(y2 - y1));
      const colour = zone.color ?? "#38bdf8";
      const alpha = zone.kind === "fvg" ? (zone.emphasis ? 0.28 : 0.14) : 0.12;

      ctx.fillStyle = withAlpha(colour, alpha);
      ctx.fillRect(left, top, Math.max(2, right - left), zoneHeight);
      ctx.strokeStyle = withAlpha(colour, zone.emphasis ? 0.9 : 0.45);
      ctx.lineWidth = zone.emphasis ? 1.5 : 1;
      ctx.setLineDash(zone.kind === "fvg" ? [] : [4, 3]);
      ctx.strokeRect(left, top, Math.max(2, right - left), zoneHeight);
      ctx.setLineDash([]);

      if (zone.label && right - left > 40) {
        ctx.fillStyle = withAlpha(colour, 0.95);
        ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
        ctx.fillText(zone.label, left + 4, top - 3 > 12 ? top - 3 : top + 12);
      }
    }

    for (const line of annotationsRef.current.filter((a) => a.kind === "trendline")) {
      const points = line.points ?? [];
      if (points.length < 2) continue;
      const xs = points.map((p) => xOf(p.date));
      const ys = points.map((p) => series.priceToCoordinate(p.price));
      if (xs.some((x) => x == null) || ys.some((y) => y == null)) continue;
      ctx.strokeStyle = withAlpha(line.color ?? "#f472b6", 0.9);
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.moveTo(xs[0] as number, ys[0] as number);
      ctx.lineTo(xs[1] as number, ys[1] as number);
      ctx.stroke();
    }
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || bars.length === 0) return;

    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "rgba(148,163,184,0.08)" },
        horzLines: { color: "rgba(148,163,184,0.08)" },
      },
      timeScale: { borderColor: "rgba(148,163,184,0.2)" },
      rightPriceScale: { borderColor: "rgba(148,163,184,0.2)" },
    });
    chartRef.current = chart;

    const candle = chart.addCandlestickSeries({
      upColor: "#16a34a",
      downColor: "#dc2626",
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
      borderVisible: false,
    });
    seriesRef.current = candle;
    candle.setData(
      bars.map((b) => ({ time: b.date, open: b.open, high: b.high, low: b.low, close: b.close })),
    );

    if (ema20) {
      const s = chart.addLineSeries({ color: "#f59e0b", lineWidth: 2 });
      s.setData(
        ema20
          .map((v, i) => ({ time: bars[i].date, value: v }))
          .filter((p): p is { time: string; value: number } => p.value != null),
      );
    }
    if (ema50) {
      const s = chart.addLineSeries({ color: "#38bdf8", lineWidth: 2 });
      s.setData(
        ema50
          .map((v, i) => ({ time: bars[i].date, value: v }))
          .filter((p): p is { time: string; value: number } => p.value != null),
      );
    }

    // Levels become price lines so they carry an axis label.
    for (const level of annotations.filter((a) => a.kind === "level" && a.price != null)) {
      candle.createPriceLine({
        price: level.price as number,
        color: level.color ?? "#38bdf8",
        lineWidth: 1,
        lineStyle: level.style === "dashed" ? LineStyle.Dashed : LineStyle.Solid,
        axisLabelVisible: true,
        title: level.label,
      });
    }

    const markers: SeriesMarker<Time>[] = annotations
      .filter((a) => a.kind === "marker" && a.date)
      .map((a) => ({
        time: a.date as Time,
        position: (a.position ?? "belowBar") as SeriesMarker<Time>["position"],
        color: a.color ?? "#f59e0b",
        shape: (a.shape ?? "arrowUp") as SeriesMarker<Time>["shape"],
        text: a.label,
      }));
    if (markers.length) candle.setMarkers(markers);

    // Fit the candles, then repaint the shading once the scale has settled.
    chart.timeScale().fitContent();
    paint();

    const scale = chart.timeScale();
    const onRange = () => paint();
    scale.subscribeVisibleLogicalRangeChange(onRange);
    const observer = new ResizeObserver(() => paint());
    observer.observe(container);

    return () => {
      observer.disconnect();
      scale.unsubscribeVisibleLogicalRangeChange(onRange);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [bars, ema20, ema50, annotations, paint]);

  return (
    <div className="relative">
      <div ref={containerRef} className="h-[320px] w-full sm:h-[460px]" />
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0" aria-hidden="true" />
    </div>
  );
}

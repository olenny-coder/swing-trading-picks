"use client";

import { useEffect, useRef } from "react";
import { ColorType, createChart, type IChartApi } from "lightweight-charts";
import type { BarOut } from "@/lib/types";

type Line = (number | null)[];

export default function PriceChart({ bars, ema20, ema50 }: { bars: BarOut[]; ema20?: Line; ema50?: Line }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;

    const chart = createChart(containerRef.current, {
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

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, ema20, ema50]);

  return <div ref={containerRef} className="h-[300px] w-full sm:h-[420px]" />;
}

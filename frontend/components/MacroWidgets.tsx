import type { EarningsEventOut, MacroEventOut } from "@/lib/types";
import { formatDateTime, formatDate, formatPct } from "@/lib/format";

export function MacroEventList({ events }: { events: MacroEventOut[] }) {
  if (events.length === 0) return <p className="text-sm text-slate-500">No upcoming macro events.</p>;
  return (
    <ul className="space-y-2">
      {events.map((e) => (
        <li key={e.id} className="flex items-start justify-between gap-2 rounded-lg bg-slate-800/40 px-3 py-2">
          <div>
            <div className="text-sm">{e.title}</div>
            <div className="text-xs text-slate-400">
              {formatDateTime(e.datetime)}
              {e.forecast ? ` · f/c ${e.forecast}` : ""}
            </div>
          </div>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold ${
              e.sentiment === "positive"
                ? "bg-emerald-500/15 text-emerald-300"
                : e.sentiment === "negative"
                  ? "bg-red-500/15 text-red-300"
                  : "bg-slate-500/15 text-slate-300"
            }`}
          >
            {e.sentiment}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function EarningsList({ earnings }: { earnings: EarningsEventOut[] }) {
  if (earnings.length === 0) return <p className="text-sm text-slate-500">No upcoming earnings.</p>;
  return (
    <ul className="space-y-2">
      {earnings.map((e) => (
        <li key={e.id} className="flex items-center justify-between rounded-lg bg-slate-800/40 px-3 py-2">
          <div>
            <div className="text-sm font-semibold text-emerald-400">{e.ticker}</div>
            <div className="text-xs text-slate-400">{e.fiscal_quarter ?? ""}</div>
          </div>
          <div className="text-right text-xs text-slate-300">{formatDate(e.report_date)}</div>
        </li>
      ))}
    </ul>
  );
}

export function SectorHeatmap({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return <p className="text-sm text-slate-500">No sector data.</p>;
  const maxAbs = Math.max(1, ...entries.map(([, v]) => Math.abs(v)));

  return (
    <ul className="space-y-2">
      {entries.map(([name, value]) => {
        const width = (Math.abs(value) / maxAbs) * 100;
        const positive = value >= 0;
        return (
          <li key={name} className="text-sm">
            <div className="mb-1 flex justify-between">
              <span className="text-slate-300">{name}</span>
              <span className={positive ? "text-emerald-400" : "text-red-400"}>{formatPct(value)}</span>
            </div>
            <div className="h-2 w-full rounded bg-slate-800">
              <div
                className={`h-2 rounded ${positive ? "bg-emerald-500" : "bg-red-500"}`}
                style={{ width: `${width}%`, marginLeft: positive ? "0" : `${100 - width}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

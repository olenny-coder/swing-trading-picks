"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export function RefreshButton({ onDone }: { onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh() {
    setBusy(true);
    setMessage("Pulling latest market data…");
    try {
      await api.refreshData();
      let done = false;
      // Poll up to ~6 minutes (120 x 3s) for the background pull to finish.
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const s = await api.refreshStatus();
        if (!s.running) {
          if (s.error) {
            setMessage(`Refresh error: ${s.error}`);
          } else if (s.result) {
            setMessage(
              `Done — ${s.result.bars} bars / ${s.result.tickers} tickers via ${s.result.provider} (signal date ${s.result.signal_date}).`,
            );
          } else {
            setMessage("Refresh finished.");
          }
          done = true;
          break;
        }
      }
      if (!done) setMessage("Refresh is still running in the background.");
      onDone?.();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <button
        onClick={refresh}
        disabled={busy}
        className="min-h-[44px] rounded-lg border border-emerald-600/60 bg-emerald-600/10 px-4 text-sm font-medium text-emerald-300 hover:bg-emerald-600/20 disabled:opacity-50"
      >
        {busy ? "Refreshing…" : "↻ Refresh data"}
      </button>
      {message && <span className="max-w-xs text-xs text-slate-400">{message}</span>}
    </div>
  );
}

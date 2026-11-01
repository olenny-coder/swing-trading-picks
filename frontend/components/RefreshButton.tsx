"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { RefreshStatus } from "@/lib/api";

/**
 * Downloads market data, then polls the background job.
 *
 * Two things this deliberately tolerates, because a long pull on a small host
 * will hit them:
 *
 * - **A dropped poll is not a failed refresh.** One `Failed to fetch` used to
 *   abort the whole wait and report an error while the job was still running
 *   fine. Transient failures are now counted and retried.
 * - **The job outlives the page.** If the tab is reloaded mid-pull, the component
 *   adopts the running job on mount instead of pretending nothing is happening.
 */
export function RefreshButton({ onDone }: { onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);

  const applyResult = useCallback(
    (status: RefreshStatus) => {
      if (status.error) {
        setMessage(`Refresh error: ${status.error}`);
        return;
      }
      const r = status.result;
      if (!r) {
        setMessage("Refresh finished.");
        return;
      }
      const intraday = r.intraday_bars ?? 0;
      setMessage(
        `Done — ${r.bars.toLocaleString()} daily bars · ${intraday.toLocaleString()} 4-hour candles · ${r.tickers} tickers via ${r.refinement_source ?? r.provider} (signal date ${r.signal_date}).`,
      );
      // A refresh that loads no 4-hour candles looks like success but leaves every
      // setup refused, so say so rather than showing a plain "Done".
      setWarnings(
        intraday === 0
          ? [
              "No 4-hour candles were loaded — every setup will be reported as No Trade until they are.",
              ...(r.warnings ?? []),
            ]
          : (r.warnings ?? []),
      );
    },
    [],
  );

  const poll = useCallback(async () => {
    let failedPolls = 0;
    for (let i = 0; i < 240; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      let status: RefreshStatus;
      try {
        status = await api.refreshStatus();
        failedPolls = 0;
      } catch {
        // The connection dropped. Keep waiting: the job runs server-side.
        failedPolls += 1;
        if (failedPolls <= 3) {
          setMessage(`Connection blipped — still waiting for the refresh (retry ${failedPolls}/3)…`);
          continue;
        }
        setMessage(
          "Lost contact with the server. The refresh is still running there — reload the page in a minute to see the result.",
        );
        return;
      }

      if (status.running) {
        setMessage(status.progress ? `Working — ${status.progress}…` : "Pulling latest market data…");
        continue;
      }

      applyResult(status);
      onDone?.();
      return;
    }
    setMessage(
      "Still running after 12 minutes. The job continues on the server — reload the page shortly to see the outcome.",
    );
  }, [applyResult, onDone]);

  // Adopt a refresh that is already running (e.g. after a reload mid-pull).
  useEffect(() => {
    let cancelled = false;
    api
      .refreshStatus()
      .then((status) => {
        if (cancelled || !status.running) return;
        setBusy(true);
        setMessage(status.progress ? `Working — ${status.progress}…` : "A refresh is already running…");
        void poll().finally(() => setBusy(false));
      })
      .catch(() => {
        /* not signed in, or offline — nothing to adopt */
      });
    return () => {
      cancelled = true;
    };
  }, [poll]);

  async function refresh() {
    setBusy(true);
    setMessage("Starting the download…");
    setWarnings([]);
    try {
      await api.refreshData();
      await poll();
    } catch (e) {
      // Only a failure to *start* lands here; polling handles its own errors.
      setMessage(
        e instanceof Error
          ? `Could not start the refresh: ${e.message}`
          : "Could not start the refresh.",
      );
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
      {warnings.map((warning) => (
        <span
          key={warning}
          className="max-w-xs rounded border border-amber-500/40 bg-amber-500/5 px-2 py-1 text-[11px] leading-relaxed text-amber-200"
        >
          {warning}
        </span>
      ))}
    </div>
  );
}

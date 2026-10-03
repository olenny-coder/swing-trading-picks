"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ResearchStatus } from "@/lib/types";

/**
 * Admin control for the LLM research agent.
 *
 * The backend runs the (sequential, rate-limited) Groq calls in a background
 * thread, so this kicks off a pass and then polls the status endpoint.
 */
export function ResearchButton({ onDone }: { onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<ResearchStatus | null>(null);

  useEffect(() => {
    api
      .researchStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  async function run() {
    setBusy(true);
    setMessage("Asking the research agent…");
    try {
      let current = await api.runResearch({});
      setStatus(current);
      // Poll up to ~5 minutes (100 x 3s); Groq free-tier calls are sequential.
      for (let i = 0; i < 100 && current.running; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        current = await api.researchStatus();
        setStatus(current);
      }

      if (current.error) {
        setMessage(`Research error: ${current.error}`);
      } else if (current.running) {
        setMessage("Still running in the background.");
      } else {
        const result = current.last_result as
          | { annotated?: number; failed?: number; model?: string }
          | null;
        setMessage(
          `Annotated ${result?.annotated ?? 0} signal(s)` +
            (result?.failed ? `, ${result.failed} failed` : "") +
            (result?.model ? ` · ${result.model}` : "") +
            ".",
        );
      }
      onDone?.();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Research run failed");
    } finally {
      setBusy(false);
    }
  }

  if (status && !status.configured) {
    return (
      <div className="flex flex-col items-start gap-1 sm:items-end">
        <span
          className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-400"
          title="Add GROQ_API_KEY (or set it under Settings) to enable the research agent"
        >
          ◆ Research agent: no Groq key
        </span>
      </div>
    );
  }

  const pending = status?.pending_signals ?? 0;

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <button
        onClick={run}
        disabled={busy}
        title={
          status
            ? `${status.annotated_signals}/${status.total_signals} annotated · model ${status.model}`
            : undefined
        }
        className="min-h-[44px] rounded-lg border border-sky-600/60 bg-sky-600/10 px-4 text-sm font-medium text-sky-300 hover:bg-sky-600/20 disabled:opacity-50"
      >
        {busy ? "Researching…" : `◆ Research signals${pending ? ` (${pending})` : ""}`}
      </button>
      {message && <span className="max-w-xs text-xs text-slate-400">{message}</span>}
    </div>
  );
}

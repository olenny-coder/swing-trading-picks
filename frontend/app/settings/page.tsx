"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SettingsResponse, TestConnectionResult } from "@/lib/types";

const inputCls =
  "min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100";

function StatusDot({ configured, source }: { configured: boolean; source: string }) {
  const color = configured ? "bg-emerald-500" : "bg-slate-600";
  return (
    <span className="inline-flex items-center gap-2 text-xs text-slate-400">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {configured ? `configured (${source})` : "not configured"}
    </span>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [alpacaKey, setAlpacaKey] = useState("");
  const [alpacaSecret, setAlpacaSecret] = useState("");
  const [isPaper, setIsPaper] = useState(true);
  const [test, setTest] = useState<TestConnectionResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [providerKeys, setProviderKeys] = useState<Record<string, string>>({});

  async function reload() {
    const s = await api.settings();
    setSettings(s);
    if (s.alpaca?.is_paper != null) setIsPaper(s.alpaca.is_paper);
  }

  useEffect(() => {
    reload().catch(() => setSettings(null));
  }, []);

  async function saveAlpaca() {
    if (!alpacaKey.trim() || !alpacaSecret.trim()) {
      setMessage("API key and secret are both required.");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      await api.saveCredential("alpaca", {
        provider: "alpaca",
        api_key: alpacaKey.trim(),
        secret_key: alpacaSecret.trim(),
        is_paper: isPaper,
      });
      setAlpacaKey("");
      setAlpacaSecret("");
      setMessage("Alpaca credentials saved (encrypted at rest).");
      await reload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function saveProvider(provider: string) {
    const key = providerKeys[provider];
    if (!key?.trim()) return;
    setSaving(true);
    setMessage("");
    try {
      await api.saveCredential(provider, { provider, api_key: key.trim() });
      setProviderKeys((p) => ({ ...p, [provider]: "" }));
      setMessage(`${provider.toUpperCase()} key saved.`);
      await reload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function runTest(provider: string) {
    setTesting(true);
    setTest(null);
    try {
      setTest(await api.testConnection(provider));
    } catch (e) {
      setTest({ provider, ok: false, message: e instanceof Error ? e.message : "Test failed", detail: null });
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold sm:text-2xl">Settings</h1>
        <p className="text-sm text-slate-400">
          Manage data-provider API keys. Keys are encrypted at rest and never returned to the browser in plaintext.
        </p>
      </div>

      {settings && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm">
          <div className="mb-2 font-semibold">Provider status</div>
          <ul className="space-y-2">
            {settings.providers.map((p) => (
              <li key={p.provider} className="flex items-center justify-between">
                <span className="font-mono text-slate-200">{p.provider}</span>
                <StatusDot configured={p.configured} source={p.source} />
              </li>
            ))}
          </ul>
          {settings.environment_variables_present && (
            <p className="mt-3 text-xs text-amber-300">
              Environment-variable fallback keys are present; UI keys take precedence when both exist.
            </p>
          )}
        </div>
      )}

      {/* Alpaca */}
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Alpaca (market data & trading)</h2>
          {settings?.alpaca && (
            <span className="text-xs text-slate-400">
              Current: {settings.alpaca.has_key ? settings.alpaca.key_masked : "none"}
            </span>
          )}
        </div>

        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">API Key</span>
            <input
              className={inputCls}
              placeholder={settings?.alpaca?.key_masked ?? "PK…"}
              value={alpacaKey}
              onChange={(e) => setAlpacaKey(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">Secret Key</span>
            <input
              className={inputCls}
              type="password"
              placeholder="Secret key"
              value={alpacaSecret}
              onChange={(e) => setAlpacaSecret(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          <label className="flex min-h-[44px] items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={isPaper}
              onChange={(e) => setIsPaper(e.target.checked)}
            />
            <span className="text-sm">Paper trading (recommended) — uncheck for live</span>
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              onClick={saveAlpaca}
              disabled={saving}
              className="min-h-[44px] rounded-lg bg-emerald-600 px-5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              Save Alpaca keys
            </button>
            <button
              onClick={() => runTest("alpaca")}
              disabled={testing}
              className="min-h-[44px] rounded-lg border border-slate-700 px-5 text-sm hover:bg-slate-800 disabled:opacity-50"
            >
              Test connection
            </button>
          </div>
          {test && test.provider === "alpaca" && (
            <p className={`text-sm ${test.ok ? "text-emerald-400" : "text-red-400"}`}>
              {test.ok ? "✓ " : "✗ "}
              {test.message}
            </p>
          )}
        </div>
      </section>

      {/* Optional providers */}
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="font-semibold">Optional data providers</h2>
        <p className="mt-1 text-xs text-slate-400">
          Finnhub (economic/earnings calendars), Polygon (options/alt data), FRED (interest rates).
        </p>
        {["finnhub", "polygon", "fred"].map((provider) => (
          <div key={provider} className="mt-4 flex flex-col gap-2 border-t border-slate-800 pt-4 first:mt-3 first:border-t-0 first:pt-0 sm:flex-row sm:items-end">
            <div className="flex-1">
              <span className="mb-1 block text-xs text-slate-400">{provider.toUpperCase()} API key</span>
              <input
                className={inputCls}
                placeholder="Optional"
                value={providerKeys[provider] ?? ""}
                onChange={(e) => setProviderKeys((p) => ({ ...p, [provider]: e.target.value }))}
                autoComplete="off"
              />
            </div>
            <button
              onClick={() => saveProvider(provider)}
              disabled={saving || !providerKeys[provider]?.trim()}
              className="min-h-[44px] rounded-lg bg-slate-700 px-4 text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
            >
              Save
            </button>
            <button
              onClick={() => runTest(provider)}
              disabled={testing}
              className="min-h-[44px] rounded-lg border border-slate-700 px-4 text-sm hover:bg-slate-800 disabled:opacity-50"
            >
              Test
            </button>
          </div>
        ))}
        {test && test.provider !== "alpaca" && (
          <p className={`mt-3 text-sm ${test.ok ? "text-emerald-400" : "text-red-400"}`}>
            {test.ok ? "✓ " : "✗ "}
            {test.message}
          </p>
        )}
      </section>

      {message && <p className="text-sm text-amber-300">{message}</p>}
    </div>
  );
}

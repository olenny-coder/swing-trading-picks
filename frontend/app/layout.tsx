import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { Nav } from "@/components/Nav";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://swing-trading-picks.vercel.app";
const title = "Swing Trading Picks — Daily US Stock Signals & Options Setups";
const description =
  "Free daily swing-trading signals for liquid US equities: momentum breakouts, doji reversals, and sell/put-option setups — each with entry, target, stop-loss and a transparent 0–100 confidence score built from technical, regime, sector, volume and macro factors.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: title,
    template: "%s · Swing Trading Picks",
  },
  description,
  applicationName: "Swing Trading Picks",
  keywords: [
    "swing trading",
    "swing trading picks",
    "daily stock picks",
    "stock signals",
    "US stock screener",
    "momentum breakout",
    "doji reversal",
    "put option ideas",
    "options signals",
    "technical analysis",
    "entry target stop loss",
    "swing trading scanner",
    "Alpaca API",
    "macro earnings filter",
  ],
  authors: [{ name: "olenny-coder" }],
  creator: "olenny-coder",
  publisher: "Swing Trading Picks",
  category: "finance",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: siteUrl,
    siteName: "Swing Trading Picks",
    title,
    description,
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f172a",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <AuthProvider>
          <Nav />
          <main className="mx-auto w-full max-w-7xl px-3 pb-16 pt-4 sm:px-6">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}

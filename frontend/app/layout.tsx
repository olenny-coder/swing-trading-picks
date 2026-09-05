import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Swing Trading Picks",
  description:
    "Daily swing-trading signals (breakout, doji reversal, and put options) for liquid US equities.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
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

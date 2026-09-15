import type { MetadataRoute } from "next";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://swing-trading-picks.vercel.app";

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  const routes: { path: string; priority: number }[] = [
    { path: "", priority: 1 },
    { path: "/history", priority: 0.7 },
    { path: "/macro", priority: 0.7 },
  ];
  return routes.map((r) => ({
    url: `${siteUrl}${r.path}`,
    lastModified,
    changeFrequency: "daily",
    priority: r.priority,
  }));
}

import type { MetadataRoute } from "next";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://swing-trading-picks.vercel.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // Keep private/admin areas out of search results.
        disallow: ["/settings", "/login"],
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}

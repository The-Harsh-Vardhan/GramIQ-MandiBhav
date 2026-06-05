import type { MetadataRoute } from "next";

const siteUrl = process.env.SITE_URL ?? "https://mandibhav.gramiq.com";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/"
    },
    sitemap: `${siteUrl}/sitemap.xml`
  };
}

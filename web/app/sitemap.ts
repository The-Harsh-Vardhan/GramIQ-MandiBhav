import type { MetadataRoute } from "next";

import { getLatestReports } from "@/lib/queries";

const siteUrl = process.env.SITE_URL ?? "https://mandibhav.gramiq.com";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const articles = await getLatestReports(200);
  return [
    {
      url: `${siteUrl}/`,
      lastModified: new Date()
    },
    {
      url: `${siteUrl}/archive`,
      lastModified: new Date()
    },
    {
      url: `${siteUrl}/about`,
      lastModified: new Date()
    },
    ...articles.map((article) => ({
      url: `${siteUrl}/article/${article.slug}`,
      lastModified: new Date(article.updated_at)
    }))
  ];
}

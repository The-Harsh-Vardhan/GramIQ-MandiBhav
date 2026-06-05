import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { TransparencyPanel } from "@/components/transparency-panel";
import { formatDate } from "@/lib/format";
import { getArticleBySlug } from "@/lib/queries";

type ArticlePageProps = {
  params: Promise<{ slug: string }>;
};

export const revalidate = 300;

export async function generateMetadata({ params }: ArticlePageProps): Promise<Metadata> {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) {
    return {
      title: "Article not found"
    };
  }
  return {
    title: article.seo_title,
    description: article.meta_description,
    alternates: {
      canonical: `/article/${article.slug}`
    },
    openGraph: {
      title: article.seo_title,
      description: article.meta_description,
      type: "article",
      url: `/article/${article.slug}`
    },
    twitter: {
      card: "summary_large_image",
      title: article.seo_title,
      description: article.meta_description
    }
  };
}

export default async function ArticlePage({ params }: ArticlePageProps) {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);

  if (!article) {
    notFound();
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(article.json_ld) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(article.faq_json_ld) }}
      />
      <div className="grid gap-8 lg:grid-cols-[1.3fr_0.7fr]">
        <article className="rounded-[2rem] border border-black/10 bg-white p-8">
          <p className="font-sans text-xs uppercase tracking-[0.35em] text-river">
            {article.market_name ?? "National"} · {formatDate(article.article_date)}
          </p>
          <h1 className="mt-4 font-serif text-5xl leading-tight text-soil">{article.title}</h1>
          <p className="mt-4 max-w-3xl text-lg leading-8 text-slate-600">
            {article.meta_description}
          </p>
          <div
            className="prose prose-lg mt-10 max-w-none prose-headings:font-serif prose-headings:text-soil"
            dangerouslySetInnerHTML={{ __html: article.body_html }}
          />
        </article>
        <TransparencyPanel article={article} />
      </div>
    </div>
  );
}

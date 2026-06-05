import Link from "next/link";

import { formatDate, formatScore, titleCase } from "@/lib/format";
import type { ArticleRecord } from "@/lib/types";

export function ArticleCard({ article }: { article: ArticleRecord }) {
  return (
    <article className="rounded-3xl border border-black/10 bg-white p-6 shadow-[0_12px_40px_rgba(0,0,0,0.06)]">
      <div className="mb-4 flex flex-wrap gap-2 text-xs uppercase tracking-[0.2em] text-slate-500">
        <span>{titleCase(article.commodity_slug)}</span>
        <span>{article.market_name ?? "National"}</span>
        <span>{formatDate(article.article_date)}</span>
      </div>
      <h3 className="font-serif text-2xl leading-tight text-soil">
        <Link href={`/article/${article.slug}`}>{article.title}</Link>
      </h3>
      <p className="mt-3 text-sm leading-6 text-slate-600">{article.meta_description}</p>
      <div className="mt-5 flex items-center justify-between text-sm text-slate-500">
        <span>Credibility {formatScore(article.credibility_score)}</span>
        <Link href={`/article/${article.slug}`} className="font-semibold text-river">
          Read report
        </Link>
      </div>
    </article>
  );
}

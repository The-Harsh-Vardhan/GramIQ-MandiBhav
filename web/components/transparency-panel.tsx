import { formatDate, formatScore, titleCase } from "@/lib/format";
import type { ArticleRecord } from "@/lib/types";

export function TransparencyPanel({ article }: { article: ArticleRecord }) {
  return (
    <aside className="rounded-3xl border border-field/30 bg-field/10 p-6">
      <h2 className="font-serif text-2xl text-soil">Transparency</h2>
      <dl className="mt-4 space-y-3 text-sm text-slate-700">
        <div className="flex justify-between gap-4">
          <dt>Published</dt>
          <dd>{formatDate(article.article_date)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Commodity</dt>
          <dd>{titleCase(article.commodity_slug)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Market</dt>
          <dd>{article.market_name ?? "National"}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>State</dt>
          <dd>{article.state ?? "India"}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Credibility score</dt>
          <dd>{formatScore(article.credibility_score)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Records analyzed</dt>
          <dd>{article.records_analyzed}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Report type</dt>
          <dd>{titleCase(article.report_type)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Data source</dt>
          <dd>{titleCase(article.data_source)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Updated</dt>
          <dd>{formatDate(article.updated_at)}</dd>
        </div>
      </dl>
    </aside>
  );
}

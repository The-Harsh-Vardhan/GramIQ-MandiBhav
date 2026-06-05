import Link from "next/link";

import { ArticleCard } from "@/components/article-card";
import { getFeaturedReport, getLatestReports } from "@/lib/queries";
import { formatDate, titleCase } from "@/lib/format";

export const revalidate = 300;

export default async function HomePage() {
  const [featured, latest] = await Promise.all([getFeaturedReport(), getLatestReports(6)]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <section className="grid gap-8 lg:grid-cols-[1.4fr_0.8fr]">
        <div className="rounded-[2rem] bg-soil px-8 py-10 text-white shadow-[0_20px_70px_rgba(90,42,26,0.25)]">
          <p className="font-sans text-xs uppercase tracking-[0.35em] text-grain">
            Daily agricultural intelligence
          </p>
          <h1 className="mt-4 max-w-3xl font-serif text-5xl leading-tight">
            Mandi reports without a static publishing bottleneck.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-white/80">
            Supabase-backed reports, dynamic search, and transparent article scoring for
            soybean and cotton markets.
          </p>
          <form action="/archive" className="mt-8 grid gap-3 rounded-3xl bg-white/10 p-4 md:grid-cols-4">
            <input
              name="q"
              placeholder="Search reports"
              className="rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-sm text-white placeholder:text-white/60"
            />
            <select
              name="commodity"
              className="rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-sm text-white"
              defaultValue=""
            >
              <option value="">All commodities</option>
              <option value="soybean">Soybean</option>
              <option value="cotton">Cotton</option>
            </select>
            <input
              name="market"
              placeholder="Market filter"
              className="rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-sm text-white placeholder:text-white/60"
            />
            <button className="rounded-2xl bg-grain px-4 py-3 text-sm font-semibold text-soil">
              Explore archive
            </button>
          </form>
        </div>

        <div className="rounded-[2rem] border border-black/10 bg-white p-8">
          <p className="font-sans text-xs uppercase tracking-[0.35em] text-river">Featured</p>
          {featured ? (
            <>
              <p className="mt-4 text-sm text-slate-500">{formatDate(featured.article_date)}</p>
              <h2 className="mt-2 font-serif text-3xl text-soil">
                <Link href={`/article/${featured.slug}`}>{featured.title}</Link>
              </h2>
              <p className="mt-4 text-sm leading-6 text-slate-600">{featured.meta_description}</p>
              <div className="mt-6 flex flex-wrap gap-2 text-xs uppercase tracking-[0.2em] text-slate-500">
                <span>{titleCase(featured.commodity_slug)}</span>
                <span>{featured.market_name ?? "National"}</span>
                <span>{featured.data_source}</span>
              </div>
            </>
          ) : (
            <p className="mt-6 text-sm text-slate-500">No published articles found yet.</p>
          )}
        </div>
      </section>

      <section className="mt-14">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <p className="font-sans text-xs uppercase tracking-[0.35em] text-river">
              Latest reports
            </p>
            <h2 className="mt-2 font-serif text-4xl text-soil">Fresh from the pipeline</h2>
          </div>
          <Link href="/archive" className="text-sm font-semibold text-river">
            View all reports
          </Link>
        </div>
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {latest.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))}
        </div>
      </section>
    </div>
  );
}

import { ArticleCard } from "@/components/article-card";
import { searchArticles } from "@/lib/queries";

type ArchivePageProps = {
  searchParams: Promise<{
    commodity?: string;
    market?: string;
    q?: string;
    from?: string;
    to?: string;
    sort?: "latest" | "oldest" | "credibility";
    page?: string;
  }>;
};

export const revalidate = 300;

export default async function ArchivePage({ searchParams }: ArchivePageProps) {
  const params = await searchParams;
  const page = Number(params.page ?? "1") || 1;
  const result = await searchArticles({
    commodity: params.commodity,
    market: params.market,
    q: params.q,
    from: params.from,
    to: params.to,
    sort: params.sort,
    page
  });

  const totalPages = Math.max(1, Math.ceil(result.total / result.pageSize));

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <div className="rounded-[2rem] border border-black/10 bg-white p-8">
        <p className="font-sans text-xs uppercase tracking-[0.35em] text-river">Archive</p>
        <h1 className="mt-2 font-serif text-5xl text-soil">Search the report ledger</h1>
        <form className="mt-8 grid gap-3 md:grid-cols-5">
          <input
            name="q"
            defaultValue={params.q}
            placeholder="Keyword search"
            className="rounded-2xl border border-black/10 px-4 py-3 text-sm"
          />
          <select
            name="commodity"
            defaultValue={params.commodity ?? ""}
            className="rounded-2xl border border-black/10 px-4 py-3 text-sm"
          >
            <option value="">All commodities</option>
            <option value="soybean">Soybean</option>
            <option value="cotton">Cotton</option>
          </select>
          <input
            name="market"
            defaultValue={params.market}
            placeholder="Market"
            className="rounded-2xl border border-black/10 px-4 py-3 text-sm"
          />
          <input
            type="date"
            name="from"
            defaultValue={params.from}
            className="rounded-2xl border border-black/10 px-4 py-3 text-sm"
          />
          <input
            type="date"
            name="to"
            defaultValue={params.to}
            className="rounded-2xl border border-black/10 px-4 py-3 text-sm"
          />
          <select
            name="sort"
            defaultValue={params.sort ?? "latest"}
            className="rounded-2xl border border-black/10 px-4 py-3 text-sm md:col-span-2 md:w-fit"
          >
            <option value="latest">Latest first</option>
            <option value="oldest">Oldest first</option>
            <option value="credibility">Highest credibility</option>
          </select>
          <button className="rounded-2xl bg-soil px-5 py-3 text-sm font-semibold text-white md:col-span-5 md:w-fit">
            Apply filters
          </button>
        </form>
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {result.articles.map((article) => (
          <ArticleCard key={article.id} article={article} />
        ))}
      </div>

      <div className="mt-10 flex items-center justify-between text-sm text-slate-600">
        <p>
          Showing page {result.page} of {totalPages} from {result.total} published reports.
        </p>
        <div className="flex gap-4">
          {result.page > 1 ? (
            <a
              href={`?${new URLSearchParams({ ...params, page: String(result.page - 1) }).toString()}`}
              className="font-semibold text-river"
            >
              Previous
            </a>
          ) : (
            <span className="text-slate-400">Previous</span>
          )}
          {result.page < totalPages ? (
            <a
              href={`?${new URLSearchParams({ ...params, page: String(result.page + 1) }).toString()}`}
              className="font-semibold text-river"
            >
              Next
            </a>
          ) : (
            <span className="text-slate-400">Next</span>
          )}
        </div>
      </div>
    </div>
  );
}

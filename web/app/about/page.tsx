export default function AboutPage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <div className="rounded-[2rem] border border-black/10 bg-white p-8">
        <p className="font-sans text-xs uppercase tracking-[0.35em] text-river">About</p>
        <h1 className="mt-2 font-serif text-5xl text-soil">Method before narrative.</h1>
        <div className="mt-8 space-y-6 text-base leading-8 text-slate-700">
          <p>
            MandiBhav by GramIQ turns OGD mandi data into structured market reports using a
            Python pipeline that performs ingestion, analytics, truthfulness checks, and SEO
            assembly before publication.
          </p>
          <p>
            Supabase is the source of truth for normalized market data, article bodies, and
            pipeline telemetry. Vercel serves the public Next.js frontend, which reads directly
            from the database instead of rebuilding static HTML files per run.
          </p>
          <p>
            Every report is published with explicit source labels, records analyzed,
            credibility scoring, report type, and timestamps so readers can inspect the basis
            of the summary rather than take it on trust.
          </p>
        </div>
      </div>
    </div>
  );
}

import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { TransparencyPanel } from "@/components/transparency-panel";
import { CallToActionBox } from "@/components/cta-box";
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
        <div className="space-y-8">
          <article className="rounded-[2rem] border border-black/10 bg-white p-8">
            <p className="font-sans text-xs uppercase tracking-[0.35em] text-river font-bold">
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

          {/* Visual FAQs Section */}
          {article.faqs && article.faqs.length > 0 && (
            <div className="rounded-[2rem] border border-black/10 bg-white p-8">
              <h2 className="font-serif text-3xl text-soil font-semibold mb-6">Frequently Asked Questions</h2>
              <div className="space-y-4">
                {article.faqs.map((faq, idx) => (
                  <details 
                    key={idx} 
                    className="group border border-black/5 rounded-2xl bg-slate-50/50 p-5 [&_summary::-webkit-details-marker]:hidden"
                  >
                    <summary className="flex items-center justify-between cursor-pointer focus:outline-none list-none">
                      <h3 className="font-serif text-lg font-semibold text-slate-800 pr-4 leading-snug">{faq.question}</h3>
                      <span className="relative flex-shrink-0 ml-1.5 w-5 h-5 text-slate-500">
                        <svg 
                          xmlns="http://www.w3.org/2000/svg" 
                          className="absolute inset-0 w-5 h-5 opacity-100 group-open:opacity-0 transition-opacity" 
                          fill="none" 
                          viewBox="0 0 24 24" 
                          stroke="currentColor" 
                          strokeWidth="2.5"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                        </svg>
                        <svg 
                          xmlns="http://www.w3.org/2000/svg" 
                          className="absolute inset-0 w-5 h-5 opacity-0 group-open:opacity-100 transition-opacity" 
                          fill="none" 
                          viewBox="0 0 24 24" 
                          stroke="currentColor" 
                          strokeWidth="2.5"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M20 12H4" />
                        </svg>
                      </span>
                    </summary>
                    <div className="mt-4 text-slate-600 leading-relaxed text-sm border-t border-black/5 pt-4">
                      {faq.answer}
                    </div>
                  </details>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-6">
          <TransparencyPanel article={article} />
          <CallToActionBox />
        </div>
      </div>
    </div>
  );
}

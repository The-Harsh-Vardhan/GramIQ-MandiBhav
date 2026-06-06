import Link from "next/link";
import type { ReactNode } from "react";

export function SiteShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-cloud text-slate-900 flex flex-col">
      {/* Navigation Bar */}
      <header className="border-b border-black/10 bg-white/80 sticky top-0 z-50 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center select-none group">
            <img 
              src="/logo.png" 
              alt="MandiBhav Logo" 
              className="h-10 w-auto object-contain transform group-hover:scale-[1.03] transition-transform duration-200"
            />
          </Link>

          <div className="flex items-center gap-6">
            <nav className="flex gap-6 font-sans text-sm font-semibold text-[#404A60]">
              <Link href="/" className="hover:text-river transition-colors">Home</Link>
              <Link href="/archive" className="hover:text-river transition-colors">Reports</Link>
              <Link href="/about" className="hover:text-river transition-colors">About</Link>
            </nav>

            <div className="lang-switcher border-l border-black/10 pl-6 h-8 flex items-center">
              <div id="google_translate_element" className="skiptranslate"></div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-grow min-h-[calc(100vh-180px)]">{children}</main>

      {/* Footer */}
      <footer className="bg-soil text-white border-t border-black/10 mt-auto">
        <div className="mx-auto max-w-6xl px-6 py-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <img 
                  src="/logo.png" 
                  alt="MandiBhav Logo" 
                  className="h-9 w-auto object-contain brightness-0 invert" 
                />
              </div>
              <p className="text-sm text-slate-300 leading-relaxed max-w-sm">
                AI-powered agricultural market intelligence for Indian farmers. Providing verified daily APMC prices in multiple languages.
              </p>
              <p className="text-xs italic text-grain font-medium">
                Pehle bhav jano, phir becho.
              </p>
            </div>
            <div>
              <h4 className="font-serif text-base font-semibold text-grain mb-4 uppercase tracking-wider">Commodities</h4>
              <ul className="space-y-2.5 text-sm text-slate-300">
                <li>
                  <Link href="/archive?commodity=soybean" className="hover:text-white transition-colors">Soybean Reports</Link>
                </li>
                <li>
                  <Link href="/archive?commodity=cotton" className="hover:text-white transition-colors">Cotton Reports</Link>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="font-serif text-base font-semibold text-grain mb-4 uppercase tracking-wider">Resources</h4>
              <ul className="space-y-2.5 text-sm text-slate-300">
                <li>
                  <a 
                    href="https://data.gov.in" 
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="hover:text-white transition-colors"
                  >
                    data.gov.in (OGD Portal)
                  </a>
                </li>
                <li>
                  <a href="/sitemap.xml" className="hover:text-white transition-colors">Sitemap</a>
                </li>
                <li>
                  <a href="/rss.xml" className="hover:text-white transition-colors">RSS Feed</a>
                </li>
                <li>
                  <a 
                    href="https://gramiq.ai" 
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="hover:text-white transition-colors"
                  >
                    GramIQ Official Site
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="border-t border-white/10 mt-12 pt-6 flex flex-col md:flex-row justify-between items-center gap-4 text-xs text-slate-400">
            <span>© {new Date().getFullYear()} GramIQ. Indicative rates only. Please check with your local APMC before trading.</span>
            <span>Powered by OGD &amp; Vercel</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

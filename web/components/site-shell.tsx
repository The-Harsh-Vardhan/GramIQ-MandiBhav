import Link from "next/link";
import type { ReactNode } from "react";

export function SiteShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-cloud text-slate-900">
      <header className="border-b border-black/10 bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <Link href="/" className="space-y-1">
            <p className="font-sans text-xs uppercase tracking-[0.35em] text-river">
              GramIQ
            </p>
            <p className="font-serif text-2xl text-soil">MandiBhav</p>
          </Link>
          <nav className="flex gap-6 font-sans text-sm font-medium">
            <Link href="/">Home</Link>
            <Link href="/archive">Archive</Link>
            <Link href="/about">About</Link>
          </nav>
        </div>
      </header>
      <main>{children}</main>
      <footer className="border-t border-black/10 bg-white/70">
        <div className="mx-auto max-w-6xl px-6 py-8 text-sm text-slate-600">
          Dynamic mandi intelligence powered by OGD data, Python analytics, Supabase, and
          Vercel.
        </div>
      </footer>
    </div>
  );
}

import type { Metadata } from "next";
import { Poppins, DM_Sans } from "next/font/google";
import Script from "next/script";

import "@/app/globals.css";
import { SiteShell } from "@/components/site-shell";

const titleFont = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800", "900"],
  variable: "--font-serif"
});

const bodyFont = DM_Sans({
  subsets: ["latin"],
  variable: "--font-sans"
});

const siteUrl = process.env.SITE_URL ?? "https://mandibhav-gramiq.vercel.app";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "MandiBhav by GramIQ",
  description: "Dynamic mandi intelligence platform for soybean and cotton markets.",
  icons: {
    icon: "/favicon.png",
  },
  openGraph: {
    title: "MandiBhav by GramIQ",
    description: "Dynamic mandi intelligence platform for soybean and cotton markets.",
    url: siteUrl,
    siteName: "MandiBhav by GramIQ",
    type: "website"
  },
  twitter: {
    card: "summary_large_image",
    title: "MandiBhav by GramIQ",
    description: "Dynamic mandi intelligence platform for soybean and cotton markets."
  }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${titleFont.variable} ${bodyFont.variable}`}>
      <body>
        <SiteShell>{children}</SiteShell>
        <Script
          id="google-translate-init"
          strategy="afterInteractive"
          dangerouslySetInnerHTML={{
            __html: `
              function googleTranslateElementInit() {
                new google.translate.TranslateElement({
                  pageLanguage: 'en',
                  includedLanguages: 'en,hi,mr,gu,pa,kn,ta,te,bn,ml,or,as,ur',
                  autoDisplay: false
                }, 'google_translate_element');
              }
            `,
          }}
        />
        <Script
          src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"
          strategy="afterInteractive"
        />
      </body>
    </html>
  );
}

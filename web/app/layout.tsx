import type { Metadata } from "next";
import { Fraunces, Work_Sans } from "next/font/google";

import "@/app/globals.css";
import { SiteShell } from "@/components/site-shell";

const serif = Fraunces({
  subsets: ["latin"],
  variable: "--font-serif"
});

const sans = Work_Sans({
  subsets: ["latin"],
  variable: "--font-sans"
});

const siteUrl = process.env.SITE_URL ?? "https://mandibhav.gramiq.com";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "MandiBhav by GramIQ",
  description: "Dynamic mandi intelligence platform for soybean and cotton markets.",
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
    <html lang="en" className={`${serif.variable} ${sans.variable}`}>
      <body>
        <SiteShell>{children}</SiteShell>
      </body>
    </html>
  );
}

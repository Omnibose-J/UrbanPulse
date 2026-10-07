import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";

import { siteUrl } from "@/lib/site";
import en from "../../messages/en.json";
import ko from "../../messages/ko.json";

// Pretendard Variable, dynamic subset: 92 unicode-range chunks, of which a page fetches only the ranges it uses
// (instead of the single 2 MB file next/font would inline). Next emits the chunks as static assets.
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./globals.css";

/** Shared card for every page; the title and the description follow the request's language (proxy header). */
export async function generateMetadata(): Promise<Metadata> {
  const locale = (await headers()).get("x-next-intl-locale") === "en" ? "en" : "ko";
  const text = locale === "en" ? en : ko;
  return {
    metadataBase: new URL(siteUrl()),
    title: { default: "UrbanPulse", template: "%s · UrbanPulse" },
    description: text.meta.description,
    applicationName: "UrbanPulse",
    manifest: "/manifest.webmanifest",
    icons: { icon: "/icon.svg", apple: "/apple-touch-icon.png" },
    openGraph: {
      type: "website",
      siteName: "UrbanPulse",
      locale: locale === "en" ? "en_US" : "ko_KR",
      title: "UrbanPulse",
      description: text.meta.description,
      images: [{ url: "/og.png", width: 1200, height: 630, alt: text.meta.ogAlt }],
    },
    twitter: { card: "summary_large_image", title: "UrbanPulse", description: text.meta.description, images: ["/og.png"] },
  };
}

export const viewport: Viewport = { themeColor: "#0f1822", width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const locale = (await headers()).get("x-next-intl-locale") ?? "ko";
  return (
    <html lang={locale} className="h-full">
      <body className="min-h-full">{children}</body>
    </html>
  );
}

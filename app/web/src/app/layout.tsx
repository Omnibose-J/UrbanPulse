import type { Metadata } from "next";
import { headers } from "next/headers";

// Pretendard Variable, dynamic subset: 92 unicode-range chunks, of which a page fetches only the ranges it uses
// (instead of the single 2 MB file next/font would inline). Next emits the chunks as static assets.
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "UrbanPulse", template: "%s · UrbanPulse" },
  description: "When to visit a Seoul place you already chose.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const locale = (await headers()).get("x-next-intl-locale") ?? "ko";
  return (
    <html lang={locale} className="h-full">
      <body className="min-h-full">{children}</body>
    </html>
  );
}

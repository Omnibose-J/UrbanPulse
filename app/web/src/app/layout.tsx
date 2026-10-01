import type { Metadata } from "next";
import { headers } from "next/headers";

import { pretendard } from "@/lib/font";

import "./globals.css";

export const metadata: Metadata = {
  title: "UrbanPulse",
  description: "When to visit a Seoul place you already chose.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const locale = (await headers()).get("x-next-intl-locale") ?? "ko";
  return (
    <html lang={locale} className={`${pretendard.variable} h-full`}>
      <body className={`${pretendard.className} min-h-full`}>{children}</body>
    </html>
  );
}

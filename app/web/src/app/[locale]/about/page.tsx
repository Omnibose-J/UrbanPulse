import type { Metadata } from "next";

import { titleOf } from "@/lib/page-title";
import { AboutScreen } from "@/screens/about";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  return titleOf(locale, (m) => m.about.title);
}

export default function Page() {
  return <AboutScreen />;
}

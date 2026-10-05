import type { Metadata } from "next";

import { titleOf } from "@/lib/page-title";
import { SearchScreen } from "@/screens/search";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  return titleOf(locale, (m) => m.search.title);
}

export default function Page() {
  return <SearchScreen />;
}

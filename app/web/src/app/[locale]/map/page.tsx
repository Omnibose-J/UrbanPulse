import type { Metadata } from "next";

import { titleOf } from "@/lib/page-title";
import { MapScreen } from "@/screens/map";

type Params = Promise<{ locale: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  return titleOf(locale, (m) => m.map.title);
}

export default async function Page({ searchParams }: { searchParams: Promise<{ date?: string; hour?: string }> }) {
  const query = await searchParams;
  return <MapScreen date={query.date} hour={query.hour} />;
}

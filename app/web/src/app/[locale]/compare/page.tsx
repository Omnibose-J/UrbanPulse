import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { titleOf } from "@/lib/page-title";
import { CompareScreen } from "@/screens/compare";

type Params = Promise<{ locale: string }>;
type Query = Promise<{ a?: string; b?: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  return titleOf(locale, (m) => m.compare.title);
}

const ID = /^[A-Z]{3}\d{3}$/;

export default async function Page({ params, searchParams }: { params: Params; searchParams: Query }) {
  const { locale } = await params;
  const { a, b } = await searchParams;
  // One valid place and no second one: pick the second in the search. Nothing valid: home.
  if (a && ID.test(a) && (!b || !ID.test(b) || b === a)) redirect(`/${locale}/search?compare=${a}`);
  if (!a || !ID.test(a) || !b || !ID.test(b)) redirect(`/${locale}`);
  return <CompareScreen key={`${a}/${b}`} a={a} b={b} />;
}

import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { findPlace } from "@/lib/queries";
import { WeekScreen } from "@/screens/week";

type Params = Promise<{ locale: string; id: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale, id } = await params;
  const place = await findPlace(id);
  if (!place) return {};
  return { title: locale === "en" && place.name_en ? place.name_en : place.name };
}

export default async function Page({ params, searchParams }: { params: Params; searchParams: Promise<{ notice?: string }> }) {
  const { id } = await params;
  const query = await searchParams;
  // An unknown place is a 404, not a 200 that says "not found".
  if (!(await findPlace(id))) notFound();
  return <WeekScreen key={id} id={id} notice={query.notice} />;
}

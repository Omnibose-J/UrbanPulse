import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { inServedRange, readDate } from "@/lib/http";
import { kstNow } from "@/lib/kst";
import { findPlace } from "@/lib/queries";
import { DayScreen } from "@/screens/day";

type Params = Promise<{ locale: string; id: string; date: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale, id, date } = await params;
  const place = await findPlace(id);
  if (!place) return {};
  const name = locale === "en" && place.name_en ? place.name_en : place.name;
  return { title: readDate(date) ? `${name} ${date}` : name };
}

export default async function Page({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<{ from?: string; hour?: string }>;
}) {
  const { locale, id, date } = await params;
  const query = await searchParams;
  // An unknown place is a 404, not a 200 that says "not found".
  if (!(await findPlace(id))) notFound();
  const today = kstNow().date;
  const valid = readDate(date);
  if (valid && valid < today) redirect(`/${locale}/p/${id}?notice=past`);
  if (!valid || !inServedRange(valid, today)) redirect(`/${locale}/p/${id}?notice=range`);
  // Keyed: a link to another date of the same place must start from a fresh screen, not reuse this one's state.
  return <DayScreen key={`${id}/${date}`} id={id} date={date} fromMap={query.from === "map"} hour={query.hour} />;
}

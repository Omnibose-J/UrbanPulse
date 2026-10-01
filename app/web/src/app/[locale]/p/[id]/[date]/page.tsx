import { redirect } from "next/navigation";

import { kstNow } from "@/lib/kst";
import { DayScreen } from "@/screens/day";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; id: string; date: string }>;
  searchParams: Promise<{ from?: string; hour?: string }>;
}) {
  const { locale, id, date } = await params;
  const query = await searchParams;
  if (date < kstNow().date) redirect(`/${locale}/p/${id}?notice=past`);
  return <DayScreen id={id} date={date} fromMap={query.from === "map"} hour={query.hour} />;
}

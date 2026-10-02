import { redirect } from "next/navigation";

import { inServedRange, readDate } from "@/lib/http";
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
  const today = kstNow().date;
  const valid = readDate(date);
  if (valid && valid < today) redirect(`/${locale}/p/${id}?notice=past`);
  if (!valid || !inServedRange(valid, today)) redirect(`/${locale}/p/${id}?notice=range`);
  return <DayScreen id={id} date={date} fromMap={query.from === "map"} hour={query.hour} />;
}

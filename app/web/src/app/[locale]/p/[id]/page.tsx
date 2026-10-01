import { WeekScreen } from "@/screens/week";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<{ notice?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  return <WeekScreen id={id} notice={query.notice} />;
}

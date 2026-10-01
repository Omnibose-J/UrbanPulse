import { MapScreen } from "@/screens/map";

export default async function Page({ searchParams }: { searchParams: Promise<{ date?: string; hour?: string }> }) {
  const query = await searchParams;
  return <MapScreen date={query.date} hour={query.hour} />;
}

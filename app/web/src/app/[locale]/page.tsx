import { HomeScreen } from "@/screens/home";

export default async function Page({ params }: { params: Promise<{ locale: "ko" | "en" }> }) {
  const { locale } = await params;
  return <HomeScreen locale={locale} />;
}

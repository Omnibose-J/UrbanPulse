import { NextIntlClientProvider } from "next-intl";
import { notFound } from "next/navigation";

import { routing } from "@/i18n/routing";
import en from "../../../messages/en.json";
import ko from "../../../messages/ko.json";

const messages = { ko, en };

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!routing.locales.includes(locale as "ko")) notFound();
  return (
    <NextIntlClientProvider locale={locale} messages={messages[locale as "ko"]}>
      {children}
    </NextIntlClientProvider>
  );
}

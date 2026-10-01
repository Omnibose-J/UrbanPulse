"use client";

import { useTranslations } from "next-intl";

import { Phone, StateBox } from "@/components/ui";
import { useLoad } from "@/lib/use-load";

type Row = { tier: string; foreign_heavy: boolean; purpose: string; tolerance: string; state: string; count: number };

export function AboutScreen() {
  const t = useTranslations();
  const loaded = useLoad<{ rows: Row[] }>("/api/flags");
  return (
    <Phone>
      <h1 className="display">{t("about.title")}</h1>
      <p className="body mt-4">{t("about.does")}</p>
      <p className="body mt-4">{t("about.how")}</p>
      <h2 className="section mb-2 mt-6">{t("about.flags")}</h2>
      {loaded.error ? <StateBox kind="error" onRetry={loaded.retry} /> : null}
      <table className="w-full text-left">
        <tbody>
          {(loaded.data?.rows ?? []).map((row) => (
            <tr key={`${row.tier}-${row.foreign_heavy}-${row.purpose}-${row.tolerance}-${row.state}`} className="row">
              <td className="caption">{row.tier}</td>
              <td className="caption">{row.purpose}</td>
              <td className="caption">{row.tolerance}</td>
              <td className="caption">{t(`about.${row.state === "on" ? "on" : row.state === "reference" ? "reference" : row.state === "off" ? "off" : "preparing"}`)}</td>
              <td className="caption text-right">{row.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="body mt-6">{t("about.limits")}</p>
      <p className="body mt-4">{t("about.sources")}</p>
    </Phone>
  );
}

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
            <tr key={`${row.tier}-${row.foreign_heavy}-${row.purpose}-${row.tolerance}-${row.state}`} className="border-b border-line">
              <td className="label py-2.5 pr-3">
                <span className="block font-semibold">
                  {t(`about.tier${row.tier}`)}
                  {row.foreign_heavy ? ` · ${t("about.foreign")}` : ""}
                </span>
                <span className="block text-text-3">
                  {row.purpose === "none" ? t(`tol.${row.tolerance}`) : `${t(`purpose.${row.purpose}`)} · ${t(`tol.${row.tolerance}`)}`}
                </span>
              </td>
              <td className="label whitespace-nowrap pr-3" style={{ color: row.state === "on" ? "var(--go-text)" : "var(--text-3)" }}>
                {t(`about.${row.state === "on" ? "on" : row.state === "reference" ? "reference" : row.state === "off" ? "off" : "preparing"}`)}
              </td>
              <td className="caption whitespace-nowrap text-right text-text-2">{t("about.places", { count: row.count })}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="body mt-6">{t("about.limits")}</p>
      <p className="body mt-4">{t("about.sources")}</p>
    </Phone>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useEffect } from "react";

/** A render or data error inside a screen: said in the app's own words, with a retry; never Next's default page.
 * The error itself goes to the console so a tester or the browser's error reporting still sees the cause. */
export default function ScreenError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useTranslations();
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="phone-shell px-4 pb-16">
      <div data-state="error" className="mt-14 rounded-[var(--r)] bg-bg-soft p-4">
        <p className="body" style={{ color: "var(--error-fg)" }}>
          {t("state.error")}
        </p>
        <button type="button" className="press body mt-2 font-semibold" onClick={reset}>
          {t("state.retry")}
        </button>
      </div>
    </div>
  );
}

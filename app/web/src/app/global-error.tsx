"use client";

import { useEffect } from "react";

import en from "../../messages/en.json";
import ko from "../../messages/ko.json";

/** The root layout itself failed, so there is no provider: the language comes from the address. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const locale = typeof window !== "undefined" && window.location.pathname.startsWith("/en") ? "en" : "ko";
  const text = locale === "en" ? en : ko;
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <html lang={locale}>
      <body style={{ margin: 0, fontFamily: "sans-serif", background: "#ffffff", color: "#101820" }}>
        <div style={{ maxWidth: 440, margin: "56px auto 0", padding: "0 16px" }}>
          <div data-state="error" style={{ background: "#f3f5f4", borderRadius: 12, padding: 16 }}>
            <p style={{ margin: 0, fontSize: 15, lineHeight: "22px", color: "#b42318" }}>{text.state.error}</p>
            <button type="button" onClick={reset} style={{ marginTop: 8, height: 48, fontSize: 15, fontWeight: 600, background: "none", border: 0, padding: 0, cursor: "pointer" }}>
              {text.state.retry}
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}

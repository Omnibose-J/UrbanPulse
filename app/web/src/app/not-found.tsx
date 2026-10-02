import { headers } from "next/headers";

import en from "../../messages/en.json";
import ko from "../../messages/ko.json";

// Rendered for any address no route matches. The locale comes from the header the middleware sets.
export default async function NotFound() {
  const locale = (await headers()).get("x-next-intl-locale") === "en" ? "en" : "ko";
  const text = locale === "en" ? en : ko;
  return (
    <div className="phone-shell px-4 pb-16">
      <div data-state="missing" className="mt-14 rounded-[var(--r)] bg-bg-soft p-4">
        <p className="body">{text.state.notFoundPage}</p>
        <a href={`/${locale}`} className="press body mt-2 flex items-center font-semibold" style={{ color: "var(--go-text)" }}>
          {text.nav.home}
        </a>
      </div>
    </div>
  );
}

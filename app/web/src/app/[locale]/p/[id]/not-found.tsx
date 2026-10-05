import { headers } from "next/headers";

import en from "../../../../../messages/en.json";
import ko from "../../../../../messages/ko.json";

// A place id that is not in `places` answers 404 with the place-missing state (design spec 5.10).
export default async function PlaceNotFound() {
  const locale = (await headers()).get("x-next-intl-locale") === "en" ? "en" : "ko";
  const text = locale === "en" ? en : ko;
  return (
    <div className="phone-shell px-4 pb-16">
      <div data-state="missing" className="mt-14 rounded-[var(--r)] bg-bg-soft p-4">
        <p className="body">{text.state.notFoundPlace}</p>
        <a href={`/${locale}`} className="press body mt-2 flex items-center font-semibold" style={{ color: "var(--go-text)" }}>
          {text.nav.home}
        </a>
      </div>
    </div>
  );
}

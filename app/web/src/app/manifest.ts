import type { MetadataRoute } from "next";

import ko from "../../messages/ko.json";

/** Web app manifest: lets a phone add the site to its home screen (iOS needs this before web push works). */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "UrbanPulse",
    short_name: "UrbanPulse",
    description: ko.meta.description,
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#0f1822",
    lang: "ko",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}

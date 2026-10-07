"use client";

/** Browser side of the weekend reminder: service worker registration, the push subscription, and the server call.
 * Every failure is returned as a named outcome so the screen can say what happened. */

const KEY = "urbanpulse.push";

export type PushOutcome = "on" | "off" | "denied" | "unsupported" | "failed";

export function pushSupported(): boolean {
  return typeof window !== "undefined" && typeof navigator.serviceWorker?.register === "function" && "PushManager" in window && "Notification" in window;
}

export function readPushOn(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

function writePushOn(on: boolean) {
  try {
    localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    // storage unavailable: the switch reads off again on the next visit
  }
}

function keyBytes(base64url: string): Uint8Array {
  const padding = "=".repeat((4 - (base64url.length % 4)) % 4);
  const base64 = (base64url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export async function enablePush(input: { locale: "ko" | "en"; placeIds: string[]; tolerance: string; purpose: string; vapidPublicKey: string }): Promise<PushOutcome> {
  if (!pushSupported()) return "unsupported";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  try {
    const registration = await navigator.serviceWorker.register("/sw.js");
    const existing = await registration.pushManager.getSubscription();
    const subscription = existing ?? (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(input.vapidPublicKey) as BufferSource }));
    const response = await fetch("/api/push/subscribe", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ subscription: subscription.toJSON(), locale: input.locale, place_ids: input.placeIds, tolerance: input.tolerance, purpose: input.purpose }),
    });
    if (!response.ok) return "failed";
    writePushOn(true);
    return "on";
  } catch {
    return "failed";
  }
}

export async function disablePush(): Promise<PushOutcome> {
  if (!pushSupported()) return "unsupported";
  try {
    const registration = await navigator.serviceWorker.getRegistration("/sw.js");
    const subscription = await registration?.pushManager.getSubscription();
    if (subscription) {
      const response = await fetch("/api/push/subscribe", { method: "DELETE", headers: { "content-type": "application/json" }, body: JSON.stringify({ endpoint: subscription.endpoint }) });
      if (!response.ok) return "failed";
      await subscription.unsubscribe();
    }
    writePushOn(false);
    return "off";
  } catch {
    return "failed";
  }
}

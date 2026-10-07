import assert from "node:assert/strict";
import test from "node:test";

import { isPushEndpoint, parseSubscribeBody, weekendDates, weekendMessage } from "./push.ts";

// Real shapes: a 65-byte key and a 16-byte secret in base64url.
const KEYS = { p256dh: "Bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", auth: "aaaaaaaaaaaaaaaaaaaaaa" };
const good = {
  subscription: { endpoint: "https://fcm.googleapis.com/fcm/send/abc", keys: KEYS },
  locale: "ko",
  place_ids: ["POI001", "STN016", "POI001"],
  tolerance: "moderate",
  purpose: "sight",
};

test("a valid subscribe body is accepted, duplicate place ids collapse, expirationTime is kept only as a number", () => {
  const parsed = parseSubscribeBody(good);
  assert.equal(parsed.ok, true);
  if (parsed.ok) {
    assert.deepEqual(parsed.body.place_ids, ["POI001", "STN016"]);
    assert.equal(parsed.body.subscription.expirationTime, null);
  }
});

test("each malformed field is refused with its name", () => {
  const cases: [unknown, RegExp][] = [
    [null, /object/],
    [{ ...good, subscription: undefined }, /subscription missing/],
    [{ ...good, subscription: { endpoint: "http://insecure", keys: good.subscription.keys } }, /endpoint/],
    [{ ...good, subscription: { endpoint: good.subscription.endpoint, keys: { p256dh: "" } } }, /keys/],
    [{ ...good, subscription: { endpoint: "https://attacker.example/x", keys: KEYS } }, /endpoint/],
    [{ ...good, subscription: { endpoint: "https://fcm.googleapis.com.attacker.example/x", keys: KEYS } }, /endpoint/],
    [{ ...good, subscription: { endpoint: "https://fcm.googleapis.com:8443/x", keys: KEYS } }, /endpoint/],
    [{ ...good, subscription: { endpoint: good.subscription.endpoint, keys: { ...KEYS, p256dh: "x".repeat(5000) } } }, /keys/],
    [{ ...good, subscription: { endpoint: good.subscription.endpoint, keys: { ...KEYS, auth: "a b" } } }, /keys/],
    [{ ...good, locale: "fr" }, /locale/],
    [{ ...good, place_ids: [] }, /place_ids/],
    [{ ...good, place_ids: ["drop table"] }, /place_ids/],
    [{ ...good, place_ids: Array.from({ length: 21 }, (_, i) => `POI${String(i).padStart(3, "0")}`) }, /place_ids/],
    [{ ...good, tolerance: "none" }, /tolerance/],
    [{ ...good, purpose: "none" }, /purpose/],
  ];
  for (const [input, pattern] of cases) {
    const parsed = parseSubscribeBody(input);
    assert.equal(parsed.ok, false);
    if (!parsed.ok) assert.match(parsed.error, pattern);
  }
});

test("weekend dates: the coming Saturday and Sunday; on the weekend itself, the current one", () => {
  assert.deepEqual(weekendDates("2026-10-06"), ["2026-10-10", "2026-10-11"]); // Tuesday
  assert.deepEqual(weekendDates("2026-10-09"), ["2026-10-10", "2026-10-11"]); // Friday
  assert.deepEqual(weekendDates("2026-10-10"), ["2026-10-10", "2026-10-11"]); // Saturday
  assert.deepEqual(weekendDates("2026-10-11"), ["2026-10-10", "2026-10-11"]); // Sunday
  assert.deepEqual(weekendDates("2026-10-12"), ["2026-10-17", "2026-10-18"]); // Monday
});

test("the message has one line per place with a pick, uses the English name when there is one, and is null with no picks", () => {
  const copy = { title: "T", line: (name: string, day: string, range: string) => `${name} ${day} ${range}`, none: "", sat: "토", sun: "일" };
  const picks = [
    { place_id: "POI001", name: "경복궁", name_en: "Gyeongbokgung", date: "2026-10-10", range: "10~12시" },
    { place_id: "POI002", name: "성수", name_en: null, date: "2026-10-11", range: "13~15시" },
  ];
  assert.deepEqual(weekendMessage(picks, "ko", copy, "2026-10-10"), { title: "T", body: "경복궁 토 10~12시\n성수 일 13~15시" });
  assert.equal(weekendMessage(picks, "en", copy, "2026-10-10")!.body.split("\n")[0], "Gyeongbokgung 토 10~12시");
  assert.equal(weekendMessage([], "ko", copy, "2026-10-10"), null);
});

test("only the browsers' push services are endpoints", () => {
  for (const ok of [
    "https://fcm.googleapis.com/fcm/send/abc",
    "https://web.push.apple.com/QJx",
    "https://updates.push.services.mozilla.com/wpush/v2/abc",
    "https://wns2-par02p.notify.windows.com/w/?token=abc",
  ]) assert.equal(isPushEndpoint(ok), true, ok);
  for (const bad of ["http://fcm.googleapis.com/x", "https://169.254.169.254/latest", "https://localhost/x", "https://evilpush.apple.com.example/x", "nope", 42]) {
    assert.equal(isPushEndpoint(bad), false, String(bad));
  }
});

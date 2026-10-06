import assert from "node:assert/strict";
import test from "node:test";

import { kindKey, kindRank } from "./kind.ts";

test("every Seoul category maps to a message key; no category means no chip; an unknown one throws", () => {
  assert.equal(kindKey("관광특구"), "kind.tourist");
  assert.equal(kindKey("발달상권"), "kind.district");
  assert.equal(kindKey("고궁·문화유산"), "kind.heritage");
  assert.equal(kindKey("공원"), "kind.park");
  assert.equal(kindKey("인구밀집지역"), "kind.dense");
  assert.equal(kindKey("역세권"), "kind.station");
  assert.equal(kindKey(null), null);
  assert.equal(kindKey(undefined), null);
  assert.throws(() => kindKey("놀이공원"));
});

test("commuter stations rank after every other kind", () => {
  assert.equal(kindRank("인구밀집지역"), 1);
  for (const kind of ["관광특구", "발달상권", "고궁·문화유산", "공원", null]) assert.equal(kindRank(kind), 0);
});

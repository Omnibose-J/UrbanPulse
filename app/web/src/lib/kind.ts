/** Seoul's place category (`places.category`) as a message key and a ranking for the home lists. The categories are
 * the city's own labels; an unknown one is a data defect, not a blank chip. */
const KEYS: Record<string, string> = {
  관광특구: "tourist",
  발달상권: "district",
  "고궁·문화유산": "heritage",
  공원: "park",
  인구밀집지역: "dense",
  역세권: "station",
};

export function kindKey(category: string | null | undefined): string | null {
  if (category === null || category === undefined) return null;
  const key = KEYS[category];
  if (!key) throw new Error(`unknown place category: ${category}`);
  return `kind.${key}`;
}

/** Home lists put commuter stations ("인구밀집지역": 강남역, 가산디지털단지역 …) after places people go to for their own
 * sake. 0 comes first. */
export function kindRank(category: string | null | undefined): number {
  return category === "인구밀집지역" ? 1 : 0;
}

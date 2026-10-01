export type ReasonWindow = {
  crowd?: number;
  act?: string | null;
  act_level?: string | null;
};

/** Message ids for the answer-card sentence. The caller translates them. */
export function reasonMessageIds(tier: string, window: ReasonWindow | null | undefined): string[] {
  if (!window || window.crowd === undefined || window.crowd === null) return [];
  if (tier === "B") {
    const band = window.crowd <= 0 ? 0 : window.crowd === 1 ? 1 : 2;
    return [`reason.b${band}`];
  }
  const ids = [`reason.crowd${window.crowd}`];
  if (window.act && window.act_level) {
    const level = window.act_level === "lively" ? "Lively" : "Quiet";
    ids.push(`reason.${window.act}${level}`);
  }
  return ids;
}

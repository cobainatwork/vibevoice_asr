import type { Segment } from "../api/types";

export const SIMILARITY_THRESHOLD = 0.8;

export interface SubtitleMatch {
  text: string;
  similarity: number;
}

/**
 * 取時段交集內的所有 YT 字幕、拼接成單一文字。
 * 規則：任何跟 [start, end] 有交集的 ref segment 都納入。
 */
export function findSubtitleAtTime(
  refSubs: Segment[],
  start: number,
  end: number,
): string {
  const matched = refSubs.filter(
    (s) => s.start_time < end && s.end_time > start,
  );
  return matched.map((s) => s.text).join(" ").trim();
}

/**
 * Levenshtein distance / max(len(a), len(b))，回 similarity (1 - editDist/max)。
 * 對短字串(< 500 chars)效能足夠。空字串對任何 → 0(完全不同)、雙空 → 1。
 */
export function computeSimilarity(a: string, b: string): number {
  if (a === b) return 1;
  if (a.length === 0 || b.length === 0) return 0;

  const m = a.length;
  const n = b.length;
  const dp: number[] = Array(n + 1).fill(0);
  for (let j = 0; j <= n; j++) dp[j] = j;

  for (let i = 1; i <= m; i++) {
    let prev = dp[0];
    dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const tmp = dp[j];
      if (a[i - 1] === b[j - 1]) {
        dp[j] = prev;
      } else {
        dp[j] = Math.min(prev, dp[j], dp[j - 1]) + 1;
      }
      prev = tmp;
    }
  }
  return 1 - dp[n] / Math.max(m, n);
}

export function matchSubtitle(
  refSubs: Segment[] | null,
  asrSegment: Segment,
): SubtitleMatch | null {
  if (refSubs === null || refSubs.length === 0) return null;
  const refText = findSubtitleAtTime(
    refSubs, asrSegment.start_time, asrSegment.end_time,
  );
  if (!refText) return null;
  return {
    text: refText,
    similarity: computeSimilarity(asrSegment.text, refText),
  };
}

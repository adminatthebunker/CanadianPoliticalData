/**
 * Per-platform credit costs and cadence math for the user-billed
 * politician-monitoring feature.
 *
 * Calibration draft (anchored at $0.10/credit, the small-pack rate):
 *
 *   Twitter   5 credits (~$0.50)  — Apify ~$0.04 actual, ~12x markup
 *                                   to amortize Apify plan fee + margin
 *   Instagram 8 credits (~$0.80)  — Apify ~$0.15 actual, ~5x markup
 *   Bluesky   1 credit  (~$0.10)  — free upstream; charge covers our
 *                                   compute + storage
 *   Mastodon  1 credit  (~$0.10)  — free upstream
 *
 * These are tunable constants — change them here and the API
 * cost-estimate endpoint + scrape worker both pick up the new rate.
 * Existing in-flight holds are unaffected (estimated_credits is
 * snapshotted into scrape_jobs at hold time).
 *
 * Phase 2 platforms (TikTok / Threads / facebook) ship later; left
 * out of the SUPPORTED_PLATFORMS export below so the API rejects
 * subscriptions to them until then.
 */

export type ScrapePlatform =
  | "twitter"
  | "bluesky"
  | "instagram"
  | "mastodon"
  | "tiktok"
  | "threads"
  | "facebook";

export type ScrapeCadence = "weekly" | "monthly" | "quarterly";

/**
 * Three job kinds share the scrape pipeline:
 *
 *   monitoring  recurring, cadence-driven, flat per-refresh cost.
 *   preflight   one-shot, cheap; returns profile metadata + cost
 *               calculator so the UI can right-size monitoring or
 *               quote an archive job.
 *   archive     one-shot, volume-priced; pulls a deep history (up to
 *               the full lifetime feed) in a single run.
 */
export type ScrapeKind = "monitoring" | "preflight" | "archive";

/**
 * Flat per-platform preflight cost. Free for platforms with free
 * public profile APIs (Bluesky / Mastodon); 1 credit for Apify-backed
 * platforms to cover the actor invocation. Cheap enough to invoke
 * automatically when a user opens the monitor dialog.
 */
const PREFLIGHT_CREDITS: Record<ScrapePlatform, number> = {
  twitter: 1,
  instagram: 1,
  bluesky: 0,
  mastodon: 0,
  tiktok: 0,
  threads: 0,
  facebook: 0,
};

/**
 * Tiered archive pricing curve. Apify charges $0.40/1k tweets with a
 * 50-tweet minimum per query, so the curve has a floor and a
 * per-50-tweets increment above. ~2.5x markup over Apify cost.
 *
 *   floor       — covers Apify's 50-tweet minimum + our overhead.
 *   perBucket   — additional credits per `bucketSize` tweets above
 *                 the first 50.
 *   bucketSize  — granularity of the curve.
 *
 * Example for Twitter (floor=10, perBucket=1, bucketSize=50):
 *
 *   50 tweets   → 10 credits  ($1.00)
 *   100 tweets  → 11 credits  ($1.10)
 *   1000 tweets → 29 credits  ($2.90)
 *   5000 tweets → 109 credits ($10.90)
 *
 * Tunable per platform — Instagram + TikTok have different upstream
 * pricing shapes and need their own curves once implemented.
 */
interface ArchiveCurve {
  floor: number;
  perBucket: number;
  bucketSize: number;
}

const ARCHIVE_CURVES: Record<ScrapePlatform, ArchiveCurve> = {
  twitter: { floor: 10, perBucket: 1, bucketSize: 50 },
  instagram: { floor: 15, perBucket: 2, bucketSize: 50 },
  bluesky: { floor: 5, perBucket: 1, bucketSize: 100 },
  mastodon: { floor: 5, perBucket: 1, bucketSize: 100 },
  tiktok: { floor: 0, perBucket: 0, bucketSize: 1 },
  threads: { floor: 0, perBucket: 0, bucketSize: 1 },
  facebook: { floor: 0, perBucket: 0, bucketSize: 1 },
};

/**
 * Cost to archive `postCount` posts from `platform`. Always at least
 * the floor; bucket-rounded above. Caller passes the post count from
 * pre-flight metadata (politician_socials.lifetime_post_count).
 */
export function archiveCreditsFor(
  platform: ScrapePlatform,
  postCount: number
): number {
  if (!SUPPORTED_PLATFORMS.has(platform)) {
    throw new Error(`platform not supported in v1: ${platform}`);
  }
  const curve = ARCHIVE_CURVES[platform];
  if (postCount <= curve.bucketSize) return curve.floor;
  const extraPosts = postCount - curve.bucketSize;
  const extraBuckets = Math.ceil(extraPosts / curve.bucketSize);
  return curve.floor + extraBuckets * curve.perBucket;
}

/**
 * Pre-flight cost — flat, per platform. Sums across the list.
 */
export function preflightCreditsFor(
  platforms: readonly ScrapePlatform[]
): number {
  let total = 0;
  for (const p of platforms) {
    if (!SUPPORTED_PLATFORMS.has(p)) {
      throw new Error(`platform not supported in v1: ${p}`);
    }
    total += PREFLIGHT_CREDITS[p];
  }
  return total;
}

const CREDITS_PER_PLATFORM: Record<ScrapePlatform, number> = {
  twitter: 5,
  instagram: 8,
  bluesky: 1,
  mastodon: 1,
  // Phase 2 — listed for type completeness but gated below.
  tiktok: 0,
  threads: 0,
  facebook: 0,
};

const SUPPORTED_PLATFORMS: ReadonlySet<ScrapePlatform> = new Set([
  "twitter",
  "bluesky",
  "instagram",
  "mastodon",
]);

const RUNS_PER_MONTH: Record<ScrapeCadence, number> = {
  weekly: 4,
  monthly: 1,
  quarterly: 1 / 3,
};

const INTERVAL_DAYS: Record<ScrapeCadence, number> = {
  weekly: 7,
  monthly: 30,
  quarterly: 91,
};

export function isPlatformSupported(p: string): p is ScrapePlatform {
  return SUPPORTED_PLATFORMS.has(p as ScrapePlatform);
}

export function isCadence(c: string): c is ScrapeCadence {
  return c === "weekly" || c === "monthly" || c === "quarterly";
}

export function creditsForPlatform(platform: ScrapePlatform): number {
  if (!SUPPORTED_PLATFORMS.has(platform)) {
    throw new Error(`platform not supported in v1: ${platform}`);
  }
  return CREDITS_PER_PLATFORM[platform];
}

/**
 * Sum of per-run credit cost across a list of platforms. Caller is
 * responsible for de-duping the input list.
 */
export function creditsPerRun(platforms: readonly ScrapePlatform[]): number {
  let total = 0;
  for (const p of platforms) total += creditsForPlatform(p);
  return total;
}

export function runsPerMonth(cadence: ScrapeCadence): number {
  return RUNS_PER_MONTH[cadence];
}

/**
 * Cost-estimate payload for the subscription UI's confirm modal.
 * `total_per_month` is a float (quarterly is one run every three
 * months); the UI rounds for display.
 */
export interface ScrapeCostEstimate {
  platforms: ScrapePlatform[];
  cadence: ScrapeCadence;
  credits_per_run: number;
  runs_per_month: number;
  total_per_month: number;
}

export function estimateScrapeCost(
  platforms: readonly ScrapePlatform[],
  cadence: ScrapeCadence
): ScrapeCostEstimate {
  const perRun = creditsPerRun(platforms);
  const perMonth = runsPerMonth(cadence);
  return {
    platforms: [...platforms],
    cadence,
    credits_per_run: perRun,
    runs_per_month: perMonth,
    total_per_month: perRun * perMonth,
  };
}

/**
 * Compute next-run timestamp from the cadence interval. Used at
 * subscription-create / cadence-change time and after every dispatch
 * tick to advance the watermark.
 */
export function nextRunAt(cadence: ScrapeCadence, from: Date = new Date()): Date {
  const days = INTERVAL_DAYS[cadence];
  return new Date(from.getTime() + days * 24 * 60 * 60 * 1000);
}

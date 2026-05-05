import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query } from "../db.js";
import { optionalUser, getUser, requireUser } from "../middleware/user-auth.js";
import { sendCorrectionInboxNotification, emailIsConfigured } from "../lib/email.js";
import { config } from "../config.js";

/**
 * Public corrections intake + signed-in user's own submissions list.
 *
 * POST /api/v1/corrections — public. If a valid user session is
 * present, we attach `user_id` and default `submitter_email` to the
 * user's email when the form didn't include one. Rate-limited per-IP
 * to keep the inbox sane; spam is the reviewer's problem for now.
 *
 * GET  /api/v1/me/corrections — authed (mounted separately under the
 * /me prefix, see index.ts). Lists the signed-in user's submissions,
 * newest first.
 */

const SUBJECT_TYPES = ["speech", "bill", "politician", "vote", "organization", "general"] as const;

const submitBody = z.object({
  subject_type: z.enum(SUBJECT_TYPES),
  subject_id: z.string().uuid().optional().nullable(),
  issue: z.string().trim().min(5).max(5000),
  proposed_fix: z.string().trim().max(5000).optional().nullable(),
  // Zod's .url() accepts javascript:/data:/file: schemes because it
  // defers to the WHATWG URL parser. That value is later rendered as
  // an <a href> in the admin review UI, so anything other than http(s)
  // is a stored-XSS sink. Lock the scheme here at the boundary.
  evidence_url: z
    .string()
    .trim()
    .max(2000)
    .url()
    .refine((u) => /^https?:\/\//i.test(u), {
      message: "evidence_url must be http(s)",
    })
    .optional()
    .nullable(),
  submitter_name: z.string().trim().max(200).optional().nullable(),
  submitter_email: z.string().trim().email().max(320).optional().nullable(),
});

interface CorrectionRow {
  id: string;
  subject_type: string;
  subject_id: string | null;
  issue: string;
  proposed_fix: string | null;
  evidence_url: string | null;
  status: string;
  reviewer_notes: string | null;
  received_at: string;
  resolved_at: string | null;
}

interface OwnCorrectionRow extends CorrectionRow {
  /**
   * Credits granted to this user for this specific correction (the
   * credit_ledger row with kind='correction_reward' and
   * reference_id=correction.id). 0 if no reward has landed yet —
   * either because the correction isn't applied, or because it was
   * applied before the reward feature shipped (no backfill).
   */
  credits_earned: number;
}

export default async function correctionsRoutes(app: FastifyInstance) {
  // ── POST /api/v1/corrections ──────────────────────────────────
  app.post(
    "/",
    {
      config: {
        rateLimit: { max: 5, timeWindow: "1 hour" },
      },
      preHandler: optionalUser,
    },
    async (req, reply) => {
      const parsed = submitBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({
          error: "invalid body",
          details: parsed.error.flatten(),
        });
      }
      const body = parsed.data;
      const signedInUser = getUser(req);

      // If signed in and submitter didn't give an email, default to the
      // account's email so reviewers can thread a reply.
      const submitter_email = body.submitter_email || signedInUser?.email || null;
      if (!submitter_email && !signedInUser) {
        return reply.code(400).send({
          error: "anonymous submissions require an email address",
        });
      }

      const rows = await query<CorrectionRow>(
        `INSERT INTO private.correction_submissions
            (subject_type, subject_id, issue, proposed_fix, evidence_url,
             submitter_name, submitter_email, user_id, source, raw)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'web', $9::jsonb)
         RETURNING id, subject_type, subject_id, issue, proposed_fix,
                   evidence_url, status, reviewer_notes, received_at, resolved_at`,
        [
          body.subject_type,
          body.subject_id ?? null,
          body.issue,
          body.proposed_fix ?? null,
          body.evidence_url ?? null,
          body.submitter_name ?? null,
          submitter_email,
          signedInUser?.sub ?? null,
          JSON.stringify({ ua: req.headers["user-agent"] ?? null }),
        ]
      );
      const inserted = rows[0];
      if (!inserted) {
        // Should be unreachable — INSERT … RETURNING always yields a row
        // unless an error already threw above.
        return reply.code(500).send({ error: "insert returned no row" });
      }
      // Fire-and-forget: notify all admins. Failure here must not roll
      // back the insert or the submitter's response. The notify path is
      // a no-op when SMTP is unconfigured (dev-stub mode).
      void notifyAdminsOfNewCorrection(req, {
        id: inserted.id,
        subjectType: inserted.subject_type,
        issue: inserted.issue,
        submitterName: body.submitter_name ?? null,
        submitterEmail: submitter_email,
        signedInUserDisplay: signedInUser?.email ?? null,
      });
      return reply.code(201).send(inserted);
    }
  );
}

/**
 * Lookup admin emails and fire one inbox-notification email per admin.
 * Skips bounced addresses and dedupes on the submitter (an admin who
 * submits their own correction shouldn't email themselves about it).
 * All sends are fire-and-forget; errors are logged at warn level.
 */
async function notifyAdminsOfNewCorrection(
  req: { log: { warn: (o: object, m: string) => void; info: (o: object, m: string) => void } },
  payload: {
    id: string;
    subjectType: string;
    issue: string;
    submitterName: string | null;
    submitterEmail: string | null;
    signedInUserDisplay: string | null;
  },
): Promise<void> {
  if (!emailIsConfigured()) return;
  try {
    const admins = await query<{ email: string }>(
      `SELECT email
         FROM private.users
        WHERE is_admin = true
          AND email_bounced_at IS NULL`,
    );
    if (admins.length === 0) return;

    const submitterLabel = payload.signedInUserDisplay
      ? `${payload.signedInUserDisplay} (signed in)`
      : payload.submitterName && payload.submitterEmail
        ? `${payload.submitterName} <${payload.submitterEmail}>`
        : payload.submitterEmail || payload.submitterName || "anonymous";

    const adminUrl = `${config.publicSiteUrl}/admin/corrections`;
    const submitterEmail = payload.submitterEmail?.toLowerCase() ?? null;

    for (const a of admins) {
      // Don't email an admin about their own submission.
      if (submitterEmail && a.email.toLowerCase() === submitterEmail) continue;
      try {
        await sendCorrectionInboxNotification(
          {
            to: a.email,
            subjectType: payload.subjectType,
            issue: payload.issue,
            submitter: submitterLabel,
            adminUrl,
          },
          req.log,
        );
      } catch (err) {
        req.log.warn(
          { err: err instanceof Error ? err.message : String(err), to: a.email, correction_id: payload.id },
          "correction inbox notification failed",
        );
      }
    }
  } catch (err) {
    req.log.warn(
      { err: err instanceof Error ? err.message : String(err), correction_id: payload.id },
      "correction inbox notification: admin roster lookup failed",
    );
  }
}

/** Mounted under /api/v1/me — lists the signed-in user's submissions. */
export async function meCorrectionsRoutes(app: FastifyInstance) {
  app.get("/corrections", { preHandler: requireUser }, async (req, reply) => {
    const claims = getUser(req);
    if (!claims) return reply.code(401).send({ error: "not signed in" });
    const rows = await query<OwnCorrectionRow>(
      `SELECT cs.id, cs.subject_type, cs.subject_id, cs.issue, cs.proposed_fix,
              cs.evidence_url, cs.status, cs.reviewer_notes,
              cs.received_at, cs.resolved_at,
              COALESCE(cl.delta, 0)::int AS credits_earned
         FROM private.correction_submissions cs
         LEFT JOIN private.credit_ledger cl
                ON cl.reference_id = cs.id::text
               AND cl.kind = 'correction_reward'
               AND cl.state IN ('committed','held')
        WHERE cs.user_id = $1
        ORDER BY cs.received_at DESC
        LIMIT 200`,
      [claims.sub]
    );
    return reply.send({ corrections: rows });
  });
}

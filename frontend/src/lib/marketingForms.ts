/**
 * marketingForms.ts
 * ─────────────────────────────────────────────────────────────
 * Ported from the static LiveVault demo site's `forms-config.js`.
 * Submits the clinic feedback form (src/pages/marketing/FeedbackPage.tsx)
 * straight to the same Google Form the demo site used — no backend
 * changes needed, and no functionality lost in the conversion to React.
 *
 * Uses mode: "no-cors" because Google Forms doesn't return CORS
 * headers — the request still goes through, we just can't read the
 * response, which is fine since we don't need to.
 * ─────────────────────────────────────────────────────────────
 */

const FEEDBACK_FORM = {
  formId: '1FAIpQLSc6h2Xv6ffrP16qPli9wX2QPQH0rF7_BtRySbiRJpFxcKuK5A',
  fields: {
    clinicName: 'entry.537912217',
    email: 'entry.1427451139',
    noShowRate: 'entry.1766799085',
    currentTool: 'entry.900432749',
    whoBooks: 'entry.2004125205',
    willingnessToPay: 'entry.1083622410',
    extraNotes: 'entry.2009941995',
  },
} as const;

export interface FeedbackFormValues {
  clinicName: string;
  email?: string;
  noShowRate?: string;
  currentTool?: string;
  whoBooks?: string;
  willingnessToPay?: string;
  extraNotes?: string;
}

export async function submitFeedback(values: FeedbackFormValues): Promise<{ ok: boolean; reason?: string }> {
  const actionUrl = `https://docs.google.com/forms/d/e/${FEEDBACK_FORM.formId}/formResponse`;
  const body = new URLSearchParams();

  for (const [key, entryId] of Object.entries(FEEDBACK_FORM.fields)) {
    const value = (values as unknown as Record<string, string | undefined>)[key];
    if (value) body.append(entryId, value);
  }

  try {
    await fetch(actionUrl, {
      method: 'POST',
      mode: 'no-cors',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    // With no-cors we can't inspect the response status — Google Forms
    // reliably accepts well-formed submissions, so a fetch that doesn't
    // throw is treated as success (same assumption the demo site made).
    return { ok: true };
  } catch (err) {
    console.error('[Vitar] Feedback submission failed:', err);
    return { ok: false, reason: 'network_error' };
  }
}

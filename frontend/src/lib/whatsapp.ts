/**
 * Vitar Enterprise sales WhatsApp link.
 *
 * Same official Vitar WhatsApp number already used on the marketing pages
 * (ContactPage, LandingPage, Privacy/Terms) — reused here rather than
 * introducing a second number.
 *
 * wa.me is its own graceful fallback: it opens the WhatsApp app when
 * installed, and falls back to WhatsApp Web in the browser when it isn't —
 * no separate device-detection branch needed.
 */
export const VITAR_SALES_WHATSAPP = '2348156792070';

export function buildEnterpriseWhatsAppUrl(hospitalName?: string, doctorCount?: number): string {
  const lines = [
    'Hello Vitar Team,',
    '',
    'We are interested in the Enterprise plan for our hospital.',
  ];
  if (hospitalName) {
    lines.push(
      doctorCount
        ? `We are ${hospitalName}, and we currently have approximately ${doctorCount} doctor${doctorCount === 1 ? '' : 's'}.`
        : `We are ${hospitalName}.`,
    );
  } else if (doctorCount) {
    lines.push(`We currently have approximately ${doctorCount} doctor${doctorCount === 1 ? '' : 's'}.`);
  }
  lines.push(
    '',
    'We would like to discuss pricing, implementation, and available features.',
    '',
    'Please let us know the best package for our requirements.',
    '',
    'Thank you.',
  );
  return `https://wa.me/${VITAR_SALES_WHATSAPP}?text=${encodeURIComponent(lines.join('\n'))}`;
}

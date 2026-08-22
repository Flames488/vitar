/**
 * Vitar — Cloudflare Turnstile widget.
 *
 * Uses Turnstile's explicit render API (window.turnstile.render) rather
 * than relying on its script auto-scanning the DOM for a .cf-turnstile div
 * on load — this is a client-rendered SPA, so the container element doesn't
 * exist yet when api.js first runs its scan.
 *
 * Renders nothing if VITE_TURNSTILE_SITE_KEY isn't set (local dev without a
 * site key configured) — onVerify never fires, so callers should treat a
 * missing token as "not required" only when they know the backend is also
 * unconfigured (verify_turnstile fails open with no TURNSTILE_SECRET_KEY).
 */
import { useEffect, useRef, useState } from 'react';

const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;

declare global {
  interface Window {
    turnstile?: {
      render: (container: HTMLElement, options: Record<string, unknown>) => string;
      remove: (widgetId: string) => void;
      reset: (widgetId: string) => void;
    };
  }
}

interface TurnstileWidgetProps {
  onVerify: (token: string) => void;
}

export default function TurnstileWidget({ onVerify }: TurnstileWidgetProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!SITE_KEY) return;

    let cancelled = false;
    let pollId: ReturnType<typeof setInterval> | undefined;

    const tryRender = () => {
      if (cancelled || !containerRef.current || widgetIdRef.current) return;
      if (!window.turnstile) return;
      widgetIdRef.current = window.turnstile.render(containerRef.current, {
        sitekey: SITE_KEY,
        callback: onVerify,
      });
      setReady(true);
      if (pollId) clearInterval(pollId);
    };

    // api.js loads async — poll briefly until window.turnstile exists rather
    // than assuming load order.
    pollId = setInterval(tryRender, 100);
    tryRender();

    return () => {
      cancelled = true;
      if (pollId) clearInterval(pollId);
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!SITE_KEY) return null;

  return <div ref={containerRef} aria-live="polite" style={{ minHeight: ready ? undefined : 65 }} />;
}

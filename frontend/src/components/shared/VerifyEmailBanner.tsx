/**
 * Vitar — Verify Email Banner
 * Soft nudge, not a gate — dismissible, shown while user.is_verified is
 * false. Full account access already works either way (see auth.py's
 * register()/login(), neither checks is_verified).
 */
import { useState } from 'react';
import { Mail, X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { authApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';

export default function VerifyEmailBanner() {
  const [dismissed, setDismissed] = useState(false);
  const [sending, setSending] = useState(false);
  if (dismissed) return null;

  const handleResend = async () => {
    setSending(true);
    try {
      await authApi.resendVerification();
      toast.success('Verification email sent — check your inbox');
    } catch (err) {
      toast.error(getApiError(err));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-4 px-4 py-2.5 text-sm bg-sky-600 text-white">
      <div className="flex items-center gap-2 min-w-0">
        <Mail className="w-4 h-4 flex-shrink-0" />
        <span className="truncate">Please verify your email address to secure your account.</span>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        <button
          onClick={handleResend}
          disabled={sending}
          className="flex items-center gap-1.5 bg-white/20 hover:bg-white/30 disabled:opacity-60 px-3 py-1 rounded-full text-white text-xs font-semibold transition-colors"
        >
          {sending && <Loader2 className="w-3 h-3 animate-spin" />}
          Resend email
        </button>
        <button onClick={() => setDismissed(true)} className="text-white/70 hover:text-white">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

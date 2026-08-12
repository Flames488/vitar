/**
 * Vitar — Verify Email Page
 * Lands here from the link in the verification email. Auto-verifies on
 * mount (no form — the token in the URL is the only input needed).
 */
import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { authApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { useAuthStore } from '@/stores/authStore';

type Status = 'verifying' | 'success' | 'error';

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const token = searchParams.get('token') ?? '';
  const [status, setStatus] = useState<Status>('verifying');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setError('This verification link is missing its token.');
      return;
    }
    authApi.verifyEmail(token)
      .then(() => {
        setStatus('success');
        // Keep any locally-cached user profile in sync so the dashboard
        // banner disappears immediately without waiting for a session refetch.
        if (user) useAuthStore.setState({ user: { ...user, is_verified: true } });
        setTimeout(() => navigate(user ? '/dashboard' : '/login'), 2500);
      })
      .catch((err) => {
        setStatus('error');
        setError(getApiError(err));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="text-center">
      {status === 'verifying' && (
        <>
          <Loader2 className="w-10 h-10 text-teal-600 animate-spin mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-1">Verifying your email…</h2>
          <p className="text-slate-500 text-sm">One moment.</p>
        </>
      )}
      {status === 'success' && (
        <>
          <CheckCircle2 className="w-10 h-10 text-teal-600 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-1">Verification complete!</h2>
          <p className="text-slate-500 text-sm">Redirecting you now…</p>
        </>
      )}
      {status === 'error' && (
        <>
          <XCircle className="w-10 h-10 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-1">Couldn't verify email</h2>
          <p className="text-slate-500 text-sm mb-4">{error || 'This link may be invalid or already used.'}</p>
          <Link to={user ? '/dashboard' : '/login'} className="text-teal-600 hover:underline text-sm">
            {user ? 'Back to dashboard' : 'Back to login'}
          </Link>
        </>
      )}
    </div>
  );
}

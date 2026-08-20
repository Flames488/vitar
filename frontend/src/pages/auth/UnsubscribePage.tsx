/**
 * Vitar — Unsubscribe Page
 * Lands here from the footer link in the weekly feature-spotlight email.
 * Auto-unsubscribes on mount — the token in the URL is the only input needed.
 */
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { authApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';

type Status = 'working' | 'success' | 'error';

export default function UnsubscribePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [status, setStatus] = useState<Status>('working');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setError('This unsubscribe link is missing its token.');
      return;
    }
    authApi.unsubscribe(token)
      .then(() => setStatus('success'))
      .catch((err) => {
        setStatus('error');
        setError(getApiError(err));
      });
  }, [token]);

  return (
    <div className="text-center">
      {status === 'working' && (
        <>
          <Loader2 className="w-10 h-10 text-teal-600 animate-spin mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-1">Unsubscribing…</h2>
          <p className="text-slate-500 text-sm">One moment.</p>
        </>
      )}
      {status === 'success' && (
        <>
          <CheckCircle2 className="w-10 h-10 text-teal-600 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-1">You're unsubscribed</h2>
          <p className="text-slate-500 text-sm mb-4">
            You won't get the weekly feature-spotlight email anymore. Booking, payment, and account
            emails will still reach you as normal.
          </p>
          <Link to="/login" className="text-teal-600 hover:underline text-sm">Back to Vitar</Link>
        </>
      )}
      {status === 'error' && (
        <>
          <XCircle className="w-10 h-10 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-1">Couldn't unsubscribe</h2>
          <p className="text-slate-500 text-sm mb-4">{error || 'This link may be invalid or expired.'}</p>
          <Link to="/login" className="text-teal-600 hover:underline text-sm">Back to Vitar</Link>
        </>
      )}
    </div>
  );
}

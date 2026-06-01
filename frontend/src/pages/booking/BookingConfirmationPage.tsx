/**
 * Vitar v5 - Booking Confirmation Page
 */
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { bookingApi } from '@/lib/api/services';

export default function BookingConfirmationPage() {
  const { token } = useParams<{ token: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['confirm', token],
    queryFn: () => bookingApi.confirm(token!),
    enabled: !!token,
  });

  if (isLoading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <Loader2 className="w-8 h-8 text-teal-600 animate-spin" />
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center space-y-4">
        {isError ? (
          <>
            <XCircle className="w-16 h-16 text-red-400 mx-auto" />
            <h2 className="text-2xl font-bold text-slate-900">Invalid Link</h2>
            <p className="text-slate-500">This confirmation link is invalid or has expired.</p>
          </>
        ) : (
          <>
            <CheckCircle className="w-16 h-16 text-teal-500 mx-auto" />
            <h2 className="text-2xl font-bold text-slate-900">Appointment Confirmed</h2>
            <p className="text-slate-500">
              Your appointment is confirmed for{' '}
              <strong>{data?.scheduled_at ? new Date(data.scheduled_at).toLocaleString() : '—'}</strong>.
            </p>
            <p className="text-slate-400 text-sm">You'll receive a reminder before your appointment.</p>
          </>
        )}
      </div>
    </div>
  );
}

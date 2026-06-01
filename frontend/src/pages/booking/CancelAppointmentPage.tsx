/**
 * Vitar v5 - Cancel Appointment Page
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { XCircle, CheckCircle, Loader2, AlertTriangle } from 'lucide-react';
import { bookingApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';

export default function CancelAppointmentPage() {
  const { token } = useParams<{ token: string }>();
  const [cancelled, setCancelled] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['cancel-page', token],
    queryFn: () => bookingApi.getCancelPage(token!),
    enabled: !!token,
  });

  const cancelMutation = useMutation({
    mutationFn: () => bookingApi.cancelByToken(token!),
    onSuccess: () => setCancelled(true),
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
            <p className="text-slate-500">This cancellation link is invalid or has expired.</p>
          </>
        ) : cancelled || data?.message?.includes('already') ? (
          <>
            <CheckCircle className="w-16 h-16 text-teal-500 mx-auto" />
            <h2 className="text-2xl font-bold text-slate-900">Appointment Cancelled</h2>
            <p className="text-slate-500">Your appointment has been cancelled successfully.</p>
          </>
        ) : (
          <>
            <AlertTriangle className="w-16 h-16 text-amber-400 mx-auto" />
            <h2 className="text-2xl font-bold text-slate-900">Cancel Appointment?</h2>
            <p className="text-slate-500">
              Appointment on{' '}
              <strong>{data?.scheduled_at ? new Date(data.scheduled_at).toLocaleString() : '—'}</strong>
            </p>
            <p className="text-slate-400 text-sm">This action cannot be undone. Please give at least 2 hours' notice where possible.</p>
            <button
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
              className="w-full bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white font-semibold py-3 rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              {cancelMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              Yes, Cancel My Appointment
            </button>
            {cancelMutation.isError && (
              <p className="text-red-500 text-sm">{getApiError(cancelMutation.error)}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

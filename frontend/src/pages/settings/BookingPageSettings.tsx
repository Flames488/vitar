// Booking Page Settings
import { useMutation } from '@tanstack/react-query';
import { clinicsApi } from '@/lib/api/services';
import { useAuthStore } from '@/stores/authStore';
import { toast } from 'sonner';
import { Copy, ExternalLink } from 'lucide-react';

export function BookingPageSettings() {
  const { clinic, refreshClinic } = useAuthStore();
  const bookingUrl = `${window.location.origin}/book/${clinic?.slug}`;

  const updateMutation = useMutation({
    mutationFn: (data: any) => clinicsApi.update(data),
    onSuccess: () => { refreshClinic(); toast.success('Saved'); },
  });

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Booking Page</h1>

      {/* URL */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
        <h2 className="font-semibold text-slate-900">Your Public Booking URL</h2>
        <div className="flex items-center gap-2 bg-slate-50 rounded-lg p-3 border border-slate-200">
          <p className="flex-1 text-sm text-slate-700 font-mono truncate">{bookingUrl}</p>
          <button onClick={() => { navigator.clipboard.writeText(bookingUrl); toast.success('Copied!'); }}
            className="text-teal-600 hover:text-teal-700">
            <Copy className="w-4 h-4" />
          </button>
          <a href={bookingUrl} target="_blank" rel="noreferrer" className="text-teal-600 hover:text-teal-700">
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>

        <div className="space-y-3 pt-2">
          {[
            { key: 'booking_page_enabled', label: 'Booking page enabled', desc: 'Patients can view your booking page' },
            { key: 'online_booking_enabled', label: 'Online booking enabled', desc: 'Patients can book appointments online' },
          ].map(({ key, label, desc }) => {
            const enabled = clinic?.[key as keyof typeof clinic] as boolean ?? true;
            return (
              <div key={key} className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-slate-900 text-sm">{label}</p>
                  <p className="text-slate-500 text-xs">{desc}</p>
                </div>
                <button onClick={() => updateMutation.mutate({ [key]: !enabled })}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${enabled ? 'bg-teal-600' : 'bg-slate-200'}`}>
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow ${enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
export default BookingPageSettings;

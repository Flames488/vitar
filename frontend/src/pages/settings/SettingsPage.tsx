// General Settings Page
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation } from '@tanstack/react-query';
import { clinicsApi } from '@/lib/api/services';
import { useAuthStore } from '@/stores/authStore';
import { toast } from 'sonner';
import { Loader2, Copy, Check, Link2 } from 'lucide-react';

// ── Clinic ID copy panel ──────────────────────────────────────────────────────

/**
 * Read-only panel showing the clinic UUID.
 *
 * The Wabizz integration requires this ID to be entered in the Wabizz dashboard
 * (Niche Modules → Hospital → Vitar Clinic ID) so that patients booked via
 * WhatsApp are linked to this clinic and appear in the Vitar dashboard.
 *
 * Bug fix: the clinic UUID was previously not surfaced anywhere in the UI,
 * making the Wabizz integration impossible to configure correctly.
 */
function ClinicIdPanel({ clinicId }: { clinicId: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(clinicId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-3">
      <div className="flex items-center gap-2">
        <Link2 className="w-4 h-4 text-teal-600" />
        <h2 className="text-sm font-semibold text-slate-900">Wabizz Integration — Clinic ID</h2>
      </div>
      <p className="text-xs text-slate-500 leading-relaxed">
        Enter this ID in your{' '}
        <span className="font-medium text-slate-700">Wabizz dashboard → Niche Modules → Hospital → Vitar Clinic ID</span>.
        Without it, patients booked via WhatsApp will not appear in your Vitar dashboard.
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-xs font-mono text-slate-700 select-all break-all">
          {clinicId}
        </code>
        <button
          onClick={handleCopy}
          title="Copy Clinic ID"
          className="shrink-0 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-teal-600" />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              Copy
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ── Settings form ─────────────────────────────────────────────────────────────

export function SettingsPage() {
  const { clinic, refreshClinic } = useAuthStore();
  const { register, handleSubmit, formState: { isSubmitting } } = useForm({
    defaultValues: {
      name: clinic?.name ?? '',
      phone: '',
      address: '',
      city: '',
      timezone: 'Africa/Lagos',
    },
  });

  const updateMutation = useMutation({
    mutationFn: clinicsApi.update,
    onSuccess: () => { refreshClinic(); toast.success('Settings saved'); },
    onError: () => toast.error('Failed to save'),
  });

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Clinic Settings</h1>

      {/* Clinic UUID panel — required for Wabizz integration */}
      {clinic?.id && <ClinicIdPanel clinicId={clinic.id} />}

      <form onSubmit={handleSubmit(d => updateMutation.mutate(d))} className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Clinic Name</label>
          <input {...register('name')} className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Phone</label>
          <input {...register('phone')} placeholder="+234..."
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Address</label>
          <input {...register('address')} placeholder="Street address"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">City</label>
          <input {...register('city')} placeholder="Lagos"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Timezone</label>
          <select {...register('timezone')} className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white">
            <option value="Africa/Lagos">Africa/Lagos (WAT)</option>
            <option value="Africa/Nairobi">Africa/Nairobi (EAT)</option>
            <option value="UTC">UTC</option>
            <option value="America/New_York">America/New_York (ET)</option>
            <option value="Europe/London">Europe/London (GMT)</option>
          </select>
        </div>
        <button type="submit" disabled={isSubmitting}
          className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2">
          {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
          Save Changes
        </button>
      </form>
    </div>
  );
}
export default SettingsPage;

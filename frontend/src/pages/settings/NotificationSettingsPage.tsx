// Notification Settings Page
import { useQuery, useMutation } from '@tanstack/react-query';
import { notificationsApi } from '@/lib/api/services';
import { toast } from 'sonner';
import { useState, useEffect } from 'react';

export function NotificationSettingsPage() {
  const { data, isLoading } = useQuery({ queryKey: ['notification-settings'], queryFn: notificationsApi.getSettings });
  const [settings, setSettings] = useState<any>({});

  useEffect(() => { if (data) setSettings(data); }, [data]);

  const updateMutation = useMutation({
    mutationFn: notificationsApi.updateSettings,
    onSuccess: () => toast.success('Notification settings saved'),
    onError: () => toast.error('Failed to save'),
  });

  if (isLoading) return <div className="p-6 text-slate-400">Loading...</div>;

  const toggle = (key: string) => setSettings((s: any) => ({ ...s, [key]: !s[key] }));

  const TOGGLES = [
    { key: 'sms_enabled', label: 'SMS Reminders', desc: 'Send SMS to patients before appointments' },
    { key: 'whatsapp_enabled', label: 'WhatsApp Reminders', desc: 'Requires WhatsApp Business API setup' },
    { key: 'email_enabled', label: 'Email Reminders', desc: 'Send email confirmations and reminders' },
    { key: 'ai_smart_reminders', label: 'AI Smart Reminders', desc: 'AI adjusts reminder frequency based on risk score' },
    { key: 'high_risk_extra_reminder', label: 'Extra Reminder for High-Risk', desc: 'Send additional reminders to critical-risk patients' },
  ];

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Notification Settings</h1>

      <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
        {TOGGLES.map(({ key, label, desc }) => (
          <div key={key} className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
            <div>
              <p className="font-medium text-slate-900">{label}</p>
              <p className="text-slate-500 text-sm">{desc}</p>
            </div>
            <button onClick={() => toggle(key)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${settings[key] ? 'bg-teal-600' : 'bg-slate-200'}`}>
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow ${settings[key] ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
          </div>
        ))}

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Primary reminder (hours before)</label>
          <select value={settings.reminder_hours_before ?? 24}
            onChange={e => setSettings((s: any) => ({ ...s, reminder_hours_before: parseInt(e.target.value) }))}
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-teal-500">
            {[1,2,4,6,12,24,48].map(h => <option key={h} value={h}>{h}h before</option>)}
          </select>
        </div>

        <button onClick={() => updateMutation.mutate(settings)} disabled={updateMutation.isPending}
          className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors">
          {updateMutation.isPending ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
export default NotificationSettingsPage;

/**
 * Vitar — Admin Dashboard: Clinic Management
 * Module 3 of the spec: table with QR preview, owner, status, and actions.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Ban, CheckCircle2, QrCode, ExternalLink, RefreshCw } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import {
  useAdminTheme, SearchInput, Select, Pagination, StatusBadge,
  EmptyState, LoadingState, Modal, TextArea, PrimaryButton, DangerButton, SecondaryButton,
} from '@/components/admin/AdminUI';

export default function AdminClinicsPage() {
  const { c } = useAdminTheme();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [qrPreview, setQrPreview] = useState<{ name: string; path: string; url: string } | null>(null);
  const [pendingDisable, setPendingDisable] = useState<{ id: string; name: string; nextValue: boolean } | null>(null);
  const [reason, setReason] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'clinics', { search, status, page }],
    queryFn: () => adminApi.clinics.list({ search: search || undefined, status: status || undefined, page, limit: 20 }),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, nextValue }: { id: string; nextValue: boolean }) =>
      adminApi.clinics.updateStatus(id, nextValue, reason || undefined),
    onSuccess: () => {
      toast.success('Clinic status updated');
      queryClient.invalidateQueries({ queryKey: ['admin', 'clinics'] });
      setPendingDisable(null); setReason('');
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const regenerateQrMutation = useMutation({
    mutationFn: (id: string) => adminApi.clinics.regenerateQr(id),
    onSuccess: () => {
      toast.success('QR code regenerated');
      queryClient.invalidateQueries({ queryKey: ['admin', 'clinics'] });
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const items = data?.items ?? [];

  return (
    <div className="p-6 space-y-4 max-w-7xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Clinics</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{data?.total ?? 0} registered clinics</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search by name or slug..." />
        </div>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="sm:w-40">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </Select>
      </div>

      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        {isLoading ? (
          <LoadingState message="Loading clinics..." />
        ) : items.length === 0 ? (
          <EmptyState message="No clinics found" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`border-b ${c.border}`}>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>QR</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Clinic</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Owner</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Plan</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Status</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Registered</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className={`divide-y ${c.divide}`}>
                {items.map((clinic: any) => (
                  <tr key={clinic.id} className={c.panelHover}>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => clinic.qr_code_path && setQrPreview({ name: clinic.name, path: clinic.qr_code_path, url: clinic.portal_url })}
                        className={`w-9 h-9 rounded-lg flex items-center justify-center ${clinic.qr_code_path ? 'bg-slate-100' : 'bg-slate-50'}`}
                      >
                        {clinic.qr_code_path ? (
                          <img src={clinic.qr_code_path} alt="QR" className="w-9 h-9 rounded-lg object-cover" />
                        ) : (
                          <QrCode className="w-4 h-4 text-slate-300" />
                        )}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <p className={`font-medium ${c.text}`}>{clinic.name}</p>
                      <p className={`text-xs ${c.textFaint}`}>/{clinic.slug}</p>
                    </td>
                    <td className={`px-4 py-3 ${c.textMuted}`}>
                      {clinic.owner ? <><div className={c.text}>{clinic.owner.full_name}</div><div className="text-xs">{clinic.owner.email}</div></> : '—'}
                    </td>
                    <td className="px-4 py-3">
                      {clinic.subscription_plan ? <span className={`capitalize ${c.text}`}>{clinic.subscription_plan}</span> : <span className={c.textFaint}>—</span>}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={clinic.is_active ? 'active' : 'disabled'} /></td>
                    <td className={`px-4 py-3 text-xs ${c.textMuted}`}>
                      {clinic.created_at ? new Date(clinic.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 justify-end">
                        <a href={clinic.portal_url} target="_blank" rel="noopener noreferrer" title="View booking page" className="text-slate-400 hover:text-teal-600">
                          <ExternalLink className="w-4 h-4" />
                        </a>
                        <button
                          onClick={() => regenerateQrMutation.mutate(clinic.id)}
                          disabled={regenerateQrMutation.isPending}
                          title="Regenerate QR code"
                          className="text-slate-400 hover:text-blue-600 disabled:opacity-40"
                        >
                          <RefreshCw className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setPendingDisable({ id: clinic.id, name: clinic.name, nextValue: !clinic.is_active })}
                          title={clinic.is_active ? 'Disable clinic' : 'Enable clinic'}
                          className={clinic.is_active ? 'text-slate-400 hover:text-red-600' : 'text-green-600 hover:text-green-800'}
                        >
                          {clinic.is_active ? <Ban className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data && <Pagination page={page} setPage={setPage} total={data.total} limit={20} />}

      {/* Disable/Enable confirm */}
      <Modal
        open={!!pendingDisable}
        onClose={() => { setPendingDisable(null); setReason(''); }}
        title={pendingDisable?.nextValue ? 'Enable clinic?' : 'Disable clinic?'}
        danger={pendingDisable?.nextValue === false}
        footer={
          <>
            <SecondaryButton onClick={() => { setPendingDisable(null); setReason(''); }}>Cancel</SecondaryButton>
            {pendingDisable?.nextValue === false ? (
              <DangerButton onClick={() => pendingDisable && statusMutation.mutate(pendingDisable)} disabled={statusMutation.isPending}>
                Disable
              </DangerButton>
            ) : (
              <PrimaryButton onClick={() => pendingDisable && statusMutation.mutate(pendingDisable)} disabled={statusMutation.isPending}>
                Enable
              </PrimaryButton>
            )}
          </>
        }
      >
        <p className={`text-sm ${c.textMuted}`}>
          {pendingDisable && <>This affects <span className={`font-medium ${c.text}`}>{pendingDisable.name}</span>{pendingDisable.nextValue === false ? ' — patients will no longer be able to book appointments.' : '.'}</>}
        </p>
        <TextArea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional, recorded in the audit log)" rows={2} />
      </Modal>

      {/* QR preview */}
      <Modal open={!!qrPreview} onClose={() => setQrPreview(null)} title={qrPreview ? `${qrPreview.name} — QR Code` : 'QR Code'}>
        {qrPreview && (
          <div className="flex flex-col items-center gap-3">
            <img src={qrPreview.path} alt="QR code" className="w-48 h-48 rounded-lg border border-slate-200" />
            <a href={qrPreview.url} target="_blank" rel="noopener noreferrer" className="text-teal-600 text-sm font-medium hover:text-teal-700">
              {qrPreview.url}
            </a>
          </div>
        )}
      </Modal>
    </div>
  );
}

/**
 * Vitar — AI Core: Sales Agent
 * Pending outreach drafts (approve/edit/reject inline) + leads grouped by
 * pipeline stage (new -> contacted -> replied -> trial_started -> paid -> lost).
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, X, Pencil, Loader2 } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import {
  useAdminTheme, EmptyState, LoadingState, Modal, TextArea, PrimaryButton, SecondaryButton, DangerButton,
} from '@/components/admin/AdminUI';

const STAGES = ['new', 'contacted', 'replied', 'trial_started', 'paid', 'lost'] as const;
const STAGE_LABEL: Record<string, string> = {
  new: 'New', contacted: 'Contacted', replied: 'Replied',
  trial_started: 'Trial Started', paid: 'Paid', lost: 'Lost',
};

export default function SalesAgentPage() {
  const { c } = useAdminTheme();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<{ id: string; body: string } | null>(null);

  const { data: draftsData, isLoading: draftsLoading } = useQuery({
    queryKey: ['admin', 'agents', 'sales', 'drafts'],
    queryFn: () => adminApi.agents.listSalesDrafts('pending_approval'),
  });

  const { data: leadsData, isLoading: leadsLoading } = useQuery({
    queryKey: ['admin', 'leads', 'all'],
    queryFn: () => adminApi.leads.list({ limit: 500 }),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'agents', 'sales', 'drafts'] });
    qc.invalidateQueries({ queryKey: ['admin', 'leads'] });
    qc.invalidateQueries({ queryKey: ['admin', 'agents', 'overview'] });
  };

  const approveMutation = useMutation({
    mutationFn: (id: string) => adminApi.agents.approveSalesDraft(id),
    onSuccess: () => { toast.success('Approved — will send on the next scheduled pass'); invalidate(); },
    onError: (err) => toast.error(getApiError(err)),
  });
  const rejectMutation = useMutation({
    mutationFn: (id: string) => adminApi.agents.rejectSalesDraft(id),
    onSuccess: () => { toast.success('Rejected'); invalidate(); },
    onError: (err) => toast.error(getApiError(err)),
  });
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => adminApi.agents.editSalesDraft(id, body),
    onSuccess: () => { toast.success('Draft updated'); setEditing(null); invalidate(); },
    onError: (err) => toast.error(getApiError(err)),
  });

  const drafts = draftsData?.drafts ?? [];
  const leads = leadsData?.leads ?? [];
  const byStage: Record<string, any[]> = {};
  for (const stage of STAGES) byStage[stage] = leads.filter((l: any) => (l.status ?? '').toLowerCase() === stage);

  const totalLeads = leads.length;
  const paidCount = byStage.paid.length;
  const conversionRate = totalLeads > 0 ? Math.round((paidCount / totalLeads) * 100) : 0;

  return (
    <div className="p-6 space-y-5 max-w-6xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Sales Agent</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{drafts.length} drafts pending approval · {conversionRate}% overall conversion</p>
      </div>

      {/* Pending drafts */}
      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        <div className={`px-5 py-4 border-b ${c.border}`}>
          <h2 className={`text-sm font-bold ${c.text}`}>Pending outreach drafts</h2>
        </div>
        {draftsLoading ? <LoadingState /> : drafts.length === 0 ? <EmptyState message="No drafts pending approval" /> : (
          <div className={`divide-y ${c.divide}`}>
            {drafts.map((d: any) => (
              <div key={d.id} className="px-5 py-4">
                <p className={`text-xs font-semibold mb-1 ${c.textMuted}`}>{d.lead_clinic_name ?? 'Unknown clinic'}</p>
                <p className={`text-sm mb-3 whitespace-pre-wrap ${c.text}`}>{d.body}</p>
                <div className="flex gap-2">
                  <PrimaryButton onClick={() => approveMutation.mutate(d.id)} disabled={approveMutation.isPending} className="flex items-center gap-1.5 text-xs px-3 py-1.5">
                    <Check className="w-3.5 h-3.5" /> Approve
                  </PrimaryButton>
                  <SecondaryButton onClick={() => setEditing({ id: d.id, body: d.body })} className="flex items-center gap-1.5 text-xs px-3 py-1.5">
                    <Pencil className="w-3.5 h-3.5" /> Edit
                  </SecondaryButton>
                  <DangerButton onClick={() => rejectMutation.mutate(d.id)} disabled={rejectMutation.isPending} className="flex items-center gap-1.5 text-xs px-3 py-1.5">
                    <X className="w-3.5 h-3.5" /> Reject
                  </DangerButton>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pipeline funnel */}
      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        <div className={`px-5 py-4 border-b ${c.border}`}>
          <h2 className={`text-sm font-bold ${c.text}`}>Pipeline</h2>
        </div>
        {leadsLoading ? <LoadingState /> : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-px bg-current opacity-90" style={{ backgroundColor: 'transparent' }}>
            {STAGES.map((stage) => (
              <div key={stage} className={`p-4 ${c.panel} border-t sm:border-t-0 ${c.border}`}>
                <p className={`text-xs font-medium ${c.textFaint}`}>{STAGE_LABEL[stage]}</p>
                <p className={`text-2xl font-bold mt-1 ${c.text}`}>{byStage[stage].length}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal open={!!editing} onClose={() => setEditing(null)} title="Edit draft"
        footer={
          <>
            <SecondaryButton onClick={() => setEditing(null)}>Cancel</SecondaryButton>
            <PrimaryButton
              onClick={() => editing && editMutation.mutate(editing)}
              disabled={editMutation.isPending || !editing?.body.trim()}
            >
              {editMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Save'}
            </PrimaryButton>
          </>
        }
      >
        <TextArea
          value={editing?.body ?? ''}
          onChange={(e) => setEditing((prev) => prev ? { ...prev, body: e.target.value } : prev)}
          rows={6}
        />
      </Modal>
    </div>
  );
}

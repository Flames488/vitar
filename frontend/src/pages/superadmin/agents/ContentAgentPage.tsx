/**
 * Vitar — AI Core: Content Agent
 * Pending-approval social post drafts (approve/reject) + approved/published
 * history. Nothing here publishes anywhere — approved content just sits
 * ready for manual posting, as specified.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, X } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { useAdminTheme, EmptyState, LoadingState, PrimaryButton, DangerButton } from '@/components/admin/AdminUI';

export default function ContentAgentPage() {
  const { c } = useAdminTheme();
  const qc = useQueryClient();

  const { data: pendingData, isLoading: pendingLoading } = useQuery({
    queryKey: ['admin', 'agents', 'content', 'drafts', 'pending'],
    queryFn: () => adminApi.agents.listContentDrafts('pending_approval'),
  });

  const { data: approvedData } = useQuery({
    queryKey: ['admin', 'agents', 'content', 'drafts', 'approved'],
    queryFn: () => adminApi.agents.listContentDrafts('approved'),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'agents', 'content'] });

  const approveMutation = useMutation({
    mutationFn: (id: string) => adminApi.agents.approveContentDraft(id),
    onSuccess: () => { toast.success('Approved'); invalidate(); },
    onError: (err) => toast.error(getApiError(err)),
  });
  const rejectMutation = useMutation({
    mutationFn: (id: string) => adminApi.agents.rejectContentDraft(id),
    onSuccess: () => { toast.success('Rejected'); invalidate(); },
    onError: (err) => toast.error(getApiError(err)),
  });

  const pending = pendingData?.drafts ?? [];
  const approved = approvedData?.drafts ?? [];

  return (
    <div className="p-6 space-y-5 max-w-4xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Content Agent</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{pending.length} drafts pending approval</p>
      </div>

      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        <div className={`px-5 py-4 border-b ${c.border}`}>
          <h2 className={`text-sm font-bold ${c.text}`}>Pending approval</h2>
        </div>
        {pendingLoading ? <LoadingState /> : pending.length === 0 ? <EmptyState message="No drafts pending approval" /> : (
          <div className={`divide-y ${c.divide}`}>
            {pending.map((d: any) => (
              <div key={d.id} className="px-5 py-4">
                <p className={`text-sm mb-3 whitespace-pre-wrap ${c.text}`}>{d.body}</p>
                <div className="flex gap-2">
                  <PrimaryButton onClick={() => approveMutation.mutate(d.id)} disabled={approveMutation.isPending} className="flex items-center gap-1.5 text-xs px-3 py-1.5">
                    <Check className="w-3.5 h-3.5" /> Approve
                  </PrimaryButton>
                  <DangerButton onClick={() => rejectMutation.mutate(d.id)} disabled={rejectMutation.isPending} className="flex items-center gap-1.5 text-xs px-3 py-1.5">
                    <X className="w-3.5 h-3.5" /> Reject
                  </DangerButton>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        <div className={`px-5 py-4 border-b ${c.border}`}>
          <h2 className={`text-sm font-bold ${c.text}`}>Approved (ready to post)</h2>
        </div>
        {approved.length === 0 ? <EmptyState message="Nothing approved yet" /> : (
          <div className={`divide-y ${c.divide}`}>
            {approved.map((d: any) => (
              <div key={d.id} className="px-5 py-4">
                <p className={`text-sm whitespace-pre-wrap ${c.text}`}>{d.body}</p>
                <p className={`text-xs mt-2 ${c.textFaint}`}>{d.created_at ? new Date(d.created_at).toLocaleDateString() : ''}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

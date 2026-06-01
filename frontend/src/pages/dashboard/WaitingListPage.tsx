// WaitingList Page
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { waitingListApi } from '@/lib/api/services';
import { format } from 'date-fns';
import { ListOrdered, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

export default function WaitingListPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ['waiting-list'], queryFn: waitingListApi.list });

  const removeMutation = useMutation({
    mutationFn: waitingListApi.remove,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['waiting-list'] }); toast.success('Removed from waiting list'); },
  });

  const entries = data?.items ?? [];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <ListOrdered className="w-6 h-6 text-teal-600" />
        <h1 className="text-2xl font-bold text-slate-900">Waiting List</h1>
        <span className="ml-2 bg-teal-100 text-teal-700 text-sm font-medium px-2.5 py-0.5 rounded-full">
          {entries.length} waiting
        </span>
      </div>

      <div className="bg-white rounded-xl border border-slate-200">
        {isLoading ? (
          <div className="py-12 text-center text-slate-400 text-sm">Loading...</div>
        ) : entries.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-sm">No one on the waiting list</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {entries.map((e: any) => (
              <div key={e.id} className="flex items-center gap-4 px-6 py-4">
                <div className="w-10 h-10 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center font-bold text-sm flex-shrink-0">
                  {e.patient_name?.charAt(0) ?? '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-900">{e.patient_name}</p>
                  <p className="text-slate-500 text-sm">{e.patient_phone}</p>
                  {e.preferred_date && (
                    <p className="text-slate-400 text-xs">
                      Preferred: {format(new Date(e.preferred_date), 'MMM d, yyyy')}
                    </p>
                  )}
                </div>
                <p className="text-slate-400 text-xs">{format(new Date(e.created_at), 'MMM d')}</p>
                <button onClick={() => removeMutation.mutate(e.id)}
                  className="text-red-400 hover:text-red-600 transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Vitar — AI Core: Agents Overview
 * Four agent cards + the "20 paying clients by Dec 2026" progress bar that
 * ties the whole system together. Pulls everything from one endpoint
 * (GET /admin/agents/overview) rather than four separate roundtrips.
 */
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Target, MessageCircle, PenSquare, HeartPulse, ArrowRight, Trophy } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { useAdminTheme, LoadingState } from '@/components/admin/AdminUI';

const STATUS_DOT: Record<string, string> = {
  green: 'bg-green-500',
  yellow: 'bg-amber-500',
  red: 'bg-red-500',
};
const STATUS_LABEL: Record<string, string> = {
  green: 'Healthy',
  yellow: 'Overdue / never run',
  red: 'Last run failed',
};

function timeAgo(iso: string | null): string {
  if (!iso) return 'never';
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function AgentCard({
  to, icon: Icon, name, agent, keyStat,
}: {
  to: string; icon: React.ComponentType<{ className?: string }>; name: string;
  agent: any; keyStat: React.ReactNode;
}) {
  const { c } = useAdminTheme();
  const dot = agent?.status ?? 'yellow';
  return (
    <Link to={to} className={`group rounded-xl border p-5 hover:shadow-md transition-all ${c.panel}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center bg-teal-500/10 text-teal-500`}>
            <Icon className="w-4 h-4" />
          </div>
          <div>
            <p className={`text-sm font-bold ${c.text}`}>{name}</p>
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[dot]}`} />
              <span className={`text-xs ${c.textFaint}`}>{STATUS_LABEL[dot]}</span>
            </div>
          </div>
        </div>
        <ArrowRight className={`w-3.5 h-3.5 ${c.textFaint} group-hover:text-teal-500 group-hover:translate-x-0.5 transition-all mt-1`} />
      </div>
      <div className="mt-4">{keyStat}</div>
      <p className={`text-xs mt-3 ${c.textFaint}`}>
        Last run: {timeAgo(agent?.last_run?.finished_at)}
        {agent?.last_run && ` · ${agent.last_run.items_processed} processed, ${agent.last_run.items_created} created`}
      </p>
    </Link>
  );
}

export default function AgentsOverviewPage() {
  const { c } = useAdminTheme();

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'agents', 'overview'],
    queryFn: adminApi.agents.overview,
    refetchInterval: 60_000,
  });

  if (isLoading) return <div className="p-6"><LoadingState /></div>;

  const goal = data?.goal ?? { target: 20, current: 0, deadline: '2026-12-31' };
  const pct = Math.min(100, Math.round((goal.current / goal.target) * 100));
  const agents = data?.agents ?? {};

  return (
    <div className="p-6 space-y-5 max-w-6xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>AI Agents — Overview</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>Lead Hunter, Sales Agent, Content Agent, Customer Success</p>
      </div>

      {/* Goal progress bar */}
      <div className={`rounded-xl border p-5 ${c.panel}`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-amber-500" />
            <span className={`text-sm font-bold ${c.text}`}>{goal.current} of {goal.target} paying clients</span>
          </div>
          <span className={`text-xs ${c.textFaint}`}>Goal: {goal.deadline}</span>
        </div>
        <div className={`h-2.5 rounded-full overflow-hidden ${c.border} bg-current opacity-10`}>
          <div className="h-full bg-teal-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
        </div>
        <p className={`text-xs mt-1.5 ${c.textFaint}`}>{pct}% of the way there</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <AgentCard
          to="/admin/agents/lead-hunter"
          icon={Target}
          name="Lead Hunter"
          agent={agents.lead_hunter}
          keyStat={<p className={`text-2xl font-bold ${c.text}`}>{agents.lead_hunter?.new_leads ?? 0} <span className={`text-xs font-normal ${c.textFaint}`}>new leads</span></p>}
        />
        <AgentCard
          to="/admin/agents/sales"
          icon={MessageCircle}
          name="Sales Agent"
          agent={agents.sales_agent}
          keyStat={
            <div className="flex items-baseline gap-4">
              <p className={`text-2xl font-bold ${c.text}`}>{agents.sales_agent?.pending_approval ?? 0} <span className={`text-xs font-normal ${c.textFaint}`}>pending</span></p>
              <p className={`text-sm font-semibold ${c.textMuted}`}>{Math.round((agents.sales_agent?.conversion_rate ?? 0) * 100)}% conv. this month</p>
            </div>
          }
        />
        <AgentCard
          to="/admin/agents/content"
          icon={PenSquare}
          name="Content Agent"
          agent={agents.content_agent}
          keyStat={<p className={`text-2xl font-bold ${c.text}`}>{agents.content_agent?.pending_approval ?? 0} <span className={`text-xs font-normal ${c.textFaint}`}>pending drafts</span></p>}
        />
        <AgentCard
          to="/admin/agents/customer-success"
          icon={HeartPulse}
          name="Customer Success"
          agent={agents.customer_success}
          keyStat={<p className={`text-2xl font-bold ${c.text}`}>{agents.customer_success?.open_signals ?? 0} <span className={`text-xs font-normal ${c.textFaint}`}>open signals</span></p>}
        />
      </div>
    </div>
  );
}

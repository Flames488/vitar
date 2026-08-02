/**
 * Vitar — Refer & Earn Card
 * Shows the clinic's referral link plus simple funnel stats. Sits on the
 * Billing page next to Payment History.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Gift, Copy, Check } from 'lucide-react';
import { referralsApi } from '@/lib/api/services';

export default function ReferralCard() {
  const [copied, setCopied] = useState(false);

  const { data: linkData, isLoading: linkLoading } = useQuery({
    queryKey: ['referrals', 'me'],
    queryFn: referralsApi.getMyLink,
  });
  const { data: stats } = useQuery({
    queryKey: ['referrals', 'stats'],
    queryFn: referralsApi.getStats,
  });

  const copyLink = () => {
    if (!linkData?.referral_link) return;
    navigator.clipboard.writeText(linkData.referral_link).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (linkLoading) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center gap-2 mb-1">
        <Gift className="w-4 h-4 text-teal-600" />
        <h2 className="text-sm font-semibold text-slate-900">Refer & Earn</h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Share your link — when a clinic you refer makes their first payment, you get 10% off your next invoice.
      </p>

      <div className="flex items-center gap-2 mb-4">
        <input
          readOnly
          value={linkData?.referral_link ?? ''}
          className="flex-1 min-w-0 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-600 bg-slate-50 truncate"
          onFocus={(e) => e.target.select()}
        />
        <button
          onClick={copyLink}
          className="flex items-center gap-1.5 rounded-lg bg-teal-600 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-700 transition-colors flex-shrink-0"
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-lg font-bold text-slate-900">{stats?.sent ?? 0}</p>
          <p className="text-[11px] text-slate-500">Referrals sent</p>
        </div>
        <div>
          <p className="text-lg font-bold text-slate-900">{stats?.converted ?? 0}</p>
          <p className="text-[11px] text-slate-500">Converted</p>
        </div>
        <div>
          <p className="text-lg font-bold text-teal-600">{stats?.discounts_earned ?? 0}</p>
          <p className="text-[11px] text-slate-500">Discounts applied</p>
        </div>
      </div>
    </div>
  );
}

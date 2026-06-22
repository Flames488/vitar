/**
 * Vitar v5 - Auth Layout
 */

import { Outlet, Link } from 'react-router-dom';
import VitarLogo from '@/components/shared/VitarLogo';

export default function AuthLayout() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-teal-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex flex-col items-center gap-3">
            <VitarLogo size={80} />
          </Link>
          <p className="text-slate-400 text-sm mt-3">Healthcare Appointment Platform</p>
        </div>
        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <Outlet />
        </div>
      </div>
    </div>
  );
}

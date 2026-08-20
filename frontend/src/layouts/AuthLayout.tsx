/**
 * Vitar v5 - Auth Layout
 */

import { Outlet, Link } from 'react-router-dom';
import { Home } from 'lucide-react';
import VitarLogo from '@/components/shared/VitarLogo';

export default function AuthLayout() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-teal-900 flex items-center justify-center p-4">
      <Link
        to="/"
        className="fixed top-4 left-4 inline-flex items-center gap-1.5 text-slate-300 hover:text-white text-sm font-medium bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg px-3 py-2 transition-colors"
      >
        <Home className="w-4 h-4" />
        Home
      </Link>
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

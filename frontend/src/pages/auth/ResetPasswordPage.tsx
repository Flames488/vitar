/**
 * Vitar v5 - Reset Password Page
 */

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import { authApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';

const schema = z.object({
  password: z.string().min(8, 'At least 8 characters'),
  confirm:  z.string(),
}).refine(d => d.password === d.confirm, { message: "Passwords don't match", path: ['confirm'] });

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [showPw, setShowPw] = useState(false);
  const token = searchParams.get('token') ?? '';

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(schema),
  });

  const onSubmit = async ({ password }: { password: string; confirm: string }) => {
    if (!token) { toast.error('Invalid reset link'); return; }
    try {
      await authApi.resetPassword(token, password);
      toast.success('Password updated — please log in');
      navigate('/login');
    } catch (err) {
      toast.error(getApiError(err));
    }
  };

  return (
    <>
      <h2 className="text-2xl font-bold text-slate-900 mb-1">Set new password</h2>
      <p className="text-slate-500 text-sm mb-6">Choose a strong password for your account</p>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {['password', 'confirm'].map((field) => (
          <div key={field}>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              {field === 'password' ? 'New password' : 'Confirm password'}
            </label>
            <div className="relative">
              <input
                {...register(field as 'password' | 'confirm')}
                type={showPw ? 'text' : 'password'}
                placeholder="••••••••"
                className="w-full border border-slate-300 rounded-lg px-3 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
              {field === 'password' && (
                <button type="button" onClick={() => setShowPw(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              )}
            </div>
            {errors[field as 'password' | 'confirm'] && (
              <p className="text-red-500 text-xs mt-1">{errors[field as 'password' | 'confirm']?.message}</p>
            )}
          </div>
        ))}

        <button
          type="submit"
          disabled={isSubmitting || !token}
          className="w-full bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
        >
          {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
          Update password
        </button>
      </form>

      <p className="text-center text-sm text-slate-500 mt-6">
        <Link to="/login" className="text-teal-600 hover:underline">Back to login</Link>
      </p>
    </>
  );
}

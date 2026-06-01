/**
 * Vitar v5 - Forgot Password Page
 */

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router-dom';
import { Loader2, CheckCircle } from 'lucide-react';
import { authApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';
import { useState } from 'react';

const schema = z.object({ email: z.string().email() });

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(schema),
  });

  const onSubmit = async ({ email }: { email: string }) => {
    try {
      await authApi.forgotPassword(email);
      setSent(true);
    } catch (err) {
      toast.error(getApiError(err));
    }
  };

  if (sent) {
    return (
      <div className="text-center py-4">
        <CheckCircle className="w-12 h-12 text-teal-500 mx-auto mb-3" />
        <h2 className="text-xl font-bold text-slate-900">Check your email</h2>
        <p className="text-slate-500 text-sm mt-2">
          If that email is registered, you'll receive a reset link shortly.
        </p>
        <Link to="/login" className="mt-4 inline-block text-teal-600 font-medium text-sm hover:underline">
          Back to login
        </Link>
      </div>
    );
  }

  return (
    <>
      <h2 className="text-2xl font-bold text-slate-900 mb-1">Reset password</h2>
      <p className="text-slate-500 text-sm mb-6">We'll send a reset link to your email</p>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <input
            {...register('email')}
            type="email"
            placeholder="clinic@example.com"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
          {errors.email && <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>}
        </div>
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
        >
          {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
          Send reset link
        </button>
      </form>

      <p className="text-center text-sm text-slate-500 mt-6">
        <Link to="/login" className="text-teal-600 hover:underline">Back to login</Link>
      </p>
    </>
  );
}

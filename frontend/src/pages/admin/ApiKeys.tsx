/**
 * Vitar — API Key Management Page (Admin)
 *
 * Allows clinic admins to:
 *   - View all API keys (label, created, last used — never the raw key)
 *   - Generate a new key (shown ONCE, then only the hash is stored)
 *   - Revoke a key (sets is_active = false)
 *
 * Place this page at the /settings/api-keys route and add a link in the
 * existing Settings navigation sidebar.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Key,
  Plus,
  Trash2,
  Copy,
  CheckCircle,
  AlertTriangle,
  Eye,
  EyeOff,
  ShieldCheck,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api/client';

// ── API helpers ───────────────────────────────────────────────────────────────

interface ApiKeyRecord {
  id: string;
  label: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

interface GeneratedKey {
  id: string;
  label: string;
  raw_key: string;   // only returned at creation time
  created_at: string;
}

async function fetchApiKeys(): Promise<ApiKeyRecord[]> {
  const { data } = await api.get('/api/v1/admin/api-keys');
  return data;
}

async function generateApiKey(label: string): Promise<GeneratedKey> {
  const { data } = await api.post('/api/v1/admin/api-keys', { label });
  return data;
}

async function revokeApiKey(id: string): Promise<void> {
  await api.delete(`/api/v1/admin/api-keys/${id}`);
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ApiKeysPage() {
  const qc = useQueryClient();
  const [newLabel, setNewLabel] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [generatedKey, setGeneratedKey] = useState<GeneratedKey | null>(null);
  const [keyCopied, setKeyCopied] = useState(false);
  const [showRawKey, setShowRawKey] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const { data: keys = [], isLoading } = useQuery({
    queryKey: ['admin', 'api-keys'],
    queryFn: fetchApiKeys,
  });

  const generateMutation = useMutation({
    mutationFn: generateApiKey,
    onSuccess: (result) => {
      setGeneratedKey(result);
      setNewLabel('');
      setShowForm(false);
      setShowRawKey(false);
      qc.invalidateQueries({ queryKey: ['admin', 'api-keys'] });
    },
    onError: () => {
      toast.error('Failed to generate API key. Please try again.');
    },
  });

  const revokeMutation = useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => {
      toast.success('API key revoked.');
      qc.invalidateQueries({ queryKey: ['admin', 'api-keys'] });
    },
    onError: () => {
      toast.error('Failed to revoke key.');
    },
    onSettled: () => setRevokingId(null),
  });

  function handleGenerate() {
    if (!newLabel.trim()) {
      toast.error('Please enter a label for this key.');
      return;
    }
    generateMutation.mutate(newLabel.trim());
  }

  async function copyKey(raw: string) {
    await navigator.clipboard.writeText(raw);
    setKeyCopied(true);
    setTimeout(() => setKeyCopied(false), 2500);
  }

  function handleRevoke(id: string, label: string) {
    if (!confirm(`Revoke API key "${label}"? This cannot be undone and will break any integration using it.`)) return;
    setRevokingId(id);
    revokeMutation.mutate(id);
  }

  function formatDate(iso: string | null) {
    if (!iso) return 'Never';
    return new Date(iso).toLocaleString('en-NG', {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  }

  return (
    <div className="max-w-2xl mx-auto py-8 px-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-2">
        <div className="rounded-xl bg-indigo-100 p-2 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">
          <Key className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">API Keys</h1>
          <p className="text-sm text-gray-500">
            Manage machine-to-machine authentication for integrations like Wabizz.
          </p>
        </div>
      </div>

      {/* Security notice */}
      <div className="flex gap-2 rounded-xl border border-indigo-200 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-900/20 p-4 text-sm text-indigo-800 dark:text-indigo-300 mb-6 mt-4">
        <ShieldCheck className="h-4 w-4 mt-0.5 shrink-0" />
        <span>
          API keys are stored as secure hashes. The raw key is shown <strong>only once</strong> at
          creation time. Store it immediately in a secrets manager.
        </span>
      </div>

      {/* One-time key display */}
      {generatedKey && (
        <div className="mb-6 rounded-2xl border-2 border-green-400 bg-green-50 dark:bg-green-900/20 p-5">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle className="h-5 w-5 text-green-600" />
            <span className="font-semibold text-green-800 dark:text-green-300">
              Key generated — copy it now!
            </span>
          </div>

          <p className="text-sm text-green-700 dark:text-green-400 mb-3">
            This is the only time the raw key will be shown. Copy it and store it in Supabase Vault
            (Wabizz) or another secrets manager.
          </p>

          <div className="flex gap-2 items-center">
            <div className="flex-1 font-mono text-sm rounded-lg border border-green-300 bg-white dark:bg-green-900/40 px-3 py-2 overflow-x-auto">
              {showRawKey ? generatedKey.raw_key : '•'.repeat(48)}
            </div>
            <button
              onClick={() => setShowRawKey((p) => !p)}
              className="p-2 rounded-lg border border-green-300 hover:bg-green-100 dark:hover:bg-green-900/40 text-green-700 dark:text-green-400 transition"
              title={showRawKey ? 'Hide key' : 'Show key'}
            >
              {showRawKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
            <button
              onClick={() => copyKey(generatedKey.raw_key)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 text-white px-3 py-2 text-sm font-medium hover:bg-green-700 transition"
            >
              {keyCopied ? <CheckCircle className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {keyCopied ? 'Copied!' : 'Copy'}
            </button>
          </div>

          <button
            onClick={() => setGeneratedKey(null)}
            className="mt-4 text-xs text-green-600 hover:underline"
          >
            I've saved it — dismiss this
          </button>
        </div>
      )}

      {/* Generate form */}
      {showForm ? (
        <div className="mb-6 rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
          <h2 className="font-semibold text-gray-900 dark:text-white mb-3">Generate New API Key</h2>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Label
          </label>
          <p className="text-xs text-gray-500 mb-2">
            A descriptive name so you know which integration uses this key.
          </p>
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
            placeholder="Wabizz Integration"
            className="w-full rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-3"
          />
          <div className="flex gap-2">
            <button
              onClick={handleGenerate}
              disabled={generateMutation.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 text-white px-4 py-2 text-sm font-semibold hover:bg-indigo-700 transition disabled:opacity-50"
            >
              {generateMutation.isPending ? (
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                <Key className="h-3.5 w-3.5" />
              )}
              Generate
            </button>
            <button
              onClick={() => { setShowForm(false); setNewLabel(''); }}
              className="rounded-lg border border-gray-200 dark:border-gray-600 px-4 py-2 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex justify-end mb-4">
          <button
            onClick={() => setShowForm(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 text-white px-4 py-2 text-sm font-semibold shadow hover:bg-indigo-700 transition"
          >
            <Plus className="h-4 w-4" />
            Generate New Key
          </button>
        </div>
      )}

      {/* Keys list */}
      {isLoading ? (
        <div className="flex justify-center py-12 text-gray-400">Loading...</div>
      ) : keys.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-center text-gray-400">
          <Key className="h-10 w-10 mb-3 opacity-30" />
          <p className="font-medium">No API keys yet</p>
          <p className="text-sm mt-1">Generate one to enable Wabizz or other integrations.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {keys.map((key) => (
            <div
              key={key.id}
              className={`rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 flex items-start gap-3 ${
                !key.is_active ? 'opacity-50' : ''
              }`}
            >
              <div className={`mt-0.5 rounded-lg p-1.5 ${key.is_active ? 'bg-indigo-100 text-indigo-600' : 'bg-gray-100 text-gray-400'}`}>
                <Key className="h-4 w-4" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-sm text-gray-900 dark:text-white truncate">
                    {key.label}
                  </p>
                  {!key.is_active && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-600 dark:bg-red-900/30 dark:text-red-400 font-medium">
                      <AlertTriangle className="h-2.5 w-2.5" />
                      Revoked
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-0.5">
                  Created {formatDate(key.created_at)} &bull; Last used: {formatDate(key.last_used_at)}
                </p>
              </div>

              {key.is_active && (
                <button
                  onClick={() => handleRevoke(key.id, key.label)}
                  disabled={revokingId === key.id}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition"
                  title="Revoke key"
                >
                  {revokingId === key.id ? (
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent block" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

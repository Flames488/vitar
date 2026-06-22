/**
 * Vitar v5 - Geo Store
 * Stores detected region, currency, payment provider for UI
 */

import { create } from 'zustand';
import { geoApi } from '@/lib/api/services';

interface CurrencyFormat {
  symbol: string;
  code: string;
  locale: string;
  decimals: number;
}

interface GeoState {
  country: string;
  currency: string;
  currency_format: CurrencyFormat;
  payment_provider: string;
  pricing_tier: string;
  plans: unknown[];
  detected: boolean;

  detect: () => Promise<void>;
  formatMoney: (amount: number) => string;
}

const DEFAULT_FORMAT: CurrencyFormat = {
  symbol: '₦', code: 'NGN', locale: 'en-NG', decimals: 0,
};

export const useGeoStore = create<GeoState>((set, get) => ({
  country: 'NG',
  currency: 'NGN',
  currency_format: DEFAULT_FORMAT,
  payment_provider: 'paystack',
  pricing_tier: 'NGN',
  plans: [],
  detected: false,

  detect: async () => {
    try {
      const data = await geoApi.detect();
      set({
        country: data.country,
        currency: data.currency,
        currency_format: data.currency_format ?? DEFAULT_FORMAT,
        payment_provider: data.payment_provider,
        pricing_tier: data.pricing_tier,
        plans: data.plans ?? [],
        detected: true,
      });
    } catch {
      set({ detected: true }); // Fail gracefully
    }
  },

  formatMoney: (amount: number) => {
    const fmt = get().currency_format;
    const symbol = fmt.symbol ?? '$';
    const decimals = fmt.decimals ?? 2;
    if (decimals === 0) return `${symbol}${Math.round(amount).toLocaleString()}`;
    return `${symbol}${amount.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}`;
  },
}));

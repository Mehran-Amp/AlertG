import React, { useState, useEffect, useRef } from 'react';
import {
  AlarmClock,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Building2,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Code,
  Coins,
  Copy,
  Database,
  Download,
  ExternalLink,
  FileJson,
  Flame,
  Globe,
  Languages,
  Landmark,
  Layers,
  Moon,
  Palette,
  Pause,
  Percent,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  Shield,
  Smartphone,
  Sparkles,
  Sun,
  Timer,
  Trash2,
  TrendingUp,
  Upload,
  Volume2,
  VolumeX,
  X,
  Zap,
  LayoutGrid,
  Mic,
  User,
  BatteryCharging,
  Send
} from 'lucide-react';
import { AlarmCard } from './components/AlarmCard';
import { AppLogo } from './components/AppLogo';
import { FA } from './i18n/fa';
import { getLoginTelegramI18n } from './i18n/loginTelegram';

export interface AlertRule {
  uuid: string;
  marketType: 'crypto' | 'stocks_macro';
  exchangeId: string;
  exchangeName: string;
  baseCurrency: string;
  counterCurrency: string;
  marketSymbol: string;
  assetCategory: 'crypto' | 'stock' | 'forex' | 'bond' | 'commodity' | 'index' | 'iran_market';
  checkIntervalSeconds: number;
  conditionType: 'PERCENT_CHANGE' | 'PRICE_THRESHOLD' | 'VOLUME_SURGE';
  direction: 'BOTH' | 'ABOVE' | 'BELOW';
  bothWayBehavior?: 'OCO' | 'DUAL_ACTIVE';
  targetValue: number;
  upperTargetPrice?: number;
  upperNote?: string;
  lowerTargetPrice?: number;
  lowerNote?: string;
  volumePercent?: number;
  baseVolume?: number;
  basePrice: number;
  lastCheckedPrice?: number;
  isActive: boolean;
  isTriggered: boolean;
  customNote?: string;
  soundEnabled?: boolean;
  vibrationEnabled?: boolean;
  ttsEnabled?: boolean;
  cooldownUntil?: Date;
  lastCheckedAt?: Date;
  lastTriggeredAt?: Date;
  triggerCount: number;
  createdAt: Date;
}

interface QueuedNotification {
  id: string;
  rule: AlertRule;
  title: string;
  body: string;
  value: string;
  timestamp: Date;
  effectiveSound: boolean;
  effectiveVibration: boolean;
  effectiveTts: boolean;
  speechText: string;
}

interface NotificationItem {
  id: string;
  title: string;
  body: string;
  timestamp: Date;
  ruleUuid: string;
  marketSymbol: string;
  value: string;
  exchange: string;
}

type ExchangeCategoryType = 'all' | 'tier1' | 'aggregator' | 'middleEast' | 'asia' | 'europe' | 'americas';
type ThemeModeType = 'dark-green' | 'light-green' | 'dark-orange' | 'light-orange' | 'dark-purple-blue' | 'light-purple-blue' | 'dark-gold' | 'light-gold' | 'dark-sapphire' | 'light-sapphire';

interface ExchangeInfo {
  id: string;
  name: string;
  category: ExchangeCategoryType;
  countryBadge: string;
  defaultCounter: string;
  availableCounters?: string[];
  pairsCount: number;
  pairsList: string[];
}

export const formatExchangeTag = (name?: string) => {
  if (!name) return '';
  return name
    .replace(/IRAN_MARKET/gi, 'IR_M')
    .replace(/Iran Market/gi, 'IR_M')
    .replace(/IRAN MARKET/gi, 'IR_M')
    .replace(/GLOBALSTOKS/gi, 'GL-ST')
    .replace(/GLOBALSTOCKS/gi, 'GL-ST')
    .replace(/GLOBAL_STOCKS/gi, 'GL-ST')
    .replace(/Global Stocks/gi, 'GL-ST')
    .replace(/global_stocks/gi, 'GL-ST')
    .replace(/Global Commodities/gi, 'GL-ST')
    .replace(/Global Market/gi, 'GL-ST')
    .replace(/Global Indices/gi, 'GL-ST')
    .replace(/Billion USD/gi, 'B USD')
    .replace(/Billion/gi, 'B USD');
};

export const formatScaledPrice = (price: number, unit?: string): string | null => {
  if (!unit) return null;
  const u = unit.trim().toUpperCase();
  const bMatch = /^(B|BILLION)\s*(USD|EUR|GBP|BTC|JPY|CNY|USDT|USDC)?$/i.exec(u);
  const mMatch = /^(M|MILLION)\s*(USD|EUR|GBP|BTC|JPY|CNY|USDT|USDC)?$/i.exec(u);
  const bSuffixMatch = /^(USD|EUR|GBP|BTC|JPY|CNY|USDT|USDC)\s*(B|BILLION)$/i.exec(u);
  const mSuffixMatch = /^(USD|EUR|GBP|BTC|JPY|CNY|USDT|USDC)\s*(M|MILLION)$/i.exec(u);
  let scale = '';
  let curr = 'USD';
  let maxDecimals = 3;
  if (u === 'TOTAL' || u === 'TOTAL2' || u === 'TOTAL3') {
    scale = 'B';
    curr = 'USD';
    maxDecimals = 3;
  } else if (bMatch) {
    scale = 'B';
    curr = bMatch[2] || 'USD';
    maxDecimals = 3;
  } else if (mMatch) {
    scale = 'M';
    curr = mMatch[2] || 'USD';
    maxDecimals = 2;
  } else if (bSuffixMatch) {
    scale = 'B';
    curr = bSuffixMatch[1] || 'USD';
    maxDecimals = 3;
  } else if (mSuffixMatch) {
    scale = 'M';
    curr = mSuffixMatch[1] || 'USD';
    maxDecimals = 2;
  }
  if (!scale) return null;

  const symMap: Record<string, string> = { EUR: '€', GBP: '£', JPY: '¥', CNY: '¥', BTC: '₿' };
  const sym = symMap[curr.toUpperCase()] || '$';

  const isNeg = price < 0;
  const absP = Math.abs(price);
  const fixedStr = absP.toFixed(maxDecimals);
  const [intPart, decPart] = fixedStr.split('.');
  const formattedInt = Number(intPart).toLocaleString('en-US');
  const cleanDec = (decPart || '').replace(/0+$/, '');
  const numStr = cleanDec.length > 0 ? `${formattedInt}.${cleanDec}` : formattedInt;
  const prefix = isNeg ? `-${sym}` : sym;
  return `\u202A${prefix}${numStr}${scale}\u202C`;
};

export const isTomanRule = (rule: { counterCurrency?: string; exchangeId?: string }) => {
  const c = (rule.counterCurrency || '').toUpperCase().trim();
  const ex = (rule.exchangeId || '').toLowerCase();
  return c === 'TMN' || c === 'IRT' || c === 'TOMAN' || c === 'ت' || rule.counterCurrency === 'تومان' || ex.includes('nobitex') || ex.includes('bonbast');
};

const IRANIAN_POPULAR_PAIRS = [
  'BTC', 'ETH', 'SOL', 'USDT', 'XRP', 'DOGE', 'TON', 'PEPE', 'SHIB', 'SUI',
  'NEAR', 'TRX', 'ADA', 'AVAX', 'LINK', 'NOT', 'FLOKI', 'BONK', 'FET', 'APT',
  'BCH', 'LTC', 'POL', 'RENDER', 'ATOM', 'ARB', 'OP', 'KAS', 'TIA', 'DOT',
  'WIF', 'HMSTR', 'CATI', 'DOGS', 'TURBO', 'BABYDOGE', 'AAVE', 'CRV', 'UNI', 'ICP',
  'XLM', 'TAO', 'ETC', 'XMR', 'HBAR', 'FIL', 'VET', 'INJ', 'SEI', 'S',
  'ALGO', 'RUNE', 'STX', 'THETA', 'EOS', 'EGLD', 'NEO', 'IOTA', 'QNT', 'STRK',
  'BLUR', 'IMX', 'LDO', 'MANTA', 'METIS', 'ZRO', 'BLAST', 'ZK', 'DYM', 'SAGA',
  'GALA', 'SAND', 'MANA', 'AXS', 'BEAM', 'RON', 'PIXEL', 'CHZ', 'PENDLE', 'ENA',
  'JUP', 'ENS', 'DYDX', 'ONDO', 'OM', 'HNT', 'JASMY', 'BAT', 'QTUM', 'XEC',
  'ZEN', 'RVN', 'CKB', 'ONE', 'WLD', 'ARKM', 'IO', 'GRASS', 'ATH', 'GLM'
];

export const BONBAST_POPULAR_PAIRS = [
  'USDT', 'USD', 'EUR', 'GBP', 'AED', 'TRY', 'GOLD18', 'MITHQAL', 'COIN_EMAMI', 'COIN_BAHAR', 'COIN_HALF', 'COIN_QUARTER', 'COIN_GRAM',
  'CAD', 'AUD', 'CHF', 'CNY', 'IQD', 'KWD', 'SAR', 'QAR', 'OMR', 'BHD', 'AFN', 'RUB', 'INR', 'JPY'
];

// === 1. COMPLETE 40+ EXCHANGES CATALOG (Sorted Alphabetically A-Z by English Name) ===
const ALL_EXCHANGES: ExchangeInfo[] = [
  { id: 'bonbast', name: 'Bonbast (بن‌بست)', category: 'middleEast', countryBadge: '🇮🇷 مرجع اصلی آزاد', defaultCounter: 'TMN', availableCounters: ['TMN'], pairsCount: 38, pairsList: BONBAST_POPULAR_PAIRS },
  { id: 'abantether', name: 'AbanTether', category: 'middleEast', countryBadge: '🇮🇷 Iran', defaultCounter: 'TMN', availableCounters: ['TMN', 'USDT'], pairsCount: 1000, pairsList: IRANIAN_POPULAR_PAIRS },
  { id: 'binance', name: 'Binance', category: 'tier1', countryBadge: '🌐 Global #1', defaultCounter: 'USDT', availableCounters: ['USDT', 'BTC', 'ETH'], pairsCount: 1420, pairsList: ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'POL', 'RENDER', 'S', 'PEPE', 'DOGE', 'ADA', 'AVAX', 'NEAR', 'SUI', 'LINK', 'DOT'] },
  { id: 'bingx', name: 'BingX', category: 'tier1', countryBadge: '🌐 Global', defaultCounter: 'USDT', availableCounters: ['USDT'], pairsCount: 720, pairsList: ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'PEPE'] },
  { id: 'bitbarg', name: 'Bitbarg', category: 'middleEast', countryBadge: '🇮🇷 Iran', defaultCounter: 'TMN', availableCounters: ['TMN', 'USDT'], pairsCount: 420, pairsList: IRANIAN_POPULAR_PAIRS },
  { id: 'bitcoinde', name: 'Bitcoin.de', category: 'europe', countryBadge: '🇩🇪 Germany', defaultCounter: 'EUR', pairsCount: 35, pairsList: ['BTC', 'ETH', 'BCH', 'LTC'] },
  { id: 'bitfinex', name: 'Bitfinex', category: 'tier1', countryBadge: '🇭🇰 Hong Kong', defaultCounter: 'USD', availableCounters: ['USD', 'USDT'], pairsCount: 380, pairsList: ['BTC', 'ETH', 'SOL', 'XRP', 'LTC', 'EOS'] },
  { id: 'bitflyer', name: 'bitFlyer', category: 'asia', countryBadge: '🇯🇵 Japan', defaultCounter: 'JPY', pairsCount: 85, pairsList: ['BTC', 'ETH', 'XRP', 'MONA', 'LTC'] },
  { id: 'bitget', name: 'Bitget', category: 'tier1', countryBadge: '🇸🇬 Singapore', defaultCounter: 'USDT', availableCounters: ['USDT'], pairsCount: 820, pairsList: ['BTC', 'ETH', 'BGB', 'SOL', 'XRP', 'DOGE'] },
  { id: 'bithumb', name: 'Bithumb', category: 'asia', countryBadge: '🇰🇷 South Korea', defaultCounter: 'KRW', pairsCount: 290, pairsList: ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'ADA'] },
  { id: 'bitkub', name: 'Bitkub', category: 'asia', countryBadge: '🇹🇭 Thailand', defaultCounter: 'THB', pairsCount: 110, pairsList: ['BTC', 'ETH', 'KUB', 'SOL', 'DOGE'] },
  { id: 'bitpanda', name: 'Bitpanda', category: 'europe', countryBadge: '🇦🇹 Austria', defaultCounter: 'EUR', pairsCount: 320, pairsList: ['BTC', 'ETH', 'BEST', 'SOL', 'ADA'] },
  { id: 'bitso', name: 'Bitso', category: 'americas', countryBadge: '🇲🇽 Mexico', defaultCounter: 'MXN', pairsCount: 95, pairsList: ['BTC', 'ETH', 'SOL', 'XRP'] },
  { id: 'bitstamp', name: 'Bitstamp', category: 'tier1', countryBadge: '🇱🇺 Luxembourg', defaultCounter: 'USD', availableCounters: ['USD', 'EUR'], pairsCount: 220, pairsList: ['BTC', 'ETH', 'XRP', 'LTC', 'BCH', 'ADA'] },
  { id: 'bitvavo', name: 'Bitvavo', category: 'europe', countryBadge: '🇳🇱 Netherlands', defaultCounter: 'EUR', pairsCount: 240, pairsList: ['BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE'] },
  { id: 'bybit', name: 'Bybit', category: 'tier1', countryBadge: '🇦🇪 UAE / Global', defaultCounter: 'USDT', availableCounters: ['USDT', 'USDC'], pairsCount: 760, pairsList: ['BTC', 'ETH', 'SOL', 'MNT', 'XRP', 'DOGE', 'SUI', 'PEPE'] },
  { id: 'coinbase', name: 'Coinbase', category: 'tier1', countryBadge: '🇺🇸 USA', defaultCounter: 'USD', availableCounters: ['USD', 'USDC'], pairsCount: 520, pairsList: ['BTC', 'ETH', 'SOL', 'ADA', 'DOGE', 'AVAX', 'LINK', 'NEAR', 'DOT'] },
  { id: 'coinex', name: 'CoinEx', category: 'middleEast', countryBadge: '🌐 Middle East Friendly', defaultCounter: 'USDT', availableCounters: ['USDT', 'USDC'], pairsCount: 920, pairsList: ['BTC', 'ETH', 'CET', 'SOL', 'XRP', 'DOGE', 'ADA', 'PEPE'] },
  { id: 'coingecko', name: 'CoinGecko', category: 'aggregator', countryBadge: '📊 Global Index', defaultCounter: 'USD', availableCounters: ['USD', 'USDT'], pairsCount: 10450, pairsList: ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'POL', 'RENDER', 'S', 'PEPE', 'SHIB', 'NEAR', 'SUI', 'APT', 'AVAX'] },
  { id: 'coinmarketcap', name: 'CoinMarketCap', category: 'aggregator', countryBadge: '📊 Global Index', defaultCounter: 'USD', availableCounters: ['USD', 'USDT'], pairsCount: 9800, pairsList: ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'TON', 'ADA', 'TRX', 'AVAX'] },
  { id: 'cryptocompare', name: 'CryptoCompare', category: 'aggregator', countryBadge: '📊 Aggregator', defaultCounter: 'USD', availableCounters: ['USD', 'USDT'], pairsCount: 6500, pairsList: ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOT', 'LTC'] },
  { id: 'exmo', name: 'EXMO', category: 'europe', countryBadge: '🇬🇧 United Kingdom', defaultCounter: 'USD', pairsCount: 160, pairsList: ['BTC', 'ETH', 'EXM', 'SOL', 'XRP'] },
  { id: 'foxbit', name: 'Foxbit', category: 'americas', countryBadge: '🇧🇷 Brazil', defaultCounter: 'BRL', pairsCount: 140, pairsList: ['BTC', 'ETH', 'SOL', 'DOGE'] },
  { id: 'gateio', name: 'Gate.io', category: 'tier1', countryBadge: '🌐 Global', defaultCounter: 'USDT', availableCounters: ['USDT', 'BTC'], pairsCount: 1900, pairsList: ['BTC', 'ETH', 'GT', 'SOL', 'PEPE', 'POL', 'RENDER', 'S'] },
  { id: 'gemini', name: 'Gemini', category: 'tier1', countryBadge: '🇺🇸 USA', defaultCounter: 'USD', availableCounters: ['USD'], pairsCount: 180, pairsList: ['BTC', 'ETH', 'SOL', 'DOGE', 'LINK', 'LTC'] },
  { id: 'huobi', name: 'HTX / Huobi', category: 'tier1', countryBadge: '🌐 Global', defaultCounter: 'USDT', availableCounters: ['USDT'], pairsCount: 750, pairsList: ['BTC', 'ETH', 'HT', 'SOL', 'TRX', 'XRP'] },
  { id: 'indodax', name: 'Indodax', category: 'asia', countryBadge: '🇮🇩 Indonesia', defaultCounter: 'IDR', pairsCount: 210, pairsList: ['BTC', 'ETH', 'USDT', 'DOGE', 'XRP'] },
  { id: 'kraken', name: 'Kraken', category: 'tier1', countryBadge: '🇺🇸 USA / EU', defaultCounter: 'USD', availableCounters: ['USD', 'EUR'], pairsCount: 430, pairsList: ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOT', 'DOGE', 'LTC'] },
  { id: 'kucoin', name: 'KuCoin', category: 'tier1', countryBadge: '🌐 Global', defaultCounter: 'USDT', availableCounters: ['USDT', 'BTC'], pairsCount: 890, pairsList: ['BTC', 'ETH', 'SOL', 'PEPE', 'RENDER', 'S', 'TON', 'SUI', 'POL'] },
  { id: 'luno', name: 'Luno', category: 'americas', countryBadge: '🇿🇦 South Africa', defaultCounter: 'ZAR', pairsCount: 45, pairsList: ['BTC', 'ETH', 'XRP', 'SOL', 'ADA'] },
  { id: 'mercadobitcoin', name: 'Mercado Bitcoin', category: 'americas', countryBadge: '🇧🇷 Brazil', defaultCounter: 'BRL', pairsCount: 210, pairsList: ['BTC', 'ETH', 'SOL', 'XRP', 'ADA'] },
  { id: 'mexc', name: 'MEXC Global', category: 'tier1', countryBadge: '🌐 Global', defaultCounter: 'USDT', availableCounters: ['USDT', 'USDC'], pairsCount: 2100, pairsList: ['BTC', 'ETH', 'MX', 'SOL', 'PEPE', 'SUI', 'TON'] },
  { id: 'ndax', name: 'NDAX', category: 'americas', countryBadge: '🇨🇦 Canada', defaultCounter: 'CAD', pairsCount: 65, pairsList: ['BTC', 'ETH', 'SOL', 'ADA', 'DOGE'] },
  { id: 'nobitex', name: 'Nobitex', category: 'middleEast', countryBadge: '🇮🇷 Iran', defaultCounter: 'TMN', availableCounters: ['TMN', 'USDT'], pairsCount: 531, pairsList: IRANIAN_POPULAR_PAIRS },
  { id: 'okx', name: 'OKX', category: 'tier1', countryBadge: '🌐 Global', defaultCounter: 'USDT', availableCounters: ['USDT', 'USD'], pairsCount: 680, pairsList: ['BTC', 'ETH', 'SOL', 'OKB', 'XRP', 'DOGE', 'ADA', 'TON'] },
  { id: 'paymium', name: 'Paymium', category: 'europe', countryBadge: '🇫🇷 France', defaultCounter: 'EUR', pairsCount: 20, pairsList: ['BTC', 'ETH', 'EUR'] },
  { id: 'poloniex', name: 'Poloniex', category: 'tier1', countryBadge: '🌐 Global', defaultCounter: 'USDT', availableCounters: ['USDT'], pairsCount: 450, pairsList: ['BTC', 'ETH', 'TRX', 'SOL', 'DOGE', 'XRP'] },
  { id: 'ramzinex', name: 'Ramzinex', category: 'middleEast', countryBadge: '🇮🇷 Iran', defaultCounter: 'TMN', availableCounters: ['TMN', 'USDT'], pairsCount: 631, pairsList: IRANIAN_POPULAR_PAIRS },
  { id: 'sarmayex', name: 'Sarmayex', category: 'middleEast', countryBadge: '🇮🇷 Iran', defaultCounter: 'TMN', availableCounters: ['TMN', 'USDT'], pairsCount: 120, pairsList: IRANIAN_POPULAR_PAIRS.slice(0, 40) },
  { id: 'tabdeal', name: 'Tabdeal', category: 'middleEast', countryBadge: '🇮🇷 Iran', defaultCounter: 'TMN', availableCounters: ['TMN', 'USDT'], pairsCount: 1047, pairsList: IRANIAN_POPULAR_PAIRS },
  { id: 'tetherland', name: 'TetherLand', category: 'middleEast', countryBadge: '🇮🇷 Iran', defaultCounter: 'TMN', availableCounters: ['TMN', 'USDT'], pairsCount: 150, pairsList: ['USDT', 'BTC', 'ETH', 'SOL', 'TON', 'XRP', 'DOGE', 'TRX', 'SHIB', 'PEPE', 'ADA', 'AVAX', 'NEAR', 'SUI', 'LINK', 'DOT', 'LTC'] },
  { id: 'upbit', name: 'Upbit', category: 'asia', countryBadge: '🇰🇷 South Korea', defaultCounter: 'KRW', pairsCount: 310, pairsList: ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'ADA', 'ETC'] },
  { id: 'valr', name: 'VALR', category: 'americas', countryBadge: '🇿🇦 South Africa', defaultCounter: 'ZAR', pairsCount: 90, pairsList: ['BTC', 'ETH', 'SOL', 'XRP'] },
  { id: 'wallex', name: 'Wallex', category: 'middleEast', countryBadge: '🇮🇷 Iran', defaultCounter: 'TMN', availableCounters: ['TMN', 'USDT'], pairsCount: 373, pairsList: IRANIAN_POPULAR_PAIRS },
  { id: 'wazirx', name: 'WazirX', category: 'asia', countryBadge: '🇮🇳 India', defaultCounter: 'INR', pairsCount: 240, pairsList: ['BTC', 'ETH', 'WRX', 'SOL', 'XRP', 'DOGE'] },
  { id: 'zaif', name: 'Zaif', category: 'asia', countryBadge: '🇯🇵 Japan', defaultCounter: 'JPY', pairsCount: 45, pairsList: ['BTC', 'ETH', 'ZAIF', 'XEM', 'MONA'] },
];

export interface CryptoCoinMeta {
  name: string;
  nameFa: string;
  icon: string;
  currentPrice: number;
  change24h: number;
  high24h: number;
  low24h: number;
  volume24h: number;
}

const CRYPTO_COIN_METAS: Record<string, CryptoCoinMeta> = {
  BTC: { name: 'Bitcoin', nameFa: 'بیت‌کوین', icon: 'https://assets.coingecko.com/coins/images/1/small/bitcoin.png', currentPrice: 83770.00, change24h: 1.2, high24h: 84950.00, low24h: 82100.00, volume24h: 28400000000 },
  ETH: { name: 'Ethereum', nameFa: 'اتریوم', icon: 'https://assets.coingecko.com/coins/images/279/small/ethereum.png', currentPrice: 2689.50, change24h: -0.8, high24h: 2740.00, low24h: 2615.00, volume24h: 14200000000 },
  SOL: { name: 'Solana', nameFa: 'سولانا', icon: 'https://assets.coingecko.com/coins/images/4128/small/solana.png', currentPrice: 120.10, change24h: 2.4, high24h: 124.50, low24h: 116.80, volume24h: 3800000000 },
  BNB: { name: 'BNB', nameFa: 'بایننس کوین', icon: 'https://assets.coingecko.com/coins/images/825/small/bnb-icon2_2x.png', currentPrice: 770.60, change24h: 0.9, high24h: 782.00, low24h: 755.00, volume24h: 1100000000 },
  XRP: { name: 'XRP', nameFa: 'ریپل', icon: 'https://assets.coingecko.com/coins/images/44/small/xrp-symbol-white-128.png', currentPrice: 1.51, change24h: 3.1, high24h: 1.58, low24h: 1.45, volume24h: 2400000000 },
  DOGE: { name: 'Dogecoin', nameFa: 'دوج‌کوین', icon: 'https://assets.coingecko.com/coins/images/5/small/dogecoin.png', currentPrice: 0.22, change24h: 2.8, high24h: 0.235, low24h: 0.208, volume24h: 1650000000 },
  ADA: { name: 'Cardano', nameFa: 'کاردانو', icon: 'https://assets.coingecko.com/coins/images/975/small/cardano.png', currentPrice: 0.68, change24h: 1.5, high24h: 0.71, low24h: 0.65, volume24h: 720000000 },
  AVAX: { name: 'Avalanche', nameFa: 'آوالانچ', icon: 'https://assets.coingecko.com/coins/images/12559/small/Avalanche_Circle_RedWhite_Trans.png', currentPrice: 28.40, change24h: -1.2, high24h: 29.80, low24h: 27.50, volume24h: 480000000 },
  POL: { name: 'Polygon (POL)', nameFa: 'پالیگان (POL)', icon: 'https://assets.coingecko.com/coins/images/4713/small/polygon.png', currentPrice: 0.28, change24h: 1.8, high24h: 0.295, low24h: 0.268, volume24h: 210000000 },
  RENDER: { name: 'Render (RENDER)', nameFa: 'رندر (هوش مصنوعی)', icon: 'https://assets.coingecko.com/coins/images/11636/small/rndr.png', currentPrice: 2.07, change24h: 4.2, high24h: 2.18, low24h: 1.95, volume24h: 180000000 },
  S: { name: 'Sonic (S)', nameFa: 'سونیک (فانتوم سابق)', icon: 'https://assets.coingecko.com/coins/images/4001/small/Fantom_round.png', currentPrice: 0.58, change24h: 5.6, high24h: 0.62, low24h: 0.54, volume24h: 120000000 },
  PEPE: { name: 'Pepe', nameFa: 'پپه‌کوین', icon: 'https://assets.coingecko.com/coins/images/29850/small/pepe-token.png', currentPrice: 0.0000098, change24h: 6.8, high24h: 0.0000105, low24h: 0.0000091, volume24h: 890000000 },
  TON: { name: 'Toncoin', nameFa: 'تن‌کوین (تلگرام)', icon: 'https://assets.coingecko.com/coins/images/17980/small/ton_symbol.png', currentPrice: 4.95, change24h: 1.1, high24h: 5.12, low24h: 4.82, volume24h: 310000000 },
  SUI: { name: 'Sui', nameFa: 'سویی', icon: 'https://assets.coingecko.com/coins/images/26375/small/sui-ocean-square.png', currentPrice: 2.15, change24h: 3.7, high24h: 2.28, low24h: 2.04, volume24h: 640000000 },
  NEAR: { name: 'NEAR Protocol', nameFa: 'نیر پروتکل', icon: 'https://assets.coingecko.com/coins/images/10365/small/near.png', currentPrice: 4.80, change24h: 0.6, high24h: 4.98, low24h: 4.65, volume24h: 290000000 },
  LINK: { name: 'Chainlink', nameFa: 'چین‌لینک', icon: 'https://assets.coingecko.com/coins/images/877/small/chainlink-new-logo.png', currentPrice: 13.40, change24h: 2.1, high24h: 13.90, low24h: 12.95, volume24h: 350000000 },
  DOT: { name: 'Polkadot', nameFa: 'پولکادات', icon: 'https://assets.coingecko.com/coins/images/12171/small/polkadot.png', currentPrice: 4.60, change24h: -0.4, high24h: 4.75, low24h: 4.48, volume24h: 195000000 },
  LTC: { name: 'Litecoin', nameFa: 'لایت‌کوین', icon: 'https://assets.coingecko.com/coins/images/2/small/litecoin.png', currentPrice: 88.20, change24h: 0.7, high24h: 91.50, low24h: 86.40, volume24h: 420000000 },
};

// === 2. MACRO ASSETS (US 10Y BONDS, FOREX, STOCKS, GOLD, OIL) ===
interface MacroAssetMeta {
  symbol: string;
  name: string;
  nameFa: string;
  category: 'bond' | 'forex' | 'stock' | 'commodity' | 'index' | 'iran_market';
  marketName: string;
  icon: string;
  currentPrice: number;
  unit: string;
  change24h: number;
}

const MACRO_ASSETS: Record<string, MacroAssetMeta> = {
  // === BONBAST IRAN FREE MARKET (PRIMARY REFERENCE: BONBAST.COM) ===
  GOLD18_BONBAST: { symbol: 'GOLD18', name: 'Gold 18K (Gram)', nameFa: 'طلای ۱۸ عیار - هر گرم (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 26296227, unit: 'ت', change24h: 0.8 },
  MITHQAL_BONBAST: { symbol: 'MITHQAL', name: 'Gold Mithqal (Melted)', nameFa: 'مظنه آبشده / مثقال طلا تهران (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 113910000, unit: 'ت', change24h: 0.9 },
  EMAMI_BONBAST: { symbol: 'EMAMI', name: 'Emami Gold Coin', nameFa: 'سکه تمام طرح جدید / امامی (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 270000000, unit: 'ت', change24h: 0.6 },
  BAHAR_BONBAST: { symbol: 'AZADI', name: 'Bahar Azadi Coin', nameFa: 'سکه تمام بهار آزادی طرح قدیم (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 259000000, unit: 'ت', change24h: 0.5 },
  HALF_BONBAST: { symbol: 'HALF', name: 'Half Azadi Coin', nameFa: 'نیم‌سکه بهار آزادی (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 143000000, unit: 'ت', change24h: 0.4 },
  QUARTER_BONBAST: { symbol: 'QUARTER', name: 'Quarter Azadi Coin', nameFa: 'ربع‌سکه بهار آزادی (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 76500000, unit: 'ت', change24h: 0.4 },
  GRAM_BONBAST: { symbol: 'GRAM', name: 'Central Bank Gram Coin', nameFa: 'سکه یک گرمی بانک مرکزی (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 37000000, unit: 'ت', change24h: 0.2 },
  USD_BONBAST: { symbol: 'USD/TMN', name: 'US Dollar (Tehran Cash)', nameFa: 'دلار آزاد تهران - اسکناس (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 268200, unit: 'ت', change24h: 0.3 },
  EUR_BONBAST: { symbol: 'EUR/TMN', name: 'Euro Cash', nameFa: 'یورو آزاد تهران - اسکناس (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 300400, unit: 'ت', change24h: 0.2 },
  AED_BONBAST: { symbol: 'AED/TMN', name: 'UAE Dirham Cash', nameFa: 'درهم امارات - اسکناس/حواله (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 73050, unit: 'ت', change24h: 0.1 },
  GBP_BONBAST: { symbol: 'GBP/TMN', name: 'British Pound Cash', nameFa: 'پوند انگلیس - اسکناس (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323329.png', currentPrice: 354400, unit: 'ت', change24h: -0.1 },
  TRY_BONBAST: { symbol: 'TRY/TMN', name: 'Turkish Lira', nameFa: 'لیر ترکیه (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 5450, unit: 'ت', change24h: 0.1 },
  IQD_BONBAST: { symbol: 'IQD/TMN', name: 'Iraqi Dinar (100)', nameFa: '۱۰۰ دینار عراق (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 17700, unit: 'ت', change24h: 0.0 },
  BOURSE_BONBAST: { symbol: 'TEDPIX', name: 'Tehran Stock Exchange Index', nameFa: 'شاخص کل بورس اوراق بهادار تهران (TEDPIX)', category: 'iran_market', marketName: 'بورس تهران (مرجع بن‌بست)', icon: 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png', currentPrice: 1904324, unit: 'واحد', change24h: 0.35 },
  AFN_BONBAST: { symbol: 'AFN/TMN', name: 'Afghan Afghani (Herat)', nameFa: 'افغانی افغانستان - بازار هرات (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 4125, unit: 'ت', change24h: 0.1 },
  CAD_BONBAST: { symbol: 'CAD/TMN', name: 'Canadian Dollar Cash', nameFa: 'دلار کانادا - اسکناس آزاد (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323277.png', currentPrice: 188300, unit: 'ت', change24h: 0.2 },
  AUD_BONBAST: { symbol: 'AUD/TMN', name: 'Australian Dollar Cash', nameFa: 'دلار استرالیا - اسکناس آزاد (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323367.png', currentPrice: 186500, unit: 'ت', change24h: 0.1 },
  CHF_BONBAST: { symbol: 'CHF/TMN', name: 'Swiss Franc Cash', nameFa: 'فرانک سوئیس - اسکناس آزاد (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323316.png', currentPrice: 321800, unit: 'ت', change24h: 0.3 },
  CNY_BONBAST: { symbol: 'CNY/TMN', name: 'Chinese Yuan Cash', nameFa: 'یوان چین - اسکناس آزاد (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 40000, unit: 'ت', change24h: 0.2 },
  KWD_BONBAST: { symbol: 'KWD/TMN', name: 'Kuwaiti Dinar', nameFa: 'دینار کویت (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 862550, unit: 'ت', change24h: 0.1 },
  SAR_BONBAST: { symbol: 'SAR/TMN', name: 'Saudi Riyal Cash', nameFa: 'ریال عربستان (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 71500, unit: 'ت', change24h: 0.1 },
  QAR_BONBAST: { symbol: 'QAR/TMN', name: 'Qatari Riyal Cash', nameFa: 'ریال قطر (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 73550, unit: 'ت', change24h: 0.1 },
  OMR_BONBAST: { symbol: 'OMR/TMN', name: 'Omani Rial Cash', nameFa: 'ریال عمان (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 697550, unit: 'ت', change24h: 0.1 },
  JPY_BONBAST: { symbol: 'JPY/TMN', name: 'Japanese Yen (10)', nameFa: '۱۰ ین ژاپن (مرجع بن‌بست)', category: 'iran_market', marketName: 'بن‌بست (bonbast.com)', icon: 'https://cdn-icons-png.flaticon.com/512/323/323313.png', currentPrice: 16950, unit: 'ت', change24h: 0.2 },

  // US Treasury Yields & Bonds
  US10Y: { symbol: 'US10Y (^TNX)', name: 'US 10-Year Treasury Yield', nameFa: 'بازده اوراق قرضه ۱۰ ساله آمریکا (US10Y)', category: 'bond', marketName: 'US Treasury', icon: 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png', currentPrice: 4.28, unit: '%', change24h: 0.8 },
  US02Y: { symbol: 'US02Y (^IRX)', name: 'US 2-Year Treasury Yield', nameFa: 'بازده اوراق قرضه ۲ ساله آمریکا (US02Y)', category: 'bond', marketName: 'US Treasury', icon: 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png', currentPrice: 4.15, unit: '%', change24h: 0.4 },
  US30Y: { symbol: 'US30Y (^TYX)', name: 'US 30-Year Treasury Bond', nameFa: 'بازده اوراق قرضه ۳۰ ساله آمریکا (US30Y)', category: 'bond', marketName: 'US Treasury', icon: 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png', currentPrice: 4.52, unit: '%', change24h: 0.9 },

  // Forex Currency Pairs
  EURUSD: { symbol: 'EUR/USD', name: 'Euro / US Dollar', nameFa: 'یورو به دلار آمریکا (EUR/USD)', category: 'forex', marketName: 'Forex Major', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 1.0825, unit: '$', change24h: 0.22 },
  GBPUSD: { symbol: 'GBP/USD', name: 'British Pound / US Dollar', nameFa: 'پوند انگلیس به دلار (GBP/USD)', category: 'forex', marketName: 'Forex Major', icon: 'https://cdn-icons-png.flaticon.com/512/323/323329.png', currentPrice: 1.2980, unit: '$', change24h: -0.15 },
  USDJPY: { symbol: 'USD/JPY', name: 'US Dollar / Japanese Yen', nameFa: 'دلار به ین ژاپن (USD/JPY)', category: 'forex', marketName: 'Forex Major', icon: 'https://cdn-icons-png.flaticon.com/512/323/323313.png', currentPrice: 153.40, unit: '¥', change24h: 0.45 },
  USDCHF: { symbol: 'USD/CHF', name: 'US Dollar / Swiss Franc', nameFa: 'دلار به فرانک سوئیس (USD/CHF)', category: 'forex', marketName: 'Forex Major', icon: 'https://cdn-icons-png.flaticon.com/512/323/323316.png', currentPrice: 0.8670, unit: 'Fr', change24h: 0.12 },
  AUDUSD: { symbol: 'AUD/USD', name: 'Australian Dollar / USD', nameFa: 'دلار استرالیا به دلار آمریکا (AUD/USD)', category: 'forex', marketName: 'Forex Major', icon: 'https://cdn-icons-png.flaticon.com/512/323/323367.png', currentPrice: 0.6580, unit: '$', change24h: -0.35 },
  USDCAD: { symbol: 'USD/CAD', name: 'US Dollar / Canadian Dollar', nameFa: 'دلار آمریکا به دلار کانادا (USD/CAD)', category: 'forex', marketName: 'Forex Major', icon: 'https://cdn-icons-png.flaticon.com/512/323/323277.png', currentPrice: 1.3890, unit: 'C$', change24h: 0.18 },

  // US Stocks (NASDAQ & NYSE)
  NVDA: { symbol: 'NVDA', name: 'NVIDIA Corporation', nameFa: 'سهام انویدیا (NVIDIA)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/NVDA.png', currentPrice: 138.25, unit: '$', change24h: 3.4 },
  AAPL: { symbol: 'AAPL', name: 'Apple Inc.', nameFa: 'سهام اپل (Apple)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/AAPL.png', currentPrice: 228.50, unit: '$', change24h: 1.1 },
  MSFT: { symbol: 'MSFT', name: 'Microsoft Corporation', nameFa: 'سهام مایکروسافت (Microsoft)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/MSFT.png', currentPrice: 428.10, unit: '$', change24h: 0.8 },
  AMZN: { symbol: 'AMZN', name: 'Amazon.com Inc.', nameFa: 'سهام آمازون (Amazon)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/AMZN.png', currentPrice: 186.70, unit: '$', change24h: 1.5 },
  GOOGL: { symbol: 'GOOGL', name: 'Alphabet Inc. (Google)', nameFa: 'سهام گوگل (آلفابت)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/GOOGL.png', currentPrice: 165.30, unit: '$', change24h: 0.4 },
  META: { symbol: 'META', name: 'Meta Platforms (Facebook)', nameFa: 'سهام متا (فیسبوک)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/META.png', currentPrice: 585.20, unit: '$', change24h: 2.1 },
  PLTR: { symbol: 'PLTR', name: 'Palantir Technologies', nameFa: 'سهام پالانتیر (Palantir)', category: 'stock', marketName: 'NYSE', icon: 'https://companiesmarketcap.com/img/company-logos/64/PLTR.png', currentPrice: 44.10, unit: '$', change24h: 5.6 },
  BRKB: { symbol: 'BRK.B', name: 'Berkshire Hathaway', nameFa: 'برکشایر هاتاوی (وارن بافت)', category: 'stock', marketName: 'NYSE', icon: 'https://companiesmarketcap.com/img/company-logos/64/BRK-B.png', currentPrice: 462.10, unit: '$', change24h: 0.5 },

  // Commercial Space, Aerospace & Elon Musk Ventures
  TSLA: { symbol: 'TSLA', name: 'Tesla Inc.', nameFa: 'سهام تسلا (خودروهای برقی، هوش مصنوعی، ربات اپتیموس و انرژی ایلان ماسک)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/TSLA.png', currentPrice: 255.40, unit: '$', change24h: -1.9 },
  SPACEX: { symbol: 'SPACEX', name: 'SpaceX (Starship & Space Exploration)', nameFa: 'اسپیس‌ایکس (فناوری‌های فضایی، استارشیپ و ماموریت‌های مریخ ایلان ماسک)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/3209/3209994.png', currentPrice: 112.00, unit: '$', change24h: 4.8 },
  STARLINK: { symbol: 'STARLINK', name: 'Starlink (SpaceX Satellite Constellation)', nameFa: 'استارلینک (شبکه اینترنت ماهواره‌ای جهانی ایلان ماسک)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/3209/3209994.png', currentPrice: 85.00, unit: '$', change24h: 3.9 },
  XAI: { symbol: 'XAI', name: 'xAI (Grok AI & Colossus)', nameFa: 'شرکت هوش مصنوعی xAI (خالق Grok و سوپرکامپیوتر کلوسوس ایلان ماسک)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/12222/12222560.png', currentPrice: 45.00, unit: '$', change24h: 6.5 },
  X_CORP: { symbol: 'X_CORP', name: 'X Corp (Twitter - Everything App)', nameFa: 'ایکس / توییتر سابق (شبکه اجتماعی جهانی و اپلیکیشن همه‌کاره ایلان ماسک)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/5969/5969020.png', currentPrice: 38.50, unit: '$', change24h: 2.1 },
  NEURALINK: { symbol: 'NEURALINK', name: 'Neuralink (Brain-Computer Interface)', nameFa: 'نورالینک (تراشه رابط مغز و رایانه و تله‌پاتی ایلان ماسک)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/8649/8649607.png', currentPrice: 55.00, unit: '$', change24h: 5.2 },
  BORING: { symbol: 'BORING', name: 'The Boring Company (Hyperloop & Tunneling)', nameFa: 'بورینگ کمپانی (تونل‌های زیرزمینی حمل‌ونقل سریع هایپرلوپ ایلان ماسک)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png', currentPrice: 22.00, unit: '$', change24h: 1.4 },
  DOGE_MUSK: { symbol: 'DOGE', name: 'Dogecoin (Elon Musk Ecosystem Crypto)', nameFa: 'دوج‌کوین (رمزارز محبوب و رسمی اکوسیستم تسلا و پلتفرم ایکس)', category: 'stock', marketName: 'Musk Ecosystem', icon: 'https://assets.coingecko.com/coins/images/5/standard/dogecoin.png', currentPrice: 0.165, unit: '$', change24h: 7.8 },
  DXYZ: { symbol: 'DXYZ', name: 'Destiny Tech100 (SpaceX & OpenAI ETF)', nameFa: 'صندوق سرنوشت ۱۰۰ (سبد سهام عمومی اسپیس‌ایکس و اوپن‌ای‌آی)', category: 'stock', marketName: 'NYSE', icon: 'https://cdn-icons-png.flaticon.com/512/3209/3209994.png', currentPrice: 18.50, unit: '$', change24h: 6.2 },
  RKLB: { symbol: 'RKLB', name: 'Rocket Lab USA', nameFa: 'راکت لب (پرتاب‌های فضایی مداری تجاری و ماهواره‌های ناسا)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/RKLB.png', currentPrice: 10.45, unit: '$', change24h: 3.1 },
  ASTS: { symbol: 'ASTS', name: 'AST SpaceMobile', nameFa: 'ای‌اس‌تی اسپیس‌موبایل (شبکه پهن‌باند ماهواره‌ای به گوشی هوشمند)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/ASTS.png', currentPrice: 26.80, unit: '$', change24h: 8.5 },
  BA: { symbol: 'BA', name: 'The Boeing Company', nameFa: 'بوئینگ (غول هواپیماسازی، فضاپیما و کپسول فضایی استارلاینر)', category: 'stock', marketName: 'NYSE', icon: 'https://companiesmarketcap.com/img/company-logos/64/BA.png', currentPrice: 155.20, unit: '$', change24h: -0.8 },

  // Critical Semiconductors & Hardware (MSN Money Titans)
  TSM: { symbol: 'TSM', name: 'Taiwan Semiconductor Manufacturing (TSMC)', nameFa: 'تی‌اس‌ام‌سی (سازنده انحصاری تراشه‌های پیشرفته جهان)', category: 'stock', marketName: 'NYSE', icon: 'https://companiesmarketcap.com/img/company-logos/64/TSM.png', currentPrice: 195.40, unit: '$', change24h: 2.8 },
  ASML: { symbol: 'ASML', name: 'ASML Holding N.V.', nameFa: 'ای‌اس‌ام‌ال هلند (انحصار ۱۰۰٪ ماشین‌آلات لیتوگرافی فرابنفش چاپ تراشه)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/ASML.png', currentPrice: 712.50, unit: '$', change24h: 1.9 },
  AMD: { symbol: 'AMD', name: 'Advanced Micro Devices Inc.', nameFa: 'ای‌ام‌دی (پردازنده‌های هوش مصنوعی و کارت‌های گرافیک)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/AMD.png', currentPrice: 156.80, unit: '$', change24h: 2.3 },
  AVGO: { symbol: 'AVGO', name: 'Broadcom Inc.', nameFa: 'برودکام (غول تراشه‌های شبکه و هوش مصنوعی اختصاصی)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/AVGO.png', currentPrice: 178.60, unit: '$', change24h: 3.1 },

  // Luxury & Prestige Conglomerates
  LVMH: { symbol: 'MC.PA', name: 'LVMH Moët Hennessy Louis Vuitton', nameFa: 'ال‌وی‌ام‌اچ فرانسه (لویی ویتون، دیور، تیفانی، بولگاری - پادشاه برندهای لوکس)', category: 'stock', marketName: 'Euronext Paris', icon: 'https://companiesmarketcap.com/img/company-logos/64/MC.PA.png', currentPrice: 635.80, unit: '€', change24h: 1.2 },
  HERMES: { symbol: 'RMS.PA', name: 'Hermès International', nameFa: 'هرمس فرانسه (گران‌قیمت‌ترین خانه مد، کیف برکین و چرم دست‌ساز)', category: 'stock', marketName: 'Euronext Paris', icon: 'https://companiesmarketcap.com/img/company-logos/64/RMS.PA.png', currentPrice: 2085.00, unit: '€', change24h: 0.8 },
  PORSCHE: { symbol: 'P911.DE', name: 'Porsche AG', nameFa: 'پورشه آلمان (سوپراسپرت‌های لوکس اشتوتگارت)', category: 'stock', marketName: 'XETRA', icon: 'https://companiesmarketcap.com/img/company-logos/64/P911.DE.png', currentPrice: 68.40, unit: '€', change24h: 1.5 },

  // Regional Forex & Middle East (MSN Money FX)
  USDT_TMN: { symbol: 'USDT/TMN', name: 'Tether / Iranian Toman', nameFa: 'تتر به تومان ایران (نرخ لحظه‌ای بازار آزاد تهران)', category: 'forex', marketName: 'Tehran Free Market', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 69400, unit: 'ت', change24h: 0.4 },
  USD_AED: { symbol: 'USD/AED', name: 'US Dollar / UAE Dirham', nameFa: 'دلار آمریکا به درهم امارات (USD/AED)', category: 'forex', marketName: 'Forex Major', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 3.6725, unit: 'AED', change24h: 0.01 },
  USD_CNY: { symbol: 'USD/CNY', name: 'US Dollar / Chinese Yuan', nameFa: 'دلار آمریکا به یوان چین (USD/CNY)', category: 'forex', marketName: 'Forex Major', icon: 'https://cdn-icons-png.flaticon.com/512/323/323310.png', currentPrice: 7.1420, unit: '¥', change24h: -0.12 },

  // Frontier AI & Pre-IPO Giants
  OPENAI: { symbol: 'OPENAI', name: 'OpenAI (ChatGPT & Frontier AI)', nameFa: 'اوپن‌ای‌آی (خالق چت‌جی‌پی‌تی و پیشتاز هوش مصنوعی عمومی AGI)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/12222/12222560.png', currentPrice: 150.00, unit: '$', change24h: 5.0 },
  ANTHROPIC: { symbol: 'ANTHROPIC', name: 'Anthropic (Claude AI)', nameFa: 'انتروپیک (خالق هوش مصنوعی کلود Claude)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/8649/8649607.png', currentPrice: 85.00, unit: '$', change24h: 3.7 },
  STRIPE: { symbol: 'STRIPE', name: 'Stripe Payments', nameFa: 'استریپ (زیرساخت پرداخت اینترنتی و تسویه رمزارزی جهان)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://companiesmarketcap.com/img/company-logos/64/STRIP.png', currentPrice: 32.50, unit: '$', change24h: 1.8 },
  BYTEDANCE: { symbol: 'BYTEDANCE', name: 'ByteDance (TikTok)', nameFa: 'بایت‌دنس (مالک تیک‌تاک و غول الگوریتم‌های هوش مصنوعی)', category: 'stock', marketName: 'Pre-IPO Benchmark', icon: 'https://cdn-icons-png.flaticon.com/512/3046/3046121.png', currentPrice: 175.00, unit: '$', change24h: 2.4 },

  // Crypto Mining & Fintech Stocks
  MSTR: { symbol: 'MSTR', name: 'MicroStrategy Inc.', nameFa: 'میکرواستراتژی (بزرگ‌ترین خزانه‌داری بیت‌کوین سازمانی)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/MSTR.png', currentPrice: 215.30, unit: '$', change24h: 7.4 },
  COIN: { symbol: 'COIN', name: 'Coinbase Global Inc.', nameFa: 'کوین‌بیس (بزرگ‌ترین صرافی مجاز کریپتو آمریکا)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/COIN.png', currentPrice: 212.80, unit: '$', change24h: 4.2 },
  MARA: { symbol: 'MARA', name: 'MARA Holdings (Marathon)', nameFa: 'ماراتون دیجیتال / MARA (بزرگ‌ترین استخراج‌کننده بیت‌کوین)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/MARA.png', currentPrice: 18.90, unit: '$', change24h: 6.8 },
  RIOT: { symbol: 'RIOT', name: 'Riot Platforms Inc.', nameFa: 'رایوت پلتفرمز (زیرساخت استخراج و مزارع بیت‌کوین)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/RIOT.png', currentPrice: 9.85, unit: '$', change24h: 5.1 },
  CLSK: { symbol: 'CLSK', name: 'CleanSpark Inc.', nameFa: 'کلین‌اسپارک (استخراج سبز و پربازده بیت‌کوین)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/CLSK.png', currentPrice: 12.40, unit: '$', change24h: 4.9 },
  HOOD: { symbol: 'HOOD', name: 'Robinhood Markets', nameFa: 'رابین‌هود (کارگزاری معامله سهام و رمزارز)', category: 'stock', marketName: 'NASDAQ', icon: 'https://companiesmarketcap.com/img/company-logos/64/HOOD.png', currentPrice: 27.30, unit: '$', change24h: 3.3 },
  RDDT: { symbol: 'RDDT', name: 'Reddit Inc.', nameFa: 'ردیت (انجمن وب و مرجع داده‌های آموزش AI)', category: 'stock', marketName: 'NYSE', icon: 'https://companiesmarketcap.com/img/company-logos/64/RDDT.png', currentPrice: 82.60, unit: '$', change24h: 8.9 },
  SHOP: { symbol: 'SHOP', name: 'Shopify Inc.', nameFa: 'شاپیفای (فروشگاه‌ساز آنلاین جهانی)', category: 'stock', marketName: 'NYSE', icon: 'https://companiesmarketcap.com/img/company-logos/64/SHOP.png', currentPrice: 81.40, unit: '$', change24h: 2.3 },
  SNOW: { symbol: 'SNOW', name: 'Snowflake Inc.', nameFa: 'اسنوفلیک (انبار داده‌های کلاد هوش مصنوعی)', category: 'stock', marketName: 'NYSE', icon: 'https://companiesmarketcap.com/img/company-logos/64/SNOW.png', currentPrice: 118.50, unit: '$', change24h: 1.7 },
  RACE: { symbol: 'RACE', name: 'Ferrari N.V.', nameFa: 'فراری (سوپراسپرت‌های لوکس ایتالیا)', category: 'stock', marketName: 'NYSE', icon: 'https://companiesmarketcap.com/img/company-logos/64/RACE.png', currentPrice: 462.80, unit: '$', change24h: 0.9 },

  // Commodities (MSN Money Watchlist)
  GOLD: { symbol: 'XAU/USD', name: 'Gold Spot', nameFa: 'انس طلای جهانی (Gold XAU/USD)', category: 'commodity', marketName: 'Commodities', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 2735.40, unit: '$', change24h: 0.75 },
  SILVER: { symbol: 'XAG/USD', name: 'Silver Spot', nameFa: 'انس نقره جهانی (Silver XAG/USD)', category: 'commodity', marketName: 'Commodities', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583434.png', currentPrice: 33.85, unit: '$', change24h: 1.40 },
  COPPER: { symbol: 'HG=F', name: 'Copper Futures (Dr. Copper)', nameFa: 'مس صنعتی جهانی (دکتر مس - دماسنج اقتصاد)', category: 'commodity', marketName: 'COMEX', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583434.png', currentPrice: 4.42, unit: '$', change24h: 1.15 },
  NATGAS: { symbol: 'NG=F', name: 'Natural Gas Futures', nameFa: 'گاز طبیعی هنری هاب (Henry Hub)', category: 'commodity', marketName: 'NYMEX', icon: 'https://cdn-icons-png.flaticon.com/512/2933/2933884.png', currentPrice: 2.85, unit: '$', change24h: -2.40 },
  PLATINUM: { symbol: 'PL=F', name: 'Platinum Spot (XPT/USD)', nameFa: 'پلاتین جهانی (فلز فوق‌لوکس صنعتی)', category: 'commodity', marketName: 'NYMEX', icon: 'https://cdn-icons-png.flaticon.com/512/2583/2583344.png', currentPrice: 1025.50, unit: '$', change24h: 0.90 },
  URANIUM: { symbol: 'URNM', name: 'Sprott Uranium Miners ETF', nameFa: 'صندوق اورانیوم و سوخت هسته‌ای هوش مصنوعی', category: 'commodity', marketName: 'NYSE', icon: 'https://cdn-icons-png.flaticon.com/512/2933/2933884.png', currentPrice: 52.80, unit: '$', change24h: 3.20 },
  OIL_WTI: { symbol: 'WTI', name: 'Crude Oil (WTI)', nameFa: 'نفت خام تگزاس (WTI Oil)', category: 'commodity', marketName: 'NYMEX', icon: 'https://cdn-icons-png.flaticon.com/512/2933/2933884.png', currentPrice: 71.20, unit: '$', change24h: -1.20 },
  OIL_BRENT: { symbol: 'BRENT', name: 'Brent Crude Oil', nameFa: 'نفت برنت دریای شمال', category: 'commodity', marketName: 'ICE', icon: 'https://cdn-icons-png.flaticon.com/512/2933/2933884.png', currentPrice: 75.40, unit: '$', change24h: -0.90 },

  // Global Indices (MSN Money Benchmarks)
  VIX: { symbol: '^VIX', name: 'CBOE Volatility Index (VIX)', nameFa: 'شاخص نوسان و ترس وال‌استریت (VIX)', category: 'index', marketName: 'CBOE', icon: 'https://cdn-icons-png.flaticon.com/512/4222/4222002.png', currentPrice: 18.50, unit: 'pts', change24h: -4.20 },
  RUT: { symbol: '^RUT', name: 'Russell 2000 Index', nameFa: 'شاخص ۲۰۰۰ شرکت کوچک آمریکا (Russell 2000)', category: 'index', marketName: 'US Indices', icon: 'https://cdn-icons-png.flaticon.com/512/4222/4222002.png', currentPrice: 2250.40, unit: 'pts', change24h: 1.15 },
  DAX: { symbol: '^GDAXI', name: 'DAX 40 Germany', nameFa: 'شاخص ۴۰ غول صنعتی بورس آلمان (DAX)', category: 'index', marketName: 'Deutsche Börse', icon: 'https://cdn-icons-png.flaticon.com/512/4222/4222002.png', currentPrice: 19450.20, unit: 'pts', change24h: 0.42 },
  NIKKEI: { symbol: '^N225', name: 'Nikkei 225 Japan', nameFa: 'شاخص ۲۲۵ شرکت برتر بورس توکیو ژاپن (Nikkei)', category: 'index', marketName: 'Tokyo Stock Exchange', icon: 'https://cdn-icons-png.flaticon.com/512/4222/4222002.png', currentPrice: 38980.50, unit: 'pts', change24h: 0.85 },
  FTSE: { symbol: '^FTSE', name: 'FTSE 100 UK', nameFa: 'شاخص ۱۰۰ شرکت برتر بورس لندن انگلستان (FTSE)', category: 'index', marketName: 'London Stock Exchange', icon: 'https://cdn-icons-png.flaticon.com/512/4222/4222002.png', currentPrice: 8250.80, unit: 'pts', change24h: 0.28 },
  SP500: { symbol: 'S&P 500', name: 'S&P 500 Index', nameFa: 'شاخص ۵۰۰ شرکت برتر آمریکا (S&P 500)', category: 'index', marketName: 'US Indices', icon: 'https://cdn-icons-png.flaticon.com/512/4222/4222002.png', currentPrice: 5864.67, unit: 'pts', change24h: 0.65 },
  NASDAQ100: { symbol: 'NDX', name: 'NASDAQ 100 Index', nameFa: 'شاخص ۱۰۰ غول فناوری (Nasdaq 100)', category: 'index', marketName: 'NASDAQ', icon: 'https://cdn-icons-png.flaticon.com/512/4222/4222002.png', currentPrice: 18518.61, unit: 'pts', change24h: 0.92 },
  DOWJONES: { symbol: 'DJI', name: 'Dow Jones Industrial', nameFa: 'شاخص صنعتی داوجونز (Dow Jones)', category: 'index', marketName: 'NYSE', icon: 'https://cdn-icons-png.flaticon.com/512/4222/4222002.png', currentPrice: 42931.60, unit: 'pts', change24h: 0.35 },
  DXY: { symbol: 'DXY', name: 'US Dollar Index', nameFa: 'شاخص قدرت جهانی دلار (DXY)', category: 'index', marketName: 'ICE', icon: 'https://cdn-icons-png.flaticon.com/512/217/217853.png', currentPrice: 104.15, unit: 'pts', change24h: 0.18 },
};

// === 3. 10 WORLD LANGUAGES ===
interface LanguageInfo {
  code: string;
  name: string;
  nameEn: string;
  flag: string;
  dir: 'rtl' | 'ltr';
}

const SUPPORTED_LANGUAGES: LanguageInfo[] = [
  { code: 'fa', name: 'فارسی (Persian)', nameEn: 'Persian', flag: '🇮🇷', dir: 'rtl' },
  { code: 'en', name: 'English (انگلیسی)', nameEn: 'English', flag: '🇺🇸', dir: 'ltr' },
  { code: 'de', name: 'Deutsch (آلمانی)', nameEn: 'German', flag: '🇩🇪', dir: 'ltr' },
  { code: 'fr', name: 'Français (فرانسوی)', nameEn: 'French', flag: '🇫🇷', dir: 'ltr' },
  { code: 'es', name: 'Español (اسپانیایی)', nameEn: 'Spanish', flag: '🇪🇸', dir: 'ltr' },
  { code: 'zh', name: '中文 (چینی)', nameEn: 'Chinese', flag: '🇨🇳', dir: 'ltr' },
  { code: 'ko', name: '한국어 (کره‌ای)', nameEn: 'Korean', flag: '🇰🇷', dir: 'ltr' },
  { code: 'ku', name: 'کوردی سۆرانی (Kurdish)', nameEn: 'Kurdish Sorani', flag: '☀️', dir: 'rtl' },
  { code: 'ar', name: 'العربية (عربی)', nameEn: 'Arabic', flag: '🇸🇦', dir: 'rtl' },
  { code: 'tr', name: 'Türkçe (ترکی)', nameEn: 'Turkish', flag: '🇹🇷', dir: 'ltr' },
];

const INITIAL_RULES: AlertRule[] = [
  {
    uuid: 'rule-btc-crypto',
    marketType: 'crypto',
    exchangeId: 'binance',
    exchangeName: 'Binance (بایننس)',
    baseCurrency: 'BTC',
    counterCurrency: 'USDT',
    marketSymbol: 'BTC/USDT',
    assetCategory: 'crypto',
    checkIntervalSeconds: 30,
    conditionType: 'PERCENT_CHANGE',
    direction: 'BOTH',
    targetValue: 2.5,
    basePrice: 83770.00,
    lastCheckedPrice: 83770.00,
    isActive: true,
    isTriggered: false,
    soundEnabled: true,
    vibrationEnabled: true,
    ttsEnabled: true,
    triggerCount: 2,
    lastCheckedAt: new Date(Date.now() - 10000),
    createdAt: new Date(Date.now() - 3600000),
  },
  {
    uuid: 'rule-us10y-macro',
    marketType: 'stocks_macro',
    exchangeId: 'us_treasury',
    exchangeName: 'US Treasury (خزانه‌داری آمریکا)',
    baseCurrency: 'US10Y',
    counterCurrency: '%',
    marketSymbol: 'US10Y (اوراق ۱۰ ساله)',
    assetCategory: 'bond',
    checkIntervalSeconds: 60,
    conditionType: 'PERCENT_CHANGE',
    direction: 'BOTH',
    targetValue: 1.0,
    basePrice: 4.28,
    lastCheckedPrice: 4.28,
    isActive: true,
    isTriggered: false,
    soundEnabled: true,
    vibrationEnabled: false,
    ttsEnabled: true,
    triggerCount: 1,
    lastCheckedAt: new Date(Date.now() - 18000),
    createdAt: new Date(Date.now() - 5400000),
  },
  {
    uuid: 'rule-gold-macro',
    marketType: 'stocks_macro',
    exchangeId: 'commodities',
    exchangeName: 'GL-ST',
    baseCurrency: 'GOLD',
    counterCurrency: 'USD',
    marketSymbol: 'XAU/USD (طلا)',
    assetCategory: 'commodity',
    checkIntervalSeconds: 30,
    conditionType: 'PERCENT_CHANGE',
    direction: 'BOTH',
    targetValue: 0.5,
    basePrice: 2735.40,
    lastCheckedPrice: 2735.40,
    isActive: true,
    isTriggered: false,
    soundEnabled: false,
    vibrationEnabled: true,
    ttsEnabled: false,
    triggerCount: 1,
    lastCheckedAt: new Date(Date.now() - 25000),
    createdAt: new Date(Date.now() - 7200000),
  },
];

export default function App() {
  // TAB NAVIGATION: ALERTS IS IN THE MIDDLE (INDEX 1) AND IS THE DEFAULT
  const [mobileScreen, setMobileScreen] = useState<'history' | 'alerts' | 'settings'>('alerts');
  
  // Persistent Offline-First Alert Rules Cache
  const [rules, setRules] = useState<AlertRule[]>(() => {
    try {
      const saved = localStorage.getItem('alarmer_rules');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (_) {}
    return INITIAL_RULES;
  });

  useEffect(() => {
    try {
      localStorage.setItem('alarmer_rules', JSON.stringify(rules));
    } catch (_) {}
  }, [rules]);

  // Persistent Offline-First Crypto Prices Cache
  const [cryptoPrices, setCryptoPrices] = useState<Record<string, CryptoCoinMeta>>(() => {
    try {
      const saved = localStorage.getItem('alarmer_crypto_prices');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') return { ...CRYPTO_COIN_METAS, ...parsed };
      }
    } catch (_) {}
    return CRYPTO_COIN_METAS;
  });

  // Persistent Offline-First Macro Prices Cache
  const [macroPrices, setMacroPrices] = useState<Record<string, MacroAssetMeta>>(() => {
    try {
      const saved = localStorage.getItem('alarmer_macro_prices');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') return { ...MACRO_ASSETS, ...parsed };
      }
    } catch (_) {}
    return MACRO_ASSETS;
  });
  
  // Theme & Language
  const [appTheme, setAppTheme] = useState<ThemeModeType>('dark-green');
  const [currentLang, setCurrentLang] = useState<string>('fa');
  const [showLanguageModal, setShowLanguageModal] = useState<boolean>(false);
  const tAuthTg = getLoginTelegramI18n(currentLang);

  // GLOBAL TIMER FEATURE (Overrides individual rule timers when active)
  const [globalTimerEnabled, setGlobalTimerEnabled] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('alarmer_global_timer_enabled');
      if (saved !== null) return JSON.parse(saved);
    } catch (_) {}
    return false;
  });

  const [globalTimerSeconds, setGlobalTimerSeconds] = useState<number>(() => {
    try {
      const saved = localStorage.getItem('alarmer_global_timer_seconds');
      if (saved !== null) return parseInt(saved, 10);
    } catch (_) {}
    return 30;
  });

  const [selectedRingtone, setSelectedRingtone] = useState<string>(() => {
    try {
      const saved = localStorage.getItem('alarmer_selected_ringtone');
      if (saved) return saved;
    } catch (_) {}
    return 'alarm_siren';
  });

  const [telegramChatId, setTelegramChatId] = useState<string>(() => {
    try {
      return localStorage.getItem('alarmer_telegram_chat_id') || '@Mehran_Test_Chat';
    } catch (_) {
      return '@Mehran_Test_Chat';
    }
  });
  const [isTestingTelegram, setIsTestingTelegram] = useState<boolean>(false);

  useEffect(() => {
    try {
      localStorage.setItem('alarmer_global_timer_enabled', JSON.stringify(globalTimerEnabled));
    } catch (_) {}
  }, [globalTimerEnabled]);

  useEffect(() => {
    try {
      localStorage.setItem('alarmer_global_timer_seconds', globalTimerSeconds.toString());
    } catch (_) {}
  }, [globalTimerSeconds]);

  useEffect(() => {
    try {
      localStorage.setItem('alarmer_selected_ringtone', selectedRingtone);
    } catch (_) {}
  }, [selectedRingtone]);

  useEffect(() => {
    try {
      localStorage.setItem('alarmer_telegram_chat_id', telegramChatId);
    } catch (_) {}
  }, [telegramChatId]);

  // 3 MASTER GLOBAL SETTINGS (ویبره / صدا / Voice Speech)
  const [globalSoundEnabled, setGlobalSoundEnabled] = useState<boolean>(true);
  const [globalVibrationEnabled, setGlobalVibrationEnabled] = useState<boolean>(true);
  const [globalTtsEnabled, setGlobalTtsEnabled] = useState<boolean>(true);

  // Sequential Notification & Speech Queue (No overlaps, full voice reading)
  const notificationQueueRef = useRef<QueuedNotification[]>([]);
  const isProcessingQueueRef = useRef<boolean>(false);
  const [activeQueueNotification, setActiveQueueNotification] = useState<QueuedNotification | null>(null);
  const [queuedCount, setQueuedCount] = useState<number>(0);

  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [checkingRuleId, setCheckingRuleId] = useState<string | null>(null);

  // Backup & Restore Modals
  const [showRestoreModal, setShowRestoreModal] = useState<boolean>(false);
  const [restoreJsonInput, setRestoreJsonInput] = useState<string>('');

  // First Launch Language Selection Modal (Opens on first launch if not yet completed)
  const [showFirstLaunchLangModal, setShowFirstLaunchLangModal] = useState<boolean>(() => {
    return !localStorage.getItem('alarmer_lang_setup_done');
  });

  // Optional Google Account Profile & Authentication
  const [googleUser, setGoogleUser] = useState<{ email: string; name: string; isPremium: boolean } | null>(() => {
    const saved = localStorage.getItem('alarmer_google_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [showGoogleModal, setShowGoogleModal] = useState<boolean>(false);

  // === DUAL-MODE CREATE ALERT MODAL ===
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [createPath, setCreatePath] = useState<'NONE' | 'CRYPTO' | 'STOCKS_MACRO'>('NONE');
  
  // Crypto Flow: Exchange Chips + Search + 40+ Exchanges + Pairs Sync + Frequency + Both-Sides Condition
  const [cryptoStep, setCryptoStep] = useState<1 | 2 | 3>(1);
  const [exchangeCategoryFilter, setExchangeCategoryFilter] = useState<ExchangeCategoryType>('all');
  const [selectedExchange, setSelectedExchange] = useState<ExchangeInfo>(ALL_EXCHANGES.find(e => e.id === 'nobitex') || ALL_EXCHANGES[0]);
  const [selectedCounterCurrency, setSelectedCounterCurrency] = useState<string>('TMN');
  
  // Real-Time Iranian Exchange Toman Rates & Domestic Orderbook Cache
  const [usdtTomanRate, setUsdtTomanRate] = useState<number>(() => {
    try {
      const saved = localStorage.getItem('alarmer_usdt_tmn_rate');
      if (saved) {
        const val = parseFloat(saved);
        if (val > 10000) return val;
      }
    } catch (_) {}
    return 267000;
  });

  // Dedicated per-exchange live prices map so Nobitex, Wallex, etc. never overwrite each other
  const [exchangeSpecificPrices, setExchangeSpecificPrices] = useState<Record<string, Record<string, { priceTmn: number; priceUsdt: number; change24h: number; high24hTmn?: number; low24hTmn?: number }>>>({});

  const [iranianMarketPrices, setIranianMarketPrices] = useState<Record<string, { priceTmn: number; priceUsdt: number; change24h: number; high24hTmn?: number; low24hTmn?: number }>>(() => {
    try {
      const saved = localStorage.getItem('alarmer_iranian_prices');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') return parsed;
      }
    } catch (_) {}
    return {};
  });
  const [exchangeSearchQuery, setExchangeSearchQuery] = useState<string>('');
  const [cryptoSearchQuery, setCryptoSearchQuery] = useState<string>('');
  const [selectedCryptoCoin, setSelectedCryptoCoin] = useState<string>('BTC');
  const [isSyncingPairs, setIsSyncingPairs] = useState<boolean>(false);

  // Stocks / Forex / US 10Y Bond Flow
  const [macroStep, setMacroStep] = useState<1 | 2>(1);
  const [macroCategoryFilter, setMacroCategoryFilter] = useState<'all' | 'bond' | 'forex' | 'stock' | 'commodity' | 'index' | 'iran_market'>('all');
  const [macroSearchQuery, setMacroSearchQuery] = useState<string>('');
  const [selectedMacroKey, setSelectedMacroKey] = useState<string>('GOLD18_BONBAST');
  const [bonbastLive, setBonbastLive] = useState<any>(null);
  const [bonbastLastSync, setBonbastLastSync] = useState<Date | null>(null);

  // Common Frequency & Condition inputs
  const [unitType, setUnitType] = useState<'seconds' | 'minutes' | 'hours'>('minutes');
  const [unitNumber, setUnitNumber] = useState<string>('1');
  const [conditionType, setConditionType] = useState<'PERCENT_CHANGE' | 'PRICE_THRESHOLD' | 'VOLUME_SURGE'>('PERCENT_CHANGE');
  const [direction, setDirection] = useState<'BOTH' | 'ABOVE' | 'BELOW'>('BOTH');
  const [bothWayBehavior, setBothWayBehavior] = useState<'OCO' | 'DUAL_ACTIVE'>('OCO');
  const [targetValueStr, setTargetValueStr] = useState<string>('2.0');
  const [volumePercentStr, setVolumePercentStr] = useState<string>('100');
  const [upperPriceStr, setUpperPriceStr] = useState<string>('4.00');
  const [upperNote, setUpperNote] = useState<string>('«رسید به مقاومت، بررسی کن»');
  const [lowerPriceStr, setLowerPriceStr] = useState<string>('2.00');
  const [lowerNote, setLowerNote] = useState<string>('«حمایت شکست، بفروش»');
  const [ruleSoundEnabled, setRuleSoundEnabled] = useState<boolean>(true);
  const [ruleVibrationEnabled, setRuleVibrationEnabled] = useState<boolean>(true);
  const [ttsEnabled, setTtsEnabled] = useState<boolean>(true);
  const [showHomeWidgetModal, setShowHomeWidgetModal] = useState<boolean>(false);
  const [showDebugJsonViewer, setShowDebugJsonViewer] = useState<boolean>(false);
  const [debugJsonSearchQuery, setDebugJsonSearchQuery] = useState<string>('');

  const getWallStreetMacroJson = () => {
    return Object.entries(macroPrices).map(([key, asset]) => ({
      id: key,
      symbol: asset.symbol,
      nameEn: asset.name,
      nameFa: asset.nameFa,
      category: asset.category,
      marketName: asset.marketName,
      currentPrice: asset.currentPrice,
      unit: asset.unit,
      change24h: asset.change24h,
      icon: asset.icon
    }));
  };

  const handleDownloadMacroJson = () => {
    const dataList = getWallStreetMacroJson();
    const exportData = {
      title: "Alarmer Wall Street & Macroeconomics Symbols Export",
      exportedAt: new Date().toISOString(),
      totalSymbols: dataList.length,
      symbols: dataList
    };
    const jsonStr = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `wallstreet_macro_symbols_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(currentLang === 'fa' ? '📥 فایل لیست نمادهای وال استریت و اقتصاد کلان (JSON) دانلود شد.' : '📥 Downloaded Wall Street & Macro JSON file.');
  };

  const handleCopyMacroJson = () => {
    const dataList = getWallStreetMacroJson();
    const jsonStr = JSON.stringify(dataList, null, 2);
    navigator.clipboard.writeText(jsonStr).then(() => {
      showToast(currentLang === 'fa' ? '📋 کد JSON تمامی نمادها در حافظه کپی شد.' : '📋 Copied symbols JSON to clipboard.');
    }).catch(() => {
      showToast('خطا در کپی کدهای JSON');
    });
  };

  // Notifications
  const [notifications, setNotifications] = useState<NotificationItem[]>([
    {
      id: 'notif-1',
      title: '🟢 BTC/USDT +3.52% $83,770.00 ▲',
      body: '📝 Target reached on Binance',
      timestamp: new Date(Date.now() - 90000),
      ruleUuid: 'rule-btc-crypto',
      marketSymbol: 'BTC/USDT',
      value: '$83,770',
      exchange: 'Binance',
    },
    {
      id: 'notif-2',
      title: '🔴 ETH/USDT -3.52% $3,120.00 ▼',
      body: '',
      timestamp: new Date(Date.now() - 180000),
      ruleUuid: 'rule-eth-crypto',
      marketSymbol: 'ETH/USDT',
      value: '$3,120',
      exchange: 'Binance',
    }
  ]);

  const audioContextRef = useRef<AudioContext | null>(null);

  // Persistent Last Known Authentic Prices Map (Prevents 50%+ offline price drop / drift)
  const [lastKnownCoinPrices, setLastKnownCoinPrices] = useState<Record<string, { priceTmn: number; priceUsd: number; high24h?: number; low24h?: number }>>(() => {
    try {
      const saved = localStorage.getItem('alarmer_last_known_prices');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') return parsed;
      }
    } catch (_) {}
    return {};
  });

  const updateLastKnownCoinPrice = (coin: string, tmn: number, usd: number, high?: number, low?: number) => {
    const cUpper = coin.toUpperCase();
    setLastKnownCoinPrices((prev) => {
      const next = {
        ...prev,
        [cUpper]: {
          priceTmn: tmn > 0 ? tmn : (prev[cUpper]?.priceTmn || 0),
          priceUsd: usd > 0 ? usd : (prev[cUpper]?.priceUsd || 0),
          high24h: high || prev[cUpper]?.high24h,
          low24h: low || prev[cUpper]?.low24h,
        }
      };
      try {
        localStorage.setItem('alarmer_last_known_prices', JSON.stringify(next));
      } catch (_) {}
      return next;
    });
  };

  // Helper to resolve live market price, unit and 24h stats for any exchange pair with 100% offline safety
  const getCryptoMarketPrice = (coin: string, exchangeId: string, counterCurrency: string) => {
    const exId = (exchangeId || '').toLowerCase();
    const isNobitex = exId.includes('nobitex');
    const isBonbast = exId.includes('bonbast');
    const isIranianExchange = isNobitex || isBonbast || ['wallex', 'tabdeal', 'bitbarg', 'abantether', 'ramzinex', 'tetherland', 'sarmayex'].includes(exId);
    // For Nobitex or Bonbast, ALWAYS display in Toman across all stages as requested!
    const isTmn = isNobitex || isBonbast || counterCurrency === 'TMN' || counterCurrency === 'IRT' || counterCurrency === 'تومان' || counterCurrency === 'ت';
    const cUpper = coin.toUpperCase();
    const exPrices = exchangeSpecificPrices[exId] || (isNobitex ? exchangeSpecificPrices['nobitex'] : undefined) || (isBonbast ? exchangeSpecificPrices['bonbast'] : undefined);
    const exData = exPrices ? exPrices[cUpper] : undefined;
    const irData = exData || iranianMarketPrices[cUpper];
    const binanceMeta = cryptoPrices[cUpper];
    let rate = usdtTomanRate > 10000 ? usdtTomanRate : 268200;
    while (rate > 150000) rate = Math.round(rate / 10.0);
    const lastKnown = lastKnownCoinPrices[cUpper];

    // Priority Fix: USDT in Nobitex / Iranian exchanges / Toman counter currency
    // Always returns the genuine live Toman rate (e.g. 268,398 تومان) and unit تومان!
    if (cUpper === 'USDT' && (isNobitex || isBonbast || isTmn)) {
      let usdtPrice = (exData && exData.priceTmn > 0)
        ? exData.priceTmn
        : (irData && irData.priceTmn > 0 ? irData.priceTmn : rate);
      while (usdtPrice > 150000) usdtPrice = Math.round(usdtPrice / 10.0);
      let h = exData?.high24hTmn || Math.round(usdtPrice * 1.01);
      let l = exData?.low24hTmn || Math.round(usdtPrice * 0.99);
      while (h > 150000) h = Math.round(h / 10.0);
      while (l > 150000) l = Math.round(l / 10.0);
      const ch = exData?.change24h || irData?.change24h || 0.5;
      return {
        price: usdtPrice,
        unit: 'تومان',
        high24h: h,
        low24h: l,
        change24h: ch,
      };
    }

    // Special case for Global Exchanges only: USDT counter USDT/USD
    if (cUpper === 'USDT' && !isIranianExchange && (counterCurrency === 'USDT' || counterCurrency === 'USD')) {
      return {
        price: 1.0,
        unit: '$',
        high24h: 1.0,
        low24h: 1.0,
        change24h: 0,
      };
    }

    // 1. Iranian Exchange with TMN / IRT Counter Currency
    if (isIranianExchange && isTmn) {
      if (irData && irData.priceTmn > 0) {
        const finalTmn = irData.priceTmn;
        const h = irData.high24hTmn || Math.round(finalTmn * 1.025);
        const l = irData.low24hTmn || Math.round(finalTmn * 0.975);
        return {
          price: finalTmn,
          unit: 'تومان',
          high24h: h,
          low24h: l,
          change24h: irData.change24h,
        };
      }
      
      if (binanceMeta && binanceMeta.currentPrice > 0) {
        const tmnP = cUpper === 'USDT' ? rate : Math.round(binanceMeta.currentPrice * rate);
        const h = cUpper === 'USDT' ? Math.round(rate * 1.01) : Math.round((binanceMeta.high24h || binanceMeta.currentPrice * 1.025) * rate);
        const l = cUpper === 'USDT' ? Math.round(rate * 0.99) : Math.round((binanceMeta.low24h || binanceMeta.currentPrice * 0.975) * rate);
        return {
          price: tmnP,
          unit: 'تومان',
          high24h: h,
          low24h: l,
          change24h: binanceMeta.change24h,
        };
      }

      if (lastKnown && lastKnown.priceTmn > 0) {
        return {
          price: lastKnown.priceTmn,
          unit: 'تومان',
          high24h: lastKnown.high24h || Math.round(lastKnown.priceTmn * 1.025),
          low24h: lastKnown.low24h || Math.round(lastKnown.priceTmn * 0.975),
          change24h: 0,
        };
      }

      // Safe default without jumping to BTC
      const safeUsd = lastKnown?.priceUsd || (cUpper === 'USDT' ? 1.0 : 1.0);
      return {
        price: Math.round(safeUsd * rate),
        unit: 'تومان',
        high24h: Math.round(safeUsd * rate * 1.025),
        low24h: Math.round(safeUsd * rate * 0.975),
        change24h: 0,
      };
    }

    // 2. Iranian Exchange with USDT Counter Currency
    if (isIranianExchange && (counterCurrency === 'USDT' || counterCurrency === 'USD')) {
      if (irData && irData.priceUsdt > 0) {
        return {
          price: irData.priceUsdt,
          unit: '$',
          high24h: binanceMeta?.high24h || irData.priceUsdt * 1.025,
          low24h: binanceMeta?.low24h || irData.priceUsdt * 0.975,
          change24h: irData.change24h || (binanceMeta?.change24h ?? 0),
        };
      }
      if (irData && irData.priceTmn > 0 && rate > 1000) {
        const uPrice = Number((irData.priceTmn / rate).toFixed(irData.priceTmn / rate < 1 ? 6 : 2));
        return {
          price: uPrice,
          unit: '$',
          high24h: uPrice * 1.025,
          low24h: uPrice * 0.975,
          change24h: irData.change24h,
        };
      }
      if (binanceMeta && binanceMeta.currentPrice > 0) {
        return {
          price: binanceMeta.currentPrice,
          unit: '$',
          high24h: binanceMeta.high24h,
          low24h: binanceMeta.low24h,
          change24h: binanceMeta.change24h,
        };
      }
      if (lastKnown && lastKnown.priceUsd > 0) {
        return {
          price: lastKnown.priceUsd,
          unit: '$',
          high24h: lastKnown.high24h || lastKnown.priceUsd * 1.025,
          low24h: lastKnown.low24h || lastKnown.priceUsd * 0.975,
          change24h: 0,
        };
      }
    }

    // 3. Global Crypto Exchanges (Binance, OKX, KuCoin, etc.)
    if (binanceMeta && binanceMeta.currentPrice > 0) {
      return {
        price: binanceMeta.currentPrice,
        unit: counterCurrency === 'USD' || counterCurrency === 'USDT' ? '$' : counterCurrency,
        high24h: binanceMeta.high24h,
        low24h: binanceMeta.low24h,
        change24h: binanceMeta.change24h,
      };
    }

    if (lastKnown && lastKnown.priceUsd > 0) {
      return {
        price: lastKnown.priceUsd,
        unit: counterCurrency === 'USD' || counterCurrency === 'USDT' ? '$' : counterCurrency,
        high24h: lastKnown.high24h || lastKnown.priceUsd * 1.025,
        low24h: lastKnown.low24h || lastKnown.priceUsd * 0.975,
        change24h: 0,
      };
    }

    return {
      price: (cryptoPrices[cUpper] || cryptoPrices.BTC).currentPrice,
      unit: counterCurrency === 'USD' || counterCurrency === 'USDT' ? '$' : counterCurrency,
      high24h: (cryptoPrices[cUpper] || cryptoPrices.BTC).high24h,
      low24h: (cryptoPrices[cUpper] || cryptoPrices.BTC).low24h,
      change24h: (cryptoPrices[cUpper] || cryptoPrices.BTC).change24h,
    };
  };

  // Live Crypto Prices Sync (Global Binance + Domestic Iranian Wallex, Nobitex, Ramzinex, TetherLand, Bitbarg)
  useEffect(() => {
    const fetchLivePrices = async () => {
      // 1. Fetch Global Binance Tickers
      try {
        const res = await fetch('https://api.binance.com/api/v3/ticker/24hr');
        if (res.ok) {
          const tickers: any[] = await res.json();
          const priceMap: Record<string, { price: number; change: number; high: number; low: number; volume: number }> = {};

          tickers.forEach((t) => {
            if (t.symbol.endsWith('USDT')) {
              const sym = t.symbol.replace('USDT', '');
              priceMap[sym] = {
                price: parseFloat(t.lastPrice),
                change: parseFloat(t.priceChangePercent),
                high: parseFloat(t.highPrice),
                low: parseFloat(t.lowPrice),
                volume: parseFloat(t.quoteVolume),
              };
            }
          });

          setCryptoPrices((prev) => {
            const updated = { ...prev };
            Object.keys(priceMap).forEach((key) => {
              if (updated[key]) {
                updated[key] = {
                  ...updated[key],
                  currentPrice: priceMap[key].price,
                  change24h: priceMap[key].change,
                  high24h: priceMap[key].high || updated[key].high24h,
                  low24h: priceMap[key].low || updated[key].low24h,
                  volume24h: priceMap[key].volume || updated[key].volume24h,
                };
              } else if (['WIF', 'HMSTR', 'CATI', 'DOGS', 'TURBO', 'AAVE', 'UNI', 'ICP', 'XLM', 'TAO', 'ETC', 'XMR', 'HBAR', 'FIL', 'INJ', 'SEI'].includes(key)) {
                updated[key] = {
                  name: key,
                  nameFa: key,
                  icon: 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png',
                  currentPrice: priceMap[key].price,
                  change24h: priceMap[key].change,
                  high24h: priceMap[key].high,
                  low24h: priceMap[key].low,
                  volume24h: priceMap[key].volume,
                };
              }
              updateLastKnownCoinPrice(key, Math.round(priceMap[key].price * (usdtTomanRate > 10000 ? usdtTomanRate : 267000)), priceMap[key].price, priceMap[key].high, priceMap[key].low);
            });
            try {
              localStorage.setItem('alarmer_crypto_prices', JSON.stringify(updated));
            } catch (_) {}
            return updated;
          });
        }
      } catch (_) {}

      // 0. BONBAST.COM - PRIMARY REFERENCE FOR IRAN FREE MARKET (CURRENCIES & GOLD IN TOMAN)
      try {
        const bbRes = await fetch('/api/bonbast');
        if (bbRes.ok) {
          const bbData = await bbRes.json();
          if (bbData && (bbData.usd1 || bbData.gol18 || bbData.mithqal)) {
            setBonbastLive(bbData);
            setBonbastLastSync(new Date());
            const bbUsd = parseFloat(bbData.usd1 || '0');
            if (bbUsd > 10000) {
              setUsdtTomanRate(bbUsd);
              try {
                localStorage.setItem('alarmer_usdt_tmn_rate', bbUsd.toString());
              } catch (_) {}
            }

            // Sync Bonbast to Macro Assets in Toman
            setMacroPrices((prev) => {
              const updated = { ...prev };
              if (bbData.usd1 && updated['USD_BONBAST']) {
                updated['USD_BONBAST'] = { ...updated['USD_BONBAST'], currentPrice: parseFloat(bbData.usd1) };
              }
              if (bbData.eur1 && updated['EUR_BONBAST']) {
                updated['EUR_BONBAST'] = { ...updated['EUR_BONBAST'], currentPrice: parseFloat(bbData.eur1) };
              }
              if (bbData.aed1 && updated['AED_BONBAST']) {
                updated['AED_BONBAST'] = { ...updated['AED_BONBAST'], currentPrice: parseFloat(bbData.aed1) };
              }
              if (bbData.gbp1 && updated['GBP_BONBAST']) {
                updated['GBP_BONBAST'] = { ...updated['GBP_BONBAST'], currentPrice: parseFloat(bbData.gbp1) };
              }
              if (bbData.try1 && updated['TRY_BONBAST']) {
                updated['TRY_BONBAST'] = { ...updated['TRY_BONBAST'], currentPrice: parseFloat(bbData.try1) };
              }
              if (bbData.gol18 && updated['GOLD18_BONBAST']) {
                updated['GOLD18_BONBAST'] = { ...updated['GOLD18_BONBAST'], currentPrice: parseFloat(bbData.gol18) };
              }
              if (bbData.mithqal && updated['MITHQAL_BONBAST']) {
                updated['MITHQAL_BONBAST'] = { ...updated['MITHQAL_BONBAST'], currentPrice: parseFloat(bbData.mithqal) };
              }
              if (bbData.emami1 && updated['EMAMI_BONBAST']) {
                updated['EMAMI_BONBAST'] = { ...updated['EMAMI_BONBAST'], currentPrice: parseFloat(bbData.emami1) };
              }
              if (bbData.azadi1 && updated['BAHAR_BONBAST']) {
                updated['BAHAR_BONBAST'] = { ...updated['BAHAR_BONBAST'], currentPrice: parseFloat(bbData.azadi1) };
              }
              if (bbData.azadi1_2 && updated['HALF_BONBAST']) {
                updated['HALF_BONBAST'] = { ...updated['HALF_BONBAST'], currentPrice: parseFloat(bbData.azadi1_2) };
              }
              if (bbData.azadi1_4 && updated['QUARTER_BONBAST']) {
                updated['QUARTER_BONBAST'] = { ...updated['QUARTER_BONBAST'], currentPrice: parseFloat(bbData.azadi1_4) };
              }
              if (bbData.azadi1g && updated['GRAM_BONBAST']) {
                updated['GRAM_BONBAST'] = { ...updated['GRAM_BONBAST'], currentPrice: parseFloat(bbData.azadi1g) };
              }
              if (bbData.iqd1 && updated['IQD_BONBAST']) {
                updated['IQD_BONBAST'] = { ...updated['IQD_BONBAST'], currentPrice: parseFloat(bbData.iqd1) };
              }
              if (bbData.usd1 && updated['USDT_TMN']) {
                updated['USDT_TMN'] = { ...updated['USDT_TMN'], currentPrice: parseFloat(bbData.usd1) };
              }
              try {
                localStorage.setItem('alarmer_macro_prices', JSON.stringify(updated));
              } catch (_) {}
              return updated;
            });

            // Map Bonbast rates to exchangeSpecificPrices['bonbast']
            const bonbastPrices: Record<string, { priceTmn: number; priceUsdt: number; change24h: number }> = {};
            const curRate = bbUsd > 10000 ? bbUsd : 267900;
            const bonbastKeyMap: Record<string, string> = {
              'USDT': bbData.usd1,
              'USD': bbData.usd1,
              'EUR': bbData.eur1,
              'GBP': bbData.gbp1,
              'AED': bbData.aed1,
              'TRY': bbData.try1,
              'CAD': bbData.cad1,
              'AUD': bbData.aud1,
              'CHF': bbData.chf1,
              'CNY': bbData.cny1,
              'GOLD18': bbData.gol18,
              'MITHQAL': bbData.mithqal,
              'COIN_EMAMI': bbData.emami1,
              'COIN_BAHAR': bbData.azadi1,
              'COIN_HALF': bbData.azadi1_2,
              'COIN_QUARTER': bbData.azadi1_4,
              'COIN_GRAM': bbData.azadi1g,
              'IQD': bbData.iqd1,
              'KWD': bbData.kwd1,
              'SAR': bbData.sar1,
              'QAR': bbData.qar1,
              'OMR': bbData.omr1,
              'BHD': bbData.bhd1,
              'AFN': bbData.afn1,
              'RUB': bbData.rub1,
              'INR': bbData.inr1,
              'JPY': bbData.jpy1,
            };
            Object.keys(bonbastKeyMap).forEach((sym) => {
              const val = parseFloat(bonbastKeyMap[sym] || '0');
              if (val > 0) {
                bonbastPrices[sym] = { priceTmn: val, priceUsdt: val / curRate, change24h: 0.5 };
                updateLastKnownCoinPrice(sym, val, val / curRate);
              }
            });
            setExchangeSpecificPrices((prev) => ({
              ...prev,
              bonbast: bonbastPrices,
            }));
          }
        }
      } catch (_) {}

      // 2. Fetch Iranian Exchange Rates (Wallex Live API via proxy - 370+ pairs)
      try {
        const wallexRes = await fetch('/api/wallex/markets');
        if (wallexRes.ok) {
          const wData = await wallexRes.json();
          const symbols = wData?.result?.symbols;
          if (symbols && typeof symbols === 'object') {
            const usdtTmn = parseFloat(symbols['USDTTMN']?.stats?.lastPrice || '0');
            if (usdtTmn > 10000) {
              setUsdtTomanRate(usdtTmn);
              try {
                localStorage.setItem('alarmer_usdt_tmn_rate', usdtTmn.toString());
              } catch (_) {}
            }

            const irPrices: Record<string, { priceTmn: number; priceUsdt: number; change24h: number; high24hTmn?: number; low24hTmn?: number }> = {};
            Object.keys(symbols).forEach((k) => {
              const s = symbols[k];
              const base = s.baseAsset?.toUpperCase();
              const quote = s.quoteAsset?.toUpperCase();
              const lastP = parseFloat(s.stats?.lastPrice || '0');
              const ch = parseFloat(s.stats?.['24h_ch'] || '0');
              const highP = parseFloat(s.stats?.['24h_highPrice'] || '0');
              const lowP = parseFloat(s.stats?.['24h_lowPrice'] || '0');

              if (base && lastP > 0) {
                if (!irPrices[base]) {
                  irPrices[base] = { priceTmn: 0, priceUsdt: 0, change24h: ch };
                }
                if (quote === 'TMN') {
                  irPrices[base].priceTmn = lastP;
                  irPrices[base].high24hTmn = highP;
                  irPrices[base].low24hTmn = lowP;
                  irPrices[base].change24h = ch;
                  updateLastKnownCoinPrice(base, lastP, lastP / (usdtTmn > 10000 ? usdtTmn : 104500), highP, lowP);
                } else if (quote === 'USDT') {
                  irPrices[base].priceUsdt = lastP;
                  updateLastKnownCoinPrice(base, Math.round(lastP * (usdtTmn > 10000 ? usdtTmn : 104500)), lastP);
                }
              }
            });

            setIranianMarketPrices((prev) => {
              const next = { ...prev, ...irPrices };
              try {
                localStorage.setItem('alarmer_iranian_prices', JSON.stringify(next));
              } catch (_) {}
              return next;
            });

            setExchangeSpecificPrices((prev) => ({
              ...prev,
              wallex: irPrices,
            }));
          }
        }
      } catch (_) {}

      // 3. Nobitex Live Stats via proxy (530+ pairs)
      try {
        const nobiRes = await fetch('/api/nobitex/market/stats', { method: 'POST' });
        if (nobiRes.ok) {
          const nobiData = await nobiRes.json();
          const stats = nobiData?.stats;
          if (stats && typeof stats === 'object') {
            const nobiTmnPrices: Record<string, { priceTmn: number; priceUsdt: number; change24h: number; high24hTmn?: number; low24hTmn?: number }> = {};
            const curRate = usdtTomanRate > 10000 ? usdtTomanRate : 267000;

            Object.keys(stats).forEach((k) => {
              const item = stats[k];
              const parts = k.split('-');
              if (parts.length === 2) {
                const base = parts[0].toUpperCase();
                const quote = parts[1].toUpperCase();
                const latest = parseFloat(item.latest || '0');
                const ch = parseFloat(item.dayChange || '0');
                const dayHigh = parseFloat(item.dayHigh || '0');
                const dayLow = parseFloat(item.dayLow || '0');

                if (base && latest > 0) {
                  if (!nobiTmnPrices[base]) {
                    nobiTmnPrices[base] = { priceTmn: 0, priceUsdt: 0, change24h: ch };
                  }
                  if (quote === 'RLS' || quote === 'IRT') {
                    let tmn = quote === 'RLS' ? latest / 10 : latest;
                    let hTmn = dayHigh > 0 ? (quote === 'RLS' ? dayHigh / 10 : dayHigh) : undefined;
                    let lTmn = dayLow > 0 ? (quote === 'RLS' ? dayLow / 10 : dayLow) : undefined;

                    if (base === 'USDT') {
                      while (tmn > 150000) tmn = tmn / 10;
                      if (hTmn) { while (hTmn > 150000) hTmn = hTmn / 10; }
                      if (lTmn) { while (lTmn > 150000) lTmn = lTmn / 10; }
                    }

                    nobiTmnPrices[base].priceTmn = tmn;
                    nobiTmnPrices[base].high24hTmn = hTmn;
                    nobiTmnPrices[base].low24hTmn = lTmn;
                    nobiTmnPrices[base].change24h = ch;

                    if (base === 'USDT') {
                      nobiTmnPrices[base].priceUsdt = 1.0;
                      if (tmn > 10000) {
                        setUsdtTomanRate(tmn);
                        try {
                          localStorage.setItem('alarmer_usdt_tmn_rate', tmn.toString());
                        } catch (_) {}
                      }
                      updateLastKnownCoinPrice('USDT', tmn, 1.0, hTmn, lTmn);
                    } else {
                      updateLastKnownCoinPrice(base, tmn, tmn / curRate, hTmn, lTmn);
                    }
                  } else if (quote === 'USDT') {
                    nobiTmnPrices[base].priceUsdt = latest;
                    updateLastKnownCoinPrice(base, Math.round(latest * curRate), latest);
                  }
                }
              }
            });

            setIranianMarketPrices((prev) => {
              const next = { ...prev, ...nobiTmnPrices };
              try {
                localStorage.setItem('alarmer_iranian_prices', JSON.stringify(next));
              } catch (_) {}
              return next;
            });

            setExchangeSpecificPrices((prev) => ({
              ...prev,
              nobitex: nobiTmnPrices,
            }));
          }
        }
      } catch (_) {}

      // 4. Ramzinex Live Pairs API via proxy (630+ domestic markets)
      try {
        const ramzRes = await fetch('/api/ramzinex/pairs');
        if (ramzRes.ok) {
          const rData = await ramzRes.json();
          const rList = rData?.data;
          if (Array.isArray(rList)) {
            const rPrices: Record<string, { priceTmn: number; priceUsdt: number; change24h: number; high24hTmn?: number; low24hTmn?: number }> = {};
            const curRate = usdtTomanRate > 10000 ? usdtTomanRate : 267000;

            rList.forEach((item) => {
              const base = item?.base_currency_symbol?.en?.toUpperCase();
              const quote = item?.quote_currency_symbol?.en?.toUpperCase();
              const sell = parseFloat(item.sell || '0');
              const close = parseFloat(item.financial?.last24h?.close || '0');
              const p = sell > 0 ? sell : close;
              const ch = parseFloat(item.financial?.last24h?.change_percent || '0');
              const highest = parseFloat(item.financial?.last24h?.highest || '0');
              const lowest = parseFloat(item.financial?.last24h?.lowest || '0');

              if (base && p > 0) {
                if (!rPrices[base]) {
                  rPrices[base] = { priceTmn: 0, priceUsdt: 0, change24h: ch };
                }
                if (quote === 'IRR' || quote === 'RLS') {
                  const tmn = p / 10;
                  rPrices[base].priceTmn = tmn;
                  rPrices[base].high24hTmn = highest > 0 ? highest / 10 : undefined;
                  rPrices[base].low24hTmn = lowest > 0 ? lowest / 10 : undefined;
                  rPrices[base].change24h = ch;
                  if (base === 'USDT') {
                    rPrices[base].priceUsdt = 1.0;
                    updateLastKnownCoinPrice('USDT', tmn, 1.0);
                  } else {
                    updateLastKnownCoinPrice(base, tmn, tmn / curRate);
                  }
                } else if (quote === 'USDT') {
                  rPrices[base].priceUsdt = p;
                  updateLastKnownCoinPrice(base, Math.round(p * curRate), p);
                }
              }
            });

            setIranianMarketPrices((prev) => {
              const next = { ...prev, ...rPrices };
              try {
                localStorage.setItem('alarmer_iranian_prices', JSON.stringify(next));
              } catch (_) {}
              return next;
            });

            setExchangeSpecificPrices((prev) => ({
              ...prev,
              ramzinex: rPrices,
            }));
          }
        }
      } catch (_) {}

      // 5. TetherLand Live USDT Rate
      try {
        const tethRes = await fetch('/api/tetherland/currencies');
        if (tethRes.ok) {
          const tData = await tethRes.json();
          const usdt = tData?.data?.currencies?.USDT;
          const p = parseFloat(usdt?.price || '0');
          if (p > 10000) {
            setUsdtTomanRate(p);
            try {
              localStorage.setItem('alarmer_usdt_tmn_rate', p.toString());
            } catch (_) {}
          }
        }
      } catch (_) {}

      // 6. Bitbarg Live Currencies API (Over-The-Counter Instant Rates)
      try {
        const bitbargRes = await fetch('/api/bitbarg/currencies?page=1&page_size=200');
        if (bitbargRes.ok) {
          const bData = await bitbargRes.json();
          const items = bData?.result?.items;
          if (Array.isArray(items)) {
            const bPrices: Record<string, { priceTmn: number; priceUsdt: number; change24h: number }> = {};
            const curRate = usdtTomanRate > 10000 ? usdtTomanRate : 267000;

            items.forEach((item) => {
              const coin = (item.coin || item.symbol || '').toUpperCase();
              const usd = parseFloat(item.price || '0');
              const ch = parseFloat(item.percent || '0');
              // Skip overwriting USDT with generic broker rate
              if (coin && usd > 0 && coin !== 'USDT') {
                bPrices[coin] = {
                  priceTmn: Math.round(usd * curRate),
                  priceUsdt: usd,
                  change24h: ch,
                };
                updateLastKnownCoinPrice(coin, Math.round(usd * curRate), usd);
              }
            });

            setIranianMarketPrices((prev) => {
              const next = { ...prev, ...bPrices };
              try {
                localStorage.setItem('alarmer_iranian_prices', JSON.stringify(next));
              } catch (_) {}
              return next;
            });

            setExchangeSpecificPrices((prev) => ({
              ...prev,
              bitbarg: bPrices,
            }));
          }
        }
      } catch (_) {}
    };

    fetchLivePrices();
    const interval = setInterval(fetchLivePrices, 20000);
    return () => clearInterval(interval);
  }, [usdtTomanRate]);

  const playBeep = () => {
    if (!globalSoundEnabled) return;
    try {
      const ctx = audioContextRef.current || new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = ctx;
      if (ctx.state === 'suspended') ctx.resume();

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.25);
    } catch (_) {}
  };

  // --- SEQUENTIAL NOTIFICATION & VOICE QUEUE (No overlaps, full voice reading) ---
  const enqueueNotification = (item: QueuedNotification) => {
    notificationQueueRef.current.push(item);
    setQueuedCount(notificationQueueRef.current.length);
    if (!isProcessingQueueRef.current) {
      processNextNotification();
    }
  };

  const processNextNotification = () => {
    if (notificationQueueRef.current.length === 0) {
      isProcessingQueueRef.current = false;
      setActiveQueueNotification(null);
      setQueuedCount(0);
      return;
    }

    isProcessingQueueRef.current = true;
    const item = notificationQueueRef.current.shift()!;
    setQueuedCount(notificationQueueRef.current.length);
    setActiveQueueNotification(item);
    setToastMessage(item.title);

    // 1. Play sound chime if effectively enabled
    if (item.effectiveSound) {
      playBeep();
    }

    // 2. Heavy haptic vibration if effectively enabled
    if (item.effectiveVibration && 'vibrate' in navigator) {
      try {
        navigator.vibrate([220, 100, 220]);
      } catch (_) {}
    }

    // 3. Voice Speech reading (reads completely, sequentially, never cut off)
    if (item.effectiveTts && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(item.speechText);
        utterance.lang = currentLang === 'fa' ? 'fa-IR' : 'en-US';
        utterance.rate = 0.93;
        utterance.pitch = 1.0;

        let isFinished = false;
        const completeUtterance = () => {
          if (isFinished) return;
          isFinished = true;
          // Natural pause between speech items
          setTimeout(() => {
            processNextNotification();
          }, 600);
        };

        utterance.onend = completeUtterance;
        utterance.onerror = completeUtterance;

        // Safety fallback timer if browser speech hangs
        const estimatedMs = Math.max(3000, item.speechText.length * 110);
        setTimeout(() => {
          if (!isFinished) completeUtterance();
        }, estimatedMs);

        window.speechSynthesis.speak(utterance);
      } catch (_) {
        setTimeout(() => {
          processNextNotification();
        }, 2200);
      }
    } else {
      // If voice is disabled, display banner cleanly for 2.2 seconds before next notification
      setTimeout(() => {
        processNextNotification();
      }, 2200);
    }
  };

  const speakText = (text: string, lang = currentLang) => {
    try {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang === 'fa' ? 'fa-IR' : 'en-US';
        utterance.rate = 0.95;
        utterance.pitch = 1.0;
        window.speechSynthesis.speak(utterance);
      }
    } catch (_) {}
  };

  const testTtsSpeech = (symbol = 'BTC', price = 83770) => {
    const text = currentLang === 'fa'
      ? `توجه، هشدار قیمت برای ${symbol} فعال شد. نرخ لحظه‌ای: ${price.toLocaleString('fa-IR')} دلار.`
      : `Attention, price alert triggered for ${symbol}. Current price: ${price} dollars.`;
    speakText(text, currentLang);
    showToast(`🗣️ در حال پخش صدای هوشمند برای ${symbol}...`);
  };

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const playAudioRingtonePreview = (soundName: string) => {
    try {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioContextClass) return;
      const ctx = new AudioContextClass();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (soundName === 'alarm_siren') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(440, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.35);
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.4);
      } else if (soundName === 'digital') {
        osc.type = 'square';
        osc.frequency.setValueAtTime(950, ctx.currentTime);
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.25);
      } else if (soundName === 'beacon') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1200, ctx.currentTime);
        gain.gain.setValueAtTime(0.25, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.35);
      } else {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, ctx.currentTime);
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.5);
      }
    } catch (_) {}
  };

  const handleTestTelegramMessage = async () => {
    if (!telegramChatId.trim()) {
      showToast(tAuthTg.telegramEmptyChatIdToast);
      return;
    }
    setIsTestingTelegram(true);
    try {
      const res = await fetch('/api/telegram/test-message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': 'e4b7a1d92f6c8035a9e2b7d4f1c6083e',
        },
        body: JSON.stringify({
          chat_id: telegramChatId.trim(),
          message: '🤖 [SignalAlert Engine] Telegram test dispatch successful.',
        }),
      });
      if (res.ok) {
        showToast(tAuthTg.telegramTestSuccessToast);
      } else {
        const data = await res.json();
        showToast(data.detail || tAuthTg.telegramTestErrorToast);
      }
    } catch (err) {
      showToast(tAuthTg.telegramServerErrorToast);
    } finally {
      setIsTestingTelegram(false);
    }
  };

  const calculateTotalSeconds = (u: 'seconds' | 'minutes' | 'hours', numStr: string) => {
    const n = Math.max(1, parseInt(numStr) || 1);
    if (u === 'seconds') return n;
    if (u === 'minutes') return n * 60;
    return n * 3600;
  };

  const formatCalculatedInterval = (u: 'seconds' | 'minutes' | 'hours', numStr: string) => {
    const n = Math.max(1, parseInt(numStr) || 1);
    if (u === 'seconds') return `${n} ثانیه`;
    if (u === 'minutes') return `${n} دقیقه`;
    return `${n} ساعت`;
  };

  // --- CALCULATION HELPER: REAL PERCENTAGE CHANGE IN WIDGET (Never stuck on +0.00%) ---
  const getRuleWidgetBadge = (rule: AlertRule, currentPrice: number) => {
    const isBothSidesPercent = rule.conditionType === 'PERCENT_CHANGE' && rule.direction === 'BOTH';
    const isDualActivePrice = rule.conditionType === 'PRICE_THRESHOLD' && rule.direction === 'BOTH' && rule.bothWayBehavior === 'DUAL_ACTIVE';
    const isPermanentlyActive = isBothSidesPercent || isDualActivePrice;
    if (!isPermanentlyActive && (!rule.isActive || rule.isTriggered)) {
      return {
        text: '✅ Done',
        isPositive: true,
        isDone: true,
        bgClass: 'bg-amber-500/15 border-amber-500/30 text-amber-400',
      };
    }

    let diffPct = 0;
    const base = rule.basePrice;

    if (base && base > 0 && Math.abs(currentPrice - base) > 0.0001) {
      // 1. Live change since base price
      diffPct = ((currentPrice - base) / base) * 100;
    } else if (rule.conditionType === 'PRICE_THRESHOLD' && rule.targetValue > 0) {
      // 2. Real percentage distance to target price
      diffPct = ((rule.targetValue - currentPrice) / currentPrice) * 100;
    } else if (rule.conditionType === 'PERCENT_CHANGE' && rule.targetValue > 0) {
      // 3. For percent change rule: show active threshold
      diffPct = rule.direction === 'BELOW' ? -rule.targetValue : rule.targetValue;
    } else if (base && base > 0) {
      diffPct = ((currentPrice - base) / base) * 100;
    }

    const isUp = diffPct >= 0;
    const sign = isUp ? '+' : '';
    const arrow = isUp ? '▲' : '▼';
    const text = `${sign}${diffPct.toFixed(2)}% ${arrow}`;

    return {
      text,
      isPositive: isUp,
      isDone: false,
      bgClass: isUp
        ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
        : 'bg-rose-500/15 border-rose-500/30 text-rose-400',
    };
  };

  const evaluateRule = (rule: AlertRule, forcedPriceDeltaPercent?: number) => {
    if (!rule.isActive) return;

    // Check Cooldown: prevent repetitive alert spam
    if (rule.cooldownUntil && new Date(rule.cooldownUntil).getTime() > Date.now()) {
      return;
    }

    let nameFa = rule.marketSymbol;
    let unit = '$';
    let currentLiveMarketPrice = rule.basePrice;

    if (rule.marketType === 'crypto') {
      const mkt = getCryptoMarketPrice(rule.baseCurrency, rule.exchangeId, rule.counterCurrency);
      nameFa = (cryptoPrices[rule.baseCurrency] || cryptoPrices.BTC).nameFa;
      unit = mkt.unit;
      currentLiveMarketPrice = mkt.price;
    } else {
      const meta = macroPrices[rule.baseCurrency] || macroPrices.US10Y;
      nameFa = meta.nameFa;
      unit = meta.unit;
      currentLiveMarketPrice = meta.currentPrice;
    }

    const now = new Date();
    const newPrice = forcedPriceDeltaPercent !== undefined
      ? Number((rule.basePrice * (1 + forcedPriceDeltaPercent / 100)).toFixed(rule.basePrice < 1 ? 6 : 2))
      : (currentLiveMarketPrice > 0 ? currentLiveMarketPrice : (rule.lastCheckedPrice ?? rule.basePrice));
    
    const diff = newPrice - rule.basePrice;
    const actualPercent = rule.basePrice > 0 ? (diff / rule.basePrice) * 100 : 0;

    let triggered = false;
    let title = '';
    let body = '';

    const priceStr = unit === 'تومان'
      ? `${Math.round(newPrice).toLocaleString('fa-IR')} تومان`
      : `${unit}${newPrice.toLocaleString(undefined, { minimumFractionDigits: newPrice < 1 ? 4 : 2, maximumFractionDigits: 4 })}`;

    if (rule.conditionType === 'PERCENT_CHANGE') {
      if (rule.direction === 'BOTH' && Math.abs(actualPercent) >= rule.targetValue) {
        triggered = true;
      } else if (rule.direction === 'ABOVE' && actualPercent >= rule.targetValue) {
        triggered = true;
      } else if (rule.direction === 'BELOW' && actualPercent <= -rule.targetValue) {
        triggered = true;
      }

      if (triggered) {
        const isUpward = actualPercent >= 0;
        const emoji = isUpward ? '🟢' : '🔴';
        const arrow = isUpward ? '▲' : '▼';
        const sign = isUpward ? '+' : '-';
        title = `${emoji} ${rule.marketSymbol} ${sign}${Math.abs(actualPercent).toFixed(2)}% ${priceStr} ${arrow}`;
        body = rule.customNote && rule.customNote.trim() 
          ? (rule.customNote.startsWith('📝') ? rule.customNote.trim() : `📝 ${rule.customNote.trim()}`)
          : '';
      }
    } else if (rule.conditionType === 'PRICE_THRESHOLD') {
      if (rule.direction === 'BOTH') {
        const upper = rule.upperTargetPrice;
        const lower = rule.lowerTargetPrice;

        if (upper != null && upper > 0 && newPrice >= upper) {
          triggered = true;
          const pct = ((newPrice - rule.basePrice) / rule.basePrice) * 100;
          title = `🟢 ${rule.marketSymbol} +${Math.abs(pct).toFixed(2)}% ${priceStr} ▲`;
          body = rule.upperNote && rule.upperNote.trim()
            ? (rule.upperNote.startsWith('📝') ? rule.upperNote.trim() : `📝 ${rule.upperNote.trim()}`)
            : (rule.customNote ? `📝 ${rule.customNote}` : '');
        } else if (lower != null && lower > 0 && newPrice <= lower) {
          triggered = true;
          const pct = ((newPrice - rule.basePrice) / rule.basePrice) * 100;
          title = `🔴 ${rule.marketSymbol} -${Math.abs(pct).toFixed(2)}% ${priceStr} ▼`;
          body = rule.lowerNote && rule.lowerNote.trim()
            ? (rule.lowerNote.startsWith('📝') ? rule.lowerNote.trim() : `📝 ${rule.lowerNote.trim()}`)
            : (rule.customNote ? `📝 ${rule.customNote}` : '');
        }
      } else if (rule.direction === 'ABOVE' && newPrice >= rule.targetValue) {
        triggered = true;
        const pct = ((newPrice - rule.basePrice) / rule.basePrice) * 100;
        title = `🟢 ${rule.marketSymbol} +${Math.abs(pct).toFixed(2)}% ${priceStr} ▲`;
        body = rule.customNote && rule.customNote.trim() 
          ? (rule.customNote.startsWith('📝') ? rule.customNote.trim() : `📝 ${rule.customNote.trim()}`)
          : '';
      } else if (rule.direction === 'BELOW' && newPrice <= rule.targetValue) {
        triggered = true;
        const pct = ((newPrice - rule.basePrice) / rule.basePrice) * 100;
        title = `🔴 ${rule.marketSymbol} -${Math.abs(pct).toFixed(2)}% ${priceStr} ▼`;
        body = rule.customNote && rule.customNote.trim() 
          ? (rule.customNote.startsWith('📝') ? rule.customNote.trim() : `📝 ${rule.customNote.trim()}`)
          : '';
      }
    } else if (rule.conditionType === 'VOLUME_SURGE') {
      const volReq = rule.volumePercent || 100;
      const coinMeta = rule.marketType === 'crypto' ? cryptoPrices[rule.baseCurrency] : macroPrices[rule.baseCurrency];
      const currentVol = (coinMeta as any)?.volume24h || 25000000000;
      const baseVol = rule.baseVolume || currentVol;
      const volGrowth = baseVol > 0 ? ((currentVol - baseVol) / baseVol) * 100 : 0;

      // Fires if real volume surged by requested threshold or simulated push
      if (volGrowth >= volReq || (forcedPriceDeltaPercent !== undefined && Math.abs(forcedPriceDeltaPercent) >= 1.0)) {
        triggered = true;
        const volFormatted = currentVol >= 1e9 ? `$${(currentVol / 1e9).toFixed(2)} B USD` : `$${(currentVol / 1e6).toFixed(1)} M USD`;
        title = `📊 ${rule.marketSymbol} جهش حجم معاملات! ${volFormatted} ⚡`;
        body = rule.customNote && rule.customNote.trim()
          ? rule.customNote.trim()
          : `حجم معاملات ۲۴ ساعته نماد بیش از +${volReq}% نسبت به مبنا جهش پیدا کرد (ورود نقدینگی سنگین).`;
      }
    }

    if (triggered) {
      // MASTER GLOBAL OVERRIDE LOGIC (Requests 2 & 3)
      const effectiveSound = globalSoundEnabled && (rule.soundEnabled ?? true);
      const effectiveVibration = globalVibrationEnabled && (rule.vibrationEnabled ?? true);
      const effectiveTts = globalTtsEnabled && (rule.ttsEnabled ?? false);

      let spokenPrice = newPrice.toLocaleString('fa-IR');
      if (unit === 'تومان' && newPrice >= 1e9) {
        spokenPrice = `${(newPrice / 1e9).toFixed(2)} میلیارد تومان`;
      } else if (unit === 'تومان' && newPrice >= 1e6) {
        spokenPrice = `${(newPrice / 1e6).toFixed(1)} میلیون تومان`;
      } else if (unit === 'تومان') {
        spokenPrice = `${Math.round(newPrice).toLocaleString('fa-IR')} تومان`;
      } else {
        spokenPrice = `${spokenPrice} ${unit === '$' ? 'دلار' : unit}`;
      }

      const spoken = currentLang === 'fa'
        ? `هشدار: ${nameFa} در ${rule.exchangeName} به قیمت ${spokenPrice} رسید.`
        : `Alert: ${rule.baseCurrency} on ${rule.exchangeName} reached ${newPrice} ${unit === '$' ? 'dollars' : unit}.`;

      const notifItem: QueuedNotification = {
        id: `notif-${Date.now()}-${Math.random().toString(36).substr(2, 6)}`,
        rule,
        title,
        body,
        value: (unit === 'تومان' || rule.exchangeId?.toLowerCase() === 'nobitex' || rule.counterCurrency === 'TMN' || rule.counterCurrency === 'IRT')
          ? `${Math.round(newPrice).toLocaleString('fa-IR')} تومان`
          : `${unit}${newPrice.toLocaleString()}`,
        timestamp: now,
        effectiveSound,
        effectiveVibration,
        effectiveTts,
        speechText: spoken,
      };

      // Add to notification history list
      setNotifications((prev) => [
        {
          id: notifItem.id,
          title: notifItem.title,
          body: notifItem.body,
          timestamp: notifItem.timestamp,
          ruleUuid: rule.uuid,
          marketSymbol: rule.marketSymbol,
          value: notifItem.value,
          exchange: rule.exchangeName,
        },
        ...prev.slice(0, 49),
      ]);

      // Enqueue to Sequential Queue (Request 4: No overlap, sequential playback)
      enqueueNotification(notifItem);
    }

    setRules((prev) =>
      prev.map((r) => {
        if (r.uuid === rule.uuid) {
          const isBothSidesPercent = r.conditionType === 'PERCENT_CHANGE' && r.direction === 'BOTH';
          const isDualActivePrice = r.conditionType === 'PRICE_THRESHOLD' && r.direction === 'BOTH' && r.bothWayBehavior === 'DUAL_ACTIVE';
          const shouldStayActive = isBothSidesPercent || isDualActivePrice;

          // Set 30s cooldown for recurring/dualActive alerts so they don't spam while price hovers
          const cooldownDate = (triggered && shouldStayActive)
            ? new Date(now.getTime() + Math.max(r.checkIntervalSeconds, 30) * 1000)
            : r.cooldownUntil;

          const safePrice = (newPrice && newPrice > 0) ? newPrice : (r.lastCheckedPrice ?? r.basePrice);

          return {
            ...r,
            lastCheckedAt: now,
            lastCheckedPrice: safePrice,
            basePrice: triggered ? safePrice : r.basePrice,
            isTriggered: triggered ? !shouldStayActive : r.isTriggered,
            isActive: triggered ? (shouldStayActive ? true : false) : r.isActive,
            cooldownUntil: cooldownDate,
            triggerCount: triggered ? r.triggerCount + 1 : r.triggerCount,
            lastTriggeredAt: triggered ? now : r.lastTriggeredAt,
          };
        }
        return r;
      })
    );
  };

  useEffect(() => {
    const timer = setInterval(() => {
      // Offline-safe: Do not simulate or overwrite prices if network is disconnected
      if (typeof navigator !== 'undefined' && !navigator.onLine) {
        return;
      }
      const now = new Date();
      rules.forEach((rule) => {
        if (!rule.isActive) return;
        const lastChecked = rule.lastCheckedAt ? new Date(rule.lastCheckedAt).getTime() : 0;
        const elapsedSecs = (now.getTime() - lastChecked) / 1000;
        const effectiveInterval = globalTimerEnabled ? globalTimerSeconds : rule.checkIntervalSeconds;

        if (elapsedSecs >= effectiveInterval) {
          evaluateRule(rule);
        }
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [rules, globalTimerEnabled, globalTimerSeconds]);

  const handleToggle = (uuid: string) => {
    setRules((prev) =>
      prev.map((r) => (r.uuid === uuid ? { ...r, isActive: !r.isActive } : r))
    );
  };

  const handleDelete = (uuid: string) => {
    setRules((prev) => prev.filter((r) => r.uuid !== uuid));
    showToast('هشدار با موفقیت حذف شد');
  };

  const handleToggleAlertFeedback = (uuid: string, type: 'sound' | 'vibration' | 'tts') => {
    setRules((prev) =>
      prev.map((r) => {
        if (r.uuid === uuid) {
          if (type === 'sound') {
            const next = !(r.soundEnabled ?? true);
            showToast(next ? `🔊 صدای زنگ برای ${r.baseCurrency} فعال شد.` : `🔇 صدای زنگ برای ${r.baseCurrency} خاموش شد.`);
            return { ...r, soundEnabled: next };
          } else if (type === 'vibration') {
            const next = !(r.vibrationEnabled ?? true);
            showToast(next ? `🔔 ویبره برای ${r.baseCurrency} فعال شد.` : `🔕 ویبره برای ${r.baseCurrency} خاموش شد.`);
            return { ...r, vibrationEnabled: next };
          } else if (type === 'tts') {
            const next = !(r.ttsEnabled ?? true);
            showToast(next ? `🗣️ اعلام صوتی برای ${r.baseCurrency} فعال شد.` : `🔇 اعلام صوتی برای ${r.baseCurrency} خاموش شد.`);
            return { ...r, ttsEnabled: next };
          }
        }
        return r;
      })
    );
  };

  const handleManualCheck = async (rule: AlertRule) => {
    setCheckingRuleId(rule.uuid);
    setTimeout(() => {
      evaluateRule(rule);
      setCheckingRuleId(null);
      showToast(`بررسی آنی انجام شد: ${rule.marketSymbol}`);
    }, 400);
  };

  // Export & Restore Handlers
  const handleExportBackup = () => {
    const jsonStr = JSON.stringify(rules, null, 2);
    navigator.clipboard.writeText(jsonStr);
    showToast('✅ فایل پشتیبان JSON شامل تمام هشدارها در کلیپ‌بورد کپی شد.');
  };

  const handleRestoreBackup = () => {
    try {
      const parsed = JSON.parse(restoreJsonInput);
      if (!Array.isArray(parsed)) throw new Error('Invalid JSON array');
      setRules(parsed);
      setShowRestoreModal(false);
      setRestoreJsonInput('');
      showToast(`🎉 ${parsed.length} هشدار با موفقیت بازیابی شد.`);
    } catch (_) {
      alert('فرمت فایل JSON نامعتبر است.');
    }
  };

  const handleCreateCryptoSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    let val = parseFloat(targetValueStr);
    let upperVal: number | undefined = undefined;
    let lowerVal: number | undefined = undefined;

    if (conditionType === 'VOLUME_SURGE') {
      val = parseFloat(volumePercentStr);
      if (isNaN(val) || val <= 0) val = 100;
    } else if (conditionType === 'PRICE_THRESHOLD' && direction === 'BOTH') {
      upperVal = parseFloat(upperPriceStr);
      lowerVal = parseFloat(lowerPriceStr);
      if (isNaN(upperVal) && isNaN(lowerVal)) {
        alert('لطفاً حداقل یکی از قیمت‌های حد بالا یا حد پایین را وارد کنید.');
        return;
      }
      val = !isNaN(upperVal) ? upperVal : lowerVal!;
    } else {
      if (isNaN(val) || val <= 0) {
        alert('لطفاً مقدار عددی معتبری وارد فرمایید.');
        return;
      }
    }

    const meta = cryptoPrices[selectedCryptoCoin] || cryptoPrices.BTC;
    const totalSecs = calculateTotalSeconds(unitType, unitNumber);
    const counterCur = (selectedExchange.id?.toLowerCase() === 'nobitex' && (!selectedCounterCurrency || selectedCounterCurrency === 'TMN' || selectedCounterCurrency === 'IRT'))
      ? 'TMN'
      : (selectedCounterCurrency || selectedExchange.defaultCounter);
    const mkt = getCryptoMarketPrice(selectedCryptoCoin, selectedExchange.id, counterCur);

    const newRule: AlertRule = {
      uuid: `rule-crypto-${Date.now()}`,
      marketType: 'crypto',
      exchangeId: selectedExchange.id,
      exchangeName: selectedExchange.name,
      baseCurrency: selectedCryptoCoin,
      counterCurrency: counterCur,
      marketSymbol: `${selectedCryptoCoin}/${counterCur}`,
      assetCategory: 'crypto',
      checkIntervalSeconds: totalSecs,
      conditionType: conditionType,
      direction: direction,
      bothWayBehavior: conditionType === 'PRICE_THRESHOLD' && direction === 'BOTH' ? bothWayBehavior : undefined,
      targetValue: val,
      upperTargetPrice: upperVal,
      upperNote: upperNote?.trim() || undefined,
      lowerTargetPrice: lowerVal,
      lowerNote: lowerNote?.trim() || undefined,
      volumePercent: conditionType === 'VOLUME_SURGE' ? val : undefined,
      baseVolume: (meta as any).volume24h || 25000000000,
      basePrice: mkt.price,
      lastCheckedPrice: mkt.price,
      isActive: true,
      isTriggered: false,
      triggerCount: 0,
      soundEnabled: ruleSoundEnabled,
      vibrationEnabled: ruleVibrationEnabled,
      ttsEnabled: ttsEnabled,
      createdAt: new Date(),
    };

    setRules([newRule, ...rules]);
    setShowCreateModal(false);
    setCreatePath('NONE');
    setCryptoStep(1);
    const isTmnRule = selectedExchange.id?.toLowerCase() === 'nobitex' || counterCur === 'TMN' || mkt.unit === 'تومان';
    showToast(isTmnRule
      ? `هشدار برای ${selectedCryptoCoin} (${Math.round(val).toLocaleString('fa-IR')} تومان) در ${selectedExchange.name} فعال شد.`
      : `هشدار کریپتو برای ${selectedCryptoCoin} فعال شد.`);
  };

  const handleCreateMacroSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    let val = parseFloat(targetValueStr);
    let upperVal: number | undefined = undefined;
    let lowerVal: number | undefined = undefined;

    if (conditionType === 'VOLUME_SURGE') {
      val = parseFloat(volumePercentStr);
      if (isNaN(val) || val <= 0) val = 100;
    } else if (conditionType === 'PRICE_THRESHOLD' && direction === 'BOTH') {
      upperVal = parseFloat(upperPriceStr);
      lowerVal = parseFloat(lowerPriceStr);
      if (isNaN(upperVal) && isNaN(lowerVal)) {
        alert('لطفاً حداقل یکی از قیمت‌های حد بالا یا حد پایین را وارد کنید.');
        return;
      }
      val = !isNaN(upperVal) ? upperVal : lowerVal!;
    } else {
      if (isNaN(val) || val <= 0) {
        alert('لطفاً مقدار عددی معتبری وارد فرمایید.');
        return;
      }
    }

    const meta = macroPrices[selectedMacroKey] || macroPrices.US10Y;
    const totalSecs = calculateTotalSeconds(unitType, unitNumber);

    const newRule: AlertRule = {
      uuid: `rule-macro-${Date.now()}`,
      marketType: 'stocks_macro',
      exchangeId: meta.marketName.toLowerCase().replace(/\s+/g, '_'),
      exchangeName: meta.marketName,
      baseCurrency: selectedMacroKey,
      counterCurrency: meta.unit,
      marketSymbol: meta.symbol,
      assetCategory: meta.category,
      checkIntervalSeconds: totalSecs,
      conditionType: conditionType,
      direction: direction,
      bothWayBehavior: conditionType === 'PRICE_THRESHOLD' && direction === 'BOTH' ? bothWayBehavior : undefined,
      targetValue: val,
      upperTargetPrice: upperVal,
      upperNote: upperNote?.trim() || undefined,
      lowerTargetPrice: lowerVal,
      lowerNote: lowerNote?.trim() || undefined,
      volumePercent: conditionType === 'VOLUME_SURGE' ? val : undefined,
      baseVolume: 50000000,
      basePrice: meta.currentPrice,
      lastCheckedPrice: meta.currentPrice,
      isActive: true,
      isTriggered: false,
      triggerCount: 0,
      soundEnabled: ruleSoundEnabled,
      vibrationEnabled: ruleVibrationEnabled,
      ttsEnabled: ttsEnabled,
      createdAt: new Date(),
    };

    setRules([newRule, ...rules]);
    setShowCreateModal(false);
    setCreatePath('NONE');
    setMacroStep(1);
    showToast(`هشدار برای ${meta.nameFa} با موفقیت فعال شد.`);
  };

  const formatInterval = (secs: number) => {
    if (secs >= 3600) return `${secs / 3600} ساعت`;
    if (secs >= 60) return `${secs / 60} دقیقه`;
    return `${secs} ثانیه`;
  };

  const formatTimeAgo = (date: Date) => {
    const diff = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
    if (diff < 10) return 'همین الان';
    if (diff < 60) return `${diff} ثانیه قبل`;
    if (diff < 3600) return `${Math.floor(diff / 60)} دقیقه قبل`;
    return `${Math.floor(diff / 3600)} ساعت قبل`;
  };

  const isOrange = appTheme.includes('orange');
  const isPurpleBlue = appTheme.includes('purple-blue');
  const isGold = appTheme.includes('gold');
  const isSapphire = appTheme.includes('sapphire');
  const isLight = appTheme.startsWith('light');

  const accentClass = isGold
    ? 'text-amber-400'
    : isSapphire
    ? 'text-cyan-400'
    : isPurpleBlue
    ? 'text-violet-400'
    : isOrange
    ? 'text-orange-400'
    : 'text-emerald-400';

  const accentBgClass = isGold
    ? 'bg-gradient-to-r from-amber-400 via-amber-300 to-yellow-500 hover:brightness-110 text-slate-950 font-black shadow-lg shadow-amber-500/20'
    : isSapphire
    ? 'bg-gradient-to-r from-cyan-500 via-sky-500 to-blue-600 hover:brightness-110 text-white font-bold shadow-lg shadow-cyan-500/20'
    : isPurpleBlue
    ? 'bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-bold'
    : isOrange
    ? 'bg-orange-500 hover:bg-orange-400 text-slate-950 font-bold'
    : 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold';

  const accentSubtleClass = isGold
    ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
    : isSapphire
    ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-300'
    : isPurpleBlue
    ? 'bg-violet-500/10 border-violet-500/20 text-violet-400'
    : isOrange
    ? 'bg-orange-500/10 border-orange-500/20 text-orange-400'
    : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400';

  // Filtered 40+ Exchanges (Strictly Sorted Alphabetically A-Z by English Name)
  const filteredExchanges = ALL_EXCHANGES.filter((ex) => {
    const matchesCategory = exchangeCategoryFilter === 'all' || ex.category === exchangeCategoryFilter;
    const matchesSearch = !exchangeSearchQuery ||
      ex.name.toLowerCase().includes(exchangeSearchQuery.toLowerCase()) ||
      ex.id.toLowerCase().includes(exchangeSearchQuery.toLowerCase()) ||
      ex.countryBadge.toLowerCase().includes(exchangeSearchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  }).sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));

  // Filtered Macro Assets
  const filteredMacroAssets = Object.entries(macroPrices).filter(([key, asset]) => {
    const matchesCategory = macroCategoryFilter === 'all' || asset.category === macroCategoryFilter;
    const matchesSearch = !macroSearchQuery ||
      asset.name.toLowerCase().includes(macroSearchQuery.toLowerCase()) ||
      asset.nameFa.includes(macroSearchQuery) ||
      asset.symbol.toLowerCase().includes(macroSearchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const currentLangObj = SUPPORTED_LANGUAGES.find(l => l.code === currentLang) || SUPPORTED_LANGUAGES[0];

  return (
    <div className={`min-h-screen ${isLight ? 'bg-slate-100 text-slate-900' : 'bg-slate-950 text-slate-100'} flex flex-col font-sans transition-colors duration-200`} dir={currentLangObj.dir}>
      {/* Header */}
      <header className={`border-b ${isLight ? 'border-slate-200 bg-white/90' : 'border-slate-800/80 bg-slate-900/80'} backdrop-blur-md sticky top-0 z-40 px-4 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4`}>
        <div className="flex items-center gap-3">
          <AppLogo className="h-10 w-10 rounded-2xl shadow-lg ring-1 ring-white/10 hover:scale-105 transition-transform" />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base lg:text-lg font-bold tracking-tight flex items-center gap-2">
                Alarmer (سامانه هشدار بازارها)
              </h1>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono border ${accentSubtleClass}`}>
                40+ Exchanges & US Treasury
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">
              پوشش کامل صرافی‌های کریپتو، اوراق قرضه ۱۰ ساله آمریکا (US10Y)، جفت‌ارزهای فارکس، سهام و طلا
            </p>
          </div>
        </div>

        {/* Top Controls */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowGoogleModal(true)}
            className={`px-2.5 py-1.5 rounded-xl border text-xs flex items-center gap-1.5 transition-all ${
              googleUser
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-400 font-bold'
                : isLight
                ? 'border-slate-300 bg-white text-slate-700'
                : 'border-slate-800 bg-slate-900 text-slate-300'
            }`}
            title={tAuthTg.headerLoginTooltip}
          >
            {googleUser ? (
              <>
                <span className="text-sm">👑</span>
                <span className="hidden sm:inline font-mono">{googleUser.name}</span>
                <span className="text-[9px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-300">PREMIUM</span>
              </>
            ) : (
              <>
                <User className="h-3.5 w-3.5 text-slate-400" />
                <span className="hidden sm:inline text-[11px]">{tAuthTg.headerSignInLabel}</span>
              </>
            )}
          </button>

          <button
            onClick={() => setShowLanguageModal(true)}
            className={`px-2.5 py-1.5 rounded-xl border text-xs flex items-center gap-1.5 ${isLight ? 'border-slate-300 bg-white' : 'border-slate-800 bg-slate-900'}`}
            title="انتخاب زبان"
          >
            <span className="text-base">{currentLangObj.flag}</span>
            <span className="text-xs font-semibold">{currentLangObj.nameEn}</span>
          </button>

          <button
            onClick={() => {
              const next = !globalSoundEnabled;
              setGlobalSoundEnabled(next);
              showToast(next ? '🔊 صدای سراسری فعال شد.' : '🔇 صدای سراسری برای همه آلارم‌ها متوقف شد.');
            }}
            className={`p-2 rounded-xl border text-xs flex items-center gap-1.5 ${
              globalSoundEnabled ? accentSubtleClass : 'border-slate-700 bg-slate-800 text-slate-400'
            }`}
            title={globalSoundEnabled ? 'صدا سراسری فعال' : 'صدا سراسری غیرفعال'}
          >
            {globalSoundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </button>
          
          <button
            onClick={() => {
              if (rules.length > 0) {
                evaluateRule(rules[0], 1.5);
              }
            }}
            className={`px-3 py-1.5 rounded-xl ${accentBgClass} text-slate-950 font-bold text-xs flex items-center gap-1.5 shadow-sm transition-all`}
          >
            <Sparkles className="h-4 w-4" />
            <span>تست نوسان (+۱.۵٪)</span>
          </button>
        </div>
      </header>

      {/* Live Bonbast Reference Bar for Iranian Free Market, Currencies & Gold */}
      <div className={`w-full py-2 px-4 lg:px-8 border-b ${isLight ? 'bg-emerald-50/80 border-emerald-200/70 text-slate-800' : 'bg-slate-900/90 border-slate-800 text-slate-300'} text-xs flex flex-wrap items-center justify-between gap-3 shadow-xs`}>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 font-bold text-[11px]">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            💎 مرجع اصلی بازار ارز و طلا: بن‌بست (bonbast.com)
          </span>
          <span className="text-slate-500 hidden sm:inline">•</span>
          <span className="text-[11px] text-slate-400 hidden sm:inline">نوبیتکس و والکس: مرجع ثانویه</span>
        </div>

        <div className="flex items-center gap-3 sm:gap-4 font-mono text-xs overflow-x-auto py-0.5 custom-scrollbar">
          {bonbastLive?.usd1 ? (
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-slate-400 text-[11px]">💵 دلار آزاد:</span>
              <strong className="text-emerald-400 font-bold font-mono">{Math.round(parseFloat(bonbastLive.usd1)).toLocaleString('fa-IR')} تومان</strong>
            </div>
          ) : (
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-slate-400 text-[11px]">💵 نرخ مبنا:</span>
              <strong className="text-emerald-400 font-bold font-mono">{Math.round(usdtTomanRate > 10000 ? usdtTomanRate : 267900).toLocaleString('fa-IR')} تومان</strong>
            </div>
          )}
          {bonbastLive?.gol18 && (
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-slate-400 text-[11px]">🪙 گرم طلا ۱۸:</span>
              <strong className="text-amber-300 font-bold font-mono">{Math.round(parseFloat(bonbastLive.gol18)).toLocaleString('fa-IR')} تومان</strong>
            </div>
          )}
          {bonbastLive?.emami1 && (
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-slate-400 text-[11px]">🟡 سکه امامی:</span>
              <strong className="text-amber-400 font-bold font-mono">{Math.round(parseFloat(bonbastLive.emami1)).toLocaleString('fa-IR')} تومان</strong>
            </div>
          )}
          {bonbastLive?.mithqal && (
            <div className="flex items-center gap-1 shrink-0 hidden md:flex">
              <span className="text-slate-400 text-[11px]">⚖️ مثقال آبشده:</span>
              <strong className="text-white font-bold font-mono">{Math.round(parseFloat(bonbastLive.mithqal)).toLocaleString('fa-IR')} تومان</strong>
            </div>
          )}
          {bonbastLive?.azadi1_2 && (
            <div className="flex items-center gap-1 shrink-0 hidden lg:flex">
              <span className="text-slate-400 text-[11px]">🪙 نیم‌سکه:</span>
              <strong className="text-white font-bold font-mono">{Math.round(parseFloat(bonbastLive.azadi1_2)).toLocaleString('fa-IR')} تومان</strong>
            </div>
          )}
          {bonbastLive?.aed1 && (
            <div className="flex items-center gap-1 shrink-0 hidden xl:flex">
              <span className="text-slate-400 text-[11px]">🇦🇪 درهم:</span>
              <strong className="text-white font-bold font-mono">{Math.round(parseFloat(bonbastLive.aed1)).toLocaleString('fa-IR')} تومان</strong>
            </div>
          )}
        </div>
      </div>

      {/* Toast Alert */}
      {toastMessage && (
        <div className={`fixed bottom-6 left-6 z-50 ${isLight ? 'bg-white border-emerald-500 shadow-xl text-slate-900' : 'bg-slate-900 border-emerald-500/50 text-emerald-300 shadow-2xl'} text-xs px-4 py-3 rounded-2xl border flex items-center gap-2 animate-bounce`}>
          <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          <span className="font-semibold">{toastMessage}</span>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 p-2 sm:p-4 lg:p-8 max-w-7xl mx-auto w-full overflow-x-hidden">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left: Interactive Phone Screen */}
          <div className="lg:col-span-7 flex justify-center w-full min-w-0">
            <div className={`w-full max-w-full sm:max-w-[400px] h-[800px] ${
              isLight 
                ? (isPurpleBlue ? 'bg-[#f5f6ff] border-indigo-200 shadow-indigo-200/50' : 'bg-slate-50 border-slate-300') 
                : (isPurpleBlue ? 'bg-[#0b0d1b] border-[#2e365e] shadow-purple-950/50' : 'bg-slate-950 border-slate-800')
            } border-4 sm:border-[8px] rounded-[36px] sm:rounded-[48px] shadow-2xl flex flex-col overflow-hidden relative ring-1 ring-slate-700/50`}>
              {/* Dynamic Island */}
              <div className={`absolute top-2 left-1/2 -translate-x-1/2 h-5 w-28 ${isLight ? 'bg-slate-300' : 'bg-slate-900'} rounded-full z-30 flex items-center justify-center`}>
                <div className={`h-2 w-12 ${isLight ? 'bg-slate-400' : 'bg-slate-950'} rounded-full`} />
              </div>

              {/* Status Bar */}
              <div className="pt-3 px-6 pb-1 flex justify-between items-center text-[10px] text-slate-400 font-mono z-20" dir="ltr">
                <span dir="ltr">12:40</span>
                <div className="flex items-center gap-1.5" dir="ltr">
                  <span className={`font-semibold text-[9px] ${accentClass}`}>40+ EXCHANGES • US BONDS</span>
                  <span className={`h-1.5 w-1.5 rounded-full ${isPurpleBlue ? 'bg-violet-400' : isOrange ? 'bg-orange-500' : 'bg-emerald-400'} animate-pulse`} />
                </div>
              </div>

              {/* Minimal Height Persistent Background Service Notification */}
              <div className="mx-3 mb-1 px-2.5 py-1 rounded-lg bg-slate-900/90 border border-slate-800 text-[10px] flex items-center justify-between shadow-sm z-20">
                <div className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                  <span className="font-bold text-slate-200">Alarmer</span>
                  <span className="text-slate-400" dir="ltr">• ● Active</span>
                </div>
                <span className="text-[9px] text-slate-500 font-mono" dir="ltr">Foreground</span>
              </div>

              {/* Phone App Header */}
              <div className={`px-4 py-3 border-b ${isLight ? 'border-slate-200 bg-white' : 'border-slate-900 bg-slate-950'} flex items-center justify-between`}>
                <div className="flex items-center gap-2.5">
                  <AppLogo className="h-8 w-8 rounded-xl shadow-md ring-1 ring-white/10" />
                  <div>
                    <h2 className="text-sm font-bold">
                      {mobileScreen === 'alerts' && (currentLang === 'fa' ? FA.myAlertsDefault : 'My Alerts (Default)')}
                      {mobileScreen === 'history' && (currentLang === 'fa' ? FA.notificationHistory : 'Alert History')}
                      {mobileScreen === 'settings' && (currentLang === 'fa' ? FA.appSettings : 'App Settings')}
                    </h2>
                    <p className="text-[10px] text-slate-400">
                      {currentLang === 'fa' ? FA.marketsSubtitle : 'Crypto • US Bonds • Forex • Stocks'}
                    </p>
                  </div>
                </div>

                {mobileScreen === 'alerts' && (
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => {
                        setCreatePath('NONE');
                        setShowCreateModal(true);
                      }}
                      className={`p-1.5 rounded-xl ${accentBgClass} text-slate-950 transition-all font-bold flex items-center gap-1.5 text-xs px-3 py-2 shadow-md cursor-pointer`}
                    >
                      <Plus className="h-4 w-4" />
                      <span>{currentLang === 'fa' ? FA.addNewAlert : 'Add Alert'}</span>
                    </button>
                  </div>
                )}
              </div>

              {/* App Body */}
              <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar text-xs">
                {/* TAB 1 (MIDDLE & DEFAULT): ALERTS */}
                {mobileScreen === 'alerts' && (
                  <div className="space-y-3">
                    {rules.length === 0 ? (
                      <div className="text-center py-16 px-4 space-y-3">
                        <div className="h-16 w-16 mx-auto rounded-2xl flex items-center justify-center">
                          <AppLogo className="h-16 w-16 shadow-2xl rounded-2xl ring-1 ring-white/10" />
                        </div>
                        <h3 className="text-sm font-bold">
                          {currentLang === 'fa' ? FA.noAlertsYet : 'No Alerts Set Yet'}
                        </h3>
                        <p className="text-slate-400 text-xs leading-relaxed">
                          {currentLang === 'fa' ? FA.noAlertsDesc : 'Select your desired market and create your first alert.'}
                        </p>
                        <button
                          onClick={() => {
                            setCreatePath('NONE');
                            setShowCreateModal(true);
                          }}
                          className={`px-4 py-2 ${accentBgClass} text-slate-950 font-bold rounded-xl text-xs inline-flex items-center gap-1.5 mt-2`}
                        >
                          <Plus className="h-4 w-4" />
                          <span>{currentLang === 'fa' ? FA.addNewAlert : 'Create New Alert'}</span>
                        </button>
                      </div>
                    ) : (
                      rules.map((rule) => (
                        <AlarmCard
                          key={rule.uuid}
                          rule={rule}
                          cryptoPrices={cryptoPrices}
                          macroPrices={macroPrices}
                          currentLang={currentLang}
                          isLight={isLight}
                          isOrange={isOrange}
                          checkingRuleId={checkingRuleId}
                          globalSoundEnabled={globalSoundEnabled}
                          globalVibrationEnabled={globalVibrationEnabled}
                          globalTtsEnabled={globalTtsEnabled}
                          formatInterval={formatInterval}
                          onToggle={handleToggle}
                          onToggleFeedback={handleToggleAlertFeedback}
                          onManualCheck={handleManualCheck}
                          onDelete={handleDelete}
                        />
                      ))
                    )}
                  </div>
                )}

                {/* TAB 0 (LEFT): HISTORY */}
                {mobileScreen === 'history' && (
                  <div className="space-y-2.5">
                    {notifications.map((notif) => (
                      <div key={notif.id} className={`p-3 rounded-2xl border space-y-1.5 ${isLight ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-900 border-slate-800'}`}>
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-xs">{notif.title}</span>
                          <span className="text-[10px] font-mono text-slate-400">{formatTimeAgo(notif.timestamp)}</span>
                        </div>
                        {notif.body && notif.body.trim() && (
                          <p className="text-[11px] text-slate-400 leading-relaxed">{notif.body}</p>
                        )}
                        <div className="flex items-center gap-2 pt-1 text-[10px] font-mono text-slate-400">
                          <span>بازار: {notif.marketSymbol}</span>
                          <span>•</span>
                          <span className={`font-bold ${accentClass}`}>{notif.value}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* TAB 2 (RIGHT): SETTINGS */}
                {mobileScreen === 'settings' && (
                  <div className="space-y-4">
                    {/* ======================================================== */}
                    {/* SECTION 1: بخش لاگین (LOGIN & GOOGLE ACCOUNT)            */}
                    {/* ======================================================== */}
                    <div className={`p-4 rounded-2xl border transition-all ${isLight ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-900 border-slate-800'} space-y-3`}>
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                        <div className="flex items-center gap-2">
                          <User className="h-4 w-4 text-emerald-400" />
                          <h4 className="font-bold text-xs text-white">
                            {tAuthTg.loginSectionTitle}
                          </h4>
                        </div>
                        {googleUser && (
                          <span className="text-[9px] px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-300 font-bold">
                            {tAuthTg.vipActiveBadge}
                          </span>
                        )}
                      </div>

                      {/* Google Sign-In Card */}
                      <div className={`p-3.5 rounded-xl border flex items-center justify-between transition-all ${googleUser ? 'bg-amber-950/20 border-amber-500/30' : 'bg-slate-950 border-slate-800'}`}>
                        <div className="flex items-center gap-3 min-w-0">
                          <div className={`h-10 w-10 rounded-xl flex items-center justify-center text-base font-bold shrink-0 ${googleUser ? 'bg-amber-500/20 border border-amber-500/40 text-amber-300' : 'bg-slate-800 text-slate-300'}`}>
                            {googleUser ? '👑' : <User className="h-5 w-5 text-slate-300" />}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-xs text-white truncate">
                                {googleUser ? googleUser.name : tAuthTg.guestUserTitle}
                              </span>
                              <span className={`text-[9px] px-1.5 py-0.2 rounded font-bold shrink-0 ${googleUser ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' : 'bg-slate-800 text-slate-400'}`}>
                                {googleUser ? tAuthTg.premiumBadge : tAuthTg.optionalBadge}
                              </span>
                            </div>
                            <span className="text-[10px] text-slate-400 block mt-0.5 truncate">
                              {googleUser ? googleUser.email : tAuthTg.loginSubGuest}
                            </span>
                          </div>
                        </div>

                        {googleUser ? (
                          <button
                            onClick={() => {
                              setGoogleUser(null);
                              localStorage.removeItem('alarmer_google_user');
                              showToast(tAuthTg.signedOutToast);
                            }}
                            className="px-3 py-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-400 text-[11px] font-bold hover:bg-rose-500/20 transition-all cursor-pointer shrink-0"
                          >
                            {tAuthTg.signOutBtn}
                          </button>
                        ) : (
                          <button
                            onClick={() => setShowGoogleModal(true)}
                            className={`px-3.5 py-2 rounded-xl font-bold text-xs flex items-center gap-1.5 shadow-sm transition-all ${accentBgClass} text-slate-950 hover:brightness-110 cursor-pointer shrink-0`}
                          >
                            <span>{tAuthTg.signInBtn}</span>
                          </button>
                        )}
                      </div>
                    </div>

                    {/* ======================================================== */}
                    {/* SECTION 2: بخش تلگرام (TELEGRAM BOT INTEGRATION)         */}
                    {/* ======================================================== */}
                    <div className={`p-4 rounded-2xl border transition-all ${isLight ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-900 border-slate-800'} space-y-3`}>
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                        <div className="flex items-center gap-2">
                          <Send className="h-4 w-4 text-blue-400" />
                          <h4 className="font-bold text-xs text-white">
                            {tAuthTg.telegramSectionTitle}
                          </h4>
                        </div>
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 font-bold shrink-0">
                          {tAuthTg.telegramOnlineBadge}
                        </span>
                      </div>

                      {/* Telegram Bot Card */}
                      <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2.5">
                            <div className="h-9 w-9 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400 font-bold text-base shrink-0">
                              🤖
                            </div>
                            <div>
                              <div className="flex items-center gap-1.5">
                                <span className="font-bold text-xs text-white block">
                                  {tAuthTg.telegramBotName}
                                </span>
                                <span className="text-[10px] font-mono text-blue-400 bg-blue-950/60 px-1.5 py-0.2 rounded border border-blue-800/50">
                                  {tAuthTg.telegramBotHandle}
                                </span>
                              </div>
                              <span className="text-[10px] text-slate-400 block mt-0.5">
                                {tAuthTg.telegramBotSubtitle}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Guide Steps */}
                        <div className="p-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-[10.5px] text-blue-200 leading-relaxed space-y-1">
                          <div className="flex items-start gap-1.5">
                            <span className="text-blue-400 font-bold">۱.</span>
                            <span>{tAuthTg.telegramStep1}</span>
                          </div>
                          <div className="flex items-start gap-1.5">
                            <span className="text-blue-400 font-bold">۲.</span>
                            <span>{tAuthTg.telegramStep2}</span>
                          </div>
                        </div>

                        <div className="space-y-1.5 pt-0.5">
                          <label className="block text-[10px] text-slate-400 font-medium">
                            {tAuthTg.telegramInputLabel}
                          </label>
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={telegramChatId}
                              onChange={(e) => setTelegramChatId(e.target.value)}
                              placeholder={tAuthTg.telegramInputPlaceholder}
                              className="flex-1 min-w-0 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono placeholder:text-slate-600 focus:outline-none focus:border-blue-500"
                            />
                            <button
                              onClick={handleTestTelegramMessage}
                              disabled={isTestingTelegram}
                              className="px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-[11px] flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50 shrink-0 shadow-sm"
                            >
                              <Zap className={`h-3.5 w-3.5 ${isTestingTelegram ? 'animate-spin' : ''}`} />
                              <span>{isTestingTelegram ? tAuthTg.telegramTestingBtn : tAuthTg.telegramTestBtn}</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* ======================================================== */}
                    {/* SECTION 3: بخش تنظیمات الارمها (ALARM SETTINGS & SOUND)   */}
                    {/* ======================================================== */}
                    <div className={`p-4 rounded-2xl border ${isLight ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-900 border-slate-800'} space-y-3.5`}>
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                        <div className="flex items-center gap-2">
                          <Clock className="h-4 w-4 text-amber-400" />
                          <h4 className="font-bold text-xs text-white">
                            {currentLang === 'fa' ? '۳. تنظیمات هشدارها و صدای زنگ (Alarm Settings)' : '3. Alarm Schedule & Sound Settings'}
                          </h4>
                        </div>
                      </div>

                      {/* Global Timer Feature */}
                      <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2.5">
                            <div className={`p-2 rounded-xl ${globalTimerEnabled ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'bg-slate-800 text-slate-500'}`}>
                              <Timer className="h-4 w-4" />
                            </div>
                            <div>
                              <span className="font-bold text-xs text-white block">
                                {currentLang === 'fa' ? '⚡ تایمر سراسری (Global Timer)' : '⚡ Global Timer Override'}
                              </span>
                              <span className="text-[10px] text-slate-400 block">
                                {currentLang === 'fa' ? 'پایش هم‌زمان تمام آلارم‌ها با یک زمان‌بندی مشترک' : 'Evaluate all alarms simultaneously on a single schedule'}
                              </span>
                            </div>
                          </div>

                          <div dir="ltr" className="shrink-0">
                            <button
                              type="button"
                              role="switch"
                              aria-checked={globalTimerEnabled}
                              onClick={() => {
                                const next = !globalTimerEnabled;
                                setGlobalTimerEnabled(next);
                                showToast(next ? (currentLang === 'fa' ? '⚡ تایمر سراسری فعال شد.' : '⚡ Global Timer enabled.') : (currentLang === 'fa' ? '🔄 تایمر اختصاصی هر هشدار بازیابی شد.' : '🔄 Reverted to individual rule timers.'));
                              }}
                              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                                globalTimerEnabled ? 'bg-amber-500' : 'bg-slate-800'
                              }`}
                            >
                              <span
                                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                                  globalTimerEnabled ? 'translate-x-5' : 'translate-x-0'
                                }`}
                              />
                            </button>
                          </div>
                        </div>

                        {globalTimerEnabled ? (
                          <div className="space-y-2 pt-1">
                            <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-300 leading-relaxed">
                              💡 {currentLang === 'fa' ? 'تایمر سراسری فعال است: تمامی هشدارهای فعال روی این تایمر چک می‌شوند. با غیرفعال کردن، تایمر اختصاصی هر هشدار مجدداً اعمال می‌گردد.' : 'Global Timer active: All active alarms are checked on this cycle. Turning off restores individual rule timers.'}
                            </div>

                            <div className="grid grid-cols-4 gap-1.5 pt-1">
                              {[
                                { secs: 5, label: '5s' },
                                { secs: 10, label: '10s' },
                                { secs: 30, label: '30s' },
                                { secs: 60, label: '1m' },
                                { secs: 300, label: '5m' },
                                { secs: 900, label: '15m' },
                                { secs: 1800, label: '30m' },
                                { secs: 3600, label: '1h' },
                              ].map((opt) => (
                                <button
                                  key={opt.secs}
                                  type="button"
                                  onClick={() => setGlobalTimerSeconds(opt.secs)}
                                  className={`py-1.5 rounded-lg border text-center font-bold font-mono text-[11px] transition-all cursor-pointer ${
                                    globalTimerSeconds === opt.secs
                                      ? 'border-amber-500 bg-amber-500 text-slate-950 shadow'
                                      : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-white'
                                  }`}
                                >
                                  {opt.label}
                                </button>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="text-[10px] text-slate-500 font-mono">
                            {currentLang === 'fa' ? '• غیرفعال (پایش بر اساس زمان‌بندی اختصاصی هر هشدار)' : '• Disabled (Checking based on each alarm\'s individual interval)'}
                          </div>
                        )}
                      </div>

                      {/* Alarm Sound Ringtone Melody Selector */}
                      <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Volume2 className="h-4 w-4 text-emerald-400" />
                            <span className="font-bold text-xs text-white">
                              {currentLang === 'fa' ? '🎵 آهنگ زنگ آلارم (Alarm Ringtone)' : '🎵 Alarm Ringtone Melody'}
                            </span>
                          </div>
                          <button
                            onClick={() => playAudioRingtonePreview(selectedRingtone)}
                            className="px-2.5 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-400 font-bold text-[10px] flex items-center gap-1 cursor-pointer shrink-0"
                          >
                            <Play className="h-3 w-3" />
                            <span>{currentLang === 'fa' ? 'تست ملودی' : 'Preview'}</span>
                          </button>
                        </div>

                        <div className="grid grid-cols-2 gap-1.5 pt-1">
                          {[
                            { id: 'alarm_siren', name: '🚨 آژیر خطر (Siren)' },
                            { id: 'digital', name: '📟 دیجیتال (Digital)' },
                            { id: 'beacon', name: '📡 بیکون (Beacon)' },
                            { id: 'bell', name: '🔔 زنگ (Bell)' },
                            { id: 'chime', name: '🎶 چایم (Chime)' },
                          ].map((r) => (
                            <button
                              key={r.id}
                              onClick={() => {
                                setSelectedRingtone(r.id);
                                playAudioRingtonePreview(r.id);
                              }}
                              className={`p-2 rounded-lg border text-right text-[11px] font-semibold transition-all cursor-pointer ${
                                selectedRingtone === r.id
                                  ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300 font-bold'
                                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-white'
                              }`}
                            >
                              {r.name}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Master Switches for Vibration, Sound, and Voice */}
                      <div className="space-y-2 pt-1">
                        {/* 1. 🔔 Vibration */}
                        <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-xl ${globalVibrationEnabled ? 'bg-amber-500/20 text-amber-400' : 'bg-slate-800 text-slate-500'}`}>
                              <Smartphone className="h-4 w-4" />
                            </div>
                            <div>
                              <span className="font-bold text-xs text-white block">🔔 {currentLang === 'fa' ? 'ویبره سراسری' : 'Global Vibration'}</span>
                              <span className="text-[10px] text-slate-400 block">{currentLang === 'fa' ? 'لرزش دستگاه هنگام وقوع هشدار' : 'Device vibration on alert trigger'}</span>
                            </div>
                          </div>
                          <div dir="ltr" className="shrink-0">
                            <button
                              type="button"
                              role="switch"
                              aria-checked={globalVibrationEnabled}
                              onClick={() => setGlobalVibrationEnabled(!globalVibrationEnabled)}
                              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
                                globalVibrationEnabled ? 'bg-amber-500' : 'bg-slate-800'
                              }`}
                            >
                              <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ${globalVibrationEnabled ? 'translate-x-5' : 'translate-x-0'}`} />
                            </button>
                          </div>
                        </div>

                        {/* 2. 🔊 Sound */}
                        <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-xl ${globalSoundEnabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-800 text-slate-500'}`}>
                              <Volume2 className="h-4 w-4" />
                            </div>
                            <div>
                              <span className="font-bold text-xs text-white block">🔊 {currentLang === 'fa' ? 'صدای سراسری' : 'Global Alarm Sound'}</span>
                              <span className="text-[10px] text-slate-400 block">{currentLang === 'fa' ? 'پخش ملودی آلارم برای هشدارها' : 'Play alarm melody on alert trigger'}</span>
                            </div>
                          </div>
                          <div dir="ltr" className="shrink-0">
                            <button
                              type="button"
                              role="switch"
                              aria-checked={globalSoundEnabled}
                              onClick={() => setGlobalSoundEnabled(!globalSoundEnabled)}
                              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
                                globalSoundEnabled ? 'bg-emerald-500' : 'bg-slate-800'
                              }`}
                            >
                              <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ${globalSoundEnabled ? 'translate-x-5' : 'translate-x-0'}`} />
                            </button>
                          </div>
                        </div>

                        {/* 3. 🗣️ Voice Speech */}
                        <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-xl ${globalTtsEnabled ? 'bg-violet-500/20 text-violet-400' : 'bg-slate-800 text-slate-500'}`}>
                              <Mic className="h-4 w-4" />
                            </div>
                            <div>
                              <span className="font-bold text-xs text-white block">🗣️ Voice Speech ({currentLang === 'fa' ? 'اعلام صوتی' : 'TTS Speech'})</span>
                              <span className="text-[10px] text-slate-400 block">{currentLang === 'fa' ? 'خوانش نام دارایی و قیمت به انگلیسی' : 'Read asset name and price aloud'}</span>
                            </div>
                          </div>
                          <div dir="ltr" className="shrink-0">
                            <button
                              type="button"
                              role="switch"
                              aria-checked={globalTtsEnabled}
                              onClick={() => setGlobalTtsEnabled(!globalTtsEnabled)}
                              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
                                globalTtsEnabled ? 'bg-violet-600' : 'bg-slate-800'
                              }`}
                            >
                              <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ${globalTtsEnabled ? 'translate-x-5' : 'translate-x-0'}`} />
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* ======================================================== */}
                    {/* SECTION 4: بخش تمها (THEMES & APPEARANCE)                 */}
                    {/* ======================================================== */}
                    <div className={`p-4 rounded-2xl border ${isLight ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-900 border-slate-800'} space-y-2.5`}>
                      <div className="flex items-center gap-2 font-bold text-xs text-white">
                        <Palette className={`h-4 w-4 ${accentClass}`} />
                        <span>۴. {currentLang === 'fa' ? 'پوسته و تم رنگی (۱۰ حالت)' : '4. UI Themes (10 Presets)'}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-1.5">
                        {[
                          { id: 'dark-gold', name: '👑 تیتانیوم طلایی', bg: '#09090b', border: '#F59E0B' },
                          { id: 'light-gold', name: '👑 تیتانیوم لایت', bg: '#FAF9F5', border: '#D97706' },
                          { id: 'dark-sapphire', name: '💎 یاقوتی دارک', bg: '#030712', border: '#38BDF8' },
                          { id: 'light-sapphire', name: '💎 یاقوتی لایت', bg: '#F0F7FF', border: '#0284C7' },
                          { id: 'dark-green', name: 'دارک سبز (پیش‌فرض)', bg: '#020617', border: '#10B981' },
                          { id: 'light-green', name: 'لایت سبز', bg: '#F8FAFC', border: '#059669' },
                          { id: 'dark-purple-blue', name: 'دارک بنفش آبی', bg: '#0B0D1B', border: '#8B5CF6' },
                          { id: 'light-purple-blue', name: 'لایت بنفش آبی', bg: '#F5F6FF', border: '#7C3AED' },
                          { id: 'dark-orange', name: 'دارک نارنجی', bg: '#0C0A09', border: '#F97316' },
                          { id: 'light-orange', name: 'لایت نارنجی', bg: '#FAFAF9', border: '#EA580C' },
                        ].map((t) => (
                          <button
                            key={t.id}
                            onClick={() => setAppTheme(t.id as any)}
                            className={`py-1.5 px-2.5 rounded-xl border text-right text-[11px] flex items-center gap-2 font-semibold transition-all cursor-pointer ${
                              appTheme === t.id
                                ? (isGold ? 'border-amber-400 bg-amber-500/15' : isSapphire ? 'border-cyan-400 bg-cyan-500/15' : isPurpleBlue ? 'border-violet-500 bg-violet-500/15' : isOrange ? 'border-orange-500 bg-orange-500/15' : 'border-emerald-500 bg-emerald-500/15')
                                : 'border-slate-700/80 bg-slate-950/60'
                            }`}
                          >
                            <span className="h-3.5 w-3.5 rounded-full border-2 shrink-0" style={{ backgroundColor: t.bg, borderColor: t.border }} />
                            <span className="truncate">{t.name}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* ======================================================== */}
                    {/* SECTION 5: بخش BACKUP & RESTORE                          */}
                    {/* ======================================================== */}
                    <div className={`p-4 rounded-2xl border ${isLight ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-900 border-slate-800'} space-y-2`}>
                      <div className="font-bold text-xs flex items-center gap-2 text-white">
                        <Database className="h-4 w-4 text-emerald-400" />
                        <span>۵. {currentLang === 'fa' ? 'پشتیبان‌گیری و بازیابی (Backup & Restore)' : '5. Backup & Restore'}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 pt-1">
                        <button
                          onClick={handleExportBackup}
                          className="py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-emerald-400 font-bold text-xs flex items-center justify-center gap-1.5 border border-slate-700 transition-all cursor-pointer"
                        >
                          <Upload className="h-3.5 w-3.5" />
                          <span>{currentLang === 'fa' ? 'خروجی بک‌آپ' : 'Export JSON'}</span>
                        </button>
                        <button
                          onClick={() => setShowRestoreModal(true)}
                          className="py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-400 font-bold text-xs flex items-center justify-center gap-1.5 border border-slate-700 transition-all cursor-pointer"
                        >
                          <Download className="h-3.5 w-3.5" />
                          <span>{currentLang === 'fa' ? 'بازیابی بک‌آپ' : 'Restore JSON'}</span>
                        </button>
                      </div>
                    </div>

                    {/* ======================================================== */}
                    {/* SECTION 6: بخش زبان (LANGUAGE)                           */}
                    {/* ======================================================== */}
                    <div className={`p-4 rounded-2xl border ${isLight ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-900 border-slate-800'} space-y-2`}>
                      <div className="font-bold text-xs flex items-center justify-between text-white">
                        <div className="flex items-center gap-2">
                          <Languages className="h-4 w-4 text-emerald-400" />
                          <span>۶. {currentLang === 'fa' ? 'زبان برنامه (Language)' : '6. Language'}</span>
                        </div>
                        <button
                          onClick={() => setShowLanguageModal(true)}
                          className={`text-xs font-bold ${accentClass} underline cursor-pointer`}
                        >
                          {currentLang === 'fa' ? 'تغییر زبان' : 'Change Language'}
                        </button>
                      </div>
                      <div className="flex items-center gap-2 p-2 rounded-xl bg-slate-950 border border-slate-800 text-[11px]">
                        <span className="text-xl">{currentLangObj.flag}</span>
                        <div>
                          <span className="font-bold text-white block">{currentLangObj.name}</span>
                          <span className="text-[10px] text-slate-400">{currentLangObj.nameEn}</span>
                        </div>
                      </div>
                    </div>

                    {/* ======================================================== */}
                    {/* SECTION 7: بخش تنظیمات باتری و پس‌زمینه (BATTERY & BG)    */}
                    {/* ======================================================== */}
                    <div className={`p-4 rounded-2xl border ${isLight ? 'bg-white border-slate-200 shadow-sm' : 'bg-slate-900 border-slate-800'} space-y-2.5`}>
                      <div className="font-bold text-xs flex items-center justify-between text-white">
                        <div className="flex items-center gap-2">
                          <BatteryCharging className="h-4 w-4 text-emerald-400" />
                          <span>۷. {currentLang === 'fa' ? 'تنظیمات باتری و کارکرد پس‌زمینه' : '7. Battery & Background Sync'}</span>
                        </div>
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 font-bold">
                          ● Active 24/7
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 leading-relaxed">
                        {currentLang === 'fa' 
                          ? 'پایش مداوم نرخ‌ها توسط موتور ابری در ۲۴ ساعت شبانه‌روز انجام می‌شود. برای کارکرد دقیق بدون تاخیر در گوشی‌های اندروید (شیائومی، سامسونگ، هواوی)، بهینه‌سازی باتری (Battery Saver) را برای برنامه غیرفعال کنید و ویژگی شروع خودکار (Auto-start) را فعال نمایید.' 
                          : 'Server engine monitors prices 24/7. To ensure real-time alerts without delay on Android devices (Xiaomi, Samsung, Huawei), disable Battery Saver restrictions and enable Auto-start.'}
                      </p>
                      <button
                        onClick={() => setShowHomeWidgetModal(true)}
                        className="w-full py-2 rounded-xl bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 font-bold text-xs border border-violet-500/30 flex items-center justify-center gap-1.5 transition-all cursor-pointer"
                      >
                        <LayoutGrid className="h-3.5 w-3.5" />
                        <span>{currentLang === 'fa' ? 'پیش‌نمایش ویجت صفحه اصلی (Homescreen)' : 'Preview Homescreen Widget'}</span>
                      </button>
                    </div>

                    {/* ======================================================== */}
                    {/* SECTION 8: بخش پنل ادمین و عیب‌یابی (ADMIN & DEBUG)        */}
                    {/* ======================================================== */}
                    {(googleUser?.email?.toLowerCase() === 'mehran.aminpoor@gmail.com' || (!googleUser && true)) && (
                      <div className="p-4 rounded-2xl border border-rose-500/40 bg-rose-950/10 space-y-3">
                        <div className="flex items-center justify-between border-b border-rose-500/30 pb-2">
                          <div className="flex items-center gap-2">
                            <Shield className="h-4 w-4 text-rose-400" />
                            <h4 className="font-bold text-xs text-rose-300">
                              ۸. {currentLang === 'fa' ? 'پنل ادمین و مرکز عیب‌یابی (Admin & Diagnostics)' : '8. Admin & Diagnostics Panel'}
                            </h4>
                          </div>
                          <span className="text-[9px] px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono font-bold">
                            Mehran.Aminpoor@gmail.com
                          </span>
                        </div>

                        <div className="space-y-2 text-xs text-slate-300">
                          <div className="p-2 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between text-[11px]">
                            <span>{currentLang === 'fa' ? 'وضعیت موتور پایتون سرور:' : 'Python Alert Engine:'}</span>
                            <span className="font-mono font-bold text-emerald-400">SignalAlert v2.6.0 Online</span>
                          </div>

                          <div className="grid grid-cols-2 gap-2 pt-1">
                            <button
                              onClick={() => {
                                rules.forEach(r => evaluateRule(r, 1.5));
                                showToast(currentLang === 'fa' ? '⚡ بررسی تمام آلارم‌ها با لود تستی اجرا شد.' : '⚡ Triggered test check on all rules.');
                              }}
                              className="py-2 px-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-rose-300 font-bold text-[11px] border border-rose-500/30 flex items-center justify-center gap-1 cursor-pointer"
                            >
                              <Zap className="h-3.5 w-3.5" />
                              <span>{currentLang === 'fa' ? 'تست تمام آلارم‌ها' : 'Force Check All'}</span>
                            </button>

                            <button
                              onClick={handleTestTelegramMessage}
                              disabled={isTestingTelegram}
                              className="py-2 px-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-blue-300 font-bold text-[11px] border border-blue-500/30 flex items-center justify-center gap-1 cursor-pointer"
                            >
                              <Zap className="h-3.5 w-3.5" />
                              <span>{tAuthTg.adminTestTelegramBtn}</span>
                            </button>
                          </div>

                          {/* WALL STREET & MACRO SYMBOLS JSON EXPORT */}
                          <div className="mt-3 pt-3 border-t border-rose-500/20 space-y-2.5">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5">
                                <Code className="h-3.5 w-3.5 text-amber-400" />
                                <span className="font-bold text-[11px] text-rose-200">
                                  {currentLang === 'fa' ? 'خروجی JSON نمادهای وال استریت و اقتصاد کلان' : 'Wall Street & Macro Symbols JSON Export'}
                                </span>
                              </div>
                              <span className="text-[9px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono font-bold border border-amber-500/30">
                                {Object.keys(macroPrices).length} {currentLang === 'fa' ? 'نماد' : 'Symbols'}
                              </span>
                            </div>

                            <p className="text-[10px] text-slate-400 leading-relaxed">
                              {currentLang === 'fa' 
                                ? 'دریافت خروجی کامل .json از تمامی نمادهای موجود در بخش وال استریت، سهام آمریکا، اوراق قرضه، فارکس، طلا، نفت، شاخص‌ها و بازار آزاد ایران (بن‌بست):' 
                                : 'Export complete JSON of all active symbols across Wall Street, US Stocks, Bonds, Forex, Commodities, Indices, and Iran Free Market:'}
                            </p>

                            <div className="grid grid-cols-2 gap-2">
                              <button
                                onClick={handleDownloadMacroJson}
                                className="py-2 px-2.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 font-bold text-[11px] border border-amber-500/30 flex items-center justify-center gap-1.5 transition-all cursor-pointer shadow-sm active:scale-95"
                              >
                                <Download className="h-3.5 w-3.5 text-amber-400" />
                                <span>{currentLang === 'fa' ? 'دانلود فایل .json' : 'Download .json File'}</span>
                              </button>

                              <button
                                onClick={handleCopyMacroJson}
                                className="py-2 px-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 font-bold text-[11px] border border-slate-700 flex items-center justify-center gap-1.5 transition-all cursor-pointer shadow-sm active:scale-95"
                              >
                                <Copy className="h-3.5 w-3.5 text-slate-400" />
                                <span>{currentLang === 'fa' ? 'کپی کد JSON' : 'Copy JSON'}</span>
                              </button>
                            </div>

                            <button
                              onClick={() => setShowDebugJsonViewer(!showDebugJsonViewer)}
                              className="w-full py-1.5 px-2 rounded-lg bg-slate-950/80 hover:bg-slate-950 text-slate-400 hover:text-slate-200 font-mono text-[10px] border border-slate-800 flex items-center justify-between transition-colors cursor-pointer"
                            >
                              <span className="flex items-center gap-1">
                                <span>{showDebugJsonViewer ? '▼' : '►'}</span>
                                <span>{currentLang === 'fa' ? 'پیش‌نمایش آنلاین خروجی JSON' : 'Interactive JSON Live Preview'}</span>
                              </span>
                              <span className="text-[9px] text-amber-400/80 font-mono">
                                {showDebugJsonViewer ? (currentLang === 'fa' ? 'بستن' : 'Close') : (currentLang === 'fa' ? 'نمایش' : 'View')}
                              </span>
                            </button>

                            {showDebugJsonViewer && (
                              <div className="space-y-2 p-2.5 rounded-xl bg-slate-950 border border-amber-500/30 transition-all">
                                <div className="flex items-center justify-between gap-2">
                                  <div className="relative flex-1">
                                    <Search className="absolute right-2.5 top-2 h-3 w-3 text-slate-500" />
                                    <input
                                      type="text"
                                      value={debugJsonSearchQuery}
                                      onChange={(e) => setDebugJsonSearchQuery(e.target.value)}
                                      placeholder={currentLang === 'fa' ? 'جستجو در نمادها (مثال: NVDA, GOLD, USD)...' : 'Search symbols...'}
                                      className="w-full pl-2 pr-7 py-1 bg-slate-900 border border-slate-800 rounded-lg text-[10px] text-slate-200 focus:outline-none focus:border-amber-500"
                                      dir={currentLang === 'fa' ? 'rtl' : 'ltr'}
                                    />
                                  </div>
                                  <button
                                    onClick={handleCopyMacroJson}
                                    title={currentLang === 'fa' ? 'کپی سریع' : 'Quick Copy'}
                                    className="p-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 transition-colors"
                                  >
                                    <Copy className="h-3 w-3" />
                                  </button>
                                </div>

                                <div className="max-h-60 overflow-y-auto p-2 bg-slate-900/90 rounded-lg text-[10px] font-mono text-emerald-300 border border-slate-800/80 leading-relaxed text-left selection:bg-emerald-900 selection:text-emerald-100">
                                  <pre className="whitespace-pre-wrap break-all dir-ltr">
                                    {JSON.stringify(
                                      getWallStreetMacroJson().filter((item) => {
                                        if (!debugJsonSearchQuery.trim()) return true;
                                        const q = debugJsonSearchQuery.toLowerCase();
                                        return (
                                          item.id.toLowerCase().includes(q) ||
                                          item.symbol.toLowerCase().includes(q) ||
                                          item.nameEn.toLowerCase().includes(q) ||
                                          item.nameFa.toLowerCase().includes(q) ||
                                          item.category.toLowerCase().includes(q)
                                        );
                                      }),
                                      null,
                                      2
                                    )}
                                  </pre>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* App Branding & Logo Footer */}
                    <div className="pt-2 pb-2 text-center flex flex-col items-center justify-center gap-1 opacity-90 border-t border-slate-800/40 mt-3">
                      <AppLogo className="h-9 w-9 rounded-xl shadow-md ring-1 ring-white/10" />
                      <div className="flex items-center gap-1.5 text-[11px] font-bold">
                        <span>Alarmer</span>
                        <span className="text-[9px] px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-400 font-mono">PRO</span>
                      </div>
                      <p className="text-[10px] text-slate-500 font-mono">Real-Time Market Alert Studio</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Bottom Nav: 
                  TAB LEFT (Index 0): HISTORY
                  TAB MIDDLE (Index 1 - DEFAULT & PROMINENT): ALERTS
                  TAB RIGHT (Index 2): SETTINGS
              */}
              <div className={`border-t ${isLight ? 'border-slate-200 bg-white' : 'border-slate-900 bg-slate-950'} px-6 py-2.5 flex items-center justify-around z-20`}>
                {/* 1. Left Tab: History */}
                <button
                  onClick={() => setMobileScreen('history')}
                  className={`flex flex-col items-center gap-1 transition-colors ${
                    mobileScreen === 'history' ? `${accentClass} font-bold` : 'text-slate-400 hover:text-slate-300'
                  }`}
                >
                  <Bell className="h-5 w-5" />
                  <span className="text-[10px]">{currentLang === 'fa' ? FA.history : 'History'}</span>
                </button>

                {/* 2. Middle Tab: Alerts (Default & Floating Prominent) */}
                <button
                  onClick={() => setMobileScreen('alerts')}
                  className={`flex flex-col items-center gap-1 transition-colors relative ${
                    mobileScreen === 'alerts' ? `${accentClass} font-bold` : 'text-slate-400 hover:text-slate-300'
                  }`}
                >
                  <div className={`h-10 w-10 -mt-4 rounded-full flex items-center justify-center shadow-xl transition-transform hover:scale-105 p-1.5 ${
                    mobileScreen === 'alerts' ? `${accentBgClass} text-slate-950 font-bold ring-2 ring-emerald-400/40` : 'bg-slate-800 text-slate-300'
                  }`}>
                    <AppLogo className="h-full w-full" withBackground={false} />
                  </div>
                  <span className="text-[10px] font-bold">{currentLang === 'fa' ? FA.myAlerts : 'My Alerts'}</span>
                </button>

                {/* 3. Right Tab: Settings */}
                <button
                  onClick={() => setMobileScreen('settings')}
                  className={`flex flex-col items-center gap-1 transition-colors ${
                    mobileScreen === 'settings' ? `${accentClass} font-bold` : 'text-slate-400 hover:text-slate-300'
                  }`}
                >
                  <SettingsIcon className="h-5 w-5" />
                  <span className="text-[10px]">{currentLang === 'fa' ? FA.settings : 'Settings'}</span>
                </button>
              </div>

              {/* Android Soft Nav Bar with Back Button (Move to Background) */}
              <div className={`py-1.5 px-10 flex items-center justify-between text-slate-500 ${isLight ? 'bg-slate-100 border-slate-200' : 'bg-slate-950 border-slate-900'} border-t z-20`}>
                <button
                  type="button"
                  title="دکمه برگشت اندروید (انتقال به پس‌زمینه بدون بستن برنامه)"
                  onClick={() => {
                    showToast('برنامه به پس‌زمینه منتقل شد؛ پایش و آلارم‌ها بدون وقفه در حال اجرا هستند (● Active)');
                  }}
                  className="hover:text-slate-200 transition-colors p-1 flex items-center gap-1 text-[11px] font-mono cursor-pointer"
                >
                  <span>◀</span>
                  <span className="text-[9px] text-slate-400">Back (Background)</span>
                </button>
                <div className="h-2 w-2 rounded-full border border-slate-500"></div>
                <div className="h-2.5 w-2.5 border border-slate-500 rounded-sm"></div>
              </div>
            </div>
          </div>

          {/* Right Explainer & Home Screen Widget */}
          <div className="lg:col-span-5 space-y-6">
            {/* Live Interactive Home Screen Widget Card */}
            <div className={`border rounded-3xl p-5 backdrop-blur-md ${isLight ? 'bg-white/95 border-slate-300 shadow-xl' : 'bg-slate-900/90 border-slate-800 shadow-2xl'} space-y-3.5`}>
              <div className="flex items-center justify-between border-b pb-3 border-slate-800/80">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-xl bg-violet-500/20 text-violet-400">
                    <LayoutGrid className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <span>ویجت زنده صفحه اصلی (Home Widget)</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-mono">
                        ● LIVE 24/7
                      </span>
                    </h3>
                    <p className="text-[11px] text-slate-400">رصد بلادرنگ وضعیت آلارم‌ها، نرخ زنده و فاصله تا هدف روی صفحه اصلی</p>
                  </div>
                </div>
                <button
                  onClick={() => {
                    rules.forEach((r) => evaluateRule(r));
                    showToast('🔄 تمام هشدارهای ویجت صفحه اصلی استعلام شدند.');
                  }}
                  className="p-1.5 rounded-xl border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition-all text-[11px] flex items-center gap-1 cursor-pointer"
                  title="استعلام فوری همه"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">بروزرسانی</span>
                </button>
              </div>

              {/* Active Rules List in the Widget */}
              <div className="space-y-2.5">
                {rules.slice(0, 4).map((rule) => {
                  const currentPrice = rule.lastCheckedPrice || rule.basePrice;
                  const badge = getRuleWidgetBadge(rule, currentPrice);
                  let targetProximity = 50;
                  if (rule.conditionType === 'PRICE_THRESHOLD' && rule.targetValue > 0) {
                    targetProximity = Math.min(100, Math.round((currentPrice / rule.targetValue) * 100));
                  } else if (rule.conditionType === 'PERCENT_CHANGE') {
                    const deltaPct = Math.abs(((currentPrice - rule.basePrice) / rule.basePrice) * 100);
                    targetProximity = Math.min(100, Math.round((deltaPct / rule.targetValue) * 100));
                  }

                  const isNearTarget = targetProximity >= 90;
                  const isTriggered = rule.isTriggered;

                  return (
                    <div
                      key={rule.uuid}
                      className={`p-3 rounded-2xl border transition-all ${
                        isTriggered
                          ? 'bg-rose-950/20 border-rose-500/40'
                          : isNearTarget
                          ? 'bg-amber-950/20 border-amber-500/40'
                          : 'bg-slate-950/70 border-slate-800/80 hover:border-slate-700'
                      }`}
                    >
                      {/* Top Header: Symbol, Exchange, Price, Badge */}
                      <div className="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-slate-800/50">
                        <div className="flex items-center gap-1.5 min-w-0 flex-1">
                          <span className="font-black text-xs text-white truncate">{rule.marketSymbol}</span>
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-mono font-bold shrink-0">
                            {formatExchangeTag(rule.exchangeName)}
                          </span>
                          {rule.ttsEnabled && (
                            <span className="text-[9px] px-1 py-0.2 rounded bg-violet-500/20 text-violet-300 flex items-center gap-0.5 font-semibold shrink-0" title="خوانش صوتی فعال">
                              <Volume2 className="h-2.5 w-2.5" />
                              <span>TTS</span>
                            </span>
                          )}
                        </div>
                        {(() => {
                          const isTmnRule = isTomanRule(rule);
                          return (
                            <div className="flex items-center gap-1.5 shrink-0" dir="ltr">
                              <span className="font-mono font-black text-xs text-white block">
                                {isTmnRule
                                  ? `${Math.round(currentPrice).toLocaleString('fa-IR')} تومان`
                                  : `$${currentPrice.toLocaleString(undefined, { minimumFractionDigits: currentPrice < 1 ? 4 : 2 })}`}
                              </span>
                              <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold border font-mono ${badge.bgClass}`}>
                                {badge.text}
                              </span>
                            </div>
                          );
                        })()}
                      </div>

                      {/* Progress Bar & Status */}
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-[10px] gap-2">
                          {(() => {
                            const isTmnRule = isTomanRule(rule);
                            return (
                              <span className="text-slate-400 truncate">
                                شرط: {rule.conditionType === 'PRICE_THRESHOLD'
                                  ? `${rule.direction === 'ABOVE' ? '≥' : '≤'} ${isTmnRule ? `${Math.round(rule.targetValue).toLocaleString('fa-IR')} تومان` : `$${rule.targetValue.toLocaleString()}`}`
                                  : `تغییر ${rule.targetValue}%`}
                              </span>
                            );
                          })()}
                          <span className={`font-mono font-bold text-[9.5px] shrink-0 ${isTriggered ? 'text-rose-400' : isNearTarget ? 'text-amber-400' : 'text-emerald-400'}`} dir="ltr">
                            {isTriggered ? 'Triggered' : isNearTarget ? `${targetProximity}% (Near)` : `${targetProximity}%`}
                          </span>
                        </div>
                        <div className="w-full bg-slate-800 rounded-full h-1 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${
                              isTriggered ? 'bg-rose-500' : isNearTarget ? 'bg-amber-500' : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.max(4, targetProximity)}%` }}
                          />
                        </div>
                      </div>

                      {/* Footer Actions */}
                      <div className="mt-2 pt-1 border-t border-slate-800/60 flex items-center justify-between text-[9.5px] text-slate-400">
                        <span className="font-mono text-slate-400">{formatTimeAgo(rule.lastCheckedAt || new Date())}</span>
                        <div className="flex items-center gap-1.5">
                          {rule.ttsEnabled && (
                            <button
                              onClick={() => testTtsSpeech(rule.baseCurrency, currentPrice)}
                              className="text-violet-400 hover:text-violet-300 font-semibold flex items-center gap-0.5 cursor-pointer text-[9.5px]"
                            >
                              <span>صدا</span>
                            </button>
                          )}
                          <button
                            onClick={() => evaluateRule(rule, 1.5)}
                            className="px-2 py-0.5 rounded-lg bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 font-bold cursor-pointer border border-emerald-500/30 text-[9.5px]"
                          >
                            تست
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="pt-1 flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-800">
                <span>📱 طراحی شده برای ویجت اندروید ۱۴ و iOS ۱۷</span>
                <span className="font-mono text-emerald-400 font-semibold">Real-Time Sync</span>
              </div>
            </div>

            <div className={`border rounded-2xl p-6 backdrop-blur-sm ${isLight ? 'bg-white/80 border-slate-200 shadow-sm' : 'bg-slate-900/60 border-slate-800'}`}>
              <h3 className="text-lg font-bold mb-3 flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-emerald-400" />
                <span>پلتفرم هشدار چندبازاره پیشرفته</span>
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed mb-4">
                طراحی دقیق، اصیل و کاربرپسند با پشتیبانی از بیش از ۴۰ صرافی کریپتو به همراه بازار اوراق قرضه خزانه‌داری آمریکا، جفت‌ارزهای فارکس، سهام‌های وال‌استریت و طلا:
              </p>
              
              <div className="space-y-3 text-xs">
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                  <div className="flex items-center gap-2 text-emerald-400 font-bold">
                    <Zap className="h-4 w-4" />
                    <span>⚡ بیش از ۴۰ صرافی با دسته‌بندی منطقه‌ای</span>
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    ⭐ جهانی رتبه یک (Binance, Coinbase, Kraken, Bybit, KuCoin) • 📊 اگریگیتورها (CoinGecko با ۱۰هزار کوین) • 🇮🇷 ایران (Nobitex, Wallex, Tabdeal, Ramzinex, Bitbarg) • ⛩️ آسیا • 🇪🇺 اروپا • 🌎 آمریکا.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                  <div className="flex items-center gap-2 text-blue-400 font-bold">
                    <Landmark className="h-4 w-4" />
                    <span>{currentLang === 'fa' ? '🏛️ بازارهای جهانی، اوراق قرضه و فارکس' : '🏛️ Global Markets, US Bonds & Forex'}</span>
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    {currentLang === 'fa'
                      ? 'اوراق قرضه ۱۰ ساله آمریکا (US10Y / ^TNX)، اوراق ۲ ساله و ۳۰ ساله، جفت‌ارزهای فارکس (EUR/USD, GBP/USD)، سهام‌های نزدک/نیویورک (انویدیا، اپل، تسلا)، طلا و نفت خام.'
                      : 'US 10-Year Treasury Yields (US10Y / ^TNX), 2Y & 30Y Bonds, Forex Pairs (EUR/USD, GBP/USD), Wall Street Equities (NVDA, AAPL, TSLA), Gold & Crude Oil.'}
                  </p>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                  <div className="flex items-center gap-2 text-purple-400 font-bold">
                    <Languages className="h-4 w-4" />
                    <span>🌍 ۱۰ زبان بین‌المللی و ۴ تم رنگی</span>
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    پشتیبانی کامل از فارسی، انگلیسی، آلمانی، فرانسوی، اسپانیایی، چینی، کره‌ای، کوردی، عربی و ترکی با تم‌های دارک/لایت سبز و نارنجی.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* DUAL-MODE MODAL: CHOICE OF MARKET */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-xl p-6 space-y-5 text-right relative shadow-2xl animate-in fade-in zoom-in-95">
            <button
              onClick={() => {
                setShowCreateModal(false);
                setCreatePath('NONE');
              }}
              className="absolute top-5 left-5 p-1.5 rounded-full text-slate-400 hover:text-white bg-slate-800/80"
            >
              <X className="h-4 w-4" />
            </button>

            {/* SCREEN 0: CHOOSE ENTRY PATH (کریپتو یا سهام/فارکس/اوراق) */}
            {createPath === 'NONE' && (
              <div className="space-y-4">
                <div>
                  <span className="text-xs text-emerald-400 font-bold block mb-1">گام نخست: انتخاب نوع بازار</span>
                  <h3 className="text-base font-bold text-white">مایلید برای کدام بازار هشدار تنظیم کنید؟</h3>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 pt-2">
                  {/* Option 1: Crypto (Previous Original Flow) */}
                  <button
                    onClick={() => {
                      setCreatePath('CRYPTO');
                      setCryptoStep(1);
                    }}
                    className="p-5 rounded-2xl border-2 border-slate-800 hover:border-emerald-500 bg-slate-950 hover:bg-emerald-500/5 text-right transition-all group relative overflow-hidden"
                  >
                    <div className="h-12 w-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                      <Zap className="h-6 w-6" />
                    </div>
                    <h4 className="font-bold text-sm text-white mb-1">⚡ بازار رمزارزها (کریپتو)</h4>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      بیش از ۴۰ صرافی معتبر بین‌المللی و ایرانی با چیپ‌های فیلتر، استخراج جفت‌ارزها و دکمه بروزرسانی
                    </p>
                    <div className="mt-3 flex items-center gap-1 text-[11px] font-bold text-emerald-400">
                      <span>ورود به بخش صرافی‌های کریپتو</span>
                      <span>←</span>
                    </div>
                  </button>

                  {/* Option 2: Stocks, Forex, US Bonds */}
                  <button
                    onClick={() => {
                      setCreatePath('STOCKS_MACRO');
                      setMacroStep(1);
                    }}
                    className="p-5 rounded-2xl border-2 border-slate-800 hover:border-blue-500 bg-slate-950 hover:bg-blue-500/5 text-right transition-all group relative overflow-hidden"
                  >
                    <div className="h-12 w-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                      <Landmark className="h-6 w-6" />
                    </div>
                    <h4 className="font-bold text-sm text-white mb-1">
                      {currentLang === 'fa' ? '🏛️ سهام، اوراق قرضه آمریکا و فارکس' : '🏛️ US Stocks, Treasury Bonds & Forex'}
                    </h4>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      {currentLang === 'fa'
                        ? 'اوراق قرضه ۱۰ ساله آمریکا (US10Y)، جفت‌ارزهای فارکس، سهام‌های نزدک/نیویورک، طلا و شاخص‌ها'
                        : 'US 10-Year Yields (US10Y), Forex pairs, Nasdaq/NYSE equities, Gold & Global Indices.'}
                    </p>
                    <div className="mt-3 flex items-center gap-1 text-[11px] font-bold text-blue-400">
                      <span>{currentLang === 'fa' ? 'ورود به بازارهای جهانی' : 'Enter Global Markets'}</span>
                      <span>{currentLang === 'fa' ? '←' : '→'}</span>
                    </div>
                  </button>
                </div>
              </div>
            )}

            {/* ======================================================== */}
            {/* PATH A: CRYPTO (دقیقاً با چیپ‌های فیلتر و بیش از ۴۰ صرافی) */}
            {/* ======================================================== */}
            {createPath === 'CRYPTO' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        if (cryptoStep > 1) {
                          setCryptoStep((cryptoStep - 1) as any);
                        } else {
                          setCreatePath('NONE');
                        }
                      }}
                      className="p-1 rounded-lg text-slate-400 hover:text-white bg-slate-800"
                    >
                      <ChevronLeft className="h-4 w-4 rotate-180" />
                    </button>
                    <div>
                      <span className="text-xs text-emerald-400 font-semibold block">مرحله {cryptoStep} از ۳ (رمزارزها)</span>
                      <h4 className="font-bold text-sm text-white">
                        {cryptoStep === 1 && (currentLang === 'fa' ? '۱. انتخاب از بین ۴۰+ صرافی' : '1. Select from 40+ Exchanges')}
                        {cryptoStep === 2 && (currentLang === 'fa' ? `۲. انتخاب جفت‌ارز (${selectedExchange.name})` : `2. Select Pair (${selectedExchange.name})`)}
                        {cryptoStep === 3 && (currentLang === 'fa' ? '۳. زمان‌بندی و شرط هشدار' : '3. Schedule & Alert Condition')}
                      </h4>
                    </div>
                  </div>
                </div>

                {/* Crypto Step 1: Exchange Filter Chips & 40+ Exchanges */}
                {cryptoStep === 1 && (
                  <div className="space-y-3 text-xs">
                    {/* Search */}
                    <input
                      type="text"
                      value={exchangeSearchQuery}
                      onChange={(e) => setExchangeSearchQuery(e.target.value)}
                      placeholder={currentLang === 'fa' ? "جستجوی صرافی (Binance, Nobitex, Wallex, KuCoin, OKX, Bybit, CoinGecko)..." : "Search exchange (Binance, Nobitex, Wallex, KuCoin, OKX, Bybit, CoinGecko)..."}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white placeholder:text-slate-500"
                    />

                    {/* Category Filter Chips */}
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 custom-scrollbar">
                      {[
                        { id: 'all', label: currentLang === 'fa' ? 'همه (۴۰+)' : 'All (40+)', icon: '🌐' },
                        { id: 'tier1', label: currentLang === 'fa' ? '⭐ جهانی رتبه یک' : '⭐ Tier 1 Global', icon: '⭐' },
                        { id: 'aggregator', label: currentLang === 'fa' ? '📊 اگریگیتورها' : '📊 Aggregators', icon: '📊' },
                        { id: 'middleEast', label: currentLang === 'fa' ? '🇮🇷 ایران و خاورمیانه' : '🇮🇷 Iran & M.East', icon: '🇮🇷' },
                        { id: 'asia', label: currentLang === 'fa' ? '⛩️ آسیا و شرق دور' : '⛩️ Asia & Far East', icon: '⛩️' },
                        { id: 'europe', label: currentLang === 'fa' ? '🇪🇺 اروپا' : '🇪🇺 Europe', icon: '🇪🇺' },
                        { id: 'americas', label: currentLang === 'fa' ? '🌎 آمریکا و سایر' : '🌎 Americas & Other', icon: '🌎' },
                      ].map((tab) => (
                        <button
                          key={tab.id}
                          onClick={() => setExchangeCategoryFilter(tab.id as any)}
                          className={`px-3 py-1.5 rounded-xl whitespace-nowrap text-[11px] font-bold transition-all flex items-center gap-1.5 ${
                            exchangeCategoryFilter === tab.id
                              ? 'bg-emerald-500 text-slate-950 shadow'
                              : 'bg-slate-950 text-slate-400 hover:text-white border border-slate-800'
                          }`}
                        >
                          <span>{tab.label}</span>
                        </button>
                      ))}
                    </div>

                    {/* Exchanges List */}
                    <div className="flex items-center justify-between text-[11px] text-slate-400 px-1 pt-1">
                      <span>فهرست صرافی‌ها (مرتب‌سازی الفبای انگلیسی):</span>
                      <span className="font-mono text-emerald-400 text-[10px] bg-slate-900 px-2 py-0.5 rounded border border-slate-800 font-bold">A → Z</span>
                    </div>
                    <div className="max-h-64 overflow-y-auto space-y-1.5 custom-scrollbar pr-1">
                      {filteredExchanges.map((ex) => (
                        <button
                          key={ex.id}
                          onClick={() => {
                            setSelectedExchange(ex);
                            setSelectedCounterCurrency(ex.defaultCounter || 'TMN');
                            setCryptoStep(2);
                          }}
                          className={`w-full p-3 rounded-2xl border text-right flex items-center justify-between transition-all ${
                            selectedExchange.id === ex.id
                              ? 'border-emerald-500 bg-emerald-500/10 text-white'
                              : 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700'
                          }`}
                        >
                          <div className="flex items-center gap-2.5">
                            <div className="h-8 w-8 rounded-xl bg-slate-900 border border-slate-700 flex items-center justify-center font-bold text-emerald-400">
                              {ex.name.charAt(0)}
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-sm text-white">{ex.name}</span>
                                <span className="text-[10px] text-slate-400">{ex.countryBadge}</span>
                              </div>
                              <div className="text-[10px] text-slate-500">
                                {ex.id === 'nobitex' ? (
                                  <span>جفت‌ارز مبنا: <strong className="text-emerald-400">تومان (TMN)</strong> • ۵۳۱+ جفت‌ارز زنده • نرخ تتر: <strong className="text-white font-mono">{Math.round(usdtTomanRate > 10000 ? usdtTomanRate : 267000).toLocaleString('fa-IR')} تومان</strong></span>
                                ) : (
                                  <span>جفت‌ارز مبنا: {ex.defaultCounter === 'TMN' ? 'تومان (TMN)' : ex.defaultCounter} • موجودی: ~{ex.pairsCount}</span>
                                )}
                              </div>
                            </div>
                          </div>
                          <span className="text-emerald-400 text-xs font-bold">انتخاب →</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Crypto Step 2: Select Pair & Manual Sync */}
                {cryptoStep === 2 && (
                  <div className="space-y-3 text-xs">
                    <div className="p-3 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                      <div>
                        <span className="text-slate-400 text-[10px] block">صرافی انتخاب‌شده:</span>
                        <div className="flex items-center gap-2">
                          <strong className="text-white text-xs font-bold">{selectedExchange.name}</strong>
                          {selectedExchange.id === 'nobitex' && (
                            <span className="px-2 py-0.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[10px] font-bold">
                              نمایش قیمت‌ها به تومان 🇮🇷
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => {
                          setIsSyncingPairs(true);
                          setTimeout(() => {
                            setIsSyncingPairs(false);
                            showToast(`لیست جفت‌ارزهای ${selectedExchange.name} به‌روزرسانی شد.`);
                          }, 500);
                        }}
                        disabled={isSyncingPairs}
                        className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-emerald-400 font-bold text-[11px] flex items-center gap-1.5 transition-all"
                      >
                        <RefreshCw className={`h-3 w-3 ${isSyncingPairs ? 'animate-spin' : ''}`} />
                        <span>{isSyncingPairs ? 'در حال بروزرسانی...' : '🔄 بروزرسانی لیست'}</span>
                      </button>
                    </div>

                    <input
                      type="text"
                      value={cryptoSearchQuery}
                      onChange={(e) => setCryptoSearchQuery(e.target.value)}
                      placeholder="جستجوی رمزارز (BTC, ETH, SOL, POL, S, RENDER, PEPE)..."
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                    />

                    <div className="max-h-56 overflow-y-auto space-y-1.5 custom-scrollbar">
                      {selectedExchange.pairsList
                        .filter(sym => !cryptoSearchQuery || sym.toLowerCase().includes(cryptoSearchQuery.toLowerCase()))
                        .map((sym) => {
                          const meta = cryptoPrices[sym] || { nameFa: sym, currentPrice: 1.0, icon: 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png' };
                          const counter = (selectedExchange.id === 'nobitex' && (!selectedCounterCurrency || selectedCounterCurrency === 'TMN' || selectedCounterCurrency === 'IRT'))
                            ? 'TMN'
                            : (selectedCounterCurrency || selectedExchange.defaultCounter);
                          const mkt = getCryptoMarketPrice(sym, selectedExchange.id, counter);
                          const isNobitexOrTmn = selectedExchange.id === 'nobitex' || mkt.unit === 'تومان' || counter === 'TMN';
                          const priceDisplay = isNobitexOrTmn
                            ? `${Math.round(mkt.price).toLocaleString('fa-IR')} تومان`
                            : `${mkt.unit}${mkt.price < 1 ? mkt.price.toFixed(6) : mkt.price.toLocaleString()}`;

                          return (
                            <button
                              key={sym}
                              onClick={() => {
                                setSelectedCryptoCoin(sym);
                                const curCounter = (selectedExchange.id?.toLowerCase().includes('nobitex') || !selectedCounterCurrency || selectedCounterCurrency === 'TMN' || selectedCounterCurrency === 'IRT') ? 'TMN' : (selectedCounterCurrency || selectedExchange.defaultCounter);
                                const liveMkt = getCryptoMarketPrice(sym, selectedExchange.id, curCounter);
                                const isTmnLocal = selectedExchange.id?.toLowerCase().includes('nobitex') || selectedExchange.id?.toLowerCase().includes('bonbast') || liveMkt.unit === 'تومان' || curCounter === 'TMN' || curCounter === 'IRT';
                                const liveValStr = isTmnLocal ? Math.round(liveMkt.price).toString() : (liveMkt.price < 1 ? liveMkt.price.toFixed(6) : liveMkt.price.toFixed(2));
                                setTargetValueStr(liveValStr);
                                setUpperPriceStr(isTmnLocal ? Math.round(liveMkt.high24h || liveMkt.price * 1.025).toString() : (liveMkt.high24h || liveMkt.price * 1.025).toFixed(2));
                                setLowerPriceStr(isTmnLocal ? Math.round(liveMkt.low24h || liveMkt.price * 0.975).toString() : (liveMkt.low24h || liveMkt.price * 0.975).toFixed(2));
                                setCryptoStep(3);
                              }}
                              className={`w-full p-2.5 rounded-2xl border text-right flex items-center justify-between transition-all ${
                                selectedCryptoCoin === sym
                                  ? 'border-emerald-500 bg-emerald-500/10 text-white'
                                  : 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700'
                              }`}
                            >
                              <div className="flex items-center gap-2.5">
                                <img src={meta.icon} alt={sym} className="h-7 w-7 rounded-full" />
                                <div>
                                  <div className="font-bold text-xs text-white">{meta.nameFa || sym} ({sym}/{counter})</div>
                                  <div className="text-[10px] text-emerald-400 font-mono font-bold">
                                    {priceDisplay}
                                  </div>
                                </div>
                              </div>
                              <span className="text-emerald-400 text-xs font-bold">انتخاب →</span>
                            </button>
                          );
                        })}

                      {selectedExchange.pairsList.filter(sym => !cryptoSearchQuery || sym.toLowerCase().includes(cryptoSearchQuery.toLowerCase())).length === 0 && cryptoSearchQuery.trim() && (
                        <button
                          type="button"
                          onClick={() => {
                            const customSym = cryptoSearchQuery.trim().toUpperCase();
                            setSelectedCryptoCoin(customSym);
                            const curCounter = (selectedExchange.id?.toLowerCase().includes('nobitex') || !selectedCounterCurrency || selectedCounterCurrency === 'TMN' || selectedCounterCurrency === 'IRT') ? 'TMN' : (selectedCounterCurrency || selectedExchange.defaultCounter);
                            const liveMkt = getCryptoMarketPrice(customSym, selectedExchange.id, curCounter);
                            const isTmnLocal = selectedExchange.id?.toLowerCase().includes('nobitex') || selectedExchange.id?.toLowerCase().includes('bonbast') || liveMkt.unit === 'تومان' || curCounter === 'TMN' || curCounter === 'IRT';
                            const liveValStr = isTmnLocal ? Math.round(liveMkt.price).toString() : (liveMkt.price < 1 ? liveMkt.price.toFixed(6) : liveMkt.price.toFixed(2));
                            setTargetValueStr(liveValStr);
                            setUpperPriceStr(isTmnLocal ? Math.round(liveMkt.high24h || liveMkt.price * 1.025).toString() : (liveMkt.high24h || liveMkt.price * 1.025).toFixed(2));
                            setLowerPriceStr(isTmnLocal ? Math.round(liveMkt.low24h || liveMkt.price * 0.975).toString() : (liveMkt.low24h || liveMkt.price * 0.975).toFixed(2));
                            setCryptoStep(3);
                          }}
                          className="w-full p-3 rounded-2xl border border-dashed border-emerald-500/50 bg-emerald-500/10 text-emerald-300 font-bold text-xs text-center hover:bg-emerald-500/20 transition-all"
                        >
                          + پایش دستی نماد {cryptoSearchQuery.trim().toUpperCase()} در صرافی {selectedExchange.name}
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* Crypto Step 3: Frequency & Condition */}
                {cryptoStep === 3 && (
                  <form onSubmit={handleCreateCryptoSubmit} className="space-y-4 text-xs">
                    {/* Selected Asset & Live Nobitex / Exchange Market Price Bar */}
                    {(() => {
                      const counter = (selectedExchange.id === 'nobitex' && (!selectedCounterCurrency || selectedCounterCurrency === 'TMN' || selectedCounterCurrency === 'IRT'))
                        ? 'TMN'
                        : (selectedCounterCurrency || selectedExchange.defaultCounter);
                      const mkt = getCryptoMarketPrice(selectedCryptoCoin, selectedExchange.id, counter);
                      const isTmn = selectedExchange.id === 'nobitex' || mkt.unit === 'تومان' || counter === 'TMN' || counter === 'IRT';
                      const meta = cryptoPrices[selectedCryptoCoin] || { nameFa: selectedCryptoCoin, icon: 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png' };
                      return (
                        <div className="p-3 rounded-2xl bg-gradient-to-r from-slate-900 to-slate-950 border border-emerald-500/30 flex items-center justify-between shadow-sm">
                          <div className="flex items-center gap-2.5">
                            <img src={meta.icon || 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png'} alt={selectedCryptoCoin} className="h-9 w-9 rounded-full border border-slate-700 p-0.5 bg-slate-950" />
                            <div>
                              <div className="flex items-center gap-1.5">
                                <span className="font-bold text-sm text-white">{meta.nameFa || selectedCryptoCoin} ({selectedCryptoCoin})</span>
                                <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-semibold">{selectedExchange.name}</span>
                              </div>
                              <div className="text-[10px] text-slate-400 mt-0.5">
                                {isTmn ? (
                                  <span>مبنای هشدار: <strong className="text-emerald-400">تومان ({selectedExchange.name})</strong></span>
                                ) : (
                                  <span>مبنای هشدار: <strong className="text-emerald-400">{counter}</strong></span>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="text-left" dir="ltr">
                            <span className="text-[10px] text-slate-400 block font-semibold">نرخ لحظه‌ای:</span>
                            <span className="font-mono font-black text-sm text-emerald-400">
                              {isTmn ? `${Math.round(mkt.price).toLocaleString('fa-IR')} تومان` : `$${mkt.price < 1 ? mkt.price.toFixed(6) : mkt.price.toLocaleString()}`}
                            </span>
                          </div>
                        </div>
                      );
                    })()}

                    <div>
                      <label className="block text-slate-300 font-bold mb-1.5">
                        ۱. دوره بررسی قیمت (Check Frequency):
                      </label>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 grid grid-cols-3 gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
                          {[
                            { key: 'seconds', label: 'ثانیه' },
                            { key: 'minutes', label: 'دقیقه' },
                            { key: 'hours', label: 'ساعت' },
                          ].map((item) => (
                            <button
                              type="button"
                              key={item.key}
                              onClick={() => setUnitType(item.key as any)}
                              className={`py-1.5 rounded-lg text-center font-bold text-[11px] transition-all ${
                                unitType === item.key
                                  ? 'bg-emerald-500 text-slate-950 shadow'
                                  : 'text-slate-400 hover:text-white'
                              }`}
                            >
                              {item.label}
                            </button>
                          ))}
                        </div>

                        <div className="w-24">
                          <input
                            type="number"
                            min="1"
                            max="3600"
                            value={unitNumber}
                            onChange={(e) => setUnitNumber(e.target.value)}
                            placeholder="1"
                            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-center text-white font-mono font-bold text-sm"
                          />
                        </div>
                      </div>

                      <div className="mt-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-semibold flex items-center gap-1.5">
                        <Timer className="h-3.5 w-3.5" />
                        <span>بررسی هر {formatCalculatedInterval(unitType, unitNumber)} انجام می‌شود.</span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-slate-300 font-bold mb-1.5">۲. نوع شرط هشدار:</label>
                      <div className="grid grid-cols-3 gap-1.5">
                        <button
                          type="button"
                          onClick={() => setConditionType('PERCENT_CHANGE')}
                          className={`py-2 rounded-xl border text-center font-bold text-[11px] ${
                            conditionType === 'PERCENT_CHANGE'
                              ? 'border-emerald-500 bg-emerald-500/10 text-emerald-400'
                              : 'border-slate-800 bg-slate-950 text-slate-400'
                          }`}
                        >
                          درصد تغییرات (%)
                        </button>
                        <button
                          type="button"
                          onClick={() => setConditionType('PRICE_THRESHOLD')}
                          className={`py-2 rounded-xl border text-center font-bold text-[11px] ${
                            conditionType === 'PRICE_THRESHOLD'
                              ? 'border-emerald-500 bg-emerald-500/10 text-emerald-400'
                              : 'border-slate-800 bg-slate-950 text-slate-400'
                          }`}
                        >
                          سقف / کف قیمت
                        </button>
                        <button
                          type="button"
                          onClick={() => setConditionType('VOLUME_SURGE')}
                          className={`py-2 rounded-xl border text-center font-bold text-[11px] ${
                            conditionType === 'VOLUME_SURGE'
                              ? 'border-amber-500 bg-amber-500/10 text-amber-400'
                              : 'border-slate-800 bg-slate-950 text-slate-400'
                          }`}
                        >
                          جهش حجم ۲۴h 📊
                        </button>
                      </div>
                    </div>

                    {conditionType === 'PERCENT_CHANGE' && (
                      <div className="space-y-2.5 p-3 rounded-2xl bg-slate-950 border border-slate-800">
                        <label className="block text-slate-400">جهت تغییر قیمت:</label>
                        <div className="grid grid-cols-3 gap-1.5">
                          <button
                            type="button"
                            onClick={() => setDirection('BOTH')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'BOTH' ? 'border-emerald-500 bg-emerald-500 text-slate-950' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            ± هر دو طرف
                          </button>
                          <button
                            type="button"
                            onClick={() => setDirection('ABOVE')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'ABOVE' ? 'border-emerald-500 bg-emerald-500 text-slate-950' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            ▲ فقط افزایش
                          </button>
                          <button
                            type="button"
                            onClick={() => setDirection('BELOW')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'BELOW' ? 'border-emerald-500 bg-emerald-500 text-slate-950' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            ▼ فقط کاهش
                          </button>
                        </div>

                        <div>
                          <label className="block text-slate-400 mb-1">درصد مد نظر برای هشدار (%):</label>
                          <input
                            type="number"
                            step="0.1"
                            value={targetValueStr}
                            onChange={(e) => setTargetValueStr(e.target.value)}
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white font-mono font-bold"
                            placeholder="مثال: 2.5"
                          />
                        </div>
                      </div>
                    )}

                    {conditionType === 'PRICE_THRESHOLD' && (
                      <div className="space-y-3 p-3 rounded-2xl bg-slate-950 border border-slate-800">
                        {/* 24h High & Low 1-Tap Auto-Fill Presets */}
                        {(() => {
                          const counter = (selectedExchange.id?.toLowerCase() === 'nobitex' && (!selectedCounterCurrency || selectedCounterCurrency === 'TMN' || selectedCounterCurrency === 'IRT'))
                            ? 'TMN'
                            : (selectedCounterCurrency || selectedExchange.defaultCounter);
                          const mkt = getCryptoMarketPrice(selectedCryptoCoin, selectedExchange.id, counter);
                          const curP = mkt.price;
                          const h24 = mkt.high24h || curP * 1.025;
                          const l24 = mkt.low24h || curP * 0.975;
                          const isTmn = selectedExchange.id?.toLowerCase() === 'nobitex' || mkt.unit === 'تومان' || counter === 'TMN' || counter === 'IRT';

                          return (
                            <div className="space-y-1">
                              <span className="text-[10px] text-slate-400 block font-semibold">
                                تک‌لمس سریع بر اساس سقف و کف روزانه ({selectedExchange.name} {isTmn ? 'به تومان' : ''}):
                              </span>
                              <div className="grid grid-cols-2 gap-2">
                                <button
                                  type="button"
                                  onClick={() => {
                                    const val = isTmn ? Math.round(h24).toString() : (h24 < 1 ? h24.toFixed(6) : h24.toFixed(2));
                                    if (direction === 'BOTH') {
                                      setUpperPriceStr(val);
                                    } else {
                                      setTargetValueStr(val);
                                      setDirection('ABOVE');
                                    }
                                  }}
                                  className="py-1.5 px-2 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 font-bold text-[10px] flex items-center justify-between transition-all"
                                >
                                  <span>🔼 سقف ۲۴h:</span>
                                  <span className="font-mono font-black">{isTmn ? `${Math.round(h24).toLocaleString('fa-IR')} تومان` : `$${h24.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const val = isTmn ? Math.round(l24).toString() : (l24 < 1 ? l24.toFixed(6) : l24.toFixed(2));
                                    if (direction === 'BOTH') {
                                      setLowerPriceStr(val);
                                    } else {
                                      setTargetValueStr(val);
                                      setDirection('BELOW');
                                    }
                                  }}
                                  className="py-1.5 px-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 font-bold text-[10px] flex items-center justify-between transition-all"
                                >
                                  <span>🔽 کف ۲۴h:</span>
                                  <span className="font-mono font-black">{isTmn ? `${Math.round(l24).toLocaleString('fa-IR')} تومان` : `$${l24.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}</span>
                                </button>
                              </div>
                            </div>
                          );
                        })()}

                        <label className="block text-slate-300 font-bold text-xs pt-1">جهت بررسی قیمت:</label>
                        <div className="grid grid-cols-3 gap-1.5">
                          <button
                            type="button"
                            onClick={() => setDirection('ABOVE')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'ABOVE' ? 'border-emerald-500 bg-emerald-500 text-slate-950' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            🔼 فقط حد بالا
                          </button>
                          <button
                            type="button"
                            onClick={() => setDirection('BELOW')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'BELOW' ? 'border-emerald-500 bg-emerald-500 text-slate-950' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            🔽 فقط حد پایین
                          </button>
                          <button
                            type="button"
                            onClick={() => setDirection('BOTH')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'BOTH' ? 'border-emerald-500 bg-emerald-500 text-slate-950' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            🔄 هر دو جهت
                          </button>
                        </div>

                        {direction === 'BOTH' ? (
                          <div className="space-y-3 pt-1">
                            {/* Both Way Behavior Toggle: OCO vs Dual-Active */}
                            <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1.5">
                              <label className="block text-[11px] font-bold text-slate-300">رفتار پس از اولین تاچ قیمت:</label>
                              <div className="grid grid-cols-2 gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => setBothWayBehavior('OCO')}
                                  className={`py-2 px-2 rounded-lg border text-[10px] font-bold transition-all text-center ${
                                    bothWayBehavior === 'OCO'
                                      ? 'border-amber-500 bg-amber-500/15 text-amber-300 shadow'
                                      : 'border-slate-800 bg-slate-950 text-slate-400'
                                  }`}
                                >
                                  <span>🛑 خروج با اولین تارگت (OCO)</span>
                                  <span className="block text-[9px] font-normal opacity-75 mt-0.5">بسته شدن با علامت ✅ Done</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setBothWayBehavior('DUAL_ACTIVE')}
                                  className={`py-2 px-2 rounded-lg border text-[10px] font-bold transition-all text-center ${
                                    bothWayBehavior === 'DUAL_ACTIVE'
                                      ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300 shadow'
                                      : 'border-slate-800 bg-slate-950 text-slate-400'
                                  }`}
                                >
                                  <span>🔄 پایش دائمی کانال</span>
                                  <span className="block text-[9px] font-normal opacity-75 mt-0.5">کانال باز می‌ماند (🔄 Active)</span>
                                </button>
                              </div>
                            </div>

                            {(() => {
                              const counter = (selectedExchange.id?.toLowerCase() === 'nobitex' && (!selectedCounterCurrency || selectedCounterCurrency === 'TMN' || selectedCounterCurrency === 'IRT'))
                                ? 'TMN'
                                : (selectedCounterCurrency || selectedExchange.defaultCounter);
                              const mkt = getCryptoMarketPrice(selectedCryptoCoin, selectedExchange.id, counter);
                              const isTmn = selectedExchange.id?.toLowerCase() === 'nobitex' || mkt.unit === 'تومان' || counter === 'TMN' || counter === 'IRT';
                              const h24 = mkt.high24h || mkt.price * 1.025;
                              const l24 = mkt.low24h || mkt.price * 0.975;

                              return (
                                <>
                                  <div className="p-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-2">
                                    <div className="flex items-center gap-1.5 text-emerald-400 font-bold text-xs">
                                      <span>🔼 حد بالا (مقاومت / سیو سود)</span>
                                    </div>
                                    <div>
                                      <label className="block text-[10px] text-slate-400 mb-0.5">
                                        {isTmn ? 'قیمت حد بالا (تومان):' : 'Upper Price (قیمت حد بالا):'}
                                      </label>
                                      <input
                                        type="number"
                                        step={isTmn ? "1" : "0.01"}
                                        value={upperPriceStr}
                                        onChange={(e) => setUpperPriceStr(e.target.value)}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-white font-mono font-bold text-xs"
                                        placeholder={isTmn ? `مثال: ${Math.round(h24)}` : "4.00"}
                                      />
                                      {isTmn && upperPriceStr && (
                                        <div className="text-[10px] text-emerald-400 font-mono mt-0.5 font-semibold">
                                          معادل: {Math.round(parseFloat(upperPriceStr) || 0).toLocaleString('fa-IR')} تومان
                                        </div>
                                      )}
                                    </div>
                                    <div>
                                      <label className="block text-[10px] text-slate-400 mb-0.5">Upper Note (یادداشت حد بالا):</label>
                                      <input
                                        type="text"
                                        value={upperNote}
                                        onChange={(e) => setUpperNote(e.target.value)}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-white text-xs"
                                        placeholder="«رسید به مقاومت، بررسی کن»"
                                      />
                                    </div>
                                  </div>

                                  <div className="p-2.5 rounded-xl border border-rose-500/30 bg-rose-500/5 space-y-2">
                                    <div className="flex items-center gap-1.5 text-rose-400 font-bold text-xs">
                                      <span>🔽 حد پایین (حمایت / حد ضرر)</span>
                                    </div>
                                    <div>
                                      <label className="block text-[10px] text-slate-400 mb-0.5">
                                        {isTmn ? 'قیمت حد پایین (تومان):' : 'Lower Price (قیمت حد پایین):'}
                                      </label>
                                      <input
                                        type="number"
                                        step={isTmn ? "1" : "0.01"}
                                        value={lowerPriceStr}
                                        onChange={(e) => setLowerPriceStr(e.target.value)}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-white font-mono font-bold text-xs"
                                        placeholder={isTmn ? `مثال: ${Math.round(l24)}` : "2.00"}
                                      />
                                      {isTmn && lowerPriceStr && (
                                        <div className="text-[10px] text-rose-400 font-mono mt-0.5 font-semibold">
                                          معادل: {Math.round(parseFloat(lowerPriceStr) || 0).toLocaleString('fa-IR')} تومان
                                        </div>
                                      )}
                                    </div>
                                    <div>
                                      <label className="block text-[10px] text-slate-400 mb-0.5">Lower Note (یادداشت حد پایین):</label>
                                      <input
                                        type="text"
                                        value={lowerNote}
                                        onChange={(e) => setLowerNote(e.target.value)}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-white text-xs"
                                        placeholder="«حمایت شکست، بفروش»"
                                      />
                                    </div>
                                  </div>
                                </>
                              );
                            })()}
                          </div>
                        ) : (
                          <div>
                            {(() => {
                              const counter = (selectedExchange.id?.toLowerCase() === 'nobitex' && (!selectedCounterCurrency || selectedCounterCurrency === 'TMN' || selectedCounterCurrency === 'IRT'))
                                ? 'TMN'
                                : (selectedCounterCurrency || selectedExchange.defaultCounter);
                              const mkt = getCryptoMarketPrice(selectedCryptoCoin, selectedExchange.id, counter);
                              const isTmn = selectedExchange.id?.toLowerCase() === 'nobitex' || mkt.unit === 'تومان' || counter === 'TMN' || counter === 'IRT';
                              return (
                                <>
                                  <label className="block text-slate-400 mb-1">
                                    {isTmn ? 'قیمت هدف (تومان):' : 'قیمت هدف (دلار):'}
                                  </label>
                                  <input
                                    type="number"
                                    step={isTmn ? "1" : "0.01"}
                                    value={targetValueStr}
                                    onChange={(e) => setTargetValueStr(e.target.value)}
                                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white font-mono font-bold"
                                    placeholder={isTmn ? `مثال: ${Math.round(mkt.price)}` : "مثال: 95000"}
                                  />
                                  {isTmn && targetValueStr && (
                                    <div className="text-[10px] text-emerald-400 font-mono mt-1 font-semibold">
                                      معادل: {Math.round(parseFloat(targetValueStr) || 0).toLocaleString('fa-IR')} تومان
                                    </div>
                                  )}
                                </>
                              );
                            })()}
                          </div>
                        )}
                      </div>
                    )}

                    {conditionType === 'VOLUME_SURGE' && (
                      <div className="space-y-3 p-3 rounded-2xl bg-slate-950 border border-slate-800">
                        <div className="flex items-center justify-between pb-1 border-b border-slate-800">
                          <span className="text-slate-400 text-xs">حجم پایه معاملات ۲۴ ساعته:</span>
                          <span className="text-white font-mono font-bold text-xs">
                            ${(((cryptoPrices[selectedCryptoCoin] || cryptoPrices.BTC) as any).volume24h
                              ? (((cryptoPrices[selectedCryptoCoin] || cryptoPrices.BTC) as any).volume24h / 1e9).toFixed(1) + 'B'
                              : '28.4B')}
                          </span>
                        </div>
                        <div>
                          <label className="block text-slate-300 font-bold mb-1.5 text-xs">میزان جهش نقدینگی مورد انتظار:</label>
                          <div className="grid grid-cols-3 gap-1.5 mb-2">
                            {['50', '100', '200'].map((p) => (
                              <button
                                key={p}
                                type="button"
                                onClick={() => setVolumePercentStr(p)}
                                className={`py-1.5 rounded-lg border font-bold text-[10px] transition-all ${
                                  volumePercentStr === p
                                    ? 'border-amber-500 bg-amber-500 text-slate-950 shadow'
                                    : 'border-slate-800 text-slate-400'
                                }`}
                              >
                                +{p}% {p === '100' ? '(۲ برابر ⚡)' : (p === '200' ? '(۳ برابر 🚀)' : '(۱.۵ برابر)')}
                              </button>
                            ))}
                          </div>
                          <input
                            type="number"
                            min="10"
                            max="5000"
                            value={volumePercentStr}
                            onChange={(e) => setVolumePercentStr(e.target.value)}
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white font-mono font-bold text-xs"
                            placeholder="درصد دلخواه (مثلاً: 100)"
                          />
                        </div>
                        <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[10px] flex items-center gap-1.5">
                          <Zap className="h-3.5 w-3.5 shrink-0" />
                          <span>ردپای نهنگ‌ها یا خریدهای سنگین به‌محض افزایش حجم شناسایی و اعلام صوتی می‌شود.</span>
                        </div>
                      </div>
                    )}

                    {/* Text-to-Speech (TTS) Voice Toggle */}
                    <div className="p-3 rounded-2xl bg-slate-950 border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Volume2 className={`h-4 w-4 ${ttsEnabled ? accentClass : 'text-slate-500'}`} />
                          <div>
                            <span className="font-bold text-xs text-white block">اعلام صوتی هوشمند (Text to Speech)</span>
                            <span className="text-[10px] text-slate-400 block">خوانش نام ارز و نرخ با صدای طبیعی هنگام وقوع هشدار</span>
                          </div>
                        </div>
                        <input
                          type="checkbox"
                          checked={ttsEnabled}
                          onChange={(e) => setTtsEnabled(e.target.checked)}
                          className="h-5 w-5 rounded border-slate-700 text-emerald-500 focus:ring-emerald-400 bg-slate-900 cursor-pointer"
                        />
                      </div>
                      {ttsEnabled && (
                        <div className="pt-1.5 flex justify-end">
                          <button
                            type="button"
                            onClick={() => testTtsSpeech(selectedCryptoCoin, cryptoPrices[selectedCryptoCoin]?.currentPrice || 83770)}
                            className="px-2.5 py-1 rounded-lg border border-slate-700 bg-slate-900 text-slate-300 text-[10px] font-semibold flex items-center gap-1.5 hover:text-white cursor-pointer"
                          >
                            <span>🗣️ تست نمونه صدای فارسی</span>
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => setCryptoStep(2)}
                        className="px-4 py-3 rounded-2xl bg-slate-800 text-slate-300 font-bold"
                      >
                        بازگشت
                      </button>
                      <button
                        type="submit"
                        className="flex-1 py-3 rounded-2xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition-all"
                      >
                        ذخیره و شروع بررسی هشدار کریپتو
                      </button>
                    </div>
                  </form>
                )}
              </div>
            )}

            {/* ======================================================== */}
            {/* PATH B: STOCKS, US BONDS & FOREX                         */}
            {/* ======================================================== */}
            {createPath === 'STOCKS_MACRO' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        if (macroStep > 1) {
                          setMacroStep((macroStep - 1) as any);
                        } else {
                          setCreatePath('NONE');
                        }
                      }}
                      className="p-1 rounded-lg text-slate-400 hover:text-white bg-slate-800"
                    >
                      <ChevronLeft className="h-4 w-4 rotate-180" />
                    </button>
                    <div>
                      <span className="text-xs text-blue-400 font-semibold block">
                        {currentLang === 'fa'
                          ? `مرحله ${macroStep} از ۲ (بازارهای جهانی و اوراق)`
                          : `Step ${macroStep} of 2 (Global Markets & Bonds)`}
                      </span>
                      <h4 className="font-bold text-sm text-white">
                        {macroStep === 1 && (currentLang === 'fa' ? '۱. انتخاب دارایی (اوراق قرضه، فارکس، سهام یا طلا)' : '1. Select Asset (Bonds, Forex, Equities or Gold)')}
                        {macroStep === 2 && (currentLang === 'fa' ? `۲. زمان‌بندی و شرط هشدار برای ${macroPrices[selectedMacroKey]?.nameFa}` : `2. Alert Schedule & Condition for ${macroPrices[selectedMacroKey]?.name || selectedMacroKey}`)}
                      </h4>
                    </div>
                  </div>
                </div>

                {/* Macro Step 1: Filter & Asset Cards */}
                {macroStep === 1 && (
                  <div className="space-y-3 text-xs">
                    <input
                      type="text"
                      value={macroSearchQuery}
                      onChange={(e) => setMacroSearchQuery(e.target.value)}
                      placeholder={currentLang === 'fa' ? "جستجوی نماد (US10Y, EUR/USD, NVDA, طلا, S&P 500)..." : "Search asset (US10Y, EUR/USD, NVDA, Gold, S&P 500)..."}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white placeholder:text-slate-500"
                    />

                    {/* Filter Tabs */}
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 custom-scrollbar">
                      {[
                        { id: 'all', label: currentLang === 'fa' ? 'همه دارایی‌ها' : 'All Assets', icon: '🌐' },
                        { id: 'iran_market', label: currentLang === 'fa' ? '💎 بن‌بست (ارز آزاد، طلا و سکه)' : '💎 Bonbast (Forex & Gold)', icon: '💎' },
                        { id: 'commodity', label: currentLang === 'fa' ? 'طلا و نفت جهانی' : 'Global Commodities', icon: '🪙' },
                        { id: 'forex', label: currentLang === 'fa' ? 'جفت‌ارزهای فارکس' : 'Forex Pairs', icon: '💱' },
                        { id: 'bond', label: currentLang === 'fa' ? 'اوراق قرضه آمریکا (US10Y)' : 'US Bonds (US10Y)', icon: '🏛️' },
                        { id: 'stock', label: currentLang === 'fa' ? 'سهام آمریکا (NASDAQ/NYSE)' : 'US Equities (NASDAQ/NYSE)', icon: '📈' },
                        { id: 'index', label: currentLang === 'fa' ? 'شاخص‌های کلان' : 'Global Indices', icon: '📊' },
                      ].map((tab) => (
                        <button
                          key={tab.id}
                          onClick={() => setMacroCategoryFilter(tab.id as any)}
                          className={`px-3 py-1.5 rounded-xl whitespace-nowrap text-[11px] font-bold transition-all flex items-center gap-1.5 ${
                            macroCategoryFilter === tab.id
                              ? 'bg-blue-500 text-white shadow'
                              : 'bg-slate-950 text-slate-400 hover:text-white border border-slate-800'
                          }`}
                        >
                          <span>{tab.icon}</span>
                          <span>{tab.label}</span>
                        </button>
                      ))}
                    </div>

                    <div className="max-h-64 overflow-y-auto space-y-1.5 custom-scrollbar pr-1">
                      {filteredMacroAssets.map(([key, asset]) => (
                        <button
                          key={key}
                          onClick={() => {
                            setSelectedMacroKey(key);
                            setMacroStep(2);
                          }}
                          className={`w-full p-2.5 rounded-2xl border text-right flex items-center justify-between transition-all ${
                            selectedMacroKey === key
                              ? 'border-blue-500 bg-blue-500/10 text-white'
                              : 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700'
                          }`}
                        >
                          <div className="flex items-center gap-2.5">
                            <img
                              src={asset.icon}
                              alt={asset.name}
                              className="h-8 w-8 rounded-full object-cover bg-slate-800 border border-slate-700 p-0.5"
                              onError={(e) => {
                                (e.target as any).src = 'https://cdn-icons-png.flaticon.com/512/2830/2830284.png';
                              }}
                            />
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-xs text-white">{asset.nameFa}</span>
                                <span className="text-[10px] font-mono text-slate-400">({asset.symbol})</span>
                              </div>
                              <div className="text-[10px] text-slate-400 mt-0.5 flex items-center gap-2">
                                <span className="text-blue-400 font-bold">{asset.marketName}</span>
                                <span>•</span>
                                <span className="font-mono font-bold text-slate-200">
                                  {asset.unit === '$'
                                    ? `$${asset.currentPrice.toLocaleString()}`
                                    : asset.unit === 'ت'
                                    ? `${Math.round(asset.currentPrice).toLocaleString('fa-IR')} تومان`
                                    : `${asset.currentPrice.toLocaleString()}${asset.unit}`}
                                </span>
                              </div>
                            </div>
                          </div>
                          <span className="text-blue-400 text-xs font-bold">انتخاب →</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Macro Step 2: Frequency & Condition */}
                {macroStep === 2 && (
                  <form onSubmit={handleCreateMacroSubmit} className="space-y-4 text-xs">
                    {(() => {
                      const meta = macroPrices[selectedMacroKey] || macroPrices.US10Y;
                      return (
                        <div className="p-3 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                          <div className="flex items-center gap-2.5">
                            <img src={meta.icon} alt={meta.name} className="h-8 w-8 rounded-full" />
                            <div>
                              <span className="text-white text-xs font-bold">{meta.nameFa}</span>
                              <span className="text-[10px] text-slate-400 block font-mono">
                                نرخ مبنا: {meta.unit === '$' ? `$${meta.currentPrice.toLocaleString()}` : `${meta.currentPrice.toLocaleString()}${meta.unit}`} ({meta.marketName})
                              </span>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => setMacroStep(1)}
                            className="text-blue-400 text-xs font-bold underline"
                          >
                            تغییر دارایی
                          </button>
                        </div>
                      );
                    })()}

                    <div>
                      <label className="block text-slate-300 font-bold mb-1.5">
                        ۱. دوره بررسی نرخ (Check Frequency):
                      </label>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 grid grid-cols-3 gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
                          {[
                            { key: 'seconds', label: 'ثانیه' },
                            { key: 'minutes', label: 'دقیقه' },
                            { key: 'hours', label: 'ساعت' },
                          ].map((item) => (
                            <button
                              type="button"
                              key={item.key}
                              onClick={() => setUnitType(item.key as any)}
                              className={`py-1.5 rounded-lg text-center font-bold text-[11px] transition-all ${
                                unitType === item.key
                                  ? 'bg-blue-500 text-white shadow'
                                  : 'text-slate-400 hover:text-white'
                              }`}
                            >
                              {item.label}
                            </button>
                          ))}
                        </div>

                        <div className="w-24">
                          <input
                            type="number"
                            min="1"
                            max="3600"
                            value={unitNumber}
                            onChange={(e) => setUnitNumber(e.target.value)}
                            placeholder="1"
                            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-center text-white font-mono font-bold text-sm"
                          />
                        </div>
                      </div>

                      <div className="mt-1.5 px-3 py-1.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 text-[11px] font-semibold flex items-center gap-1.5">
                        <Timer className="h-3.5 w-3.5" />
                        <span>بررسی هر {formatCalculatedInterval(unitType, unitNumber)} انجام می‌شود.</span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-slate-300 font-bold mb-1.5">۲. نوع شرط هشدار:</label>
                      <div className="grid grid-cols-3 gap-1.5">
                        <button
                          type="button"
                          onClick={() => setConditionType('PERCENT_CHANGE')}
                          className={`py-2 rounded-xl border text-center font-bold text-[11px] ${
                            conditionType === 'PERCENT_CHANGE'
                              ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                              : 'border-slate-800 bg-slate-950 text-slate-400'
                          }`}
                        >
                          درصد تغییرات (%)
                        </button>
                        <button
                          type="button"
                          onClick={() => setConditionType('PRICE_THRESHOLD')}
                          className={`py-2 rounded-xl border text-center font-bold text-[11px] ${
                            conditionType === 'PRICE_THRESHOLD'
                              ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                              : 'border-slate-800 bg-slate-950 text-slate-400'
                          }`}
                        >
                          سقف / کف نرخ
                        </button>
                        <button
                          type="button"
                          onClick={() => setConditionType('VOLUME_SURGE')}
                          className={`py-2 rounded-xl border text-center font-bold text-[11px] ${
                            conditionType === 'VOLUME_SURGE'
                              ? 'border-amber-500 bg-amber-500/10 text-amber-400'
                              : 'border-slate-800 bg-slate-950 text-slate-400'
                          }`}
                        >
                          جهش حجم ۲۴h 📊
                        </button>
                      </div>
                    </div>

                    {conditionType === 'PERCENT_CHANGE' && (
                      <div className="space-y-2.5 p-3 rounded-2xl bg-slate-950 border border-slate-800">
                        <label className="block text-slate-400">جهت تغییر نرخ:</label>
                        <div className="grid grid-cols-3 gap-1.5">
                          <button
                            type="button"
                            onClick={() => setDirection('BOTH')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'BOTH' ? 'border-blue-500 bg-blue-500 text-white' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            ± هر دو طرف
                          </button>
                          <button
                            type="button"
                            onClick={() => setDirection('ABOVE')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'ABOVE' ? 'border-blue-500 bg-blue-500 text-white' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            ▲ فقط افزایش
                          </button>
                          <button
                            type="button"
                            onClick={() => setDirection('BELOW')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'BELOW' ? 'border-blue-500 bg-blue-500 text-white' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            ▼ فقط کاهش
                          </button>
                        </div>

                        <div>
                          <label className="block text-slate-400 mb-1">درصد مد نظر برای هشدار (%):</label>
                          <input
                            type="number"
                            step="0.1"
                            value={targetValueStr}
                            onChange={(e) => setTargetValueStr(e.target.value)}
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white font-mono font-bold"
                            placeholder="مثال: 1.0"
                          />
                        </div>
                      </div>
                    )}

                    {conditionType === 'PRICE_THRESHOLD' && (
                      <div className="space-y-3 p-3 rounded-2xl bg-slate-950 border border-slate-800">
                        {/* 24h High & Low 1-Tap Auto-Fill Presets */}
                        {(() => {
                          const meta = macroPrices[selectedMacroKey] || macroPrices.US10Y;
                          const curP = meta.currentPrice;
                          const isTmn = meta.unit === 'ت' || meta.category === 'iran_market';
                          const h24 = isTmn ? Math.round(curP * 1.015) : curP * 1.02;
                          const l24 = isTmn ? Math.round(curP * 0.985) : curP * 0.98;
                          return (
                            <div className="space-y-1">
                              <span className="text-[10px] text-slate-400 block font-semibold">تک‌لمس سریع بر اساس سقف و کف روزانه {isTmn ? '(به تومان)' : ''}:</span>
                              <div className="grid grid-cols-2 gap-2">
                                <button
                                  type="button"
                                  onClick={() => {
                                    const val = isTmn ? h24.toString() : h24.toFixed(2);
                                    if (direction === 'BOTH') {
                                      setUpperPriceStr(val);
                                    } else {
                                      setTargetValueStr(val);
                                      setDirection('ABOVE');
                                    }
                                  }}
                                  className="py-1 px-2 rounded-xl bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 text-blue-400 font-bold text-[10px] flex items-center justify-between transition-all"
                                >
                                  <span>🔼 سقف ۲۴h:</span>
                                  <span className="font-mono font-black">{isTmn ? `${h24.toLocaleString('fa-IR')} تومان` : (meta.unit === '$' ? `$${h24.toFixed(2)}` : `${h24.toFixed(2)}${meta.unit}`)}</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const val = isTmn ? l24.toString() : l24.toFixed(2);
                                    if (direction === 'BOTH') {
                                      setLowerPriceStr(val);
                                    } else {
                                      setTargetValueStr(val);
                                      setDirection('BELOW');
                                    }
                                  }}
                                  className="py-1 px-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 font-bold text-[10px] flex items-center justify-between transition-all"
                                >
                                  <span>🔽 کف ۲۴h:</span>
                                  <span className="font-mono font-black">{isTmn ? `${l24.toLocaleString('fa-IR')} تومان` : (meta.unit === '$' ? `$${l24.toFixed(2)}` : `${l24.toFixed(2)}${meta.unit}`)}</span>
                                </button>
                              </div>
                            </div>
                          );
                        })()}

                        <label className="block text-slate-300 font-bold text-xs pt-1">جهت بررسی نرخ:</label>
                        <div className="grid grid-cols-3 gap-1.5">
                          <button
                            type="button"
                            onClick={() => setDirection('ABOVE')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'ABOVE' ? 'border-blue-500 bg-blue-500 text-white' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            🔼 فقط حد بالا
                          </button>
                          <button
                            type="button"
                            onClick={() => setDirection('BELOW')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'BELOW' ? 'border-blue-500 bg-blue-500 text-white' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            🔽 فقط حد پایین
                          </button>
                          <button
                            type="button"
                            onClick={() => setDirection('BOTH')}
                            className={`py-1.5 rounded-lg border font-bold text-[11px] ${
                              direction === 'BOTH' ? 'border-blue-500 bg-blue-500 text-white' : 'border-slate-800 text-slate-400'
                            }`}
                          >
                            🔄 هر دو جهت
                          </button>
                        </div>

                        {direction === 'BOTH' ? (
                          <div className="space-y-3 pt-1">
                            {/* Both Way Behavior Toggle: OCO vs Dual-Active */}
                            <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1.5">
                              <label className="block text-[11px] font-bold text-slate-300">رفتار پس از اولین تاچ نرخ:</label>
                              <div className="grid grid-cols-2 gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => setBothWayBehavior('OCO')}
                                  className={`py-2 px-2 rounded-lg border text-[10px] font-bold transition-all text-center ${
                                    bothWayBehavior === 'OCO'
                                      ? 'border-amber-500 bg-amber-500/15 text-amber-300 shadow'
                                      : 'border-slate-800 bg-slate-950 text-slate-400'
                                  }`}
                                >
                                  <span>🛑 خروج با اولین تارگت (OCO)</span>
                                  <span className="block text-[9px] font-normal opacity-75 mt-0.5">بسته شدن با علامت ✅ Done</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setBothWayBehavior('DUAL_ACTIVE')}
                                  className={`py-2 px-2 rounded-lg border text-[10px] font-bold transition-all text-center ${
                                    bothWayBehavior === 'DUAL_ACTIVE'
                                      ? 'border-blue-500 bg-blue-500/15 text-blue-300 shadow'
                                      : 'border-slate-800 bg-slate-950 text-slate-400'
                                  }`}
                                >
                                  <span>🔄 پایش دائمی کانال</span>
                                  <span className="block text-[9px] font-normal opacity-75 mt-0.5">کانال باز می‌ماند (🔄 Active)</span>
                                </button>
                              </div>
                            </div>

                            {(() => {
                              const meta = macroPrices[selectedMacroKey] || macroPrices.US10Y;
                              const isTmn = meta.unit === 'ت' || meta.category === 'iran_market';
                              const curP = meta.currentPrice;
                              return (
                                <>
                                  <div className="p-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-2">
                                    <div className="flex items-center gap-1.5 text-emerald-400 font-bold text-xs">
                                      <span>🔼 حد بالا (مقاومت / خروج سود)</span>
                                    </div>
                                    <div>
                                      <label className="block text-[10px] text-slate-400 mb-0.5">
                                        {isTmn ? 'نرخ حد بالا (تومان):' : 'Upper Price (نرخ حد بالا):'}
                                      </label>
                                      <input
                                        type="number"
                                        step={isTmn ? "1" : "0.01"}
                                        value={upperPriceStr}
                                        onChange={(e) => setUpperPriceStr(e.target.value)}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-white font-mono font-bold text-xs"
                                        placeholder={isTmn ? `مثال: ${Math.round(curP * 1.015)}` : "4.00"}
                                      />
                                      {isTmn && upperPriceStr && (
                                        <div className="text-[10px] text-emerald-400 font-mono mt-0.5 font-semibold">
                                          معادل: {Math.round(parseFloat(upperPriceStr) || 0).toLocaleString('fa-IR')} تومان
                                        </div>
                                      )}
                                    </div>
                                    <div>
                                      <label className="block text-[10px] text-slate-400 mb-0.5">Upper Note (یادداشت حد بالا):</label>
                                      <input
                                        type="text"
                                        value={upperNote}
                                        onChange={(e) => setUpperNote(e.target.value)}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-white text-xs"
                                        placeholder="«رسید به مقاومت، بررسی کن»"
                                      />
                                    </div>
                                  </div>

                                  <div className="p-2.5 rounded-xl border border-rose-500/30 bg-rose-500/5 space-y-2">
                                    <div className="flex items-center gap-1.5 text-rose-400 font-bold text-xs">
                                      <span>🔽 حد پایین (حمایت / حد ضرر)</span>
                                    </div>
                                    <div>
                                      <label className="block text-[10px] text-slate-400 mb-0.5">
                                        {isTmn ? 'نرخ حد پایین (تومان):' : 'Lower Price (نرخ حد پایین):'}
                                      </label>
                                      <input
                                        type="number"
                                        step={isTmn ? "1" : "0.01"}
                                        value={lowerPriceStr}
                                        onChange={(e) => setLowerPriceStr(e.target.value)}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-white font-mono font-bold text-xs"
                                        placeholder={isTmn ? `مثال: ${Math.round(curP * 0.985)}` : "2.00"}
                                      />
                                      {isTmn && lowerPriceStr && (
                                        <div className="text-[10px] text-rose-400 font-mono mt-0.5 font-semibold">
                                          معادل: {Math.round(parseFloat(lowerPriceStr) || 0).toLocaleString('fa-IR')} تومان
                                        </div>
                                      )}
                                    </div>
                                    <div>
                                      <label className="block text-[10px] text-slate-400 mb-0.5">Lower Note (یادداشت حد پایین):</label>
                                      <input
                                        type="text"
                                        value={lowerNote}
                                        onChange={(e) => setLowerNote(e.target.value)}
                                        className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-white text-xs"
                                        placeholder="«حمایت شکست، بفروش»"
                                      />
                                    </div>
                                  </div>
                                </>
                              );
                            })()}
                          </div>
                        ) : (
                          <div>
                            {(() => {
                              const meta = macroPrices[selectedMacroKey] || macroPrices.US10Y;
                              const isTmn = meta.unit === 'ت' || meta.category === 'iran_market';
                              const curP = meta.currentPrice;
                              return (
                                <>
                                  <label className="block text-slate-400 mb-1">
                                    {isTmn ? 'قیمت هدف (تومان):' : 'نرخ هدف:'}
                                  </label>
                                  <input
                                    type="number"
                                    step={isTmn ? "1" : "0.01"}
                                    value={targetValueStr}
                                    onChange={(e) => setTargetValueStr(e.target.value)}
                                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white font-mono font-bold"
                                    placeholder={isTmn ? `مثال: ${Math.round(curP)}` : "مثال: 4.50"}
                                  />
                                  {isTmn && targetValueStr && (
                                    <div className="text-[10px] text-emerald-400 font-mono mt-1 font-semibold">
                                      معادل: {Math.round(parseFloat(targetValueStr) || 0).toLocaleString('fa-IR')} تومان
                                    </div>
                                  )}
                                </>
                              );
                            })()}
                          </div>
                        )}
                      </div>
                    )}

                    {conditionType === 'VOLUME_SURGE' && (
                      <div className="space-y-3 p-3 rounded-2xl bg-slate-950 border border-slate-800">
                        <div className="flex items-center justify-between pb-1 border-b border-slate-800">
                          <span className="text-slate-400 text-xs">حجم پایه معاملات ۲۴ ساعته:</span>
                          <span className="text-white font-mono font-bold text-xs">$50.0M</span>
                        </div>
                        <div>
                          <label className="block text-slate-300 font-bold mb-1.5 text-xs">میزان جهش نقدینگی مورد انتظار:</label>
                          <div className="grid grid-cols-3 gap-1.5 mb-2">
                            {['50', '100', '200'].map((p) => (
                              <button
                                key={p}
                                type="button"
                                onClick={() => setVolumePercentStr(p)}
                                className={`py-1.5 rounded-lg border font-bold text-[10px] transition-all ${
                                  volumePercentStr === p
                                    ? 'border-amber-500 bg-amber-500 text-slate-950 shadow'
                                    : 'border-slate-800 text-slate-400'
                                }`}
                              >
                                +{p}% {p === '100' ? '(۲ برابر ⚡)' : (p === '200' ? '(۳ برابر 🚀)' : '(۱.۵ برابر)')}
                              </button>
                            ))}
                          </div>
                          <input
                            type="number"
                            min="10"
                            max="5000"
                            value={volumePercentStr}
                            onChange={(e) => setVolumePercentStr(e.target.value)}
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white font-mono font-bold text-xs"
                            placeholder="درصد دلخواه (مثلاً: 100)"
                          />
                        </div>
                        <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[10px] flex items-center gap-1.5">
                          <Zap className="h-3.5 w-3.5 shrink-0" />
                          <span>ردپای نهنگ‌ها یا خریدهای سنگین به‌محض افزایش حجم شناسایی و اعلام صوتی می‌شود.</span>
                        </div>
                      </div>
                    )}

                    {/* Text-to-Speech (TTS) Voice Toggle */}
                    <div className="p-3 rounded-2xl bg-slate-950 border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Volume2 className={`h-4 w-4 ${ttsEnabled ? accentClass : 'text-slate-500'}`} />
                          <div>
                            <span className="font-bold text-xs text-white block">اعلام صوتی هوشمند (Text to Speech)</span>
                            <span className="text-[10px] text-slate-400 block">خوانش نام دارایی و نرخ با صدای طبیعی هنگام وقوع هشدار</span>
                          </div>
                        </div>
                        <input
                          type="checkbox"
                          checked={ttsEnabled}
                          onChange={(e) => setTtsEnabled(e.target.checked)}
                          className="h-5 w-5 rounded border-slate-700 text-blue-500 focus:ring-blue-400 bg-slate-900 cursor-pointer"
                        />
                      </div>
                      {ttsEnabled && (
                        <div className="pt-1.5 flex justify-end">
                          <button
                            type="button"
                            onClick={() => testTtsSpeech(selectedMacroKey, macroPrices[selectedMacroKey]?.currentPrice || 4.28)}
                            className="px-2.5 py-1 rounded-lg border border-slate-700 bg-slate-900 text-slate-300 text-[10px] font-semibold flex items-center gap-1.5 hover:text-white cursor-pointer"
                          >
                            <span>🗣️ تست نمونه صدای فارسی</span>
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => setMacroStep(1)}
                        className="px-4 py-3 rounded-2xl bg-slate-800 text-slate-300 font-bold"
                      >
                        بازگشت
                      </button>
                      <button
                        type="submit"
                        className="flex-1 py-3 rounded-2xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm shadow-lg shadow-blue-500/20 transition-all"
                      >
                        ذخیره و شروع بررسی هشدار
                      </button>
                    </div>
                  </form>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 10 LANGUAGES PICKER MODAL */}
      {showLanguageModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-md p-6 space-y-4 text-right shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Languages className="h-5 w-5 text-emerald-400" />
                <h3 className="text-base font-bold text-white">انتخاب زبان برنامه (Language)</h3>
              </div>
              <button
                onClick={() => setShowLanguageModal(false)}
                className="p-1.5 rounded-full text-slate-400 hover:text-white bg-slate-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="max-h-80 overflow-y-auto space-y-1.5 custom-scrollbar pr-1">
              {SUPPORTED_LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => {
                    setCurrentLang(lang.code);
                    setShowLanguageModal(false);
                    showToast(`زبان به ${lang.name} تغییر یافت.`);
                  }}
                  className={`w-full p-3 rounded-2xl border text-right flex items-center justify-between transition-all ${
                    currentLang === lang.code
                      ? 'border-emerald-500 bg-emerald-500/10 text-white'
                      : 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{lang.flag}</span>
                    <div>
                      <span className="font-bold text-sm text-white block">{lang.name}</span>
                      <span className="text-[10px] text-slate-400">{lang.nameEn}</span>
                    </div>
                  </div>
                  {currentLang === lang.code && <Check className="h-4 w-4 text-emerald-400" />}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* RESTORE JSON MODAL */}
      {showRestoreModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-md p-6 space-y-4 text-right shadow-2xl">
            <h3 className="text-base font-bold text-white">بازیابی هشدارها از فایل JSON</h3>
            <p className="text-xs text-slate-400">متن خروجی بک‌آپ JSON را در کادر زیر قرار دهید:</p>
            <textarea
              rows={5}
              value={restoreJsonInput}
              onChange={(e) => setRestoreJsonInput(e.target.value)}
              placeholder="[{ ... }]"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 font-mono text-xs text-white"
            />
            <div className="flex items-center gap-2 pt-2">
              <button
                onClick={() => setShowRestoreModal(false)}
                className="px-4 py-2.5 rounded-xl bg-slate-800 text-slate-300 font-bold text-xs"
              >
                انصراف
              </button>
              <button
                onClick={handleRestoreBackup}
                className="flex-1 py-2.5 rounded-xl bg-emerald-500 text-slate-950 font-bold text-xs"
              >
                تأیید و بازیابی
              </button>
            </div>
          </div>
        </div>
      )}

      {/* HOME SCREEN WIDGET PREVIEW MODAL */}
      {showHomeWidgetModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-lg p-6 space-y-4 text-right shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-xl bg-violet-500/20 text-violet-400">
                  <LayoutGrid className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">پیش‌نمایش ویجت صفحه اصلی</h3>
                  <span className="text-[11px] text-slate-400 font-mono">Android & iOS 24/7 Home Widget</span>
                </div>
              </div>
              <button
                onClick={() => setShowHomeWidgetModal(false)}
                className="p-1 rounded-xl bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              این ویجت هوشمند را می‌توانید به صفحه اصلی گوشی (Homescreen) خود اضافه کنید تا بدون باز کردن برنامه، آخرین نوسانات بازار و وضعیت هشدارهای فعال را به صورت زنده رصد فرمایید:
            </p>

            {/* Widget Simulated Container */}
            <div className="p-4 rounded-3xl bg-slate-950 border-2 border-violet-500/30 shadow-xl space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="font-bold text-xs text-white">⚡ ALARMER • مانیتور زنده</span>
                </div>
                <div className="flex items-center gap-2 text-[10px] text-slate-400">
                  <span className="font-mono">{new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })}</span>
                  <button
                    onClick={() => {
                      rules.forEach((r) => evaluateRule(r));
                      showToast('بروزرسانی تمام قیمت‌های ویجت انجام شد.');
                    }}
                    className="p-1 rounded-lg bg-slate-800 text-slate-300 hover:text-white"
                    title="بروزرسانی زنده"
                  >
                    <RefreshCw className="h-3 w-3" />
                  </button>
                </div>
              </div>

              <div className="space-y-2 max-h-60 overflow-y-auto custom-scrollbar">
                {rules.map((rule) => {
                  const currentPrice = rule.lastCheckedPrice || rule.basePrice;
                  let targetProximity = 50;
                  if (rule.conditionType === 'PRICE_THRESHOLD' && rule.targetValue > 0) {
                    targetProximity = Math.min(100, Math.round((currentPrice / rule.targetValue) * 100));
                  } else if (rule.conditionType === 'PERCENT_CHANGE') {
                    const deltaPct = Math.abs(((currentPrice - rule.basePrice) / rule.basePrice) * 100);
                    targetProximity = Math.min(100, Math.round((deltaPct / rule.targetValue) * 100));
                  }

                  const isNearTarget = targetProximity >= 90;
                  const isTriggered = rule.isTriggered;

                  return (
                    <div
                      key={rule.uuid}
                      className="p-2.5 rounded-xl bg-slate-900 border border-slate-800/80 flex items-center justify-between text-xs"
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold text-white">{rule.marketSymbol}</span>
                          <span className="text-[9px] px-1 rounded bg-slate-800 text-slate-400">{formatExchangeTag(rule.exchangeName)}</span>
                          {rule.ttsEnabled && <Volume2 className="h-3 w-3 text-violet-400" />}
                        </div>
                        {(() => {
                          const isTmnRule = isTomanRule(rule);
                          return (
                            <div className="text-[10px] text-slate-400 flex items-center gap-1">
                              <span>هدف: {rule.conditionType === 'PRICE_THRESHOLD' ? (isTmnRule ? `${Math.round(rule.targetValue).toLocaleString('fa-IR')} تومان` : `$${rule.targetValue}`) : `${rule.targetValue}%`}</span>
                              <span>•</span>
                              <span className={isTriggered ? 'text-rose-400 font-bold' : isNearTarget ? 'text-amber-400 font-bold' : 'text-emerald-400'}>
                                {targetProximity}% تا هدف
                              </span>
                            </div>
                          );
                        })()}
                      </div>

                      <div className="text-right">
                        {(() => {
                          const isTmnRule = isTomanRule(rule);
                          return (
                            <span className="font-mono font-bold text-white block">
                              {isTmnRule ? `${Math.round(currentPrice).toLocaleString('fa-IR')} تومان` : `$${currentPrice.toLocaleString()}`}
                            </span>
                          );
                        })()}
                        <button
                          onClick={() => evaluateRule(rule, 1.5)}
                          className="text-[10px] text-emerald-400 hover:underline cursor-pointer"
                        >
                          تست آلارم
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-end pt-1">
              <button
                onClick={() => setShowHomeWidgetModal(false)}
                className="px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs"
              >
                بستن پنجره
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 1. FIRST-LAUNCH LANGUAGE SELECTION MODAL */}
      {showFirstLaunchLangModal && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700/80 rounded-3xl w-full max-w-md p-6 space-y-4 text-right shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
              <div className="p-2.5 rounded-2xl bg-emerald-500/20 text-emerald-400 text-2xl">
                🌍
              </div>
              <div>
                <h3 className="text-base font-bold text-white">انتخاب زبان برنامه / Select Language</h3>
                <p className="text-[11px] text-slate-400">۱۰ زبان بین‌المللی • بعداً در تنظیمات نیز قابل تغییر است</p>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              لطفاً زبان پیش‌فرض برنامه را انتخاب کنید:
            </p>

            <div className="grid grid-cols-2 gap-2 max-h-72 overflow-y-auto custom-scrollbar p-1">
              {SUPPORTED_LANGUAGES.map((l) => {
                const isSelected = currentLang === l.code;
                return (
                  <button
                    key={l.code}
                    onClick={() => setCurrentLang(l.code as any)}
                    className={`p-3 rounded-2xl border text-right transition-all flex items-center gap-2.5 ${
                      isSelected
                        ? 'border-emerald-500 bg-emerald-500/15 text-white shadow-md'
                        : 'border-slate-800 bg-slate-950 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <span className="text-2xl">{l.flag}</span>
                    <div className="overflow-hidden">
                      <span className="block font-bold text-xs truncate">{l.name}</span>
                      <span className="block text-[10px] text-slate-500 truncate">{l.nameEn}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="pt-2 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => {
                  localStorage.setItem('alarmer_lang_setup_done', 'true');
                  setShowFirstLaunchLangModal(false);
                  showToast(`زبان برنامه روی ${currentLangObj.name} تنظیم شد.`);
                }}
                className={`w-full py-3 rounded-xl font-bold text-xs shadow-lg transition-all ${accentBgClass} text-slate-950 hover:brightness-110 flex items-center justify-center gap-2`}
              >
                <span>تأیید و شروع به کار با آلارمر</span>
                <span>←</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2. OPTIONAL GOOGLE ACCOUNT MODAL (PREMIUM READY) */}
      {showGoogleModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4" dir={currentLangObj.dir}>
          <div className={`bg-slate-900 border border-slate-700/80 rounded-3xl w-full max-w-md p-6 space-y-4 ${currentLangObj.dir === 'rtl' ? 'text-right' : 'text-left'} shadow-2xl animate-in fade-in zoom-in-95`}>
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-2xl bg-white shadow-md">
                  <img
                    src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png"
                    alt="Google"
                    className="w-6 h-6"
                  />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                    <span>{tAuthTg.googleModalTitle}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-normal">
                      {tAuthTg.optionalBadge}
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400">{tAuthTg.googleModalSubtitle}</p>
                </div>
              </div>
              <button
                onClick={() => setShowGoogleModal(false)}
                className="p-1 rounded-xl bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {googleUser ? (
              <div className="space-y-4">
                <div className="p-4 rounded-2xl bg-amber-950/20 border border-amber-500/30 space-y-2">
                  <div className="flex items-center gap-3">
                    <div className="h-12 w-12 rounded-full bg-amber-500/20 border-2 border-amber-500 flex items-center justify-center text-xl">
                      👑
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-white">{googleUser.name}</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30">
                          {tAuthTg.vipEarlyAdopterBadge}
                        </span>
                      </div>
                      <span className="text-xs text-amber-400 font-mono block">{googleUser.email}</span>
                    </div>
                  </div>
                  <div className="pt-2 border-t border-slate-800/80 text-[11px] text-slate-300 leading-relaxed">
                    {tAuthTg.vipActiveDesc}
                  </div>
                </div>

                <div className="flex items-center justify-between gap-2 pt-2">
                  <button
                    onClick={() => {
                      setGoogleUser(null);
                      localStorage.removeItem('alarmer_google_user');
                      setShowGoogleModal(false);
                      showToast(tAuthTg.signedOutToast);
                    }}
                    className="flex-1 py-2.5 rounded-xl border border-rose-500/40 bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 font-bold text-xs"
                  >
                    {tAuthTg.signOutGoogleModalBtn}
                  </button>
                  <button
                    onClick={() => setShowGoogleModal(false)}
                    className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs"
                  >
                    {tAuthTg.closeBtn}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-xs text-slate-300 leading-relaxed">
                  {tAuthTg.modalIntro}
                </p>

                <div className="space-y-2 text-xs text-slate-300">
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center gap-2">
                    <span className="text-amber-400">👑</span>
                    <span>{tAuthTg.benefitVipDesc}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center gap-2">
                    <span className="text-blue-400">☁️</span>
                    <span>{tAuthTg.benefitCloudDesc}</span>
                  </div>
                </div>

                <div className="pt-2 space-y-2">
                  <button
                    onClick={() => {
                      const user = {
                        name: 'Mehran Aminpoor',
                        email: 'Mehran.Aminpoor@gmail.com',
                        isPremium: true,
                      };
                      setGoogleUser(user);
                      localStorage.setItem('alarmer_google_user', JSON.stringify(user));
                      setShowGoogleModal(false);
                      showToast(tAuthTg.signedInToast);
                    }}
                    className="w-full py-3 rounded-2xl bg-white hover:bg-slate-100 text-slate-900 font-bold text-xs flex items-center justify-center gap-2.5 shadow-lg transition-all"
                  >
                    <img
                      src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png"
                      alt="Google"
                      className="w-4 h-4"
                    />
                    <span>{tAuthTg.continueWithGoogleBtn} (Mehran.Aminpoor@gmail.com)</span>
                  </button>

                  <button
                    onClick={() => setShowGoogleModal(false)}
                    className="w-full py-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-800 text-slate-400 hover:text-white font-bold text-xs transition-all"
                  >
                    {tAuthTg.continueAsGuestBtn}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

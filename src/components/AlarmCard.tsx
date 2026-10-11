import React from 'react';
import { Volume2, Smartphone, Mic, Timer, RefreshCw, Trash2, Zap } from 'lucide-react';
import { AlertRule, formatExchangeTag, formatScaledPrice } from '../App';
import { FA } from '../i18n/fa';

export interface AlarmCardProps {
  rule: AlertRule;
  cryptoPrices: Record<string, any>;
  macroPrices: Record<string, any>;
  currentLang?: string;
  isLight?: boolean;
  isOrange?: boolean;
  checkingRuleId?: string | null;
  globalSoundEnabled?: boolean;
  globalVibrationEnabled?: boolean;
  globalTtsEnabled?: boolean;
  formatInterval?: (secs: number) => string;
  onToggle: (uuid: string) => void;
  onToggleFeedback: (uuid: string, type: 'sound' | 'vibration' | 'tts') => void;
  onManualCheck: (rule: AlertRule) => void;
  onDelete: (uuid: string) => void;
}

const defaultFormatInterval = (secs: number) => {
  if (secs >= 3600) return `${Math.round(secs / 3600)} ${FA.hour}`;
  if (secs >= 60) return `${Math.round(secs / 60)} ${FA.minute}`;
  return `${secs} ${FA.second}`;
};

export const AlarmCard: React.FC<AlarmCardProps> = ({
  rule,
  cryptoPrices,
  macroPrices,
  currentLang = 'fa',
  isLight = false,
  isOrange = false,
  checkingRuleId = null,
  globalSoundEnabled = true,
  globalVibrationEnabled = true,
  globalTtsEnabled = true,
  formatInterval = defaultFormatInterval,
  onToggle,
  onToggleFeedback,
  onManualCheck,
  onDelete,
}) => {
  // Always render alarm cards in LTR and English layout regardless of app language
  const isFa = false;
  let iconUrl = '';
  let displayName = rule.marketSymbol;
  const resolveUnit = (curr: string) => {
    const c = (curr || '').toUpperCase().trim();
    if (c === 'TMN' || c === 'IRT' || c === 'TOMAN' || curr === 'تومان' || curr === 'ت' || (rule.exchangeId && (rule.exchangeId.toLowerCase().includes('nobitex') || rule.exchangeId.toLowerCase().includes('bonbast')))) {
      return 'تومان';
    }
    if (c === 'IRR' || c === 'RLS' || curr === 'ریال') {
      return 'تومان';
    }
    return curr || '$';
  };

  let unit = '$';

  if (rule.marketType === 'crypto') {
    const meta = cryptoPrices[rule.baseCurrency] || cryptoPrices.BTC;
    iconUrl = meta?.icon || '';
    const nameFa = meta?.nameFa || rule.baseCurrency;
    displayName = isFa ? nameFa : rule.baseCurrency;
    unit = resolveUnit(rule.counterCurrency);
  } else {
    const meta = macroPrices[rule.baseCurrency] || macroPrices.US10Y;
    iconUrl = meta?.icon || '';
    const nameFa = meta?.nameFa || rule.baseCurrency;
    displayName = isFa ? nameFa : (meta?.name || rule.baseCurrency);
    unit = resolveUnit(meta?.unit || rule.counterCurrency || '$');
  }

  const isChecking = checkingRuleId === rule.uuid;
  let rawDisplayP = rule.lastCheckedPrice ?? rule.basePrice;
  let rawBaseP = rule.basePrice;
  let rawTargetV = rule.targetValue;
  let rawUpperP = rule.upperTargetPrice;
  let rawLowerP = rule.lowerTargetPrice;

  // Safety net: Normalize any raw Rial values to Tomans for Nobitex / Bonbast / Iranian currencies
  if (unit === 'تومان' || (rule.exchangeId && (rule.exchangeId.toLowerCase().includes('nobitex') || rule.exchangeId.toLowerCase().includes('bonbast')))) {
    unit = 'تومان';
    if (rule.baseCurrency === 'USDT' || rule.marketSymbol.startsWith('USDT')) {
      while (rawDisplayP > 150000) rawDisplayP = Math.round(rawDisplayP / 10.0);
      while (rawBaseP > 150000) rawBaseP = Math.round(rawBaseP / 10.0);
      while (rawTargetV > 150000) rawTargetV = Math.round(rawTargetV / 10.0);
      if (rawUpperP) { while (rawUpperP > 150000) rawUpperP = Math.round(rawUpperP / 10.0); }
      if (rawLowerP) { while (rawLowerP > 150000) rawLowerP = Math.round(rawLowerP / 10.0); }
    }
  }

  const displayP = rawDisplayP;

  // Market 24h Meta & Effective Percentage Calculation
  const marketMeta =
    rule.marketType === 'crypto'
      ? cryptoPrices[rule.baseCurrency] || cryptoPrices.BTC
      : macroPrices[rule.baseCurrency] || macroPrices.US10Y;

  const deltaFromBase =
    rule.basePrice > 0 ? ((displayP - rule.basePrice) / rule.basePrice) * 100 : 0;
  const effectivePct =
    Math.abs(deltaFromBase) > 0.01 ? deltaFromBase : (marketMeta?.change24h ?? 0);
  const isZero = Math.abs(effectivePct) < 0.005;
  const isPositive = effectivePct > 0.005;

  // Proximity Calculation (0 to 100%)
  let targetProximity = 50;
  if (rule.conditionType === 'PRICE_THRESHOLD' && rule.targetValue > 0) {
    targetProximity = Math.min(100, Math.round((displayP / rule.targetValue) * 100));
  } else if (rule.conditionType === 'PERCENT_CHANGE' && rule.targetValue > 0) {
    const deltaPct = Math.abs(((displayP - rule.basePrice) / rule.basePrice) * 100);
    targetProximity = Math.min(100, Math.round((deltaPct / rule.targetValue) * 100));
  }

  return (
    <div
      dir="ltr"
      className={`w-full max-w-full overflow-hidden p-3 rounded-2xl border transition-all shadow-sm h-[208px] flex flex-col justify-between ${
        isLight
          ? 'bg-white border-slate-200/90 shadow-slate-100'
          : rule.isActive
          ? 'bg-slate-900/90 border-slate-800 hover:border-slate-700/80 shadow-slate-950/30'
          : 'bg-slate-950/40 border-slate-900/60 opacity-60'
      }`}
    >
      {/* 1. Header: Icon + Dedicated Wide Title & Exchange + Toggle Switch */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
          <div className="relative shrink-0">
            <img
              src={iconUrl}
              alt={displayName}
              className="h-8.5 w-8.5 rounded-xl object-cover border border-slate-700/70 p-0.5 bg-slate-950 shrink-0"
              onError={(e) => {
                (e.target as any).src =
                  'https://cdn-icons-png.flaticon.com/512/2830/2830284.png';
              }}
            />
            <span
              className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-slate-900 ${
                rule.isActive ? 'bg-emerald-500 ring-1 ring-emerald-500/30' : 'bg-slate-600'
              }`}
            />
          </div>

          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="flex items-center gap-1.5 min-w-0">
              <span
                className="font-black text-xs text-white truncate max-w-full"
                title={displayName}
              >
                {displayName}
              </span>
              <span dir="ltr" className="text-[10px] font-mono text-slate-400 shrink-0 font-semibold">
                {rule.marketSymbol}
              </span>
            </div>
            <div className="flex items-center gap-1 mt-0.5 min-w-0">
              <span dir="ltr" className="px-1.5 py-0.5 rounded text-[8.5px] font-bold tracking-wider bg-slate-800/90 text-slate-300 border border-slate-700/50 shrink-0 font-mono truncate max-w-[120px]">
                {formatExchangeTag(rule.exchangeName)}
              </span>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => onToggle(rule.uuid)}
          className={`w-8 h-4.5 rounded-full transition-colors relative cursor-pointer shrink-0 ${
            rule.isActive
              ? isOrange
                ? 'bg-orange-500'
                : 'bg-emerald-500'
              : 'bg-slate-800 border border-slate-700'
          }`}
          title={rule.isActive ? FA.on : FA.off}
        >
          <div
            className={`absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white transition-all ${
              rule.isActive ? 'right-0.5' : 'left-0.5'
            }`}
          />
        </button>
      </div>

      {/* 2. Financial Metrics Bar: Live Price + Strikethrough Base Price + Percent/Done Badge */}
      <div className="flex items-center justify-between gap-2 min-w-0 py-0.5">
        <div className="min-w-0 flex-1 overflow-hidden" dir="ltr">
          <div className="h-3 text-[10px] font-mono text-slate-400 truncate">
            {rule.basePrice > 0 && Math.abs(displayP - rule.basePrice) > 1e-8 ? (
              <span className="line-through">
                {formatScaledPrice(rule.basePrice, rule.counterCurrency) ??
                  (rule.counterCurrency === '%' || unit === '%'
                    ? `${rule.basePrice.toFixed(2)}%`
                    : unit === '$'
                    ? `$${
                        rule.basePrice >= 1000
                          ? (rule.basePrice % 1 === 0 ? rule.basePrice.toLocaleString('en-US') : rule.basePrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
                          : rule.basePrice < 1
                          ? rule.basePrice.toFixed(5)
                          : rule.basePrice.toFixed(2)
                      }`
                    : `${
                        rule.basePrice >= 1000
                          ? (rule.basePrice % 1 === 0 ? rule.basePrice.toLocaleString('en-US') : rule.basePrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
                          : rule.basePrice.toFixed(2)
                      } ${unit}`)}
              </span>
            ) : null}
          </div>
          <div className="text-[15px] font-black font-mono tracking-tight text-white leading-tight truncate">
            {formatScaledPrice(displayP, rule.counterCurrency) ??
              (rule.counterCurrency === '%' || unit === '%'
                ? `${displayP.toFixed(2)}%`
                : unit === '$'
                ? `$${
                    displayP >= 1000
                      ? (displayP % 1 === 0 ? displayP.toLocaleString('en-US') : displayP.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
                      : displayP < 1
                      ? displayP.toFixed(5)
                      : displayP.toFixed(2)
                  }`
                : `${
                    displayP >= 1000
                      ? (displayP % 1 === 0 ? displayP.toLocaleString('en-US') : displayP.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
                      : displayP.toFixed(2)
                  } ${unit}`)}
          </div>
        </div>

        <div className="shrink-0" dir="ltr">
          {rule.isTriggered ? (
            <span dir="ltr" className="inline-block px-2 py-0.5 rounded text-[9.5px] font-mono font-bold bg-amber-500/15 border border-amber-500/30 text-amber-400">
              Done
            </span>
          ) : (
            <span
              dir="ltr"
              className={`inline-block px-2 py-0.5 rounded text-[9.5px] font-mono font-bold ${
                isZero
                  ? 'bg-slate-800 text-slate-400'
                  : isPositive
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : 'bg-rose-500/15 text-rose-400'
              }`}
            >
              {isZero ? '• ' : isPositive ? '+' : ''}
              {effectivePct.toFixed(2)}%
            </span>
          )}
        </div>
      </div>

      {/* Middle: Target Proximity Progress Strip */}
      <div className="my-2 bg-slate-950/70 p-2 rounded-xl border border-slate-800/50 min-w-0 overflow-hidden">
        <div className="flex items-center justify-between text-[10.5px] mb-1.5 gap-2 min-w-0">
          <div className="flex items-center gap-1 text-slate-300 min-w-0 flex-1 overflow-hidden">
            <Zap className="h-3 w-3 text-amber-400 shrink-0" />
            <span className="font-semibold truncate min-w-0">
              {rule.conditionType === 'PERCENT_CHANGE' ? (
                isFa ? (
                  <span>
                    {FA.rateChange}{' '}
                    <span dir="ltr" className="font-mono">
                      {rule.direction === 'BOTH' ? '±' : rule.direction === 'ABOVE' ? '+' : '-'}
                      {rule.targetValue}%
                    </span>
                  </span>
                ) : (
                  <span>
                    Rate Change{' '}
                    <span dir="ltr" className="font-mono">
                      {rule.direction === 'BOTH' ? '±' : rule.direction === 'ABOVE' ? '+' : '-'}
                      {rule.targetValue}%
                    </span>
                  </span>
                )
              ) : rule.direction === 'BOTH' ? (
                isFa ? (
                  <span>
                    {FA.high}{' '}
                    <span dir="ltr" className="font-mono">
                      {rawUpperP?.toLocaleString() ?? '—'}
                    </span>{' '}
                    | {FA.low}{' '}
                    <span dir="ltr" className="font-mono">
                      {rawLowerP?.toLocaleString() ?? '—'}
                    </span>
                  </span>
                ) : (
                  <span>
                    High:{' '}
                    <span dir="ltr" className="font-mono">
                      {rawUpperP?.toLocaleString() ?? '—'}
                    </span>{' '}
                    | Low:{' '}
                    <span dir="ltr" className="font-mono">
                      {rawLowerP?.toLocaleString() ?? '—'}
                    </span>
                  </span>
                )
              ) : isFa ? (
                <span>
                  {FA.target} {rule.direction === 'ABOVE' ? FA.above : FA.below}{' '}
                  <span dir="ltr" className="font-mono">
                    {formatScaledPrice(rawTargetV, rule.counterCurrency) ??
                      (rule.counterCurrency === '%' || unit === '%' ? (
                        <>{rawTargetV.toFixed(2)}%</>
                      ) : (
                        <>
                          {rawTargetV.toLocaleString()} {unit}
                        </>
                      ))}
                  </span>
                </span>
              ) : (
                <span>
                  Target: {rule.direction === 'ABOVE' ? 'Above' : 'Below'}{' '}
                  <span dir="ltr" className="font-mono">
                    {formatScaledPrice(rawTargetV, rule.counterCurrency) ??
                      (rule.counterCurrency === '%' || unit === '%' ? (
                        <>{rawTargetV.toFixed(2)}%</>
                      ) : (
                        <>
                          {unit === '$' ? `$${rawTargetV.toLocaleString()}` : `${rawTargetV.toLocaleString()} ${unit}`}
                        </>
                      ))}
                  </span>
                </span>
              )}
            </span>
          </div>
          <span
            dir="ltr"
            className={`font-mono font-bold text-[9.5px] shrink-0 ${
              rule.isTriggered
                ? 'text-amber-400'
                : targetProximity >= 85
                ? 'text-amber-400'
                : 'text-emerald-400'
            }`}
          >
            {rule.isTriggered
              ? 'Done'
              : rule.conditionType === 'PERCENT_CHANGE' && rule.direction === 'BOTH'
              ? 'Active'
              : `${targetProximity}%`}
          </span>
        </div>
        <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              targetProximity >= 85
                ? 'bg-gradient-to-r from-emerald-500 to-amber-400'
                : 'bg-emerald-500'
            }`}
            style={{ width: `${Math.max(4, targetProximity)}%` }}
          />
        </div>
      </div>

      {/* Footer: Compact Toggle Chips (Sound, Vibe, Voice) + Interval & Actions */}
      <div className="flex items-center justify-between text-[10px] pt-1 gap-1.5 flex-nowrap min-w-0">
        {/* Left: Feedback Notification Badges */}
        <div className="flex items-center gap-1 min-w-0 flex-nowrap shrink-0">
          {/* Sound */}
          <button
            type="button"
            onClick={() => onToggleFeedback(rule.uuid, 'sound')}
            title={
              !globalSoundEnabled
                ? FA.globalSoundDisabled
                : (rule.soundEnabled ?? true)
                ? FA.soundEnabled
                : FA.soundDisabled
            }
            className={`h-6 px-1.5 rounded-lg flex items-center gap-1 font-mono text-[9px] transition-all cursor-pointer border ${
              !globalSoundEnabled
                ? 'bg-slate-900 border-slate-800 text-slate-500 opacity-50'
                : (rule.soundEnabled ?? true)
                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400 font-bold'
                : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-400'
            }`}
          >
            <Volume2 className="h-2.5 w-2.5 shrink-0" />
            <span>{isFa ? FA.sound : 'Snd'}</span>
          </button>

          {/* Vibration */}
          <button
            type="button"
            onClick={() => onToggleFeedback(rule.uuid, 'vibration')}
            title={
              !globalVibrationEnabled
                ? FA.globalVibeDisabled
                : (rule.vibrationEnabled ?? true)
                ? FA.vibeEnabled
                : FA.vibeDisabled
            }
            className={`h-6 px-1.5 rounded-lg flex items-center gap-1 font-mono text-[9px] transition-all cursor-pointer border ${
              !globalVibrationEnabled
                ? 'bg-slate-900 border-slate-800 text-slate-500 opacity-50'
                : (rule.vibrationEnabled ?? true)
                ? 'bg-amber-500/15 border-amber-500/40 text-amber-400 font-bold'
                : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-400'
            }`}
          >
            <Smartphone className="h-2.5 w-2.5 shrink-0" />
            <span>{isFa ? FA.vibration : 'Vib'}</span>
          </button>

          {/* Voice */}
          <button
            type="button"
            onClick={() => onToggleFeedback(rule.uuid, 'tts')}
            title={
              !globalTtsEnabled
                ? FA.globalVoiceDisabled
                : (rule.ttsEnabled ?? true)
                ? FA.voiceEnabled
                : FA.voiceDisabled
            }
            className={`h-6 px-1.5 rounded-lg flex items-center gap-1 font-mono text-[9px] transition-all cursor-pointer border ${
              !globalTtsEnabled
                ? 'bg-slate-900 border-slate-800 text-slate-500 opacity-50'
                : (rule.ttsEnabled ?? true)
                ? 'bg-violet-500/15 border-violet-500/40 text-violet-400 font-bold'
                : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-400'
            }`}
          >
            <Mic className="h-2.5 w-2.5 shrink-0" />
            <span>{isFa ? FA.voice : 'TTS'}</span>
          </button>
        </div>

        {/* Right: Timer Interval + Refresh Check & Delete */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span dir="ltr" className="text-[9.5px] font-mono text-slate-400 flex items-center gap-0.5">
            <Timer className="h-2.5 w-2.5 text-slate-500 shrink-0" />
            <span>{formatInterval(rule.checkIntervalSeconds)}</span>
          </span>

          <button
            onClick={() => onManualCheck(rule)}
            disabled={isChecking}
            className="h-6 px-2 rounded-lg bg-slate-800 hover:bg-slate-700/80 text-emerald-400 flex items-center gap-1 text-[9.5px] font-bold border border-slate-700/60 transition-all cursor-pointer shrink-0"
            title={isFa ? FA.checkNow : 'Check Now'}
          >
            <RefreshCw className={`h-2.5 w-2.5 shrink-0 ${isChecking ? 'animate-spin' : ''}`} />
            <span>{isFa ? FA.check : 'Check'}</span>
          </button>

          <button
            onClick={() => onDelete(rule.uuid)}
            className="h-6 w-6 flex items-center justify-center rounded-lg hover:bg-rose-500/15 text-slate-500 hover:text-rose-400 transition-all cursor-pointer shrink-0"
            title={isFa ? FA.deleteAlert : 'Delete'}
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default AlarmCard;

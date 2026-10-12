import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Volume2, Smartphone, Mic, Timer, RefreshCw, Trash2, Zap, Power } from 'lucide-react';
import { AlertRule, formatExchangeTag, formatScaledPrice } from '../App';
import { FA } from '../i18n/fa';
import { getSymbolEnglishFullName } from '../utils/symbolNames';

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

/**
 * Renders price with custom sizing for Iranian currency units ("تومان" / "IRT" / "TMN").
 * Keeps numeric digits large, sharp, and prominent, while the currency label is noticeably smaller.
 */
export const renderFormattedPrice = (
  price: number,
  unit: string,
  counterCurr?: string,
  isBase = false
) => {
  const scaled = formatScaledPrice(price, counterCurr);
  if (scaled) {
    return <span>{scaled}</span>;
  }

  if (counterCurr === '%' || unit === '%') {
    return <span>{price.toFixed(2)}%</span>;
  }

  if (unit === '$') {
    const formatted =
      price >= 1000
        ? price % 1 === 0
          ? price.toLocaleString('en-US')
          : price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : price < 1
        ? price.toFixed(5)
        : price.toFixed(2);
    return <span>${formatted}</span>;
  }

  const isToman =
    unit === 'تومان' ||
    unit === 'ت' ||
    unit === 'IRT' ||
    unit === 'TMN' ||
    unit === 'TOMAN';

  const formattedNum =
    price >= 1000
      ? price % 1 === 0
        ? price.toLocaleString('en-US')
        : price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : price.toFixed(2);

  if (isToman) {
    const displayUnit = unit === 'IRT' || unit === 'TMN' ? 'IRT' : 'تومان';
    return (
      <span className="inline-flex items-baseline gap-1" dir="ltr">
        <span>{formattedNum}</span>
        <span
          className={`${
            isBase ? 'text-[8px]' : 'text-[9.5px]'
          } font-normal text-slate-400 select-none tracking-normal`}
        >
          {displayUnit}
        </span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-baseline gap-1" dir="ltr">
      <span>{formattedNum}</span>
      <span
        className={`${
          isBase ? 'text-[8px]' : 'text-[9.5px]'
        } font-normal text-slate-400 select-none`}
      >
        {unit}
      </span>
    </span>
  );
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
  const isFa = false; // Always render alarm cards in clean LTR financial layout
  let iconUrl = '';

  const resolveUnit = (curr: string) => {
    const c = (curr || '').toUpperCase().trim();
    if (
      c === 'TMN' ||
      c === 'IRT' ||
      c === 'TOMAN' ||
      curr === 'تومان' ||
      curr === 'ت' ||
      (rule.exchangeId &&
        (rule.exchangeId.toLowerCase().includes('nobitex') ||
          rule.exchangeId.toLowerCase().includes('bonbast')))
    ) {
      return 'تومان';
    }
    if (c === 'IRR' || c === 'RLS' || curr === 'ریال') {
      return 'تومان';
    }
    return curr || '$';
  };

  let unit = '$';
  let marketMeta: any = null;

  if (rule.marketType === 'crypto') {
    marketMeta = cryptoPrices[rule.baseCurrency] || cryptoPrices.BTC;
    iconUrl = marketMeta?.icon || '';
    unit = resolveUnit(rule.counterCurrency);
  } else {
    marketMeta = macroPrices[rule.baseCurrency] || macroPrices.US10Y;
    iconUrl = marketMeta?.icon || '';
    unit = resolveUnit(marketMeta?.unit || rule.counterCurrency || '$');
  }

  // Symbol full name resolution (English name for international, Persian for Iranian assets)
  const fullDisplayName = getSymbolEnglishFullName(
    rule.baseCurrency,
    marketMeta?.name || rule.marketSymbol
  );

  const isChecking = checkingRuleId === rule.uuid;
  let rawDisplayP = rule.lastCheckedPrice ?? rule.basePrice;
  let rawBaseP = rule.basePrice;
  let rawTargetV = rule.targetValue;
  let rawUpperP = rule.upperTargetPrice;
  let rawLowerP = rule.lowerTargetPrice;

  // Normalize raw Rial values to Tomans for Iranian currencies
  if (
    unit === 'تومان' ||
    (rule.exchangeId &&
      (rule.exchangeId.toLowerCase().includes('nobitex') ||
        rule.exchangeId.toLowerCase().includes('bonbast')))
  ) {
    unit = 'تومان';
    if (rule.baseCurrency === 'USDT' || rule.marketSymbol.startsWith('USDT')) {
      while (rawDisplayP > 150000) rawDisplayP = Math.round(rawDisplayP / 10.0);
      while (rawBaseP > 150000) rawBaseP = Math.round(rawBaseP / 10.0);
      while (rawTargetV > 150000) rawTargetV = Math.round(rawTargetV / 10.0);
      if (rawUpperP) {
        while (rawUpperP > 150000) rawUpperP = Math.round(rawUpperP / 10.0);
      }
      if (rawLowerP) {
        while (rawLowerP > 150000) rawLowerP = Math.round(rawLowerP / 10.0);
      }
    }
  }

  const displayP = rawDisplayP;

  // 24h delta / effective percent
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

  // --- SWIPE GESTURE ENGINE (Touch & Mouse Drag) ---
  const [dragOffset, setDragOffset] = useState<number>(0);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const dragStartX = useRef<number>(0);
  const currentDragX = useRef<number>(0);
  const cardRef = useRef<HTMLDivElement>(null);

  const SWIPE_THRESHOLD = 75; // px required to trigger action
  const MAX_DRAG = 130;

  const handleDragStart = (clientX: number, target: EventTarget | null) => {
    // Avoid triggering drag if user clicked directly on an interactive button
    if (target && (target as HTMLElement).closest('button')) {
      return;
    }
    dragStartX.current = clientX;
    currentDragX.current = clientX;
    setIsDragging(true);
  };

  const handleDragMove = useCallback(
    (clientX: number) => {
      if (!isDragging) return;
      const delta = clientX - dragStartX.current;
      // Dampen drag past maximum
      const clamped =
        Math.sign(delta) * Math.min(Math.abs(delta), MAX_DRAG);
      currentDragX.current = clientX;
      setDragOffset(clamped);
    },
    [isDragging]
  );

  const handleDragEnd = useCallback(() => {
    if (!isDragging) return;
    setIsDragging(false);

    if (dragOffset > SWIPE_THRESHOLD) {
      // Swiped Right -> Toggle Active/Inactive
      onToggle(rule.uuid);
      setDragOffset(0);
    } else if (dragOffset < -SWIPE_THRESHOLD) {
      // Swiped Left -> Delete Card
      setIsDeleting(true);
      setDragOffset(-350);
      setTimeout(() => {
        onDelete(rule.uuid);
      }, 220);
    } else {
      // Released below threshold -> Spring back
      setDragOffset(0);
    }
  }, [isDragging, dragOffset, rule.uuid, onToggle, onDelete]);

  // Mouse drag event listeners attached to window for smooth outside tracking
  useEffect(() => {
    if (!isDragging) return;

    const onMouseMove = (e: MouseEvent) => {
      handleDragMove(e.clientX);
    };

    const onMouseUp = () => {
      handleDragEnd();
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);

    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDragging, handleDragMove, handleDragEnd]);

  const isSwipingRight = dragOffset > 15;
  const isSwipingLeft = dragOffset < -15;
  const isRightThresholdPassed = dragOffset >= SWIPE_THRESHOLD;
  const isLeftThresholdPassed = dragOffset <= -SWIPE_THRESHOLD;

  return (
    <div
      dir="ltr"
      className="relative w-full max-w-full overflow-hidden rounded-2xl select-none"
      style={{ touchAction: 'pan-y' }}
    >
      {/* BACKGROUND SWIPE ACTION REVEAL LAYER */}
      <div
        className={`absolute inset-0 rounded-2xl flex items-center justify-between px-4 transition-colors duration-200 pointer-events-none ${
          isSwipingRight
            ? isRightThresholdPassed
              ? rule.isActive
                ? 'bg-amber-600/90'
                : 'bg-emerald-600/90'
              : 'bg-emerald-700/60'
            : isSwipingLeft
            ? isLeftThresholdPassed
              ? 'bg-rose-600'
              : 'bg-rose-700/70'
            : 'bg-transparent'
        }`}
      >
        {/* Left Action: Toggle Active / Inactive (Reveals when swiping right) */}
        <div
          className={`flex items-center gap-2 text-white font-bold transition-all duration-200 ${
            isSwipingRight
              ? 'opacity-100 transform translate-x-0 scale-100'
              : 'opacity-0 -translate-x-4 scale-90'
          }`}
        >
          <div
            className={`h-9 w-9 rounded-xl flex items-center justify-center transition-transform ${
              isRightThresholdPassed ? 'scale-110 bg-white/20' : 'bg-black/20'
            }`}
          >
            <Power className="h-5 w-5 text-white" />
          </div>
          <div className="flex flex-col text-left">
            <span className="text-[11px] font-black tracking-wide">
              {rule.isActive ? 'DEACTIVATE' : 'ACTIVATE'}
            </span>
            <span className="text-[9px] text-white/80 font-normal">
              {isRightThresholdPassed ? 'Release to toggle' : 'Swipe further'}
            </span>
          </div>
        </div>

        {/* Right Action: Delete Card (Reveals when swiping left) */}
        <div
          className={`flex items-center gap-2 text-white font-bold transition-all duration-200 ml-auto ${
            isSwipingLeft
              ? 'opacity-100 transform translate-x-0 scale-100'
              : 'opacity-0 translate-x-4 scale-90'
          }`}
        >
          <div className="flex flex-col text-right">
            <span className="text-[11px] font-black tracking-wide">DELETE</span>
            <span className="text-[9px] text-white/80 font-normal">
              {isLeftThresholdPassed ? 'Release to delete' : 'Swipe further'}
            </span>
          </div>
          <div
            className={`h-9 w-9 rounded-xl flex items-center justify-center transition-transform ${
              isLeftThresholdPassed ? 'scale-110 bg-white/20' : 'bg-black/20'
            }`}
          >
            <Trash2 className="h-5 w-5 text-white" />
          </div>
        </div>
      </div>

      {/* FOREGROUND CARD SURFACE */}
      <div
        ref={cardRef}
        onTouchStart={(e) => handleDragStart(e.touches[0].clientX, e.target)}
        onTouchMove={(e) => handleDragMove(e.touches[0].clientX)}
        onTouchEnd={handleDragEnd}
        onTouchCancel={handleDragEnd}
        onMouseDown={(e) => handleDragStart(e.clientX, e.target)}
        style={{
          transform: `translateX(${dragOffset}px)`,
          transition: isDragging
            ? 'none'
            : isDeleting
            ? 'transform 0.22s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.22s'
            : 'transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1)',
          opacity: isDeleting ? 0 : 1,
        }}
        className={`w-full max-w-full overflow-hidden p-3 rounded-2xl border transition-[background-color,border-color,opacity] shadow-sm flex flex-col justify-between cursor-grab active:cursor-grabbing ${
          isLight
            ? 'bg-white border-slate-200/90 shadow-slate-100'
            : rule.isActive
            ? 'bg-slate-900/95 border-slate-800 hover:border-slate-700/80 shadow-slate-950/30'
            : 'bg-slate-950/60 border-slate-900/70 opacity-65'
        }`}
      >
        {/* 1. TOP SECTION: TWO-ROW BALANCED FINANCIAL HEADER */}
        <div className="flex flex-col gap-1 min-w-0">
          {/* Row 1: Icon + Symbol (Left)  |  Price + Strike Base Price (Right) */}
          <div className="flex items-center justify-between gap-2 min-w-0">
            {/* Left: Coin Icon + Symbol Code */}
            <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
              <div className="relative shrink-0">
                <img
                  src={iconUrl}
                  alt={rule.marketSymbol}
                  className="h-8.5 w-8.5 rounded-xl object-cover border border-slate-700/70 p-0.5 bg-slate-950 shrink-0"
                  onError={(e) => {
                    (e.target as any).src =
                      'https://cdn-icons-png.flaticon.com/512/2830/2830284.png';
                  }}
                />
                <span
                  className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-slate-900 ${
                    rule.isActive
                      ? isOrange
                        ? 'bg-orange-500 ring-1 ring-orange-500/30'
                        : 'bg-emerald-500 ring-1 ring-emerald-500/30'
                      : 'bg-slate-600'
                  }`}
                  title={rule.isActive ? 'Active' : 'Inactive'}
                />
              </div>

              <div className="min-w-0 flex-1 overflow-hidden">
                <div
                  className="font-black text-[13px] sm:text-[14px] text-white truncate max-w-full tracking-tight font-mono"
                  title={rule.marketSymbol}
                >
                  {rule.marketSymbol}
                </div>
              </div>
            </div>

            {/* Right: Price + Strikethrough Base Price */}
            <div className="shrink-0 flex flex-col items-end text-right min-w-0 pl-1" dir="ltr">
              {rule.basePrice > 0 && Math.abs(displayP - rule.basePrice) > 1e-8 && (
                <div className="text-[9.5px] font-mono text-slate-500 line-through leading-tight truncate">
                  {renderFormattedPrice(rule.basePrice, unit, rule.counterCurrency, true)}
                </div>
              )}
              <div className="text-[15px] sm:text-[16px] font-black font-mono tracking-tight text-white leading-tight">
                {renderFormattedPrice(displayP, unit, rule.counterCurrency, false)}
              </div>
            </div>
          </div>

          {/* Row 2: Full English Name • Exchange (Left)  |  Percentage Badge (Right - directly under price!) */}
          <div className="flex items-center justify-between gap-2 min-w-0 pt-0.5">
            {/* Left: Full Name • Exchange Badge */}
            <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden text-[10.5px]">
              <span
                className="font-medium text-slate-300 truncate max-w-[150px] sm:max-w-[210px]"
                title={fullDisplayName}
              >
                {fullDisplayName}
              </span>
              <span className="text-slate-600 shrink-0 select-none">•</span>
              <span
                dir="ltr"
                className="px-1.5 py-0.2 rounded text-[8.5px] font-bold tracking-wider bg-slate-800/90 text-slate-400 border border-slate-700/50 shrink-0 font-mono truncate max-w-[95px] sm:max-w-[120px]"
              >
                {formatExchangeTag(rule.exchangeName)}
              </span>
            </div>

            {/* Right: Percentage Badge (Directly below price) */}
            <div className="shrink-0 text-right" dir="ltr">
              {rule.isTriggered ? (
                <span className="inline-block px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-500/15 border border-amber-500/30 text-amber-400 leading-none">
                  Done
                </span>
              ) : (
                <span
                  className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-mono font-bold leading-none ${
                    isZero
                      ? 'bg-slate-800 text-slate-400 border border-slate-700/40'
                      : isPositive
                      ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-400'
                      : 'bg-rose-500/15 border border-rose-500/30 text-rose-400'
                  }`}
                >
                  {isZero ? '• ' : isPositive ? '+' : ''}
                  {effectivePct.toFixed(2)}%
                </span>
              )}
            </div>
          </div>
        </div>

        {/* 2. MIDDLE: TARGET PROXIMITY PROGRESS STRIP */}
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
                      {renderFormattedPrice(rawTargetV, unit, rule.counterCurrency)}
                    </span>
                  </span>
                ) : (
                  <span>
                    Target: {rule.direction === 'ABOVE' ? 'Above' : 'Below'}{' '}
                    <span dir="ltr" className="font-mono">
                      {renderFormattedPrice(rawTargetV, unit, rule.counterCurrency)}
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

        {/* 3. FOOTER: SOUND / VIBE / TTS CHIPS + INTERVAL & CHECK BUTTON (TOGGLE & TRASH REMOVED) */}
        <div className="flex items-center justify-between text-[10px] pt-0.5 gap-1.5 flex-nowrap min-w-0">
          {/* Left: Feedback Notification Badges */}
          <div className="flex items-center gap-1 min-w-0 flex-nowrap shrink-0">
            {/* Sound */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleFeedback(rule.uuid, 'sound');
              }}
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
              onClick={(e) => {
                e.stopPropagation();
                onToggleFeedback(rule.uuid, 'vibration');
              }}
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
              onClick={(e) => {
                e.stopPropagation();
                onToggleFeedback(rule.uuid, 'tts');
              }}
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

          {/* Right: Timer Interval + Refresh Check */}
          <div className="flex items-center gap-1.5 shrink-0">
            <span
              dir="ltr"
              className="text-[9.5px] font-mono text-slate-400 flex items-center gap-0.5"
            >
              <Timer className="h-2.5 w-2.5 text-slate-500 shrink-0" />
              <span>{formatInterval(rule.checkIntervalSeconds)}</span>
            </span>

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onManualCheck(rule);
              }}
              disabled={isChecking}
              className="h-6 px-2 rounded-lg bg-slate-800 hover:bg-slate-700/80 text-emerald-400 flex items-center gap-1 text-[9.5px] font-bold border border-slate-700/60 transition-all cursor-pointer shrink-0"
              title={isFa ? FA.checkNow : 'Check Now'}
            >
              <RefreshCw
                className={`h-2.5 w-2.5 shrink-0 ${isChecking ? 'animate-spin' : ''}`}
              />
              <span>{isFa ? FA.check : 'Check'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AlarmCard;

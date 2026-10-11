import 'package:equatable/equatable.dart';
import 'package:uuid/uuid.dart';
import '../../../../core/utils/mojibake_repair_helper.dart';
import '../../exchanges/base/currency_pair.dart';
import 'alert_type.dart';
import 'trigger_mode.dart';

export 'alert_type.dart';
export 'trigger_mode.dart';

/// Personal Price Alert Rule entity.
/// Represents a single, dedicated condition with its own polling interval, sound, vibration & note.
class AlertRule extends Equatable {
  /// Unique UUID string (primary business key)
  final String uuid;

  /// Standardized currency pair
  final String baseCurrency;
  final String counterCurrency;
  final String marketSymbol;

  /// Currency pair helper getter
  CurrencyPair get pair => CurrencyPair(
        baseCurrency: baseCurrency,
        counterCurrency: counterCurrency,
        marketSymbol: marketSymbol,
      );

  /// Exchange ID acting as the price source (e.g. "binance", "coingecko")
  final String exchangeId;

  /// Individual polling interval in seconds (e.g. 10s, 30s, 60s, 300s, 3600s)
  final int checkIntervalSeconds;

  /// The single condition type for this rule
  final AlertConditionType conditionType;

  /// Evaluation direction: above, below, or bothSides
  final AlertDirection direction;

  /// Behavior mode for Both Way price alerts (OCO vs Dual-Active)
  final BothWayBehavior bothWayBehavior;

  /// Trigger mode: auto-set based on conditionType
  final TriggerMode triggerMode;

  /// For priceThreshold: target price in counter currency
  final double? targetPrice;

  /// For Both Way priceThreshold: upper threshold price
  final double? upperTargetPrice;

  /// For Both Way priceThreshold: dedicated note for upper breakout
  final String? upperNote;

  /// For Both Way priceThreshold: lower threshold price
  final double? lowerTargetPrice;

  /// For Both Way priceThreshold: dedicated note for lower breakdown
  final String? lowerNote;

  /// For percentChange: percentage change from basePrice (e.g. 3.0 for 3%)
  final double? percent;

  /// For absolutePriceChange: price delta from basePrice (e.g. 1000.0)
  final double? deltaAbsolute;

  /// For volumeChange: volume percentage change from baseVolume
  final double? volumePercent;

  /// Baseline reference price (updated on recurring trigger)
  final double? basePrice;

  /// Most recently fetched/checked price from exchange
  final double? lastCheckedPrice;

  /// Previous checked price before the latest update (e.g. was 22, now 23)
  final double? previousPrice;

  /// Helper getter for current display price
  double? get currentDisplayPrice => lastCheckedPrice ?? basePrice;

  /// Helper getter for target value across various condition types
  double? get targetValue => targetPrice ?? percent ?? deltaAbsolute ?? volumePercent;

  /// Helper getter for polling time window
  int get timeWindowSeconds => checkIntervalSeconds;

  /// Baseline reference volume
  final double? baseVolume;

  /// Custom note / trade thesis (e.g. "TP1 Hit - take profit", "Stop Loss")
  final String? customNote;

  /// Convenient alias for customNote
  String? get note => customNote;

  /// Custom alarm sound tone ID for this specific alert
  final String? customSound;

  /// Preferred voice language for Text-To-Speech (e.g. "fa", "en", "ar")
  final String? language;

  /// Whether sound is enabled for this alert
  final bool soundEnabled;

  /// Whether text-to-speech voice reading is enabled for this alert
  final bool ttsEnabled;

  /// Whether vibration is enabled for this alert
  final bool vibrationEnabled;

  /// Whether to prefer server proxy over direct local fetch (determined during creation)
  final bool preferServerProxy;

  /// Whether this alert is actively checked by the scheduler
  final bool isActive;

  /// True if a one-shot alert has triggered and is waiting for manual re-arm
  final bool isTriggered;

  /// Timestamp until which the rule is silenced by cooldown
  final DateTime? cooldownUntil;

  /// Total number of times this rule was triggered
  final int triggerCount;

  /// Timestamp when the scheduler last polled and evaluated this rule
  final DateTime? lastCheckedAt;

  /// Timestamp when this rule was last triggered
  final DateTime? lastTriggeredAt;

  /// Timestamp when the rule was created
  final DateTime createdAt;

  // --- Display & Compatibility Helpers ---

  /// Helper to check if rule is currently suppressed by cooldown
  bool get isInCooldown =>
      cooldownUntil != null && cooldownUntil!.isAfter(DateTime.now());

  /// Maps conditionType to display AlertType
  AlertType get alertType {
    switch (conditionType) {
      case AlertConditionType.priceThreshold:
        return AlertType.priceCross;
      case AlertConditionType.percentChange:
        return AlertType.percentChange;
      case AlertConditionType.absolutePriceChange:
        return AlertType.price;
      case AlertConditionType.volumeChange:
        return AlertType.volumeSurge;
    }
  }

  /// Maps conditionType to display localized title
  String getLocalizedTitle(String lang) {
    switch (conditionType) {
      case AlertConditionType.priceThreshold:
        if (lang == 'fa') return 'هشدار عبور از قیمت هدف';
        if (lang == 'ckb') return 'ئاگاداری تێپەڕینی نرخی ئامانج';
        if (lang == 'ar') return 'إنذار تجاوز السعر المستهدف';
        if (lang == 'de') return 'Zielpreis-Alarm';
        if (lang == 'tr') return 'Hedef Fiyat Alarmı';
        if (lang == 'es') return 'Alerta de Precio Objetivo';
        if (lang == 'fr') return 'Alerte Prix Cible';
        if (lang == 'ru') return 'Оповещение о целевой цене';
        if (lang == 'zh') return '目标价格预警';
        return 'Target Price Alert';
      case AlertConditionType.percentChange:
        if (lang == 'fa') return 'هشدار تغییر درصدی قیمت';
        if (lang == 'ckb') return 'ئاگاداری گۆڕانکاری ڕێژەیی نرخ';
        if (lang == 'ar') return 'إنذار نسبة التغير في السعر';
        if (lang == 'de') return 'Prozentuale Preisänderung';
        if (lang == 'tr') return 'Yüzdesel Fiyat Değişimi';
        if (lang == 'es') return 'Alerta de Cambio Porcentual';
        if (lang == 'fr') return 'Alerte Variation Pourcentage';
        if (lang == 'ru') return 'Процентное изменение цены';
        if (lang == 'zh') return '价格变动百分比预警';
        return 'Percentage Change Alert';
      case AlertConditionType.absolutePriceChange:
        if (lang == 'fa') return 'هشدار مقدار نوسان دلاری';
        if (lang == 'ckb') return 'ئاگاداری بڕی نوسانی دۆلاری';
        if (lang == 'ar') return 'إنذار مقدار التغير السعري';
        if (lang == 'de') return 'Preis-Delta-Alarm';
        if (lang == 'tr') return 'Fiyat Farkı Alarmı';
        if (lang == 'es') return 'Alerta de Variación de Precio';
        if (lang == 'fr') return 'Alerte Écart de Prix';
        if (lang == 'ru') return 'Изменение цены в USD';
        if (lang == 'zh') return '美元波动额预警';
        return 'Price Delta Alert';
      case AlertConditionType.volumeChange:
        if (lang == 'fa') return 'هشدار پامپ و حجم معاملات';
        if (lang == 'ckb') return 'ئاگاداری پەمپ و قەبارەی مامەڵەکان';
        if (lang == 'ar') return 'إنذار حجم التداول';
        if (lang == 'de') return 'Volumenanstieg-Alarm';
        if (lang == 'tr') return 'Hacim Artışı Alarmı';
        if (lang == 'es') return 'Alerta de Pico de Volumen';
        if (lang == 'fr') return 'Alerte Volume Élevé';
        if (lang == 'ru') return 'Всплеск объема торгов';
        if (lang == 'zh') return '成交量突增预警';
        return 'Volume Surge Alert';
    }
  }

  const AlertRule({
    required this.uuid,
    required this.baseCurrency,
    required this.counterCurrency,
    required this.marketSymbol,
    required this.exchangeId,
    required this.checkIntervalSeconds,
    required this.conditionType,
    required this.direction,
    this.bothWayBehavior = BothWayBehavior.oco,
    required this.triggerMode,
    this.targetPrice,
    this.upperTargetPrice,
    this.upperNote,
    this.lowerTargetPrice,
    this.lowerNote,
    this.percent,
    this.deltaAbsolute,
    this.volumePercent,
    this.basePrice,
    this.lastCheckedPrice,
    this.previousPrice,
    this.baseVolume,
    this.customNote,
    this.customSound,
    this.language,
    this.soundEnabled = true,
    this.ttsEnabled = false,
    this.vibrationEnabled = true,
    this.preferServerProxy = false,
    this.isActive = true,
    this.isTriggered = false,
    this.cooldownUntil,
    this.triggerCount = 0,
    this.lastCheckedAt,
    this.lastTriggeredAt,
    required this.createdAt,
  });

  /// Factory to create a new rule with auto-derived triggerMode and generated UUID
  factory AlertRule.create({
    required CurrencyPair pair,
    required String exchangeId,
    required int checkIntervalSeconds,
    required AlertConditionType conditionType,
    required AlertDirection direction,
    BothWayBehavior bothWayBehavior = BothWayBehavior.oco,
    double? targetPrice,
    double? upperTargetPrice,
    String? upperNote,
    double? lowerTargetPrice,
    String? lowerNote,
    double? percent,
    double? deltaAbsolute,
    double? volumePercent,
    double? currentPrice,
    double? previousPrice,
    double? currentVolume,
    String? customNote,
    String? customSound,
    String? language,
    bool soundEnabled = true,
    bool ttsEnabled = false,
    bool vibrationEnabled = true,
    bool preferServerProxy = false,
    DateTime? cooldownUntil,
    int triggerCount = 0,
  }) {
    final mode = (conditionType == AlertConditionType.priceThreshold && bothWayBehavior != BothWayBehavior.dualActive ||
            (conditionType == AlertConditionType.percentChange &&
                direction != AlertDirection.bothSides))
        ? TriggerMode.oneShot
        : TriggerMode.recurring;

    return AlertRule(
      uuid: const Uuid().v4(),
      baseCurrency: pair.baseCurrency,
      counterCurrency: pair.counterCurrency,
      marketSymbol: pair.marketSymbol,
      exchangeId: exchangeId,
      checkIntervalSeconds: checkIntervalSeconds,
      conditionType: conditionType,
      direction: direction,
      bothWayBehavior: bothWayBehavior,
      triggerMode: mode,
      targetPrice: targetPrice,
      upperTargetPrice: upperTargetPrice,
      upperNote: upperNote,
      lowerTargetPrice: lowerTargetPrice,
      lowerNote: lowerNote,
      percent: percent,
      deltaAbsolute: deltaAbsolute,
      volumePercent: volumePercent,
      basePrice: currentPrice,
      lastCheckedPrice: currentPrice,
      previousPrice: previousPrice ?? currentPrice,
      baseVolume: currentVolume,
      customNote: customNote,
      customSound: customSound,
      language: language,
      soundEnabled: soundEnabled,
      ttsEnabled: ttsEnabled,
      vibrationEnabled: vibrationEnabled,
      preferServerProxy: preferServerProxy,
      isActive: true,
      isTriggered: false,
      cooldownUntil: cooldownUntil,
      triggerCount: triggerCount,
      lastCheckedAt: DateTime.now(),
      createdAt: DateTime.now(),
    );
  }

  /// Check if the rule is due for checking based on its individual interval
  bool isDue(DateTime now) {
    if (!isActive) return false;
    if (lastCheckedAt == null) return true;
    final nextCheck = lastCheckedAt!.add(Duration(seconds: checkIntervalSeconds));
    return now.isAfter(nextCheck) || now.isAtSameMomentAs(nextCheck);
  }

  AlertRule copyWith({
    String? baseCurrency,
    String? counterCurrency,
    String? marketSymbol,
    String? exchangeId,
    int? checkIntervalSeconds,
    AlertConditionType? conditionType,
    AlertDirection? direction,
    BothWayBehavior? bothWayBehavior,
    TriggerMode? triggerMode,
    double? targetPrice,
    double? upperTargetPrice,
    String? upperNote,
    double? lowerTargetPrice,
    String? lowerNote,
    double? percent,
    double? deltaAbsolute,
    double? volumePercent,
    String? customNote,
    String? customSound,
    String? language,
    bool? soundEnabled,
    bool? ttsEnabled,
    bool? vibrationEnabled,
    bool? preferServerProxy,
    bool? isActive,
    bool? isTriggered,
    DateTime? cooldownUntil,
    int? triggerCount,
    double? basePrice,
    double? lastCheckedPrice,
    double? previousPrice,
    double? baseVolume,
    DateTime? lastCheckedAt,
    DateTime? lastTriggeredAt,
  }) {
    return AlertRule(
      uuid: uuid,
      baseCurrency: baseCurrency ?? this.baseCurrency,
      counterCurrency: counterCurrency ?? this.counterCurrency,
      marketSymbol: marketSymbol ?? this.marketSymbol,
      exchangeId: exchangeId ?? this.exchangeId,
      checkIntervalSeconds: checkIntervalSeconds ?? this.checkIntervalSeconds,
      conditionType: conditionType ?? this.conditionType,
      direction: direction ?? this.direction,
      bothWayBehavior: bothWayBehavior ?? this.bothWayBehavior,
      triggerMode: triggerMode ?? this.triggerMode,
      targetPrice: targetPrice ?? this.targetPrice,
      upperTargetPrice: upperTargetPrice ?? this.upperTargetPrice,
      upperNote: upperNote ?? this.upperNote,
      lowerTargetPrice: lowerTargetPrice ?? this.lowerTargetPrice,
      lowerNote: lowerNote ?? this.lowerNote,
      percent: percent ?? this.percent,
      deltaAbsolute: deltaAbsolute ?? this.deltaAbsolute,
      volumePercent: volumePercent ?? this.volumePercent,
      customNote: customNote ?? this.customNote,
      customSound: customSound ?? this.customSound,
      language: language ?? this.language,
      soundEnabled: soundEnabled ?? this.soundEnabled,
      ttsEnabled: ttsEnabled ?? this.ttsEnabled,
      vibrationEnabled: vibrationEnabled ?? this.vibrationEnabled,
      preferServerProxy: preferServerProxy ?? this.preferServerProxy,
      basePrice: basePrice ?? this.basePrice,
      lastCheckedPrice: lastCheckedPrice ?? this.lastCheckedPrice,
      previousPrice: previousPrice ?? this.previousPrice,
      baseVolume: baseVolume ?? this.baseVolume,
      isActive: isActive ?? this.isActive,
      isTriggered: isTriggered ?? this.isTriggered,
      cooldownUntil: cooldownUntil ?? this.cooldownUntil,
      triggerCount: triggerCount ?? this.triggerCount,
      lastCheckedAt: lastCheckedAt ?? this.lastCheckedAt,
      lastTriggeredAt: lastTriggeredAt ?? this.lastTriggeredAt,
      createdAt: createdAt,
    );
  }

  Map<String, dynamic> toJson() => {
        'uuid': uuid,
        'baseCurrency': baseCurrency,
        'counterCurrency': counterCurrency,
        'marketSymbol': marketSymbol,
        'exchangeId': exchangeId,
        'checkIntervalSeconds': checkIntervalSeconds,
        'conditionType': conditionType.name,
        'direction': direction.name,
        'bothWayBehavior': bothWayBehavior.name,
        'triggerMode': triggerMode.name,
        'targetPrice': targetPrice,
        'upperTargetPrice': upperTargetPrice,
        'upperNote': upperNote,
        'lowerTargetPrice': lowerTargetPrice,
        'lowerNote': lowerNote,
        'percent': percent,
        'deltaAbsolute': deltaAbsolute,
        'volumePercent': volumePercent,
        'basePrice': basePrice,
        'lastCheckedPrice': lastCheckedPrice,
        'previousPrice': previousPrice,
        'baseVolume': baseVolume,
        'customNote': customNote,
        'customSound': customSound,
        'language': language,
        'soundEnabled': soundEnabled,
        'ttsEnabled': ttsEnabled,
        'vibrationEnabled': vibrationEnabled,
        'preferServerProxy': preferServerProxy,
        'isActive': isActive,
        'isTriggered': isTriggered,
        'cooldownUntil': cooldownUntil?.toIso8601String(),
        'triggerCount': triggerCount,
        'lastCheckedAt': lastCheckedAt?.toIso8601String(),
        'lastTriggeredAt': lastTriggeredAt?.toIso8601String(),
        'createdAt': createdAt.toIso8601String(),
      };

  factory AlertRule.fromJson(Map<String, dynamic> json) => AlertRule(
        uuid: json['uuid'] as String,
        baseCurrency: json['baseCurrency'] as String,
        counterCurrency: repairMojibake(json['counterCurrency'] as String?) ?? (json['counterCurrency'] as String? ?? 'USDT'),
        marketSymbol: json['marketSymbol'] as String,
        exchangeId: json['exchangeId'] as String,
        checkIntervalSeconds: json['checkIntervalSeconds'] as int? ?? 30,
        conditionType: AlertConditionType.values.byName(
            json['conditionType'] as String? ?? 'percentChange'),
        direction: AlertDirection.values
            .byName(json['direction'] as String? ?? 'bothSides'),
        bothWayBehavior: json['bothWayBehavior'] != null
            ? BothWayBehavior.values.firstWhere(
                (e) => e.name == json['bothWayBehavior'],
                orElse: () => BothWayBehavior.oco,
              )
            : BothWayBehavior.oco,
        triggerMode: TriggerMode.values
            .byName(json['triggerMode'] as String? ?? 'recurring'),
        targetPrice: (json['targetPrice'] as num?)?.toDouble(),
        upperTargetPrice: (json['upperTargetPrice'] as num?)?.toDouble(),
        upperNote: repairMojibake(json['upperNote'] as String?),
        lowerTargetPrice: (json['lowerTargetPrice'] as num?)?.toDouble(),
        lowerNote: repairMojibake(json['lowerNote'] as String?),
        percent: (json['percent'] as num?)?.toDouble(),
        deltaAbsolute: (json['deltaAbsolute'] as num?)?.toDouble(),
        volumePercent: (json['volumePercent'] as num?)?.toDouble(),
        basePrice: (json['basePrice'] as num?)?.toDouble(),
        lastCheckedPrice: (json['lastCheckedPrice'] as num?)?.toDouble(),
        previousPrice: (json['previousPrice'] as num?)?.toDouble() ?? (json['previous_price'] as num?)?.toDouble(),
        baseVolume: (json['baseVolume'] as num?)?.toDouble(),
        customNote: repairMojibake(json['customNote'] as String?),
        customSound: json['customSound'] as String?,
        language: json['language'] as String?,
        soundEnabled: json['soundEnabled'] as bool? ?? true,
        ttsEnabled: json['ttsEnabled'] as bool? ?? false,
        vibrationEnabled: json['vibrationEnabled'] as bool? ?? true,
        preferServerProxy: json['preferServerProxy'] as bool? ?? false,
        isActive: json['isActive'] as bool? ?? true,
        isTriggered: json['isTriggered'] as bool? ?? false,
        cooldownUntil: json['cooldownUntil'] != null
            ? DateTime.tryParse(json['cooldownUntil'] as String)
            : null,
        triggerCount: json['triggerCount'] as int? ?? 0,
        lastCheckedAt: json['lastCheckedAt'] != null
            ? DateTime.tryParse(json['lastCheckedAt'] as String)
            : null,
        lastTriggeredAt: json['lastTriggeredAt'] != null
            ? DateTime.tryParse(json['lastTriggeredAt'] as String)
            : null,
        createdAt: json['createdAt'] != null
            ? DateTime.parse(json['createdAt'] as String)
            : DateTime.now(),
      );

  @override
  List<Object?> get props => [
        uuid,
        baseCurrency,
        counterCurrency,
        marketSymbol,
        exchangeId,
        checkIntervalSeconds,
        conditionType,
        direction,
        bothWayBehavior,
        triggerMode,
        targetPrice,
        upperTargetPrice,
        upperNote,
        lowerTargetPrice,
        lowerNote,
        percent,
        deltaAbsolute,
        volumePercent,
        basePrice,
        lastCheckedPrice,
        previousPrice,
        baseVolume,
        customNote,
        customSound,
        language,
        soundEnabled,
        ttsEnabled,
        vibrationEnabled,
        preferServerProxy,
        isActive,
        isTriggered,
        cooldownUntil,
        triggerCount,
        lastCheckedAt,
        lastTriggeredAt,
        createdAt,
      ];
}

/// Supported trigger modes for alert rules
enum TriggerMode {
  /// Fires once when the condition is met, then deactivates (isActive = false, isTriggered = true)
  oneShot,

  /// Fires each time the condition is met, updates basePrice/baseVolume, and stays active forever
  recurring,
}

/// Supported condition types across markets
enum AlertConditionType {
  /// Target price crossing above or below (one-shot by default)
  priceThreshold,

  /// Percentage price change from basePrice (recurring)
  percentChange,

  /// Absolute price delta change from basePrice (recurring)
  absolutePriceChange,

  /// Volume percentage change from baseVolume (recurring)
  volumeChange,

  /// Iranian Bourse: instrument enters buy queue at today's upper limit (server-evaluated)
  queueBuy,

  /// Iranian Bourse: instrument enters sell queue at today's lower limit (server-evaluated)
  queueSell,

  /// Iranian Bourse: today's cumulative share volume reaches targetPrice shares (server-evaluated)
  volumeAbove,
}

/// Direction of condition evaluation
enum AlertDirection {
  above,
  below,
  bothSides,
}

/// Behavior mode for Both Way Price Target alerts
enum BothWayBehavior {
  /// One-Cancels-the-Other: When first boundary (upper or lower) triggers, rule deactivates with Done
  oco,

  /// Dual-Active: Continually monitors both sides of the price channel without deactivating
  dualActive,
}

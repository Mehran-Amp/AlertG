/// Supported trigger modes for alert rules
enum TriggerMode {
  /// Fires once when the condition is met, then deactivates (isActive = false, isTriggered = true)
  oneShot,

  /// Fires each time the condition is met, updates basePrice/baseVolume, and stays active forever
  recurring,
}

/// The four strictly supported condition types
enum AlertConditionType {
  /// Target price crossing above or below (one-shot by default)
  priceThreshold,

  /// Percentage price change from basePrice (recurring)
  percentChange,

  /// Absolute price delta change from basePrice (recurring)
  absolutePriceChange,

  /// Volume percentage change from baseVolume (recurring)
  volumeChange,
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

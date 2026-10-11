/// Display and compatibility enums for AlertRule presentation.
enum AlertType {
  price,
  percent,
  absolute,
  volume,
  priceCross,
  percentChange,
  volumeSurge,
  compound,
}

enum ConditionType {
  priceThreshold,
  percentChange,
  absolutePriceChange,
  volumeChange,
  above,
  below,
  percentUp,
  percentDown,
  percentBoth,
  volumeSurge,
}

enum LogicOperator {
  and,
  or,
}

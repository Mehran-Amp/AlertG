/// Central Localization Strings for BitcoinChecker.
/// All user-facing labels, titles, error messages, and tooltips are defined here.
/// Ensures 100% decoupling from UI code and enables trivial future Persian translation.
abstract class S {
  // App & General
  static const String appName = 'BitcoinChecker';
  static const String cancel = 'Cancel';
  static const String save = 'Save Alert';
  static const String confirm = 'Confirm';
  static const String searchPlaceholder = 'Search asset or pair (e.g. BTC, ETH, PEPE)...';
  static const String emptySearchResult = 'No matching markets found';
  static const String pullToRefresh = 'Pull down to refresh pairs';
  static const String liveTicking = 'LIVE TICKING';
  static const String connected = 'Connected';
  static const String connecting = 'Connecting...';
  static const String disconnected = 'Disconnected';

  // Market Ticker Row
  static const String high24h = 'High:';
  static const String low24h = 'Low:';
  static const String vol24h = 'Vol:';
  static const String setAlert = 'Set Alert';

  // Alert Rule Builder Dialog
  static const String createAlertTitle = 'Create Market Alert';
  static const String step1Title = '1. Select Alert Condition Type';
  static const String step2Title = '2. Define Condition Parameters';
  static const String step3Title = '3. Composite Logic (Optional)';

  // Condition Types
  static const String typeThreshold = 'Price Threshold';
  static const String typePercent = 'Percent Change';
  static const String typeVolume = 'Volume Surge';
  static const String typeComposite = 'Composite (AND / OR)';

  // Threshold Fields
  static const String conditionAbove = 'Crosses Above Target';
  static const String conditionBelow = 'Crosses Below Target';
  static const String targetPriceLabel = 'Target Price (USD / USDT)';
  static const String targetPriceHint = 'e.g. 95000.00';

  // Percent Change Fields
  static const String percentDirectionUp = 'Surges Up (+%)';
  static const String percentDirectionDown = 'Drops Down (-%)';
  static const String percentChangeLabel = 'Percentage Change (%)';
  static const String percentChangeHint = 'e.g. 5.0';
  static const String timeWindowLabel = 'Rolling Time Window';
  static const String timeWindowHint = 'Value';

  // Time Units
  static const String unitSeconds = 'Sec';
  static const String unitMinutes = 'Min';
  static const String unitHours = 'Hour';

  // Volume Fields
  static const String volumeSurgeLabel = 'Volume Surge Target (USD)';
  static const String volumeSurgeHint = 'e.g. 10000000';

  // Composite Logic
  static const String addSecondaryCondition = '+ Add Secondary Condition';
  static const String removeSecondaryCondition = 'Remove Secondary Condition';
  static const String operatorAnd = 'AND';
  static const String operatorOr = 'OR';
  static const String andDescription = 'Both primary AND secondary conditions must trigger together';
  static const String orDescription = 'Either primary OR secondary condition triggers the alert';

  // Form Validation Errors
  static const String validationRequired = 'This field is required';
  static const String validationNumeric = 'Please enter a valid positive number';
  static const String validationPositive = 'Value must be greater than zero';
  static const String validationWindowMin = 'Time window must be at least 5 seconds';

  // Cooldown Banner
  static const String cooldownNotice = 'Note: All triggered alerts have a 3-minute cooldown window to prevent notification spam.';

  // Navigation Bar Tabs (Material 3)
  static const String tabMarketTicker = 'Markets';
  static const String tabAlerts = 'Alerts';
  static const String tabHistory = 'History';
  static const String tabSettings = 'Settings';

  // Alert List Page
  static const String alertListTitle = 'My Alerts';
  static const String noAlertsTitle = 'No Active Alerts';
  static const String noAlertsSubtitle = 'Tap the alert icon on any market to set your first price or volume notification.';
  static const String alertDeleted = 'Alert deleted';
  static const String undo = 'Undo';
  static const String rearmNow = 'Re-arm Now';
  static const String rearmConfirmTitle = 'Re-arm Alert Now?';
  static const String rearmConfirmBody = 'This will immediately end the 3-minute cooldown period and re-enable real-time triggers for this rule.';
  static const String duplicateAlert = 'Duplicate';
  static const String editAlert = 'Edit';
  static const String exportAlert = 'Export Rule';
  static const String alertDuplicated = 'Alert rule duplicated';

  // Notification History Page
  static const String notificationHistoryTitle = 'Trigger History';
  static const String dateToday = 'Today';
  static const String dateYesterday = 'Yesterday';
  static const String filterAll = 'All';
  static const String filterTriggered = 'Triggered';
  static const String filterSuppressed = 'Suppressed';
  static const String noHistoryTitle = 'No Notifications Yet';
  static const String noHistorySubtitle = 'Triggered market conditions will appear here chronologically.';

  // Settings Page
  static const String settingsTitle = 'Settings';
  static const String sectionGeneral = 'Appearance & General';
  static const String sectionPreferences = 'Appearance & Language';
  static const String sectionData = 'Backup & Storage';
  static const String sectionSystem = 'System & Permissions';
  static const String themeMode = 'Theme Mode';
  static const String themeSystem = 'System';
  static const String themeDark = 'Dark';
  static const String themeLight = 'Light';
  static const String language = 'Language';
  static const String languageEnglish = 'English';
  static const String languagePersian = 'فارسی (Persian)';
  static const String clearHistory = 'Clear Notification History';
  static const String clearHistoryConfirmTitle = 'Clear All History?';
  static const String clearHistoryConfirmBody = 'This will permanently remove all logged notification triggers from local storage.';
  static const String historyCleared = 'Notification history cleared';
  static const String exportAlerts = 'Export Alerts to JSON';
  static const String importAlerts = 'Import Alerts from JSON';
  static const String exportSuccess = 'Alerts exported successfully';
  static const String importSuccess = 'Alerts imported successfully';
  static const String importError = 'Failed to parse JSON file';
  static const String batteryOptimization = 'Battery Optimization Exemption';
  static const String batteryOptimizationSubtitle = 'Request Android system exemption to guarantee alerts in Doze mode.';
  static const String batteryOptimizationGranted = 'Battery exemption is active';
  static const String batteryOptimizationTitle = 'Background Battery Optimization';
  static const String batteryExemptStatus = 'Exempted (Reliable background checks)';
  static const String batteryOptimizedStatus = 'Optimized (May delay background checks)';
  static const String batteryOptimizationDesc = 'Android may restrict background execution when battery optimization is enabled. Requesting exemption ensures alerts fire on time.';
  static const String requestExemptionButton = 'Request Exemption';
}

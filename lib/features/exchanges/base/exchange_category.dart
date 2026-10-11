import '../../../core/localization/app_strings.dart';

enum ExchangeCategory {
  all,
  tier1,
  iran,
  middleEast,
  asia,
  europe,
  americas,
  aggregator,
}

extension ExchangeCategoryExt on ExchangeCategory {
  String getTitle(String lang) {
    switch (this) {
      case ExchangeCategory.all:
        return AppStrings.get('cat_all_exchanges', lang);
      case ExchangeCategory.tier1:
        return AppStrings.get('cat_tier1', lang);
      case ExchangeCategory.iran:
        return AppStrings.get('cat_iran', lang);
      case ExchangeCategory.middleEast:
        return AppStrings.get('cat_middle_east', lang);
      case ExchangeCategory.asia:
        return AppStrings.get('cat_asia', lang);
      case ExchangeCategory.europe:
        return AppStrings.get('cat_europe', lang);
      case ExchangeCategory.americas:
        return AppStrings.get('cat_americas', lang);
      case ExchangeCategory.aggregator:
        return AppStrings.get('cat_aggregator', lang);
    }
  }

  String get titleFa {
    return getTitle('fa');
  }

  String get icon {
    switch (this) {
      case ExchangeCategory.all:
        return '🌐';
      case ExchangeCategory.tier1:
        return '⭐';
      case ExchangeCategory.iran:
        return '🇮🇷';
      case ExchangeCategory.middleEast:
        return '🕌';
      case ExchangeCategory.asia:
        return '⛩️';
      case ExchangeCategory.europe:
        return '🇪🇺';
      case ExchangeCategory.americas:
        return '🌎';
      case ExchangeCategory.aggregator:
        return '📊';
    }
  }
}

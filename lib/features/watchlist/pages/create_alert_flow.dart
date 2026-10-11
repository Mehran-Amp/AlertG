import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/crypto_icons.dart';
import '../../../core/utils/format_utils.dart';
import '../../alert_engine/models/alert_rule.dart';
import '../../alert_engine/repositories/json_alert_rule_repository.dart';
import '../../exchanges/base/crypto_catalog_data.dart';
import '../../exchanges/base/currency_pair.dart';
import '../../exchanges/base/exchange.dart';
import '../../exchanges/base/exchange_category.dart';
import '../../exchanges/registry/exchange_registry.dart';
import '../../exchanges/stocks/global_stocks_exchange.dart';
import '../../exchanges/stocks/iran_domestic_exchange.dart';
import '../../settings/services/settings_service.dart';
import '../../settings/services/sound_manager.dart';
import '../../../core/services/tts_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../../../core/utils/symbol_filter_helper.dart';

enum CheckUnit { seconds, minutes, hours }

enum MarketFlowType {
  none,
  crypto,
  macro,
  iran,
}

class CreateAlertFlow extends StatefulWidget {
  final ExchangeRegistry registry;
  final JsonAlertRuleRepository repository;
  final AlertRule? initialRule;

  const CreateAlertFlow({
    super.key,
    required this.registry,
    required this.repository,
    this.initialRule,
  });

  static Future<bool?> open(
    BuildContext context, {
    required ExchangeRegistry registry,
    required JsonAlertRuleRepository repository,
    AlertRule? initialRule,
  }) {
    return Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => CreateAlertFlow(
          registry: registry,
          repository: repository,
          initialRule: initialRule,
        ),
      ),
    );
  }

  @override
  State<CreateAlertFlow> createState() => _CreateAlertFlowState();
}

class _CreateAlertFlowState extends State<CreateAlertFlow> {
  MarketFlowType _flowType = MarketFlowType.none;
  int _step = 1;

  // Crypto Flow State
  ExchangeCategory _selectedCategory = ExchangeCategory.all;
  Exchange? _selectedExchange;
  String _exchangeSearchQuery = '';
  List<CurrencyPair> _exchangePairs = [];
  bool _isLoadingPairs = false;
  String _pairSearchQuery = '';
  CurrencyPair? _selectedPair;

  // Macro Flow State
  String _macroCategoryFilter = 'all';
  String _macroSearchQuery = '';
  Map<String, dynamic>? _selectedMacroAsset;
  final Map<String, double> _macroLivePrices = {};

  // Iran Flow State
  int _iranSubTab = 0;
  Exchange? _selectedIranExchange;
  String _iranCategoryFilter = 'all';
  String _iranSearchQuery = '';
  Map<String, dynamic>? _selectedIranDomesticAsset;
  final Map<String, double> _iranLivePrices = {};
  Map<String, dynamic>? _iranMarketsStatus;
  final Map<String, Map<String, dynamic>> _iranItemMeta = {};
  bool _isLoadingIranPairs = false;
  String _iranPairSearchQuery = '';
  List<CurrencyPair> _iranExchangePairs = [];

  // Snapshot
  double? _currentPrice;
  bool _isLoadingPrice = false;

  // Frequency
  CheckUnit _checkUnit = CheckUnit.minutes;
  late final TextEditingController _unitValueController;

  // Condition
  AlertConditionType _conditionType = AlertConditionType.percentChange;
  AlertDirection _direction = AlertDirection.bothSides;
  BothWayBehavior _bothWayBehavior = BothWayBehavior.oco;
  late final TextEditingController _percentController;
  late final TextEditingController _targetPriceController;
  late final TextEditingController _upperPriceController;
  late final TextEditingController _upperNoteController;
  late final TextEditingController _lowerPriceController;
  late final TextEditingController _lowerNoteController;

  // Custom Notification, Sound & Note
  late final TextEditingController _customNoteController;
  String _selectedSound = 'alarm_siren';
  bool _soundEnabled = true;
  bool _ttsEnabled = false;
  bool _vibrationEnabled = true;
  bool _preferServerProxy = false;

  @override
  void initState() {
    super.initState();

    if (widget.initialRule != null) {
      final rule = widget.initialRule!;
      _conditionType = rule.conditionType;
      _direction = rule.direction;
      _bothWayBehavior = rule.bothWayBehavior;
      _currentPrice = rule.currentDisplayPrice;
      _selectedSound = rule.customSound ?? 'alarm_siren';
      _soundEnabled = rule.soundEnabled;
      _ttsEnabled = rule.ttsEnabled;
      _vibrationEnabled = rule.vibrationEnabled;
      _customNoteController = TextEditingController(text: rule.customNote ?? '');

      // Determine Interval Unit and Value
      final secs = rule.checkIntervalSeconds;
      if (secs % 3600 == 0 && secs >= 3600) {
        _checkUnit = CheckUnit.hours;
        _unitValueController = TextEditingController(text: (secs ~/ 3600).toString());
      } else if (secs % 60 == 0 && secs >= 60) {
        _checkUnit = CheckUnit.minutes;
        _unitValueController = TextEditingController(text: (secs ~/ 60).toString());
      } else {
        _checkUnit = CheckUnit.seconds;
        _unitValueController = TextEditingController(text: secs.toString());
      }

      final rawPct = rule.percent ?? 2.5;
      final pctText = (rawPct == rawPct.roundToDouble()) ? rawPct.toInt().toString() : rawPct.toString();
      _percentController = TextEditingController(
        text: pctText,
      );
      _targetPriceController = TextEditingController(
        text: rule.targetPrice != null
            ? FormatUtils.formatInputNumberForUnit(rule.targetPrice!, rule.counterCurrency)
            : (_currentPrice != null
                ? FormatUtils.formatInputNumberForUnit(_currentPrice!, rule.counterCurrency)
                : ''),
      );
      _upperPriceController = TextEditingController(
        text: rule.upperTargetPrice != null
            ? FormatUtils.formatInputNumberForUnit(rule.upperTargetPrice!, rule.counterCurrency)
            : '',
      );
      _upperNoteController = TextEditingController(
        text: rule.upperNote ?? '',
      );
      _lowerPriceController = TextEditingController(
        text: rule.lowerTargetPrice != null
            ? FormatUtils.formatInputNumberForUnit(rule.lowerTargetPrice!, rule.counterCurrency)
            : '',
      );
      _lowerNoteController = TextEditingController(
        text: rule.lowerNote ?? '',
      );

      // Determine Market Type
      if (rule.exchangeId == 'global_stocks') {
        _flowType = MarketFlowType.macro;
        _step = 2;
        _selectedMacroAsset = GlobalStocksExchange.predefinedStocks.firstWhere(
          (s) => s['symbol'] == rule.baseCurrency,
          orElse: () => {
            'symbol': rule.baseCurrency,
            'name': rule.pair.displayName,
            'nameFa': rule.pair.displayName,
            'cat': 'Custom',
            'price': rule.currentDisplayPrice ?? 0.0,
          },
        );
      } else if (rule.exchangeId == 'iran_market') {
        _flowType = MarketFlowType.iran;
        _step = 2;
        _iranSubTab = 0;
        _selectedIranDomesticAsset = IranDomesticExchange.predefinedAssets.firstWhere(
          (s) => s['symbol'] == rule.baseCurrency,
          orElse: () => {
            'symbol': rule.baseCurrency,
            'name': rule.pair.displayName,
            'nameFa': rule.pair.displayName,
            'cat': 'Custom',
            'unit': 'تومان',
            'price': rule.currentDisplayPrice ?? 0.0,
          },
        );
      } else if (['nobitex', 'wallex', 'ramzinex', 'tabdeal', 'bitbarg', 'tetherland', 'abantether', 'sarmayex', 'exir'].contains(rule.exchangeId)) {
        _flowType = MarketFlowType.iran;
        _step = 3;
        _iranSubTab = 1;
        _selectedIranExchange = widget.registry.get(rule.exchangeId);
        _selectedExchange = _selectedIranExchange;
        _selectedPair = rule.pair;
      } else {
        _flowType = MarketFlowType.crypto;
        _step = 3;
        _selectedExchange = widget.registry.get(rule.exchangeId);
        _selectedPair = rule.pair;
      }
    } else {
      _unitValueController = TextEditingController(text: '3');
      _percentController = TextEditingController();
      _targetPriceController = TextEditingController();
      _upperPriceController = TextEditingController();
      _upperNoteController = TextEditingController();
      _lowerPriceController = TextEditingController();
      _lowerNoteController = TextEditingController();
      _customNoteController = TextEditingController();
      _selectedSound = 'alarm_siren';
      _soundEnabled = true;
      _vibrationEnabled = true;
    }

    _loadIranMarketOverview();
  }

  @override
  void dispose() {
    _unitValueController.dispose();
    _percentController.dispose();
    _targetPriceController.dispose();
    _upperPriceController.dispose();
    _upperNoteController.dispose();
    _lowerPriceController.dispose();
    _lowerNoteController.dispose();
    _customNoteController.dispose();
    super.dispose();
  }

  int _calculateTotalIntervalSeconds() {
    final value = int.tryParse(_unitValueController.text.trim()) ?? 3;
    switch (_checkUnit) {
      case CheckUnit.seconds:
        return (value * 60).clamp(60, 86400 * 7);
      case CheckUnit.minutes:
        return (value * 60).clamp(60, 86400 * 7);
      case CheckUnit.hours:
        return (value * 3600).clamp(3600, 86400 * 30);
    }
  }

  String _formatCalculatedInterval(String lang) {
    final val = int.tryParse(_unitValueController.text.trim()) ?? 3;
    switch (_checkUnit) {
      case CheckUnit.seconds:
        return '$val ${AppStrings.get('minutes', lang)}';
      case CheckUnit.minutes:
        return '$val ${AppStrings.get('minutes', lang)}';
      case CheckUnit.hours:
        return '$val ${AppStrings.get('hours', lang)}';
    }
  }

  void _onExchangeChosen(Exchange exchange) {
    setState(() {
      _selectedExchange = exchange;
      _step = 2;
    });
    _fetchPairsForSelectedExchange();
  }

  Future<void> _fetchPairsForSelectedExchange({bool forceRefresh = false}) async {
    if (_selectedExchange == null) return;
    setState(() => _isLoadingPairs = true);
    try {
      final pairs = forceRefresh
          ? await widget.registry.refreshCurrencyPairs(_selectedExchange!.id)
          : await widget.registry.getCurrencyPairs(_selectedExchange!.id);
      if (mounted) {
        setState(() {
          _exchangePairs = pairs.isNotEmpty
              ? pairs
              : CryptoCatalogData.buildPairs(
                  quoteCurrencies: [_selectedExchange!.defaultCounterCurrency],
                );
          _isLoadingPairs = false;
        });
      }
    } catch (_) {
      if (mounted) {
        final fallback = CryptoCatalogData.buildPairs(
          quoteCurrencies: [_selectedExchange?.defaultCounterCurrency ?? 'USDT'],
        );
        setState(() {
          _exchangePairs = fallback;
          _isLoadingPairs = false;
        });
      }
    }
  }

  String _formatSmartPrice(double price, String quoteCurrency) {
    // 1. Check for scaled currency abbreviation (e.g. quoteCurrency == 'Billion USD', 'B USD', 'M USD', 'TOTAL')
    final scaled = FormatUtils.formatScaledCurrencyPrice(price, quoteCurrency);
    if (scaled != null) {
      return scaled;
    }
    if (quoteCurrency == 'Billion USD' || quoteCurrency == 'B USD') {
      return FormatUtils.formatScaledCurrencyPrice(price, 'B USD') ?? '\$${_formatInputNumber(price, 'B USD')}B';
    }

    final lang = context.read<SettingsService>().settings.language;
    final upper = quoteCurrency.toUpperCase();
    final isToman = upper == 'TMN' || upper == 'IRT' || upper == 'TOMAN' || quoteCurrency == 'تومان' || quoteCurrency == 'ت';
    if (_flowType == MarketFlowType.iran || isToman) {
      return FormatUtils.formatIranPrice(price, unit: quoteCurrency, lang: lang);
    }
    final numStr = _formatInputNumber(price, quoteCurrency);
    final isRials = upper == 'IRR' || upper == 'RLS' || quoteCurrency == 'ریال';
    if (isRials) {
      final faNum = lang == 'fa' ? FormatUtils.toPersianDigits(FormatUtils.formatPrice(price, showSymbol: false, lang: lang)) : FormatUtils.formatPrice(price, showSymbol: false, lang: lang);
      final rUnit = FormatUtils.resolveCurrencyDisplayName(quoteCurrency, lang: lang);
      return '$faNum $rUnit';
    } else if (quoteCurrency == 'EUR') {
      return '€$numStr';
    } else if (quoteCurrency == 'GBP') {
      return '£$numStr';
    } else if (quoteCurrency == 'BTC') {
      return '₿${price.toStringAsFixed(8)}';
    } else if (quoteCurrency == '%' || upper == 'BTC.D' || upper == 'USDT.D' || upper == 'ETH.D') {
      return '${price.toStringAsFixed(2)}%';
    } else if (quoteCurrency == 'pts') {
      return '$numStr pts';
    } else if (quoteCurrency == 'JPY' || quoteCurrency == 'CNY') {
      return '¥$numStr';
    } else if (quoteCurrency == 'CHF') {
      return '$numStr CHF';
    } else if (quoteCurrency == 'CAD') {
      return 'C\$$numStr';
    } else if (quoteCurrency == 'TRY') {
      return '₺$numStr';
    } else if (quoteCurrency == 'AED') {
      return '$numStr AED';
    } else {
      return '\$$numStr';
    }
  }

  String _formatInputNumber(double price, [String? quoteCurrency]) {
    final quote = quoteCurrency ??
        (_selectedMacroAsset != null ? (_selectedMacroAsset!['unit'] as String?) : null) ??
        _selectedPair?.counterCurrency ??
        (_flowType == MarketFlowType.iran ? (_selectedIranDomesticAsset?['unit'] as String? ?? 'TMN') : (_selectedExchange?.defaultCounterCurrency ?? 'USD'));
    return FormatUtils.formatInputNumberForUnit(price, quote);
  }

  String _formatSmartNumber(double price, [String? quoteCurrency]) {
    return _formatInputNumber(price, quoteCurrency);
  }

  Future<void> _fetchLivePriceForSelectedAsset() async {
    // 0. Iran Domestic Asset Special Handling (Bonbast, TSETMC, ICE & Iranian Crypto Exchanges)
    if (_flowType == MarketFlowType.iran && _selectedIranDomesticAsset != null) {
      final sym = _selectedIranDomesticAsset!['symbol'] as String;
      final unit = (_selectedIranDomesticAsset!['unit'] as String?) ?? 'TMN';
      final pair = CurrencyPair(baseCurrency: sym, counterCurrency: unit, marketSymbol: sym);

      setState(() => _isLoadingPrice = true);

      // Local fetch
      try {
        final snapshot = await widget.registry.fetchSnapshotFrom('iran_market', pair).timeout(const Duration(seconds: 5));
        if (snapshot != null && snapshot.price > 0 && mounted) {
          setState(() {
            _iranLivePrices[sym] = snapshot.price;
            _currentPrice = snapshot.price;
            _targetPriceController.text = _formatSmartNumber(snapshot.price);
            _preferServerProxy = false;
            _isLoadingPrice = false;
          });
          return;
        }
      } catch (_) {}

      // Server fetch with 60s cache
      try {
        final serverPrice = await ServerAlertService.fetchPriceViaServer('iran_market', sym);
        if (serverPrice != null && serverPrice > 0 && mounted) {
          setState(() {
            _iranLivePrices[sym] = serverPrice;
            _currentPrice = serverPrice;
            _targetPriceController.text = _formatSmartNumber(serverPrice);
            _preferServerProxy = true;
            _isLoadingPrice = false;
          });
          return;
        }
      } catch (_) {}

      if (mounted) setState(() => _isLoadingPrice = false);
      return;
    }

    if (_selectedPair == null || _selectedExchange == null) return;
    setState(() {
      _isLoadingPrice = true;
    });

    // 1. Try local direct fetch first with 5-second timeout (for weak Iranian internet)
    try {
      final snapshot = await widget.registry.fetchSnapshotFrom(
        _selectedExchange!.id,
        _selectedPair!,
      ).timeout(const Duration(seconds: 5));

      if (snapshot != null && snapshot.price > 0 && mounted) {
        setState(() {
          _currentPrice = snapshot.price;
          _targetPriceController.text = _formatSmartNumber(snapshot.price);
          _preferServerProxy = false; // Local direct fetch working
          _isLoadingPrice = false;
        });
        return;
      }
    } catch (_) {
      // Local fetch failed (or exchange API is filtered/blocked by ISP)
    }

    // 2. Fallback: Query via server proxy (if ISP filtered)
    try {
      final serverPrice = await ServerAlertService.fetchPriceViaServer(
        _selectedExchange!.id,
        _selectedPair!.marketSymbol,
      );

      if (serverPrice != null && serverPrice > 0 && mounted) {
        setState(() {
          _currentPrice = serverPrice;
          _targetPriceController.text = _formatSmartNumber(serverPrice);
          _preferServerProxy = true; // Route marked to use server proxy
          _isLoadingPrice = false;
        });
        return;
      }
    } catch (_) {}

    if (mounted) {
      setState(() => _isLoadingPrice = false);
    }
  }

  Future<void> _onIranDomesticAssetChosen(Map<String, dynamic> asset) async {
    setState(() {
      _selectedIranDomesticAsset = asset;
      _selectedIranExchange = null;
      _selectedExchange = null;
      _selectedPair = null;
      _step = 2;
      _isLoadingPrice = true;
      _currentPrice = (asset['price'] as num?)?.toDouble();
      if (_currentPrice != null && _currentPrice! > 0) {
        _targetPriceController.text = _formatSmartNumber(_currentPrice!);
      }
    });

    final sym = asset['symbol'] as String;
    final unit = (asset['unit'] as String?) ?? 'TMN';
    final pair = CurrencyPair(baseCurrency: sym, counterCurrency: unit, marketSymbol: sym);

    // 1. Try local direct fetch
    try {
      final snapshot = await widget.registry.fetchSnapshotFrom('iran_market', pair).timeout(const Duration(seconds: 5));
      if (snapshot != null && snapshot.price > 0 && mounted) {
        setState(() {
          _iranLivePrices[sym] = snapshot.price;
          _currentPrice = snapshot.price;
          _targetPriceController.text = _formatSmartNumber(snapshot.price);
          _preferServerProxy = false;
          _isLoadingPrice = false;
        });
        return;
      }
    } catch (_) {}

    // 2. Fallback server fetch with 60-second cache
    try {
      final details = await ServerAlertService.fetchPriceDetailsViaServer('iran_market', sym);
      if (details != null && mounted) {
        final serverPrice = (details['price'] as num?)?.toDouble();
        setState(() {
          _iranItemMeta[sym] = details;
          if (serverPrice != null && serverPrice > 0) {
            _iranLivePrices[sym] = serverPrice;
            _currentPrice = serverPrice;
            _targetPriceController.text = _formatSmartNumber(serverPrice);
          } else {
            _currentPrice = null;
          }
          _preferServerProxy = true;
          _isLoadingPrice = false;
        });
        return;
      }
    } catch (_) {}

    if (mounted) {
      setState(() => _isLoadingPrice = false);
    }
  }

  Future<void> _loadIranMarketOverview() async {
    try {
      final overview = await ServerAlertService.fetchMarketsOverview();
      if (overview != null && mounted) {
        setState(() {
          if (overview['markets'] is Map<String, dynamic>) {
            _iranMarketsStatus = overview['markets'] as Map<String, dynamic>;
          }
          final items = overview['items'] as Map<String, dynamic>?;
          if (items != null) {
            items.forEach((key, val) {
              if (val is Map<String, dynamic>) {
                _iranItemMeta[key] = val;
                final p = (val['price'] as num?)?.toDouble();
                if (p != null && p > 0) {
                  _iranLivePrices[key] = p;
                }
              }
            });
          }
        });
      }
    } catch (e) {
      debugPrint('⚠️ Error fetching Iran market overview: $e');
    }
  }

  Future<void> _onIranExchangeChosen(Exchange ex) async {
    setState(() {
      _selectedIranExchange = ex;
      _selectedIranDomesticAsset = null;
      _selectedExchange = ex;
      _step = 2;
      _isLoadingIranPairs = true;
      _iranPairSearchQuery = '';
    });

    await _fetchPairsForIranExchange();
  }

  Future<void> _fetchPairsForIranExchange({bool forceRefresh = false}) async {
    if (_selectedIranExchange == null) return;
    setState(() => _isLoadingIranPairs = true);

    try {
      List<CurrencyPair> pairs;
      if (forceRefresh) {
        pairs = await widget.registry.refreshCurrencyPairs(_selectedIranExchange!.id);
      } else {
        pairs = await widget.registry.getCurrencyPairs(_selectedIranExchange!.id);
      }
      if (mounted) {
        setState(() {
          _iranExchangePairs = pairs;
          _isLoadingIranPairs = false;
        });
      }
    } catch (_) {
      if (mounted) {
        final fallback = CryptoCatalogData.buildPairs(
          quoteCurrencies: [_selectedIranExchange?.defaultCounterCurrency ?? 'TMN', 'USDT'],
        );
        setState(() {
          _iranExchangePairs = fallback;
          _isLoadingIranPairs = false;
        });
      }
    }
  }

  Future<void> _onIranPairChosen(CurrencyPair pair) async {
    setState(() {
      _selectedPair = pair;
      _step = 3;
      _isLoadingPrice = true;
      _currentPrice = null;
    });

    await _fetchLivePriceForSelectedAsset();
  }

  Future<void> _onPairChosen(CurrencyPair pair) async {
    setState(() {
      _selectedPair = pair;
      _step = 3;
      _isLoadingPrice = true;
      _currentPrice = null;
    });

    await _fetchLivePriceForSelectedAsset();
  }

  Future<void> _onMacroAssetChosen(Map<String, dynamic> asset) async {
    setState(() {
      _selectedMacroAsset = asset;
      _step = 2;
      _isLoadingPrice = true;
    });

    final sym = asset['symbol'] as String;
    final unit = (asset['unit'] as String?) ?? 'USD';
    final pair = CurrencyPair(baseCurrency: sym, counterCurrency: unit, marketSymbol: '$sym/USD');

    // 1. Try local direct fetch first
    try {
      final snapshot = await widget.registry.fetchSnapshotFrom('global_stocks', pair).timeout(const Duration(seconds: 5));
      if (snapshot != null && snapshot.price > 0 && mounted) {
        setState(() {
          _macroLivePrices[sym] = snapshot.price;
          _currentPrice = snapshot.price;
          _targetPriceController.text = FormatUtils.formatInputNumberForUnit(snapshot.price, unit);
          _preferServerProxy = false;
          _isLoadingPrice = false;
        });
        return;
      }
    } catch (e) {
      debugPrint('Local stock price fetch failed for $sym: $e');
    }

    // 2. Server Fallback for Stocks & Macro
    try {
      final serverPrice = await ServerAlertService.fetchPriceViaServer('global_stocks', sym);
      if (serverPrice != null && serverPrice > 0 && mounted) {
        setState(() {
          _macroLivePrices[sym] = serverPrice;
          _currentPrice = serverPrice;
          _targetPriceController.text = FormatUtils.formatInputNumberForUnit(serverPrice, unit);
          _preferServerProxy = true;
          _isLoadingPrice = false;
        });
        return;
      }
    } catch (e) {
      debugPrint('Server fallback price fetch failed for $sym: $e');
    }

    if (mounted) {
      setState(() {
        _isLoadingPrice = false;
      });
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      final lang = widget.initialRule?.language ?? 'fa';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(lang == 'fa'
              ? 'دریافت قیمت زنده $sym از منابع محلی و سرور امکان‌پذیر نبود. می‌توانید قیمت هدف را به صورت دستی وارد نمایید.'
              : 'Could not fetch live price for $sym from providers or server. You may enter target price manually.'),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 4),
        ),
      );
    }
  }

  Future<void> _saveAlert(String lang) async {
    final intervalSeconds = _calculateTotalIntervalSeconds();

    // Enforce minimum 3 minutes (180 seconds) check interval rule
    if (intervalSeconds < 180) {
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      final isRtl = (lang == 'fa' || lang == 'ar' || lang == 'ckb');
      final msg = isRtl
          ? '⏱️ حداقل زمان پایش آلارم باید ۳ دقیقه (۱۸۰ ثانیه) یا بیشتر باشد.'
          : '⏱️ Minimum check interval must be 3 minutes (180 seconds) or more.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(msg),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 4),
        ),
      );
      return;
    }

    String exchangeId;
    CurrencyPair pair;

    if (_flowType == MarketFlowType.crypto) {
      if (_selectedExchange == null || _selectedPair == null) return;
      exchangeId = _selectedExchange!.id;
      pair = _selectedPair!;
    } else if (_flowType == MarketFlowType.iran) {
      if (_selectedIranDomesticAsset != null) {
        exchangeId = 'iran_market';
        final sym = _selectedIranDomesticAsset!['symbol'] as String;
        final unit = (_selectedIranDomesticAsset!['unit'] as String?) ?? 'TMN';
        pair = CurrencyPair(
          baseCurrency: sym,
          counterCurrency: unit,
          marketSymbol: sym,
        );
      } else if (_selectedIranExchange != null && _selectedPair != null) {
        exchangeId = _selectedIranExchange!.id;
        pair = _selectedPair!;
      } else {
        return;
      }
    } else {
      if (_selectedMacroAsset == null) return;
      exchangeId = 'global_stocks';
      final sym = _selectedMacroAsset!['symbol'] as String;
      final unit = (_selectedMacroAsset!['unit'] as String?) ?? 'USD';
      pair = CurrencyPair(
        baseCurrency: sym,
        counterCurrency: unit,
        marketSymbol: '$sym/USD',
      );
    }

    double? percent;
    double? targetPrice;
    double? upperTargetPrice;
    String? upperNote;
    double? lowerTargetPrice;
    String? lowerNote;

    if (_conditionType == AlertConditionType.percentChange) {
      final textVal = _percentController.text.trim();
      final parsed = double.tryParse(FormatUtils.normalizePersianDigits(textVal));
      if (parsed == null || parsed <= 0) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(lang == 'fa'
                ? 'لطفاً درصد نوسان مورد نظر خود را وارد کنید (مثال: ۲.۵٪)'
                : 'Please enter a target percentage (e.g. 2.5%)'),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 3),
          ),
        );
        return;
      }
      if (_flowType == MarketFlowType.iran) {
        percent = parsed.roundToDouble(); // Integer percentage only for Iran market
      } else {
        percent = parsed;
      }
    } else if (_conditionType == AlertConditionType.priceThreshold && _direction == AlertDirection.bothSides) {
      upperTargetPrice = double.tryParse(FormatUtils.normalizePersianDigits(_upperPriceController.text.trim()));
      lowerTargetPrice = double.tryParse(FormatUtils.normalizePersianDigits(_lowerPriceController.text.trim()));
      upperNote = _upperNoteController.text.trim().isNotEmpty ? _upperNoteController.text.trim() : null;
      lowerNote = _lowerNoteController.text.trim().isNotEmpty ? _lowerNoteController.text.trim() : null;

      if (upperTargetPrice == null && lowerTargetPrice == null) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(lang == 'fa' ? 'لطفاً حداقل یکی از قیمت‌های حد بالا یا حد پایین را وارد کنید' : 'Please enter at least Upper Price or Lower Price'),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 3),
          ),
        );
        return;
      }
    } else {
      targetPrice = double.tryParse(FormatUtils.normalizePersianDigits(_targetPriceController.text.trim()));
      if (targetPrice == null) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(AppStrings.get('target_price_required', lang)),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 3),
          ),
        );
        return;
      }
    }

    final customNote = _customNoteController.text.trim().isNotEmpty
        ? _customNoteController.text.trim()
        : null;

    // Ensure live current price is available for percentage calculation
    var liveBasePrice = _currentPrice;
    if (liveBasePrice == null || liveBasePrice <= 0) {
      liveBasePrice = await ServerAlertService.fetchPriceViaServer(exchangeId, pair.marketSymbol);
    }

    // Calculate real effective target price for server (never send 0.0 or 1.0 fallback for percent change rules)
    double effectiveTargetPrice;
    if (_conditionType == AlertConditionType.percentChange) {
      if (liveBasePrice == null || liveBasePrice <= 0) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(lang == 'fa'
                ? 'برای نمادهای فاقد قیمت یا بازار بسته، لطفاً نوع شرط را روی «رسیدن به قیمت هدف» بگذارید تا بتوانید قیمت دلخواه خود را مستقیماً وارد کنید.'
                : 'For symbols without live price, please use "Target Price" condition to set your desired price directly.'),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 4),
          ),
        );
        return;
      }
      final p = percent ?? 2.5;
      final baseP = liveBasePrice;
      if (_direction == AlertDirection.below) {
        effectiveTargetPrice = baseP * (1.0 - (p / 100.0));
      } else {
        effectiveTargetPrice = baseP * (1.0 + (p / 100.0));
      }
    } else {
      effectiveTargetPrice = targetPrice ?? upperTargetPrice ?? lowerTargetPrice ?? liveBasePrice ?? 0.0;
    }

    final realUserId = await ServerAlertService.getEffectiveUserId();

    if (widget.initialRule != null) {
      final updatedRule = widget.initialRule!.copyWith(
        baseCurrency: pair.baseCurrency,
        counterCurrency: pair.counterCurrency,
        marketSymbol: pair.marketSymbol,
        exchangeId: exchangeId,
        checkIntervalSeconds: intervalSeconds,
        conditionType: _conditionType,
        direction: _direction,
        bothWayBehavior: _bothWayBehavior,
        percent: percent,
        targetPrice: targetPrice,
        upperTargetPrice: upperTargetPrice,
        upperNote: upperNote,
        lowerTargetPrice: lowerTargetPrice,
        lowerNote: lowerNote,
        customNote: customNote,
        customSound: _selectedSound,
        language: lang,
        soundEnabled: _soundEnabled,
        ttsEnabled: _ttsEnabled,
        vibrationEnabled: _vibrationEnabled,
        preferServerProxy: _preferServerProxy,
        basePrice: _currentPrice ?? widget.initialRule!.basePrice,
        lastCheckedPrice: _currentPrice ?? widget.initialRule!.lastCheckedPrice,
        previousPrice: (_currentPrice != null && widget.initialRule!.lastCheckedPrice != null && (_currentPrice! - widget.initialRule!.lastCheckedPrice!).abs() > 1e-8)
            ? widget.initialRule!.lastCheckedPrice
            : (widget.initialRule!.previousPrice ?? widget.initialRule!.basePrice),
      );
      await widget.repository.saveRule(updatedRule);
      // Sync to Python Alert Engine
      ServerAlertService.createAlertOnServer(
        ruleId: updatedRule.uuid,
        userId: realUserId,
        exchange: exchangeId,
        symbol: pair.marketSymbol,
        targetPrice: effectiveTargetPrice,
        condition: _direction == AlertDirection.below ? 'BELOW' : (_direction == AlertDirection.bothSides ? 'BOTHSIDES' : 'ABOVE'),
        conditionType: _conditionType.name,
        direction: _direction.name,
        bothWayBehavior: _bothWayBehavior.name,
        percent: percent,
        upperTargetPrice: upperTargetPrice,
        upperNote: upperNote,
        lowerTargetPrice: lowerTargetPrice,
        lowerNote: lowerNote,
        basePrice: updatedRule.basePrice,
        baseCurrency: pair.baseCurrency,
        counterCurrency: pair.counterCurrency,
        marketSymbol: pair.marketSymbol,
        language: lang,
        preferServerProxy: _preferServerProxy,
        checkIntervalSeconds: intervalSeconds,
        note: customNote ?? upperNote ?? lowerNote,
        triggerMode: updatedRule.triggerMode == TriggerMode.recurring ? 'recurring' : 'oneShot',
        soundEnabled: _soundEnabled,
        vibrationEnabled: _vibrationEnabled,
        ttsEnabled: _ttsEnabled,
        sound: _selectedSound,
        rawRule: updatedRule.toJson(),
      );
    } else {
      final newRule = AlertRule.create(
        pair: pair,
        exchangeId: exchangeId,
        checkIntervalSeconds: intervalSeconds,
        conditionType: _conditionType,
        direction: _direction,
        bothWayBehavior: _bothWayBehavior,
        percent: percent,
        targetPrice: targetPrice,
        upperTargetPrice: upperTargetPrice,
        upperNote: upperNote,
        lowerTargetPrice: lowerTargetPrice,
        lowerNote: lowerNote,
        customNote: customNote,
        customSound: _selectedSound,
        language: lang,
        soundEnabled: _soundEnabled,
        ttsEnabled: _ttsEnabled,
        vibrationEnabled: _vibrationEnabled,
        preferServerProxy: _preferServerProxy,
        currentPrice: _currentPrice,
      );
      await widget.repository.saveRule(newRule);
      // Sync to Python Alert Engine
      ServerAlertService.createAlertOnServer(
        ruleId: newRule.uuid,
        userId: realUserId,
        exchange: exchangeId,
        symbol: pair.marketSymbol,
        targetPrice: effectiveTargetPrice,
        condition: _direction == AlertDirection.below ? 'BELOW' : (_direction == AlertDirection.bothSides ? 'BOTHSIDES' : 'ABOVE'),
        conditionType: _conditionType.name,
        direction: _direction.name,
        bothWayBehavior: _bothWayBehavior.name,
        percent: percent,
        upperTargetPrice: upperTargetPrice,
        upperNote: upperNote,
        lowerTargetPrice: lowerTargetPrice,
        lowerNote: lowerNote,
        basePrice: newRule.basePrice,
        baseCurrency: pair.baseCurrency,
        counterCurrency: pair.counterCurrency,
        marketSymbol: pair.marketSymbol,
        language: lang,
        preferServerProxy: _preferServerProxy,
        checkIntervalSeconds: intervalSeconds,
        note: customNote ?? upperNote ?? lowerNote,
        triggerMode: newRule.triggerMode == TriggerMode.recurring ? 'recurring' : 'oneShot',
        soundEnabled: _soundEnabled,
        vibrationEnabled: _vibrationEnabled,
        ttsEnabled: _ttsEnabled,
        sound: _selectedSound,
        rawRule: newRule.toJson(),
      );
    }

    if (mounted) {
      Navigator.of(context).pop(true);
    }
  }

  void _handleBackNavigation() {
    if (widget.initialRule != null) {
      Navigator.of(context).pop();
    } else if (_flowType == MarketFlowType.iran) {
      if (_step > 1) {
        setState(() {
          _selectedIranDomesticAsset = null;
          _selectedExchange = null;
          _selectedPair = null;
          _step = 1;
        });
      } else {
        setState(() {
          _flowType = MarketFlowType.none;
          _step = 1;
        });
      }
    } else if (_step > 1) {
      setState(() => _step--);
    } else if (_flowType != MarketFlowType.none) {
      setState(() {
        _flowType = MarketFlowType.none;
        _step = 1;
      });
    } else {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final settingsService = context.watch<SettingsService>();
    final lang = settingsService.settings.language;

    final isEditMode = widget.initialRule != null;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        _handleBackNavigation();
      },
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          backgroundColor: theme.colorScheme.surface,
          elevation: 0,
          leading: IconButton(
            icon: Icon(Icons.arrow_back_rounded, color: theme.colorScheme.onSurface),
            onPressed: _handleBackNavigation,
          ),
          title: Text(
            isEditMode
                ? AppStrings.get('edit_alert_title', lang)
                : (_flowType == MarketFlowType.none
                    ? AppStrings.get('choose_market_step', lang)
                    : (_flowType == MarketFlowType.crypto
                        ? AppStrings.get('crypto_market_title', lang)
                        : (_flowType == MarketFlowType.macro
                            ? AppStrings.get('macro_market_title', lang)
                            : (_step == 2 && _selectedIranExchange != null
                                ? '${AppStrings.get('exchange', lang)}: ${_selectedIranExchange!.name}'
                                : AppStrings.get('iran_market_title', lang))))),
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
          ),
        ),
        body: _buildCurrentBody(theme, lang),
      ),
    );
  }

  Widget _buildCurrentBody(ThemeData theme, String lang) {
    if (_flowType == MarketFlowType.none) {
      return _buildMarketTypeChooser(theme, lang);
    } else if (_flowType == MarketFlowType.crypto) {
      if (_step == 1) return _buildCryptoExchangePicker(theme, lang);
      if (_step == 2) return _buildCryptoPairPicker(theme, lang);
      return _buildConditionAndFrequencyStep(theme, lang);
    } else if (_flowType == MarketFlowType.macro) {
      if (_step == 1) return _buildMacroAssetPicker(theme, lang);
      return _buildConditionAndFrequencyStep(theme, lang);
    } else {
      // MarketFlowType.iran -> 100% STRICT RTL & PURE PERSIAN
      Widget iranChild;
      if (_step == 1) {
        iranChild = _buildIranMarketPicker(theme, 'fa');
      } else {
        iranChild = _buildConditionAndFrequencyStep(theme, 'fa');
      }
      return Directionality(
        textDirection: TextDirection.rtl,
        child: iranChild,
      );
    }
  }

  Widget _buildMarketTypeChooser(ThemeData theme, String lang) {
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: theme.colorScheme.primary.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.auto_awesome_rounded, size: 14, color: theme.colorScheme.primary),
              const SizedBox(width: 6),
              Text(
                AppStrings.get('choose_market_step', lang),
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.primary),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Text(
          AppStrings.get('choose_market_title', lang),
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: theme.colorScheme.onSurface),
        ),
        const SizedBox(height: 6),
        Text(
          AppStrings.get('choose_market_desc', lang),
          style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.65)),
        ),
        const SizedBox(height: 24),

        // CARD 1: INTERNATIONAL CRYPTO MARKET (Exclusively Global)
        _buildMarketCard(
          theme: theme,
          icon: Icons.public_rounded,
          iconBg: theme.colorScheme.primary.withValues(alpha: 0.15),
          iconColor: theme.colorScheme.primary,
          borderColor: theme.colorScheme.primary.withValues(alpha: 0.35),
          badgeText: AppStrings.get('crypto_market_badge', lang),
          title: AppStrings.get('crypto_market_title', lang),
          description: AppStrings.get('crypto_market_desc', lang),
          tags: ['Binance', 'Bybit', 'OKX', 'KuCoin', 'MEXC', 'Gate.io'],
          buttonText: AppStrings.get('crypto_market_cta', lang),
          buttonColor: theme.colorScheme.primary,
          onTap: () {
            setState(() {
              _flowType = MarketFlowType.crypto;
              _step = 1;
            });
          },
        ),

        const SizedBox(height: 18),

        // CARD 2: GLOBAL STOCKS, BONDS & FOREX
        _buildMarketCard(
          theme: theme,
          icon: Icons.account_balance_rounded,
          iconBg: theme.colorScheme.secondary.withValues(alpha: 0.15),
          iconColor: theme.colorScheme.secondary,
          borderColor: theme.colorScheme.secondary.withValues(alpha: 0.35),
          badgeText: AppStrings.get('macro_market_badge', lang),
          title: AppStrings.get('macro_market_title', lang),
          description: AppStrings.get('macro_market_desc', lang),
          tags: ['NVDA', 'Apple', 'Gold (XAU)', 'EUR/USD', 'S&P 500', 'US10Y'],
          buttonText: AppStrings.get('macro_market_cta', lang),
          buttonColor: theme.colorScheme.secondary,
          onTap: () {
            setState(() {
              _flowType = MarketFlowType.macro;
              _step = 1;
            });
          },
        ),

        const SizedBox(height: 18),

        // CARD 3: IRAN DOMESTIC & TOMAN MARKET (Dedicated 2-Part Hub)
        _buildMarketCard(
          theme: theme,
          icon: Icons.monetization_on_rounded,
          iconBg: const Color(0xFFFFB300).withValues(alpha: 0.15),
          iconColor: const Color(0xFFFFB300),
          borderColor: const Color(0xFFFFB300).withValues(alpha: 0.4),
          badgeText: AppStrings.get('iran_market_badge', lang),
          title: AppStrings.get('iran_market_title', lang),
          description: AppStrings.get('iran_market_desc', lang),
          tags: ['دلار آزاد', 'طلای ۱۸ عیار', 'سکه امامی', 'نوبیتکس', 'والکس', 'تبدیل', 'تترلند'],
          buttonText: AppStrings.get('iran_market_cta', lang),
          buttonColor: const Color(0xFFFFB300),
          onTap: () {
            setState(() {
              _flowType = MarketFlowType.iran;
              _step = 1;
              _iranSubTab = 0;
            });
            _loadIranMarketOverview();
          },
        ),
      ],
    );
  }

  Widget _buildMarketCard({
    required ThemeData theme,
    required IconData icon,
    required Color iconBg,
    required Color iconColor,
    required Color borderColor,
    required String badgeText,
    required String title,
    required String description,
    required List<String> tags,
    required String buttonText,
    required Color buttonColor,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: borderColor, width: 1.5),
          boxShadow: [
            BoxShadow(
              color: buttonColor.withValues(alpha: 0.08),
              blurRadius: 14,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    color: iconBg,
                    shape: BoxShape.circle,
                    border: Border.all(color: buttonColor.withValues(alpha: 0.3)),
                  ),
                  child: Icon(icon, color: iconColor, size: 26),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: theme.dividerColor),
                  ),
                  child: Text(
                    badgeText,
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: buttonColor),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              title,
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: theme.colorScheme.onSurface),
            ),
            const SizedBox(height: 8),
            Text(
              description,
              style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.7), height: 1.5),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: tags
                  .map((t) => Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: theme.dividerColor.withValues(alpha: 0.5)),
                        ),
                        child: Text(
                          t,
                          style: TextStyle(fontSize: 10, color: theme.colorScheme.onSurface.withValues(alpha: 0.65)),
                        ),
                      ))
                  .toList(),
            ),
            const SizedBox(height: 16),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 12),
              decoration: BoxDecoration(
                color: buttonColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: buttonColor.withValues(alpha: 0.3)),
              ),
              alignment: Alignment.center,
              child: Text(
                buttonText,
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: buttonColor),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCryptoExchangePicker(ThemeData theme, String lang) {
    const iranExchangeIds = {
      'iran_market', 'nobitex', 'wallex', 'ramzinex', 'tabdeal', 'bitbarg',
      'tetherland', 'abantether', 'sarmayex', 'exir'
    };
    final allExchanges = widget.registry.getAll().where((ex) {
      if (ex.id == 'global_stocks' || iranExchangeIds.contains(ex.id)) return false;
      if (ex.category == ExchangeCategory.middleEast || ex.defaultCounterCurrency == 'TMN') return false;
      return true;
    }).toList();

    final filtered = allExchanges.where((ex) {
      if (_selectedCategory != ExchangeCategory.all && ex.category != _selectedCategory) {
        return false;
      }
      final q = _exchangeSearchQuery.trim().toLowerCase();
      if (q.isEmpty) return true;
      return ex.name.toLowerCase().contains(q) ||
          ex.id.toLowerCase().contains(q) ||
          ex.countryBadge.toLowerCase().contains(q);
    }).toList()
      ..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: TextField(
            onChanged: (val) => setState(() => _exchangeSearchQuery = val),
            style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurface),
            decoration: InputDecoration(
              hintText: AppStrings.get('search_exchange_hint', lang),
              prefixIcon: Icon(Icons.search, size: 20, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
              filled: true,
              fillColor: theme.colorScheme.surface,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
            ),
          ),
        ),

        // Category Filter Chips
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: ExchangeCategory.values.map((cat) {
              final isSelected = _selectedCategory == cat;
              return Padding(
                padding: const EdgeInsets.only(right: 6, bottom: 6),
                child: FilterChip(
                  selected: isSelected,
                  label: Text('${cat.icon} ${cat.getTitle(lang)}'),
                  labelStyle: TextStyle(
                    fontSize: 11,
                    fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                    color: isSelected ? theme.colorScheme.primary : theme.colorScheme.onSurface.withValues(alpha: 0.7),
                  ),
                  selectedColor: theme.colorScheme.primary.withValues(alpha: 0.15),
                  backgroundColor: theme.colorScheme.surface,
                  side: BorderSide(color: isSelected ? theme.colorScheme.primary : theme.dividerColor),
                  onSelected: (_) => setState(() => _selectedCategory = cat),
                ),
              );
            }).toList(),
          ),
        ),

        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: filtered.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final ex = filtered[index];
              return InkWell(
                onTap: () => _onExchangeChosen(ex),
                borderRadius: BorderRadius.circular(14),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: theme.dividerColor),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: theme.colorScheme.primary.withValues(alpha: 0.12),
                          shape: BoxShape.circle,
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          ex.name.substring(0, 1).toUpperCase(),
                          style: TextStyle(fontWeight: FontWeight.bold, color: theme.colorScheme.primary),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(ex.name, style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: theme.colorScheme.onSurface)),
                            const SizedBox(height: 2),
                            Text(
                              '${ex.countryBadge} · ${ex.defaultCounterCurrency}',
                              style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                            ),
                          ],
                        ),
                      ),
                      Icon(Icons.arrow_forward_ios_rounded, size: 14, color: theme.colorScheme.onSurface.withValues(alpha: 0.4)),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildCryptoPairPicker(ThemeData theme, String lang) {
    final filtered = SymbolFilterHelper.filterAndSort(_exchangePairs, _pairSearchQuery);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: theme.dividerColor),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    '${AppStrings.get('exchange', lang)}: ${_selectedExchange?.name} (${_exchangePairs.length} ${AppStrings.get('pair', lang)})',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: theme.colorScheme.onSurface),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: _isLoadingPairs ? null : () => _fetchPairsForSelectedExchange(forceRefresh: true),
                  icon: _isLoadingPairs
                      ? const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.sync_rounded, size: 14),
                  label: Text(AppStrings.get('refresh_list', lang), style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.colorScheme.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  ),
                ),
              ],
            ),
          ),
        ),

        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: TextField(
            onChanged: (val) => setState(() => _pairSearchQuery = val),
            style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurface),
            decoration: InputDecoration(
              hintText: AppStrings.get('search_crypto_hint', lang),
              prefixIcon: Icon(Icons.search, size: 20, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
              filled: true,
              fillColor: theme.colorScheme.surface,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
            ),
          ),
        ),
        const SizedBox(height: 8),

        Expanded(
          child: _isLoadingPairs
              ? Center(child: CircularProgressIndicator(color: theme.colorScheme.primary))
              : (filtered.isEmpty
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.search_off_rounded, size: 48, color: theme.colorScheme.onSurface.withValues(alpha: 0.3)),
                            const SizedBox(height: 12),
                            Text(
                              'نماد مورد نظر یافت نشد',
                              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: theme.colorScheme.onSurface),
                            ),
                            if (_pairSearchQuery.trim().isNotEmpty) ...[
                              const SizedBox(height: 16),
                              ElevatedButton.icon(
                                onPressed: () {
                                  final base = _pairSearchQuery.trim().toUpperCase();
                                  final quote = _selectedExchange?.defaultCounterCurrency ?? 'USDT';
                                  _onPairChosen(CurrencyPair(
                                    baseCurrency: base,
                                    counterCurrency: quote,
                                    marketSymbol: '$base$quote',
                                  ));
                                },
                                icon: const Icon(Icons.add_circle_outline_rounded, size: 18),
                                label: Text(
                                  'پایش دستی ${_pairSearchQuery.trim().toUpperCase()} / ${_selectedExchange?.defaultCounterCurrency ?? "USDT"}',
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: theme.colorScheme.primary,
                                  foregroundColor: Colors.white,
                                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: filtered.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 8),
                      itemBuilder: (context, index) {
                        final pair = filtered[index];
                        final fullName = CryptoIcons.getName(pair.baseCurrency);
                        return InkWell(
                          onTap: () => _onPairChosen(pair),
                          borderRadius: BorderRadius.circular(14),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.surface,
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: theme.dividerColor),
                            ),
                            child: Row(
                              children: [
                                CryptoIcons.buildLogo(pair.baseCurrency, size: 36),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Text(
                                        pair.displayName,
                                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: theme.colorScheme.onSurface),
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                        fullName,
                                        style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ],
                                  ),
                                ),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: theme.colorScheme.primary.withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Text(
                                    AppStrings.get('select_cta', lang),
                                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: theme.colorScheme.primary),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    )),
        ),
      ],
    );
  }

  Widget _buildMacroAssetPicker(ThemeData theme, String lang) {
    final allAssets = GlobalStocksExchange.predefinedStocks;
    final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';
    final filtered = allAssets.where((a) {
      if (_macroCategoryFilter != 'all') {
        if (_macroCategoryFilter == 'Top100') {
          if (a['cat'] != 'Top100' && a['isTop100'] != true) return false;
        } else if (_macroCategoryFilter == 'China') {
          if (a['cat'] != 'China') return false;
        } else if (a['cat'] != _macroCategoryFilter) {
          return false;
        }
      }
      final q = _macroSearchQuery.trim().toLowerCase();
      if (q.isEmpty) return true;
      final sym = (a['symbol'] as String).toLowerCase();
      final name = (a['name'] as String).toLowerCase();
      final nameFa = (a['nameFa'] as String).toLowerCase();
      return sym.contains(q) || name.contains(q) || nameFa.contains(q);
    }).toList();

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: TextField(
            onChanged: (val) => setState(() => _macroSearchQuery = val),
            style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurface),
            decoration: InputDecoration(
              hintText: isFa ? 'جستجوی نماد، طلا، نفت، شاخص‌ها، سهام، فارکس...' : 'Search symbol, Gold, Oil, Indices, Stocks, Forex...',
              prefixIcon: Icon(Icons.search, size: 20, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
              filled: true,
              fillColor: theme.colorScheme.surface,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
            ),
          ),
        ),

        // Category Filter Chips
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              _buildMacroChip(isFa ? '🌐 همه نمادها' : 'All', 'all', theme),
              _buildMacroChip(isFa ? '🚀 هوافضا، استارلینک و فضا' : 'SpaceX & Space', 'Aerospace', theme),
              _buildMacroChip(isFa ? '💻 تراشه‌ها و فناوری' : 'Semiconductors & Tech', 'Tech', theme),
              _buildMacroChip(isFa ? '⛏️ ماینینگ و فین‌تک' : 'Mining & Fintech', 'FintechMining', theme),
              _buildMacroChip(isFa ? '🪙 شاخص‌های کلان کریپتو و دامیننس' : 'Crypto Macro & Dominance', 'CryptoMacro', theme),
              _buildMacroChip(isFa ? '🇨🇳 بازارهای چین و آسیا' : 'China & Asia', 'China', theme),
              _buildMacroChip(isFa ? '🏆 ۱۰۰ شرکت برتر جهان' : 'Top 100 Global', 'Top100', theme),
              _buildMacroChip(isFa ? '🏛️ اوراق و شاخص دلار' : 'Macro & DXY', 'Macro', theme),
              _buildMacroChip(isFa ? '📊 شاخص‌های جهانی' : 'Indices', 'Indices', theme),
              _buildMacroChip(isFa ? '🥇 طلا، نقره و انرژی' : 'Metals & Energy', 'Commodities', theme),
              _buildMacroChip(isFa ? '💱 فارکس' : 'Forex', 'Forex', theme),
            ],
          ),
        ),

        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: filtered.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final asset = filtered[index];
              final sym = asset['symbol'] as String;
              final unit = (asset['unit'] as String?) ?? 'USD';
              final livePrice = _macroLivePrices[sym];
              final displayName = isFa ? (asset['nameFa'] as String) : (asset['name'] as String);
              final iconStr = asset['icon']?.toString() ?? '📊';

              return InkWell(
                onTap: () => _onMacroAssetChosen(asset),
                borderRadius: BorderRadius.circular(14),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: theme.dividerColor),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 38,
                        height: 38,
                        decoration: BoxDecoration(
                          color: theme.colorScheme.secondary.withValues(alpha: 0.12),
                          shape: BoxShape.circle,
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          iconStr,
                          style: const TextStyle(fontSize: 18),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              asset['name'] as String,
                              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: theme.colorScheme.onSurface),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '${asset['symbol']} · ${asset['cat'] ?? ''}',
                              style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            livePrice != null ? _formatSmartPrice(livePrice, unit) : '—',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 13,
                              fontFamily: 'monospace',
                              color: livePrice != null
                                  ? theme.colorScheme.onSurface
                                  : theme.colorScheme.onSurface.withValues(alpha: 0.45),
                            ),
                          ),
                          Text(
                            AppStrings.get('select_cta', lang),
                            style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: theme.colorScheme.secondary),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildMacroChip(String label, String catKey, ThemeData theme) {
    final isSelected = _macroCategoryFilter == catKey;
    return Padding(
      padding: const EdgeInsets.only(right: 6, bottom: 6),
      child: FilterChip(
        selected: isSelected,
        label: Text(label),
        labelStyle: TextStyle(
          fontSize: 11,
          fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
          color: isSelected ? theme.colorScheme.secondary : theme.colorScheme.onSurface.withValues(alpha: 0.7),
        ),
        selectedColor: theme.colorScheme.secondary.withValues(alpha: 0.15),
        backgroundColor: theme.colorScheme.surface,
        side: BorderSide(color: isSelected ? theme.colorScheme.secondary : theme.dividerColor),
        onSelected: (_) => setState(() => _macroCategoryFilter = catKey),
      ),
    );
  }

  
  // =========================================================================
  // IRAN DOMESTIC & TOMAN MARKET HUB (UNIFIED SINGLE-LIST SCREEN)
  // =========================================================================
  Widget _buildIranMarketPicker(ThemeData theme, String lang) {
    final allAssets = IranDomesticExchange.predefinedAssets;
    final filtered = allAssets.where((a) {
      if (_iranCategoryFilter != 'all') {
        if (a['cat'] != _iranCategoryFilter) return false;
      }
      final q = _iranSearchQuery.trim().toLowerCase();
      if (q.isEmpty) return true;
      final sym = (a['symbol'] as String).toLowerCase();
      final name = (a['name'] as String).toLowerCase();
      final nameFa = (a['nameFa'] as String).toLowerCase();
      return sym.contains(q) || name.contains(q) || nameFa.contains(q);
    }).toList();

    return Column(
      children: [
        // Search Bar in Persian
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: TextField(
            onChanged: (val) => setState(() => _iranSearchQuery = val),
            style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurface),
            decoration: InputDecoration(
              hintText: 'جستجوی نماد (دلار، طلای ۱۸، سکه، عیار، طلا، تتر نوبیتکس، درهم، بورس)...',
              prefixIcon: Icon(Icons.search, size: 20, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
              filled: true,
              fillColor: theme.colorScheme.surface,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
            ),
          ),
        ),

        // Category Filter Chips in Persian
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              _buildIranChip(AppStrings.get('iran_cat_all', lang), 'all', theme),
              _buildIranChip(AppStrings.get('iran_cat_gold', lang), 'Gold', theme),
              _buildIranChip(AppStrings.get('iran_cat_coins', lang), 'Coins', theme),
              _buildIranChip(AppStrings.get('iran_cat_currencies', lang), 'Currencies', theme),
              _buildIranChip(AppStrings.get('iran_cat_tether', lang), 'Tether', theme),
              _buildIranChip(AppStrings.get('iran_cat_digital_gold', lang), 'DigitalGold', theme),
              _buildIranChip(AppStrings.get('iran_cat_gold_funds', lang), 'GoldFunds', theme),
              _buildIranChip(AppStrings.get('iran_cat_leveraged', lang), 'LeveragedFunds', theme),
              _buildIranChip(AppStrings.get('iran_cat_top_stocks', lang), 'TopStocks', theme),
              _buildIranChip(AppStrings.get('iran_cat_bourse', lang), 'Bourse', theme),
            ],
          ),
        ),

        // Market Closed Notice Banner (Rule 6: Show TSE status, schedule_fa, next_open)
        Builder(
          builder: (context) {
            final tseInfo = _iranMarketsStatus?['tse'] as Map<String, dynamic>?;
            final isTseClosed = tseInfo != null ? (tseInfo['status'] == 'closed') : true;
            final scheduleFa = tseInfo?['schedule_fa'] as String? ?? 'شنبه تا چهارشنبه، ۰۹:۰۰ تا ۱۲:۳۰ (وقت تهران)';
            final nextOpenFa = tseInfo?['next_open_fa'] as String? ?? tseInfo?['next_open'] as String?;
            final exchangeStateFa = tseInfo?['exchange_state_fa'] as String?;

            if (!isTseClosed) return const SizedBox(height: 4);

            return Container(
              margin: const EdgeInsets.fromLTRB(16, 6, 16, 4),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: const Color(0xFFE65100).withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFE65100).withValues(alpha: 0.25)),
              ),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2.5),
                    decoration: BoxDecoration(
                      color: Colors.red.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: Colors.red.withValues(alpha: 0.3)),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.lock_clock, size: 12, color: Colors.redAccent),
                        SizedBox(width: 4),
                        Text(
                          'بسته',
                          style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.redAccent),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          scheduleFa,
                          style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600, color: theme.colorScheme.onSurface.withValues(alpha: 0.9)),
                        ),
                        if (nextOpenFa != null || exchangeStateFa != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 2),
                            child: Text(
                              [
                                if (nextOpenFa != null) 'بازگشایی: $nextOpenFa',
                                if (exchangeStateFa != null) 'وضعیت: $exchangeStateFa',
                              ].join(' · '),
                              style: TextStyle(fontSize: 9.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),

        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: filtered.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final asset = filtered[index];
              final sym = asset['symbol'] as String;
              final unit = (asset['unit'] as String?) ?? 'تومان';
              final livePrice = _iranLivePrices[sym] ?? (asset['price'] as num?)?.toDouble();
              final displayName = asset['nameFa'] as String? ?? asset['name'] as String;
              final iconStr = asset['icon']?.toString() ?? '🪙';
              final cat = asset['cat'] as String? ?? '';
              final isTseAsset = cat == 'Bourse' || cat == 'GoldFunds' || cat == 'LeveragedFunds' || cat == 'IndexFunds' || cat == 'TopStocks';
              final tseInfo = _iranMarketsStatus?['tse'] as Map<String, dynamic>?;
              final isTseClosed = tseInfo != null ? (tseInfo['status'] == 'closed') : true;
              final showClosedBadge = isTseAsset && isTseClosed;

              return InkWell(
                onTap: () => _onIranDomesticAssetChosen(asset),
                borderRadius: BorderRadius.circular(14),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: theme.dividerColor),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: const Color(0xFFFFB300).withValues(alpha: 0.12),
                          shape: BoxShape.circle,
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          iconStr,
                          style: const TextStyle(fontSize: 20),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Flexible(
                                  child: Text(
                                    displayName,
                                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: theme.colorScheme.onSurface),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                if (showClosedBadge) ...[
                                  const SizedBox(width: 6),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                                    decoration: BoxDecoration(
                                      color: Colors.red.withValues(alpha: 0.12),
                                      borderRadius: BorderRadius.circular(4),
                                    ),
                                    child: const Text(
                                      'بسته',
                                      style: TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: Colors.redAccent),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                            const SizedBox(height: 2),
                            Text(
                              _iranItemMeta[sym]?['state_fa'] != null
                                  ? '$sym · ${_iranItemMeta[sym]!['state_fa']}'
                                  : '$sym · ${asset['cat'] ?? ''}',
                              style: TextStyle(
                                fontSize: 11,
                                color: (_iranItemMeta[sym]?['state'] == 'no_data' || _iranItemMeta[sym]?['state'] == 'no_trade_today')
                                    ? Colors.orangeAccent.withValues(alpha: 0.9)
                                    : theme.colorScheme.onSurface.withValues(alpha: 0.55),
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            livePrice != null ? _formatSmartPrice(livePrice, unit) : '—',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 13,
                              fontFamily: 'monospace',
                              color: livePrice != null ? const Color(0xFFFFB300) : theme.colorScheme.onSurface.withValues(alpha: 0.4),
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            livePrice != null ? AppStrings.get('select_cta', lang) : (_iranItemMeta[sym]?['state_fa'] ?? 'فعلاً داده‌ای نیست'),
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                              color: livePrice != null ? const Color(0xFFFFB300) : Colors.orangeAccent.withValues(alpha: 0.8),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildIranChip(String label, String catKey, ThemeData theme) {
    final isSelected = _iranCategoryFilter == catKey;
    return Padding(
      padding: const EdgeInsets.only(right: 6, bottom: 6),
      child: FilterChip(
        selected: isSelected,
        label: Text(label),
        labelStyle: TextStyle(
          fontSize: 11,
          fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
          color: isSelected ? const Color(0xFFFFB300) : theme.colorScheme.onSurface.withValues(alpha: 0.7),
        ),
        selectedColor: const Color(0xFFFFB300).withValues(alpha: 0.15),
        backgroundColor: theme.colorScheme.surface,
        side: BorderSide(color: isSelected ? const Color(0xFFFFB300) : theme.dividerColor),
        onSelected: (_) => setState(() => _iranCategoryFilter = catKey),
      ),
    );
  }
  Widget _buildConditionAndFrequencyStep(ThemeData theme, String lang) {
    final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';
    final String assetName;
    final String quoteCurrency;
    final String? exchangeDisplayName;

    if (_flowType == MarketFlowType.crypto) {
      assetName = _selectedPair?.displayName ?? '';
      quoteCurrency = _selectedPair?.counterCurrency ?? 'USDT';
      exchangeDisplayName = _selectedExchange?.name;
    } else if (_flowType == MarketFlowType.iran) {
      if (_selectedIranDomesticAsset != null) {
        assetName = (_selectedIranDomesticAsset!['nameFa'] as String?) ?? (_selectedIranDomesticAsset!['name'] as String? ?? '');
        quoteCurrency = (_selectedIranDomesticAsset!['unit'] as String?) ?? 'TMN';
        final displayUnit = FormatUtils.resolveCurrencyDisplayName(quoteCurrency, lang: lang);
        exchangeDisplayName = isFa ? '🇮🇷 بازار تهران ($displayUnit)' : '🇮🇷 Tehran Market ($displayUnit)';
      } else {
        assetName = _selectedPair?.displayName ?? '';
        quoteCurrency = _selectedPair?.counterCurrency ?? 'TMN';
        exchangeDisplayName = _selectedIranExchange?.name;
      }
    } else {
      final macro = _selectedMacroAsset;
      if (macro != null) {
        assetName = (isFa ? macro['nameFa'] : macro['name']) as String? ?? '';
        quoteCurrency = (macro['unit'] as String?) ?? 'USD';
      } else {
        assetName = '';
        quoteCurrency = 'USD';
      }
      exchangeDisplayName = '🏛️ بازارهای جهانی';
    }

    final bool isMacroIndicator = _flowType == MarketFlowType.macro &&
        (_selectedMacroAsset?['cat'] == 'Macro' ||
         _selectedMacroAsset?['cat'] == 'CryptoMacro' ||
         ['CPI', 'FEDFUNDS', 'US10Y', 'UNRATE', 'DX-Y.NYB'].contains(_selectedMacroAsset?['symbol']));

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        // Premium Selected Asset & Live Price Card
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.35), width: 1.5),
            boxShadow: [
              BoxShadow(
                color: theme.colorScheme.primary.withValues(alpha: 0.06),
                blurRadius: 16,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  if (_flowType == MarketFlowType.crypto && _selectedPair != null)
                    CryptoIcons.buildLogo(_selectedPair!.baseCurrency, size: 42)
                  else
                    Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.secondary.withValues(alpha: 0.15),
                        shape: BoxShape.circle,
                      ),
                      alignment: Alignment.center,
                      child: Icon(Icons.show_chart_rounded, color: theme.colorScheme.secondary, size: 24),
                    ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                assetName,
                                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 8),
                            if (exchangeDisplayName != null)
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: _flowType == MarketFlowType.iran
                                      ? const Color(0xFFFFB300).withValues(alpha: 0.15)
                                      : theme.colorScheme.primary.withValues(alpha: 0.12),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Text(
                                  exchangeDisplayName,
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.bold,
                                    color: _flowType == MarketFlowType.iran
                                        ? const Color(0xFFFFB300)
                                        : theme.colorScheme.primary,
                                  ),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 2),
                        Text(
                          _flowType == MarketFlowType.crypto && _selectedPair != null
                              ? CryptoIcons.getName(_selectedPair!.baseCurrency)
                              : AppStrings.get('selected_asset', lang),
                          style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Divider(height: 1, color: theme.dividerColor),
              const SizedBox(height: 12),

              // Live Current Price Row
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: _isLoadingPrice
                              ? Colors.amber
                              : (_currentPrice != null ? const Color(0xFF00E676) : Colors.red),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        _isLoadingPrice
                            ? AppStrings.get('fetching_live_price', lang)
                            : (_currentPrice != null
                                ? AppStrings.get('live_market_price', lang)
                                : AppStrings.get('live_price_unavailable', lang)),
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                        ),
                      ),
                    ],
                  ),
                  if (_isLoadingPrice)
                    SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: theme.colorScheme.primary),
                    )
                  else if (_currentPrice != null)
                    Row(
                      children: [
                        Text(
                          _formatSmartPrice(_currentPrice!, quoteCurrency),
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w900,
                            fontFamily: 'monospace',
                            color: theme.colorScheme.primary,
                          ),
                        ),
                        const SizedBox(width: 6),
                        InkWell(
                          onTap: _fetchLivePriceForSelectedAsset,
                          borderRadius: BorderRadius.circular(16),
                          child: Padding(
                            padding: const EdgeInsets.all(4),
                            child: Icon(Icons.refresh_rounded, size: 18, color: theme.colorScheme.primary),
                          ),
                        ),
                      ],
                    )
                  else
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: Colors.orange.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(color: Colors.orange.withValues(alpha: 0.3)),
                          ),
                          child: Text(
                            (_selectedIranDomesticAsset != null && _iranItemMeta[_selectedIranDomesticAsset!['symbol']]?['state_fa'] != null)
                                ? _iranItemMeta[_selectedIranDomesticAsset!['symbol']]!['state_fa']
                                : AppStrings.get('live_price_unavailable', lang),
                            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.orangeAccent),
                          ),
                        ),
                        const SizedBox(width: 6),
                        InkWell(
                          onTap: _fetchLivePriceForSelectedAsset,
                          borderRadius: BorderRadius.circular(16),
                          child: Padding(
                            padding: const EdgeInsets.all(4),
                            child: Icon(Icons.refresh_rounded, size: 18, color: theme.colorScheme.primary),
                          ),
                        ),
                      ],
                    ),
                ],
              ),
              if (_flowType == MarketFlowType.iran && _selectedIranDomesticAsset != null) ...[
                Builder(
                  builder: (context) {
                    final symKey = _selectedIranDomesticAsset!['symbol'] as String? ?? '';
                    final cat = _selectedIranDomesticAsset!['cat'] as String? ?? '';
                    final meta = _iranItemMeta[symKey];
                    final isTseAsset = cat == 'Bourse' || cat == 'GoldFunds' || cat == 'LeveragedFunds' || cat == 'IndexFunds' || cat == 'TopStocks';
                    final tseInfo = _iranMarketsStatus?['tse'] as Map<String, dynamic>?;
                    final isTseClosed = tseInfo != null ? (tseInfo['status'] == 'closed') : true;

                    if (_currentPrice == null || meta?['state'] == 'no_data') {
                      final stateFa = meta?['state_fa'] as String? ?? 'فعلاً داده‌ای نیست';
                      return Container(
                        margin: const EdgeInsets.only(top: 12),
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.orange.withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.orange.withValues(alpha: 0.25)),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.info_outline, size: 16, color: Colors.orangeAccent),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    stateFa,
                                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.orangeAccent),
                                  ),
                                  Text(
                                    'این نماد در سامانه پشتیبانی می‌شود. لطفاً قیمت هدف دلخواه خود را مستقیماً وارد نمایید تا پس از معامله در بازار بررسی گردد.',
                                    style: TextStyle(fontSize: 10, color: theme.colorScheme.onSurface.withValues(alpha: 0.8)),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      );
                    }

                    if (!isTseAsset || !isTseClosed) return const SizedBox.shrink();

                    final scheduleFa = tseInfo?['schedule_fa'] as String? ?? 'شنبه تا چهارشنبه، ۰۹:۰۰ تا ۱۲:۳۰ (وقت تهران)';
                    final nextOpenFa = tseInfo?['next_open_fa'] as String? ?? tseInfo?['next_open'] as String?;
                    final exchangeStateFa = tseInfo?['exchange_state_fa'] as String?;

                    return Container(
                      margin: const EdgeInsets.only(top: 12),
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.red.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.lock_clock, size: 16, color: Colors.redAccent),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'بازار بورس بسته است (آخرین قیمت ثبت‌شده)',
                                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.redAccent),
                                ),
                                Text(
                                  scheduleFa,
                                  style: TextStyle(fontSize: 10, color: theme.colorScheme.onSurface.withValues(alpha: 0.8)),
                                ),
                                if (nextOpenFa != null || exchangeStateFa != null)
                                  Text(
                                    [
                                      if (nextOpenFa != null) 'بازگشایی: $nextOpenFa',
                                      if (exchangeStateFa != null) 'وضعیت: $exchangeStateFa',
                                    ].join(' · '),
                                    style: TextStyle(fontSize: 9.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 20),

        // 1. FREQUENCY SECTION
        Text(
          AppStrings.get('auto_check_schedule', lang),
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: theme.colorScheme.onSurface),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              flex: 2,
              child: TextField(
                controller: _unitValueController,
                keyboardType: TextInputType.number,
                style: TextStyle(fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                decoration: InputDecoration(
                  labelText: AppStrings.get('unit_count', lang),
                  filled: true,
                  fillColor: theme.colorScheme.surface,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              flex: 3,
              child: DropdownButtonFormField<CheckUnit>(
                initialValue: _checkUnit == CheckUnit.seconds ? CheckUnit.minutes : _checkUnit,
                decoration: InputDecoration(
                  labelText: AppStrings.get('time_unit', lang),
                  filled: true,
                  fillColor: theme.colorScheme.surface,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
                ),
                items: [
                  DropdownMenuItem(value: CheckUnit.minutes, child: Text(AppStrings.get('minutes', lang))),
                  DropdownMenuItem(value: CheckUnit.hours, child: Text(AppStrings.get('hours', lang))),
                ],
                onChanged: (val) {
                  if (val != null) setState(() => _checkUnit = val);
                },
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          '${AppStrings.get('interval_prefix', lang)}${_formatCalculatedInterval(lang)}${AppStrings.get('interval_suffix', lang)}',
          style: TextStyle(fontSize: 11, color: theme.colorScheme.primary, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 20),

        // 2. CONDITION TYPE
        Text(
          AppStrings.get('condition_type', lang),
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: theme.colorScheme.onSurface),
        ),
        const SizedBox(height: 8),

        if (isMacroIndicator) ...[
          // Specialized Macro Indicator Condition Selector
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: theme.colorScheme.secondary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: theme.colorScheme.secondary.withValues(alpha: 0.25)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.query_stats_rounded, size: 16, color: theme.colorScheme.secondary),
                    const SizedBox(width: 6),
                    Text(
                      lang == 'fa' ? 'نوع شرط شاخص کلان اقتصادی:' : 'Macro Economic Alert Condition:',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.secondary),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: InkWell(
                        onTap: () {
                          setState(() {
                            _conditionType = AlertConditionType.percentChange;
                            _percentController.text = '0.01';
                          });
                        },
                        borderRadius: BorderRadius.circular(10),
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
                          decoration: BoxDecoration(
                            color: _conditionType == AlertConditionType.percentChange
                                ? theme.colorScheme.secondary.withValues(alpha: 0.2)
                                : theme.colorScheme.surface,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: _conditionType == AlertConditionType.percentChange
                                  ? theme.colorScheme.secondary
                                  : theme.dividerColor,
                            ),
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            AppStrings.get('macro_cond_new_value', lang),
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: _conditionType == AlertConditionType.percentChange
                                  ? theme.colorScheme.secondary
                                  : theme.colorScheme.onSurface.withValues(alpha: 0.8),
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: InkWell(
                        onTap: () {
                          setState(() {
                            _conditionType = AlertConditionType.priceThreshold;
                          });
                        },
                        borderRadius: BorderRadius.circular(10),
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
                          decoration: BoxDecoration(
                            color: _conditionType == AlertConditionType.priceThreshold
                                ? theme.colorScheme.secondary.withValues(alpha: 0.2)
                                : theme.colorScheme.surface,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: _conditionType == AlertConditionType.priceThreshold
                                  ? theme.colorScheme.secondary
                                  : theme.dividerColor,
                            ),
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            AppStrings.get('macro_cond_threshold', lang),
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: _conditionType == AlertConditionType.priceThreshold
                                  ? theme.colorScheme.secondary
                                  : theme.colorScheme.onSurface.withValues(alpha: 0.8),
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
        ] else ...[
          // Standard Financial Price Condition Selector (Crypto, Stocks, Forex, Commodities, Iran)
          Row(
            children: [
              Expanded(
                child: InkWell(
                  onTap: () => setState(() => _conditionType = AlertConditionType.percentChange),
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    decoration: BoxDecoration(
                      color: _conditionType == AlertConditionType.percentChange
                          ? theme.colorScheme.primary.withValues(alpha: 0.15)
                          : theme.colorScheme.surface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: _conditionType == AlertConditionType.percentChange
                            ? theme.colorScheme.primary
                            : theme.dividerColor,
                      ),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      AppStrings.get('percent_change', lang),
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                        color: _conditionType == AlertConditionType.percentChange
                            ? theme.colorScheme.primary
                            : theme.colorScheme.onSurface.withValues(alpha: 0.7),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: InkWell(
                  onTap: () => setState(() => _conditionType = AlertConditionType.priceThreshold),
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    decoration: BoxDecoration(
                      color: _conditionType == AlertConditionType.priceThreshold
                          ? theme.colorScheme.primary.withValues(alpha: 0.15)
                          : theme.colorScheme.surface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: _conditionType == AlertConditionType.priceThreshold
                            ? theme.colorScheme.primary
                            : theme.dividerColor,
                      ),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      AppStrings.get('price_target', lang),
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                        color: _conditionType == AlertConditionType.priceThreshold
                            ? theme.colorScheme.primary
                            : theme.colorScheme.onSurface.withValues(alpha: 0.7),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
        const SizedBox(height: 16),

        if (_conditionType == AlertConditionType.percentChange) ...[
          Text(
            AppStrings.get('price_direction', lang),
            style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              _buildDirectionChip(AppStrings.get('both_ways', lang), AlertDirection.bothSides, theme),
              const SizedBox(width: 8),
              _buildDirectionChip(AppStrings.get('above_only', lang), AlertDirection.above, theme),
              const SizedBox(width: 8),
              _buildDirectionChip(AppStrings.get('below_only', lang), AlertDirection.below, theme),
            ],
          ),
          const SizedBox(height: 12),
          if (_flowType == MarketFlowType.iran) ...[
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [1, 2, 3, 5, 10, 15, 20].map((p) {
                    final currentVal = FormatUtils.normalizePersianDigits(_percentController.text.trim());
                    final isSel = currentVal == p.toString();
                    return Padding(
                      padding: const EdgeInsets.only(left: 6),
                      child: ActionChip(
                        label: Text(FormatUtils.toPersianDigits('$p٪')),
                        labelStyle: TextStyle(
                          fontSize: 11,
                          fontWeight: isSel ? FontWeight.bold : FontWeight.normal,
                          color: isSel ? const Color(0xFFFFB300) : theme.colorScheme.onSurface.withValues(alpha: 0.7),
                        ),
                        backgroundColor: isSel ? const Color(0xFFFFB300).withValues(alpha: 0.15) : theme.colorScheme.surface,
                        side: BorderSide(color: isSel ? const Color(0xFFFFB300) : theme.dividerColor),
                        onPressed: () {
                          setState(() {
                            _percentController.text = p.toString();
                          });
                        },
                      ),
                    );
                  }).toList(),
                ),
              ),
            ),
          ],
          TextField(
            controller: _percentController,
            keyboardType: _flowType == MarketFlowType.iran
                ? TextInputType.number
                : const TextInputType.numberWithOptions(decimal: true),
            style: TextStyle(fontWeight: FontWeight.bold, fontFamily: 'monospace', color: theme.colorScheme.onSurface),
            decoration: InputDecoration(
              labelText: _flowType == MarketFlowType.iran ? 'درصد نوسان مد نظر (%)' : AppStrings.get('percent_label', lang),
              hintText: _flowType == MarketFlowType.iran ? 'یک درصد وارد کنید (مثال: ۲)' : (lang == 'fa' ? 'یک درصد وارد کنید (مثال: ۲.۵)' : 'Enter a percentage (e.g. 2.5)'),
              helperText: lang == 'fa' ? 'درصد تغییرات دلخواه را وارد کنید' : 'Enter target percentage change',
              filled: true,
              fillColor: theme.colorScheme.surface,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
            ),
          ),
        ],

        if (_conditionType == AlertConditionType.priceThreshold) ...[
          Text(
            lang == 'fa' ? 'حالت هشدار قیمت (Price Target Mode):' : 'Price Target Mode:',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface.withValues(alpha: 0.8)),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _buildDirectionChip(lang == 'fa' ? '🔼 فقط حد بالا' : '🔼 Above', AlertDirection.above, theme),
              const SizedBox(width: 6),
              _buildDirectionChip(lang == 'fa' ? '🔽 فقط حد پایین' : '🔽 Below', AlertDirection.below, theme),
              const SizedBox(width: 6),
              _buildDirectionChip(lang == 'fa' ? '🔄 هر دو جهت' : '🔄 Both Way', AlertDirection.bothSides, theme),
            ],
          ),
          const SizedBox(height: 10),

          if (_currentPrice != null && _currentPrice! > 0) ...[
            Builder(builder: (context) {
              final h24 = _currentPrice! * 1.025;
              final l24 = _currentPrice! * 0.975;
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(
                  children: [
                    Expanded(
                      child: InkWell(
                        onTap: () {
                          if (_direction == AlertDirection.bothSides) {
                            _upperPriceController.text = _formatInputNumber(h24);
                          } else {
                            _targetPriceController.text = _formatInputNumber(h24);
                            setState(() => _direction = AlertDirection.above);
                          }
                        },
                        borderRadius: BorderRadius.circular(8),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                          decoration: BoxDecoration(
                            color: AppTokens.positive.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: AppTokens.positive.withValues(alpha: 0.3)),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(lang == 'fa' ? '🔼 سقف ۲۴h:' : '🔼 24h High:', style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: AppTokens.positive)),
                              const SizedBox(width: 4),
                              Flexible(
                                child: Text(_formatInputNumber(h24), style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, fontFamily: 'monospace', color: AppTokens.positive), overflow: TextOverflow.ellipsis),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: InkWell(
                        onTap: () {
                          if (_direction == AlertDirection.bothSides) {
                            _lowerPriceController.text = _formatInputNumber(l24);
                          } else {
                            _targetPriceController.text = _formatInputNumber(l24);
                            setState(() => _direction = AlertDirection.below);
                          }
                        },
                        borderRadius: BorderRadius.circular(8),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                          decoration: BoxDecoration(
                            color: AppTokens.negative.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: AppTokens.negative.withValues(alpha: 0.3)),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(lang == 'fa' ? '🔽 کف ۲۴h:' : '🔽 24h Low:', style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: AppTokens.negative)),
                              const SizedBox(width: 4),
                              Flexible(
                                child: Text(_formatInputNumber(l24), style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, fontFamily: 'monospace', color: AppTokens.negative), overflow: TextOverflow.ellipsis),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],

          // Both Way Mode Inputs
          if (_direction == AlertDirection.bothSides) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // BOTH WAY BEHAVIOR MODE (OCO vs Dual-Active)
                  Text(
                    lang == 'fa' ? 'رفتار پس از اولین تاچ قیمت:' : 'Behavior after first trigger:',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 11.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.8)),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Expanded(
                        child: InkWell(
                          onTap: () => setState(() => _bothWayBehavior = BothWayBehavior.oco),
                          borderRadius: BorderRadius.circular(10),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                            decoration: BoxDecoration(
                              color: _bothWayBehavior == BothWayBehavior.oco
                                  ? AppTokens.warning.withValues(alpha: 0.15)
                                  : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: _bothWayBehavior == BothWayBehavior.oco
                                    ? AppTokens.warning
                                    : theme.dividerColor,
                              ),
                            ),
                            child: Column(
                              children: [
                                Text(
                                  lang == 'fa' ? '🛑 خروج با اولین تارگت' : '🛑 One-Cancels-Other',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                    color: _bothWayBehavior == BothWayBehavior.oco
                                        ? AppTokens.warning
                                        : theme.colorScheme.onSurface,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  lang == 'fa' ? 'بسته شدن با ✅ Done' : 'Deactivates with Done',
                                  style: TextStyle(fontSize: 9.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: InkWell(
                          onTap: () => setState(() => _bothWayBehavior = BothWayBehavior.dualActive),
                          borderRadius: BorderRadius.circular(10),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                            decoration: BoxDecoration(
                              color: _bothWayBehavior == BothWayBehavior.dualActive
                                  ? theme.colorScheme.primary.withValues(alpha: 0.15)
                                  : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: _bothWayBehavior == BothWayBehavior.dualActive
                                    ? theme.colorScheme.primary
                                    : theme.dividerColor,
                              ),
                            ),
                            child: Column(
                              children: [
                                Text(
                                  lang == 'fa' ? '🔄 پایش دائمی کانال' : '🔄 Dual-Active Channel',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                    color: _bothWayBehavior == BothWayBehavior.dualActive
                                        ? theme.colorScheme.primary
                                        : theme.colorScheme.onSurface,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  lang == 'fa' ? 'کانال باز می‌ماند (Active)' : 'Stays active forever',
                                  style: TextStyle(fontSize: 9.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 10),
                    child: Divider(height: 1),
                  ),

                  // UPPER TARGET SECTION
                  Row(
                    children: [
                      const Icon(Icons.arrow_upward_rounded, size: 16, color: AppTokens.positive),
                      const SizedBox(width: 6),
                      Text(
                        lang == 'fa' ? 'حد بالا (Upper Target / مقاومت):' : 'Upper Target (Resistance):',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: AppTokens.positive),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _upperPriceController,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    style: TextStyle(fontWeight: FontWeight.bold, fontFamily: 'monospace', color: theme.colorScheme.onSurface),
                    decoration: InputDecoration(
                      labelText: lang == 'fa' ? 'قیمت حد بالا (Upper Price)' : 'Upper Price',
                      hintText: '4.00',
                      prefixIcon: const Icon(Icons.show_chart_rounded, size: 18),
                      filled: true,
                      fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: theme.dividerColor)),
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _upperNoteController,
                    style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface),
                    decoration: InputDecoration(
                      labelText: lang == 'fa' ? 'یادداشت حد بالا (Upper Note)' : 'Upper Note',
                      hintText: lang == 'fa' ? '«رسید به مقاومت، بررسی کن»' : 'Hit resistance, check take profit',
                      prefixIcon: const Icon(Icons.edit_note_rounded, size: 18),
                      filled: true,
                      fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: theme.dividerColor)),
                    ),
                  ),

                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: Divider(height: 1),
                  ),

                  // LOWER TARGET SECTION
                  Row(
                    children: [
                      const Icon(Icons.arrow_downward_rounded, size: 16, color: AppTokens.negative),
                      const SizedBox(width: 6),
                      Text(
                        lang == 'fa' ? 'حد پایین (Lower Target / حمایت):' : 'Lower Target (Support):',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: AppTokens.negative),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _lowerPriceController,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    style: TextStyle(fontWeight: FontWeight.bold, fontFamily: 'monospace', color: theme.colorScheme.onSurface),
                    decoration: InputDecoration(
                      labelText: lang == 'fa' ? 'قیمت حد پایین (Lower Price)' : 'Lower Price',
                      hintText: '2.00',
                      prefixIcon: const Icon(Icons.trending_down_rounded, size: 18),
                      filled: true,
                      fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: theme.dividerColor)),
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _lowerNoteController,
                    style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface),
                    decoration: InputDecoration(
                      labelText: lang == 'fa' ? 'یادداشت حد پایین (Lower Note)' : 'Lower Note',
                      hintText: lang == 'fa' ? '«حمایت شکست، بفروش»' : 'Support broke, sell / stop loss',
                      prefixIcon: const Icon(Icons.edit_note_rounded, size: 18),
                      filled: true,
                      fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: theme.dividerColor)),
                    ),
                  ),
                ],
              ),
            ),
          ] else ...[
            // Single Direction Mode (Above or Below)
            TextField(
              controller: _targetPriceController,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              style: TextStyle(fontWeight: FontWeight.bold, fontFamily: 'monospace', color: theme.colorScheme.onSurface),
              decoration: InputDecoration(
                labelText: _flowType == MarketFlowType.iran ? (lang == 'fa' ? 'قیمت هدف به تومان' : 'Target Price (IRT)') : AppStrings.get('target_price_label', lang),
                hintText: _flowType == MarketFlowType.iran ? (_currentPrice != null ? FormatUtils.toPersianDigits(_formatSmartNumber(_currentPrice!)) : '۲۷۰۰۰۰') : '95000',
                filled: true,
                fillColor: theme.colorScheme.surface,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
              ),
            ),
          ],
        ],

        const SizedBox(height: 20),

        // 3. CUSTOM NOTIFICATION, SOUND & NOTE SECTION
        Text(
          AppStrings.get('sound_and_vibrate_section', lang),
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: theme.colorScheme.onSurface),
        ),
        const SizedBox(height: 8),

        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: theme.dividerColor),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 3.1 Custom Note / Message TextField
              TextField(
                controller: _customNoteController,
                style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurface),
                decoration: InputDecoration(
                  labelText: AppStrings.get('custom_note_title', lang),
                  hintText: AppStrings.get('custom_note_hint', lang),
                  prefixIcon: Icon(Icons.edit_note_rounded, size: 22, color: theme.colorScheme.primary),
                  filled: true,
                  fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: theme.dividerColor)),
                ),
              ),
              const SizedBox(height: 12),

              // 3.2 Sound Selection Tile with Audition
              Builder(builder: (context) {
                final currentPreset = SoundManager.presets.firstWhere(
                  (p) => p.id == _selectedSound,
                  orElse: () => SoundManager.presets.first,
                );
                final soundTitle = currentPreset.getTitle(lang);
                final isPlaying = SoundManager().isSoundPlaying(currentPreset.id);

                return InkWell(
                  onTap: () => _showSoundPickerModal(context, theme, lang),
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.06),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.25)),
                    ),
                    child: Row(
                      children: [
                        Text(currentPreset.icon, style: const TextStyle(fontSize: 22)),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                AppStrings.get('alarm_sound_title', lang),
                                style: TextStyle(fontSize: 10, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
                              ),
                              Text(
                                soundTitle,
                                style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.primary),
                              ),
                            ],
                          ),
                        ),
                        IconButton(
                          icon: Icon(
                            isPlaying ? Icons.stop_circle_rounded : Icons.play_circle_filled_rounded,
                            color: isPlaying ? AppTokens.negative : theme.colorScheme.primary,
                            size: 26,
                          ),
                          onPressed: () async {
                            if (isPlaying) {
                              await SoundManager().stop();
                            } else {
                              await SoundManager().playPreset(currentPreset.id);
                            }
                            setState(() {});
                          },
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            AppStrings.get('change_sound_btn', lang),
                            style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.white),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
              const SizedBox(height: 8),

              // 3.3 Sound & Vibration Toggles
              Row(
                children: [
                  Expanded(
                    child: SwitchListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        AppStrings.get('play_sound_label', lang),
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                      ),
                      value: _soundEnabled,
                      activeThumbColor: Colors.white,
                      activeTrackColor: theme.colorScheme.primary,
                      inactiveThumbColor: Colors.grey.shade400,
                      inactiveTrackColor: theme.colorScheme.surfaceContainerHighest,
                      onChanged: (val) => setState(() => _soundEnabled = val),
                    ),
                  ),
                  Expanded(
                    child: SwitchListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        AppStrings.get('vibrate_phone_label', lang),
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                      ),
                      value: _vibrationEnabled,
                      activeThumbColor: Colors.white,
                      activeTrackColor: theme.colorScheme.primary,
                      inactiveThumbColor: Colors.grey.shade400,
                      inactiveTrackColor: theme.colorScheme.surfaceContainerHighest,
                      onChanged: (val) => setState(() => _vibrationEnabled = val),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 10),

              // 3.4 Text-to-Speech (TTS) Voice Announcer
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: theme.scaffoldBackgroundColor.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: _ttsEnabled
                        ? theme.colorScheme.primary.withValues(alpha: 0.4)
                        : theme.colorScheme.onSurface.withValues(alpha: 0.08),
                  ),
                ),
                child: Column(
                  children: [
                    SwitchListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      secondary: Icon(
                        Icons.record_voice_over_rounded,
                        color: _ttsEnabled ? theme.colorScheme.primary : theme.colorScheme.onSurface.withValues(alpha: 0.5),
                        size: 22,
                      ),
                      title: Text(
                        AppStrings.get('tts_voice_title', lang),
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                      subtitle: Text(
                        AppStrings.get('tts_voice_desc', lang),
                        style: TextStyle(
                          fontSize: 10,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                        ),
                      ),
                      value: _ttsEnabled,
                      activeThumbColor: Colors.white,
                      activeTrackColor: theme.colorScheme.primary,
                      inactiveThumbColor: Colors.grey.shade400,
                      inactiveTrackColor: theme.colorScheme.surfaceContainerHighest,
                      onChanged: (val) => setState(() => _ttsEnabled = val),
                    ),
                    if (_ttsEnabled) ...[
                      const SizedBox(height: 6),
                      Align(
                        alignment: (lang == 'fa' || lang == 'ar' || lang == 'ckb')
                            ? Alignment.centerLeft
                            : Alignment.centerRight,
                        child: OutlinedButton.icon(
                          onPressed: () => TtsService.instance.testVoice(),
                          icon: const Icon(Icons.volume_up_rounded, size: 14),
                          label: Text(
                            AppStrings.get('tts_test_button', lang),
                            style: const TextStyle(fontSize: 11),
                          ),
                          style: OutlinedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            visualDensity: VisualDensity.compact,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 24),

        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: () => _saveAlert(lang),
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: Text(
              AppStrings.get(widget.initialRule != null ? 'save_changes_cta' : 'save_alert_cta', lang),
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
            ),
          ),
        ),
      ],
    );
  }

  void _showSoundPickerModal(BuildContext context, ThemeData theme, String lang) {
    final isRtl = AppStrings.isRtl(lang);

    showModalBottomSheet(
      context: context,
      backgroundColor: theme.colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) => Directionality(
          textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.music_note_rounded, size: 22),
                        const SizedBox(width: 8),
                        Text(
                          AppStrings.get('select_alarm_sound', lang),
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                      ],
                    ),
                    IconButton(
                      icon: Icon(Icons.close_rounded, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                      onPressed: () {
                        SoundManager().stop();
                        Navigator.pop(ctx);
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Expanded(
                  child: ListView.separated(
                    itemCount: SoundManager.presets.length,
                    separatorBuilder: (_, __) => Divider(height: 1, color: theme.dividerColor),
                    itemBuilder: (context, index) {
                      final preset = SoundManager.presets[index];
                      final isSelected = _selectedSound == preset.id;
                      final isPlaying = SoundManager().isSoundPlaying(preset.id);
                      final title = preset.getTitle(lang);

                      return InkWell(
                        onTap: () async {
                          await SoundManager().playPreset(preset.id);
                          setState(() {
                            _selectedSound = preset.id;
                          });
                          setModalState(() {});
                        },
                        borderRadius: BorderRadius.circular(12),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? theme.colorScheme.primary.withValues(alpha: 0.1)
                                : Colors.transparent,
                            borderRadius: BorderRadius.circular(12),
                            border: isSelected
                                ? Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.35))
                                : null,
                          ),
                          child: Row(
                            children: [
                              Text(preset.icon, style: const TextStyle(fontSize: 22)),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Text(
                                  title,
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 13,
                                    color: isSelected ? theme.colorScheme.primary : theme.colorScheme.onSurface,
                                  ),
                                ),
                              ),
                              IconButton(
                                icon: Icon(
                                  isPlaying ? Icons.stop_circle_rounded : Icons.play_circle_filled_rounded,
                                  color: isPlaying ? AppTokens.negative : theme.colorScheme.primary,
                                  size: 28,
                                ),
                                onPressed: () async {
                                  if (isPlaying) {
                                    await SoundManager().stop();
                                  } else {
                                    await SoundManager().playPreset(preset.id);
                                  }
                                  setModalState(() {});
                                },
                              ),
                              if (isSelected)
                                Icon(Icons.check_circle_rounded, color: theme.colorScheme.primary, size: 22),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: () {
                      SoundManager().stop();
                      Navigator.pop(ctx);
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: theme.colorScheme.primary,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                    child: Text(AppStrings.get('confirm_sound_btn', lang), style: const TextStyle(fontWeight: FontWeight.bold)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ).whenComplete(() {
      SoundManager().stop();
    });
  }

  Widget _buildDirectionChip(String label, AlertDirection dir, ThemeData theme) {
    final isSelected = _direction == dir;
    return Expanded(
      child: InkWell(
        onTap: () => setState(() => _direction = dir),
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: isSelected ? theme.colorScheme.primary : theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: isSelected ? theme.colorScheme.primary : theme.dividerColor),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
              color: isSelected ? Colors.white : theme.colorScheme.onSurface.withValues(alpha: 0.7),
            ),
          ),
        ),
      ),
    );
  }
}

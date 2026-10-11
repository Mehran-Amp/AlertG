import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Comprehensive Iran Domestic Market Adapter (TSETMC, Bonbast, ICE, Nobitex, Wallex, etc.)
/// Quote currency is strictly Toman (TMN).
class IranDomesticExchange implements Exchange {
  final http.Client _client;

  IranDomesticExchange({http.Client? client})
      : _client = client ?? http.Client();

  @override
  String get id => 'iran_market';

  @override
  String get name => 'بازار ایران (طلا، سکه، ارز آزاد، بورس و تتر)';

  @override
  ExchangeCategory get category => ExchangeCategory.iran;

  @override
  String get countryBadge => '🇮🇷 بازار تهران و تومان';

  @override
  String get defaultCounterCurrency => 'TMN';

  static const List<Map<String, dynamic>> predefinedAssets = [
    // ==========================================
    // ۱. طلا و مسکوکات فیزیکی (Physical Gold & Coins)
    // ==========================================
    {
      'symbol': 'GERAM18',
      'name': 'Gold 18K (1 Gram)',
      'nameFa': 'طلای ۱۸ عیار (هر گرم)',
      'cat': 'Gold',
      'icon': '🥇',
      'price': 26738000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GERAM24',
      'name': 'Gold 24K (1 Gram)',
      'nameFa': 'طلای ۲۴ عیار (هر گرم)',
      'cat': 'Gold',
      'icon': '✨',
      'price': 35650000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'MESGHAL',
      'name': 'Mithqal Gold (Tehran Benchmark)',
      'nameFa': 'مثقال طلا (مظنه بازار تهران)',
      'cat': 'Gold',
      'icon': '⚖️',
      'price': 115830000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOLD_USED',
      'name': 'Second-hand Gold (No Making Charge)',
      'nameFa': 'طلای دست دوم (بدون اجرت)',
      'cat': 'Gold',
      'icon': '💍',
      'price': 26350000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOLD_MELTED',
      'name': 'Melted Gold Cash',
      'nameFa': 'آبشده نقدی بنکداری',
      'cat': 'Gold',
      'icon': '🔥',
      'price': 115900000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'COIN_EMAMI',
      'name': 'Emami Gold Coin (New Design)',
      'nameFa': 'سکه امامی (طرح جدید)',
      'cat': 'Coins',
      'icon': '🪙',
      'price': 271910000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'COIN_BAHAR',
      'name': 'Bahar Azadi Coin (Old Design)',
      'nameFa': 'سکه تمام بهار آزادی (طرح قدیم)',
      'cat': 'Coins',
      'icon': '🏵️',
      'price': 264220000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'COIN_HALF',
      'name': 'Half Bahar Azadi Coin',
      'nameFa': 'نیم سکه بهار آزادی',
      'cat': 'Coins',
      'icon': '🌗',
      'price': 143460000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'COIN_QUARTER',
      'name': 'Quarter Bahar Azadi Coin',
      'nameFa': 'ربع سکه بهار آزادی',
      'cat': 'Coins',
      'icon': '🌘',
      'price': 77230000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'COIN_GRAM',
      'name': 'Gram Bahar Azadi Coin',
      'nameFa': 'سکه گرمی بانک مرکزی',
      'cat': 'Coins',
      'icon': '🔹',
      'price': 38150000.0,
      'unit': 'تومان',
    },

    // ==========================================
    // ۲. صندوق‌های طلای بورس تهران (Gold ETFs - TSETMC)
    // ==========================================
    {
      'symbol': 'AYAR',
      'name': 'Ayar Gold ETF (Lotus)',
      'nameFa': 'صندوق طلای عیار لوتوس (عیار)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 23450.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'TALA',
      'name': 'Kian Gold ETF (Tala)',
      'nameFa': 'صندوق طلای کیان (طلا)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 22890.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'ZAR',
      'name': 'Zarfam Gold ETF (Zar)',
      'nameFa': 'صندوق طلای زرفام (زر)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 24120.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KAHROBA',
      'name': 'Kahroba Gold ETF',
      'nameFa': 'صندوق طلای کهربا (کهربا)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 21980.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOHAR',
      'name': 'Gohar Gold ETF (Mofid)',
      'nameFa': 'صندوق طلای گوهر مفید (گوهر)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 25670.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'NAAB',
      'name': 'Naab Gold ETF',
      'nameFa': 'صندوق طلای ناب (ناب)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 19840.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'NAFIS',
      'name': 'Nafis Gold ETF',
      'nameFa': 'صندوق طلای نفیس (نفیس)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 18760.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'TALT',
      'name': 'Taban Gold ETF',
      'nameFa': 'صندوق طلای تابان (تابا)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 20450.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'ALTUN',
      'name': 'Altun Gold ETF',
      'nameFa': 'صندوق طلای آلتون (آلتون)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 22100.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'MESGHAL_ETF',
      'name': 'Mesghal Gold Fund ETF (Bourse)',
      'nameFa': 'صندوق طلای مثقال بورس (مثقال)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 21400.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'JAVAHER',
      'name': 'Javaher Gold ETF',
      'nameFa': 'صندوق طلای جواهر (جواهر)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 23900.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'ZARFAM',
      'name': 'Zarfam Gold ETF',
      'nameFa': 'صندوق طلای زرفام (زرفام)',
      'cat': 'GoldFunds',
      'icon': '🏆',
      'price': 24200.0,
      'unit': 'تومان',
    },

    // ==========================================
    // ۳. صندوق‌های اهرمی بورس تهران (Leveraged ETFs)
    // ==========================================
    {
      'symbol': 'AHRAM',
      'name': 'Charisma Leveraged ETF (Ahram)',
      'nameFa': 'صندوق اهرمی کاریزما (اهرم)',
      'cat': 'LeveragedFunds',
      'icon': '⚡',
      'price': 2150.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'JAHESH',
      'name': 'Jahesh Leveraged ETF',
      'nameFa': 'صندوق اهرمی جهش (جهش)',
      'cat': 'LeveragedFunds',
      'icon': '⚡',
      'price': 1980.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'TAVAN',
      'name': 'Tavan Leveraged ETF (Mofid)',
      'nameFa': 'صندوق اهرمی توان مفید (توان)',
      'cat': 'LeveragedFunds',
      'icon': '⚡',
      'price': 2340.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SHETAB',
      'name': 'Shetab Leveraged ETF (Agah)',
      'nameFa': 'صندوق اهرمی شتاب آگاه (شتاب)',
      'cat': 'LeveragedFunds',
      'icon': '⚡',
      'price': 1890.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'MOJ',
      'name': 'Moj Leveraged ETF (Firouzeh)',
      'nameFa': 'صندوق اهرمی موج فیروزه (موج)',
      'cat': 'LeveragedFunds',
      'icon': '⚡',
      'price': 2080.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'BIDAR',
      'name': 'Bidar Leveraged ETF',
      'nameFa': 'صندوق اهرمی بیدار (بیدار)',
      'cat': 'LeveragedFunds',
      'icon': '⚡',
      'price': 1920.0,
      'unit': 'تومان',
    },

    // ==========================================
    // ۴. صندوق‌های شاخصی و دولتی بورس (Index & State ETFs)
    // ==========================================
    {
      'symbol': 'PALAYESH',
      'name': 'Palayesh State ETF',
      'nameFa': 'صندوق پالایش یکم (پالایش)',
      'cat': 'IndexFunds',
      'icon': '📊',
      'price': 16850.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'DARA1',
      'name': 'Dara Yekom State Banking ETF',
      'nameFa': 'صندوق دارا یکم (دارا یکم)',
      'cat': 'IndexFunds',
      'icon': '📊',
      'price': 14200.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'FIRUZEH',
      'name': 'Firouzeh Success Index ETF',
      'nameFa': 'صندوق شاخصی فیروزه (فیروزه)',
      'cat': 'IndexFunds',
      'icon': '📊',
      'price': 4850.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SERVO',
      'name': 'Sarv Equity ETF',
      'nameFa': 'صندوق سهامی سرو (سرو)',
      'cat': 'IndexFunds',
      'icon': '📊',
      'price': 5200.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'TEMESHK',
      'name': 'Temeshk Fund of Funds',
      'nameFa': 'صندوق در صندوق تمشک (تمشک)',
      'cat': 'IndexFunds',
      'icon': '🍇',
      'price': 2450.0,
      'unit': 'تومان',
    },

    // ==========================================
    // ۵. غول‌ها و سهام لیدر بورس تهران (Top TSE Leaders)
    // ==========================================
    {
      'symbol': 'FOOLAD',
      'name': 'Mobarakeh Steel Co (Foolad)',
      'nameFa': 'فولاد مبارکه اصفهان (فولاد)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 585.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'FEMELLI',
      'name': 'National Iranian Copper (Femelli)',
      'nameFa': 'ملی صنایع مس ایران (فملی)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 720.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'FARES',
      'name': 'Persian Gulf Petrochemical (Fars)',
      'nameFa': 'صنایع پتروشیمی خلیج فارس (فارس)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 1120.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SHEPNA',
      'name': 'Isfahan Oil Refining (Shepna)',
      'nameFa': 'پالایش نفت اصفهان (شپنا)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 460.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SHETRAN',
      'name': 'Tehran Oil Refining (Shetran)',
      'nameFa': 'پالایش نفت تهران (شتران)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 295.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'VEBMELAT',
      'name': 'Bank Mellat (Vebmelat)',
      'nameFa': 'بانک ملت (وبملت)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 240.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KHODRO',
      'name': 'Iran Khodro (Khodro)',
      'nameFa': 'ایران خودرو (خودرو)',
      'cat': 'TopStocks',
      'icon': '🚗',
      'price': 285.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KHASAPA',
      'name': 'Saipa (Khasapa)',
      'nameFa': 'سایپا (خساپا)',
      'cat': 'TopStocks',
      'icon': '🚗',
      'price': 235.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SHASTA',
      'name': 'Social Security Investment (Shasta)',
      'nameFa': 'سرمایه‌گذاری تامین اجتماعی (شستا)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 135.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'VEBSADER',
      'name': 'Bank Saderat Iran (Vebsader)',
      'nameFa': 'بانک صادرات ایران (وبصادر)',
      'cat': 'TopStocks',
      'icon': '🏦',
      'price': 195.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'VETEJARAT',
      'name': 'Tejarat Bank (Vetejarat)',
      'nameFa': 'بانک تجارت (وتجارت)',
      'cat': 'TopStocks',
      'icon': '🏦',
      'price': 210.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'VEPASAR',
      'name': 'Bank Pasargad (Vepasar)',
      'nameFa': 'بانک پاسارگاد (وپاسار)',
      'cat': 'TopStocks',
      'icon': '🏦',
      'price': 340.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'VEBANK',
      'name': 'National Development Group (Vebank)',
      'nameFa': 'سرمایه‌گذاری گروه توسعه ملی (وبانک)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 780.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'VESEPAH',
      'name': 'Sepah Investment (Vesepah)',
      'nameFa': 'سرمایه‌گذاری سپه (وسپه)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 430.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'VEGHADIR',
      'name': 'Ghadir Investment (Veghadir)',
      'nameFa': 'سرمایه‌گذاری غدیر (وغدیر)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 1850.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'VEMAADEN',
      'name': 'Mines & Metals Development (Vemaaden)',
      'nameFa': 'توسعه معادن و فلزات (ومعادن)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 480.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KEGOL',
      'name': 'Gol Gohar Iron Ore (Kegol)',
      'nameFa': 'سنگ آهن گل‌گهر (کگل)',
      'cat': 'TopStocks',
      'icon': '⛏️',
      'price': 640.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KECHAD',
      'name': 'Chadormalu Mining (Kechad)',
      'nameFa': 'معدنی و صنعتی چادرملو (کچاد)',
      'cat': 'TopStocks',
      'icon': '⛏️',
      'price': 590.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'NOURI',
      'name': 'Nouri Petrochemical (Nouri)',
      'nameFa': 'پتروشیمی نوری (نوری)',
      'cat': 'TopStocks',
      'icon': '⚗️',
      'price': 12500.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'PARSAN',
      'name': 'Parsian Oil & Gas (Parsan)',
      'nameFa': 'گسترش نفت و گاز پارسیان (پارسان)',
      'cat': 'TopStocks',
      'icon': '🛢️',
      'price': 3200.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'TAPICO',
      'name': 'Tamin Petroleum & Petrochemical (Tapico)',
      'nameFa': 'سرمایه‌گذاری نفت و گاز و پتروشیمی تامین (تاپیکو)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 1450.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SHEPDIS',
      'name': 'Pardis Petrochemical (Shepdis)',
      'nameFa': 'پتروشیمی پردیس (شپدیس)',
      'cat': 'TopStocks',
      'icon': '⚗️',
      'price': 16800.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'ZAGROS',
      'name': 'Zagros Petrochemical (Zagros)',
      'nameFa': 'پتروشیمی زاگرس (زاگرس)',
      'cat': 'TopStocks',
      'icon': '⚗️',
      'price': 9800.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SHESEPA',
      'name': 'Sepahan Oil (Shesepa)',
      'nameFa': 'نفت سپاهان (شسپا)',
      'cat': 'TopStocks',
      'icon': '🛢️',
      'price': 790.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'FAKHOOZ',
      'name': 'Khuzestan Steel (Fakhooz)',
      'nameFa': 'فولاد خوزستان (فخوز)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 390.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'FASMIN',
      'name': 'Calcimin (Fasmin)',
      'nameFa': 'کالسیمین (فاسمین)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 650.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'FAYRA',
      'name': 'Iran Aluminum (Fayra)',
      'nameFa': 'آلومینیوم ایران (فایرا)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 580.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'AKHABER',
      'name': 'Telecommunication Co of Iran (Akhaber)',
      'nameFa': 'مخابرات ایران (اخابر)',
      'cat': 'TopStocks',
      'icon': '📡',
      'price': 890.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'HAMRAH',
      'name': 'Mobile Telecommunication of Iran (Hamrah)',
      'nameFa': 'ارتباطات سیار ایران (همراه)',
      'cat': 'TopStocks',
      'icon': '📱',
      'price': 420.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KHAVAR',
      'name': 'Iran Khodro Diesel (Khavar)',
      'nameFa': 'ایران خودرو دیزل (خاور)',
      'cat': 'TopStocks',
      'icon': '🚛',
      'price': 280.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KHEGOSTAR',
      'name': 'Gostaresh Khodro (Khegostar)',
      'nameFa': 'گسترش سرمایه‌گذاری ایران خودرو (خگستر)',
      'cat': 'TopStocks',
      'icon': '🚗',
      'price': 410.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KHATOUR',
      'name': 'Iran Radiator (Khatour)',
      'nameFa': 'رادیاتور ایران (ختور)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 320.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'HATOKA',
      'name': 'Tuka Transportation (Hatoka)',
      'nameFa': 'حمل و نقل توکا (حتوکا)',
      'cat': 'TopStocks',
      'icon': '🚛',
      'price': 360.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KERMAN',
      'name': 'Kerman Province Investment (Kerman)',
      'nameFa': 'سرمایه‌گذاری استان کرمان (کرمان)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 110.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SHABANDAR',
      'name': 'Bandar Abbas Oil Refining (Shabandar)',
      'nameFa': 'پالایش نفت بندرعباس (شبندر)',
      'cat': 'TopStocks',
      'icon': '🛢️',
      'price': 890.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SHABRIZ',
      'name': 'Tabriz Oil Refining (Shabriz)',
      'nameFa': 'پالایش نفت تبریز (شبریز)',
      'cat': 'TopStocks',
      'icon': '🛢️',
      'price': 1150.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KARAMAD',
      'name': 'Karamad Fixed Income ETF',
      'nameFa': 'صندوق درآمد ثابت کارآمد (کارآمد)',
      'cat': 'IndexFunds',
      'icon': '🏛️',
      'price': 1050.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'ATLAS',
      'name': 'Atlas Equity ETF',
      'nameFa': 'صندوق سهامی اطلس (اطلس)',
      'cat': 'IndexFunds',
      'icon': '📈',
      'price': 6200.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'LOTUS',
      'name': 'Lotus Parsian Investment Bank (Lotus)',
      'nameFa': 'تأمین سرمایه لوتوس پارسیان (لوتوس)',
      'cat': 'TopStocks',
      'icon': '🏢',
      'price': 480.0,
      'unit': 'تومان',
    },

    // ==========================================
    // ۶. تتر و طلای صرافی‌های ایرانی (USDT & Gold)
    // ==========================================
    {
      'symbol': 'USDT_NOBITEX',
      'name': 'Nobitex Tether (USDT/TMN)',
      'nameFa': 'تتر نوبیتکس (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268950.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_WALLEX',
      'name': 'Wallex Tether (USDT/TMN)',
      'nameFa': 'تتر والکس (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268900.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_TABDEAL',
      'name': 'Tabdeal Tether (USDT/TMN)',
      'nameFa': 'تتر تبدیل (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268880.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_TETHERLAND',
      'name': 'Tetherland Tether (USDT/TMN)',
      'nameFa': 'تتر تترلند (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268920.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_RAMZINEX',
      'name': 'Ramzinex Tether (USDT/TMN)',
      'nameFa': 'تتر رمزینکس (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268850.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_ABAN',
      'name': 'AbanTether (USDT/TMN)',
      'nameFa': 'تتر آبان‌تتر (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268900.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_BITPIN',
      'name': 'Bitpin Tether (USDT/TMN)',
      'nameFa': 'تتر بیت‌پین (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268920.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_BITBARG',
      'name': 'Bitbarg Tether (USDT/TMN)',
      'nameFa': 'تتر بیت‌برگ (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 269100.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_EXIR',
      'name': 'Exir Tether (USDT/TMN)',
      'nameFa': 'تتر اکسیر (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268930.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'USDT_SARMAYEX',
      'name': 'Sarmayex Tether (USDT/TMN)',
      'nameFa': 'تتر سرمایکس (USDT)',
      'cat': 'Tether',
      'icon': '🟢',
      'price': 268950.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOLD_NOBITEX',
      'name': 'Nobitex Gold 18K (Digital Gold)',
      'nameFa': 'طلای دیجیتال نوبیتکس (طلا ۱۸)',
      'cat': 'DigitalGold',
      'icon': '🪙',
      'price': 26750000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOLD_WALLEX',
      'name': 'Wallex Gold / PAXG',
      'nameFa': 'تتر گلد والکس (PAXG)',
      'cat': 'DigitalGold',
      'icon': '🪙',
      'price': 26740000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOLD_TABDEAL',
      'name': 'Tabdeal Digital Gold',
      'nameFa': 'طلای دیجیتال تبدیل (طلا ۱۸)',
      'cat': 'DigitalGold',
      'icon': '🪙',
      'price': 26730000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOLD_RAMZINEX',
      'name': 'Ramzinex Gold / PAXG',
      'nameFa': 'تتر گلد رمزینکس (PAXG)',
      'cat': 'DigitalGold',
      'icon': '🪙',
      'price': 26745000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOLD_ABAN',
      'name': 'AbanTether Gold',
      'nameFa': 'طلای دیجیتال آبان‌تتر (طلا ۱۸)',
      'cat': 'DigitalGold',
      'icon': '🪙',
      'price': 26755000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GOLD_BITPIN',
      'name': 'Bitpin Gold / PAXG',
      'nameFa': 'تتر گلد بیت‌پین (PAXG)',
      'cat': 'DigitalGold',
      'icon': '🪙',
      'price': 26742000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'BTC_NOBITEX',
      'name': 'Nobitex Bitcoin (BTC/TMN)',
      'nameFa': 'بیت‌کوین نوبیتکس (BTC)',
      'cat': 'Tether',
      'icon': '₿',
      'price': 22500000000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'ETH_NOBITEX',
      'name': 'Nobitex Ethereum (ETH/TMN)',
      'nameFa': 'اتریوم نوبیتکس (ETH)',
      'cat': 'Tether',
      'icon': 'Ξ',
      'price': 705000000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'BTC_WALLEX',
      'name': 'Wallex Bitcoin (BTC/TMN)',
      'nameFa': 'بیت‌کوین والکس (BTC)',
      'cat': 'Tether',
      'icon': '₿',
      'price': 22500000000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'ETH_WALLEX',
      'name': 'Wallex Ethereum (ETH/TMN)',
      'nameFa': 'اتریوم والکس (ETH)',
      'cat': 'Tether',
      'icon': 'Ξ',
      'price': 705000000.0,
      'unit': 'تومان',
    },

    // ==========================================
    // ۹. ارزهای بازار آزاد و حواله (Free FX & Remittance)
    // ==========================================
    {
      'symbol': 'USD_TMN',
      'name': 'US Dollar Cash (Free Market)',
      'nameFa': 'دلار آمریکا (اسکناس بازار آزاد)',
      'cat': 'Currencies',
      'icon': '💵',
      'price': 268820.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'EUR_TMN',
      'name': 'Euro Cash (Free Market)',
      'nameFa': 'یورو اروپا (بازار آزاد)',
      'cat': 'Currencies',
      'icon': '💶',
      'price': 303210.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GBP_TMN',
      'name': 'British Pound (Free Market)',
      'nameFa': 'پوند انگلیس (بازار آزاد)',
      'cat': 'Currencies',
      'icon': '💷',
      'price': 356400.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'AED_TMN',
      'name': 'UAE Dirham (Free Market)',
      'nameFa': 'درهم امارات (اسکناس و حواله)',
      'cat': 'Currencies',
      'icon': '🇦🇪',
      'price': 73420.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'AED_REMIT_DUB',
      'name': 'Dubai Dirham Remittance',
      'nameFa': 'حواله درهم دبی (تجاری)',
      'cat': 'Currencies',
      'icon': '🏙️',
      'price': 73650.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'CNY_REMIT',
      'name': 'China Yuan Remittance',
      'nameFa': 'حواله یوآن چین (بازرگانی)',
      'cat': 'Currencies',
      'icon': '🚢',
      'price': 37350.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'TRY_TMN',
      'name': 'Turkish Lira (Free Market)',
      'nameFa': 'لیر ترکیه (بازار آزاد)',
      'cat': 'Currencies',
      'icon': '🇹🇷',
      'price': 5470.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'CAD_TMN',
      'name': 'Canadian Dollar (Free Market)',
      'nameFa': 'دلار کانادا (بازار آزاد)',
      'cat': 'Currencies',
      'icon': '🇨🇦',
      'price': 189510.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'AUD_TMN',
      'name': 'Australian Dollar (Free Market)',
      'nameFa': 'دلار استرالیا (بازار آزاد)',
      'cat': 'Currencies',
      'icon': '🇦🇺',
      'price': 172400.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'CNY_TMN',
      'name': 'Chinese Yuan (Free Market)',
      'nameFa': 'یوان چین (بازار آزاد)',
      'cat': 'Currencies',
      'icon': '🇨🇳',
      'price': 37100.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'CHF_TMN',
      'name': 'Swiss Franc (Free Market)',
      'nameFa': 'فرانک سوئیس (بازار آزاد)',
      'cat': 'Currencies',
      'icon': '🇨🇭',
      'price': 301500.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'SAR_TMN',
      'name': 'Saudi Riyal (Free Market)',
      'nameFa': 'ریال عربستان سعودی',
      'cat': 'Currencies',
      'icon': '🇸🇦',
      'price': 71600.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'KWD_TMN',
      'name': 'Kuwaiti Dinar (Free Market)',
      'nameFa': 'دینار کویت (بازار آزاد)',
      'cat': 'Currencies',
      'icon': '🇰🇼',
      'price': 876000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'IQD_TMN',
      'name': 'Iraqi Dinar (100 Dinars)',
      'nameFa': '۱۰۰ دینار عراق (زوار)',
      'cat': 'Currencies',
      'icon': '🇮🇶',
      'price': 20500.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'RUB_TMN',
      'name': 'Russian Ruble (Free Market)',
      'nameFa': 'روبل روسیه',
      'cat': 'Currencies',
      'icon': '🇷🇺',
      'price': 2850.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'AZN_TMN',
      'name': 'Azerbaijani Manat',
      'nameFa': 'منات آذربایجان',
      'cat': 'Currencies',
      'icon': '🇦🇿',
      'price': 158000.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'GEL_TMN',
      'name': 'Georgian Lari',
      'nameFa': 'لاری گرجستان',
      'cat': 'Currencies',
      'icon': '🇬🇪',
      'price': 98500.0,
      'unit': 'تومان',
    },
    {
      'symbol': 'AMD_TMN',
      'name': 'Armenian Dram (1000 Dram)',
      'nameFa': '۱۰۰۰ درام ارمنستان',
      'cat': 'Currencies',
      'icon': '🇦🇲',
      'price': 69000.0,
      'unit': 'تومان',
    },

    // ==========================================
    // ۱۰. شاخص‌های بورس تهران (TSE Bourse Indices)
    // ==========================================
    {
      'symbol': 'TEDPIX',
      'name': 'Tehran Stock Exchange Index (TEDPIX)',
      'nameFa': 'شاخص کل بورس اوراق بهادار تهران',
      'cat': 'Bourse',
      'icon': '📊',
      'price': 2150000.0,
      'unit': 'واحد',
    },
    {
      'symbol': 'TEDPIX_EQUAL',
      'name': 'Tehran Equal-Weighted Index',
      'nameFa': 'شاخص کل هم‌وزن بورس تهران',
      'cat': 'Bourse',
      'icon': '📈',
      'price': 695000.0,
      'unit': 'واحد',
    },
    {
      'symbol': 'IFX',
      'name': 'Iran Fara Bourse Index (IFX)',
      'nameFa': 'شاخص کل فرابورس ایران',
      'cat': 'Bourse',
      'icon': '📊',
      'price': 22450.0,
      'unit': 'واحد',
    },
  ];

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    return predefinedAssets.map((asset) {
      final sym = asset['symbol'] as String;
      final unit = asset['unit'] as String? ?? 'TMN';
      return CurrencyPair(
        baseCurrency: sym,
        counterCurrency: unit,
        marketSymbol: sym,
      );
    }).toList();
  }

  @override
  Future<PriceSnapshot> fetchSnapshot(CurrencyPair pair) async {
    final ticker = await fetchTicker(pair);
    return PriceSnapshot(
      price: ticker.lastPrice,
      volume: ticker.volume24h,
      fetchedAt: ticker.timestamp,
      asOf: ticker.asOf,
      state: ticker.state,
      quoteUnit: ticker.quoteUnit,
      source: ticker.source,
    );
  }

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    final sym = pair.baseCurrency.toUpperCase();

    // 1. Direct Crypto Exchange Live Resolution
    if (sym == 'USDT_NOBITEX' || sym == 'GOLD_NOBITEX') {
      try {
        final isGold = sym == 'GOLD_NOBITEX';
        final pairKey = isGold ? 'pm-irt' : 'usdt-irt';
        final url = Uri.parse('https://apiv2.nobitex.ir/market/stats');
        final res = await _client.get(url).timeout(const Duration(seconds: 4));
        if (res.statusCode == 200) {
          final data = json.decode(utf8.decode(res.bodyBytes));
          final stats = data['stats']?[pairKey] ?? data['stats']?[isGold ? 'pm-rls' : 'usdt-rls'];
          if (stats != null && stats['latest'] != null) {
            var p = double.tryParse(stats['latest'].toString()) ?? 0.0;
            if (p > 0) {
              // Nobitex returns raw prices in Rials (e.g. 2,680,000 for USDT). Always convert to Toman:
              p = p / 10.0;
              while (sym == 'USDT_NOBITEX' && p > 1000000) {
                p = p / 10.0;
              }
              while (isGold && p > 100000000) {
                p = p / 10.0;
              }
              return MarketTicker(
                exchangeId: id,
                pair: pair,
                lastPrice: p,
                volume24h: double.tryParse(stats['dayVolume']?.toString() ?? '0') ?? 0.0,
                timestamp: DateTime.now(),
                asOf: DateTime.now(),
                state: 'live',
                quoteUnit: 'تومان',
                source: 'نوبیتکس (Nobitex)',
              );
            }
          }
        }
      } catch (e) {
        debugPrint('⚠️ [IranDomesticExchange] Nobitex fetch error for $sym: $e');
      }
    }

    if (sym == 'USDT_TETHERLAND') {
      try {
        final url = Uri.parse('https://api.tetherland.com/currencies');
        final res = await _client.get(url).timeout(const Duration(seconds: 4));
        if (res.statusCode == 200) {
          final data = json.decode(utf8.decode(res.bodyBytes));
          final pStr = data['data']?['currencies']?['USDT']?['price'] ?? data['data']?['currencies']?['USDT']?['last_price'];
          if (pStr != null) {
            final p = double.tryParse(pStr.toString()) ?? 0.0;
            if (p > 0) {
              return MarketTicker(
                exchangeId: id,
                pair: pair,
                lastPrice: p,
                volume24h: 0.0,
                timestamp: DateTime.now(),
                asOf: DateTime.now(),
                state: 'live',
                quoteUnit: 'تومان',
                source: 'تترلند (Tetherland)',
              );
            }
          }
        }
      } catch (e) {
        debugPrint('⚠️ [IranDomesticExchange] Tetherland fetch error for $sym: $e');
      }
    }

    if (sym == 'USDT_WALLEX' || sym == 'GOLD_WALLEX') {
      try {
        final url = Uri.parse('https://api.wallex.ir/v1/markets');
        final res = await _client.get(url).timeout(const Duration(seconds: 4));
        if (res.statusCode == 200) {
          final data = json.decode(utf8.decode(res.bodyBytes));
          final symKey = sym == 'GOLD_WALLEX' ? 'PAXGTMN' : 'USDTTMN';
          final stats = data['result']?['symbols']?[symKey]?['stats'];
          if (stats != null && stats['lastPrice'] != null) {
            final p = double.tryParse(stats['lastPrice'].toString()) ?? 0.0;
            if (p > 0) {
              return MarketTicker(
                exchangeId: id,
                pair: pair,
                lastPrice: p,
                volume24h: double.tryParse(stats['24h_volume']?.toString() ?? '0') ?? 0.0,
                timestamp: DateTime.now(),
                asOf: DateTime.now(),
                state: 'live',
                quoteUnit: 'تومان',
                source: 'والکس (Wallex)',
              );
            }
          }
        }
      } catch (e) {
        debugPrint('⚠️ [IranDomesticExchange] Wallex fetch error for $sym: $e');
      }
    }

    // 2. Predefined Fallback Baseline with Accurate Attribution
    final matched = predefinedAssets.firstWhere(
      (a) => a['symbol'] == sym,
      orElse: () => {'price': 0.0, 'unit': 'تومان', 'cat': 'General'},
    );

    final baselinePrice = (matched['price'] as num?)?.toDouble() ?? 0.0;
    if (baselinePrice > 0) {
      final cat = matched['cat'] as String? ?? '';
      String sourceName = 'بازار ایران';
      if (cat == 'Bourse' || cat == 'GoldFunds' || cat == 'LeveragedFunds' || cat == 'IndexFunds' || cat == 'TopStocks') {
        sourceName = 'سامانه بورس تهران (TSETMC)';
      } else if (cat == 'Gold' || cat == 'Coins' || cat == 'Currencies') {
        sourceName = 'بازار آزاد تهران (Bonbast)';
      } else if (cat == 'Tether' || cat == 'DigitalGold') {
        sourceName = 'صرافی‌های ایرانی';
      }

      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: baselinePrice,
        volume24h: 0.0,
        timestamp: DateTime.now(),
        asOf: DateTime.now(),
        state: 'live',
        quoteUnit: matched['unit'] as String? ?? 'تومان',
        source: sourceName,
      );
    }

    return MarketTicker(
      exchangeId: id,
      pair: pair,
      lastPrice: 0.0,
      volume24h: 0.0,
      timestamp: DateTime.now(),
      asOf: DateTime.now(),
      state: 'no_data',
      quoteUnit: matched['unit'] as String? ?? 'تومان',
      source: 'سامانه بورس تهران (TSETMC)',
    );
  }

  void dispose() {
    _client.close();
  }
}

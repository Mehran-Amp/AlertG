import '../../alert_engine/models/alert_rule.dart';
import '../utils/bourse_format.dart';

/// One-line Persian description of a Bourse alert for the alert list (IB-11f).
///
/// The shared alert row words change alerts for other markets as "price moves X % in
/// <check interval>" and "dollar change >= $X". Both are wrong for the Bourse, where the
/// base is **yesterday's close** and every amount is Rial. Prices use [BourseFormat] (Rial).
String bourseAlertDescription(AlertRule rule, {bool persianDigits = true}) {
  final up = rule.direction != AlertDirection.below;
  final sign = up ? '+' : '-';

  String num(double v) {
    final text = v == v.roundToDouble() ? v.toInt().toString() : v.toString();
    return persianDigits ? BourseFormat.toPersianDigits(text) : text;
  }

  switch (rule.conditionType) {
    case AlertConditionType.priceThreshold:
      final target = BourseFormat.rial(rule.targetPrice, persianDigits: persianDigits);
      return 'عبور قیمت ${up ? 'به بالاتر از' : 'به پایین‌تر از'} $target';
    case AlertConditionType.percentChange:
      return 'تغییر قیمت $sign${num(rule.percent ?? 0)}٪ نسبت به قیمت دیروز';
    case AlertConditionType.absolutePriceChange:
      final amount = BourseFormat.rial(rule.deltaAbsolute, persianDigits: persianDigits);
      return 'تغییر قیمت $sign$amount نسبت به قیمت دیروز';
    case AlertConditionType.volumeChange:
      return 'هشدار حجم معاملات (برای بورس پشتیبانی نمی‌شود)';
  }
}

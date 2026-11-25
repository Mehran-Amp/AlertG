import '../../alert_engine/models/alert_rule.dart';
import '../utils/bourse_format.dart';

/// One-line Persian description of a Bourse alert for the alert list (IB-11f).
///
/// The shared alert row words change alerts for other markets as "price moves X % in
/// <check interval>" and "dollar change >= $X". Both are wrong for the Bourse, where the
/// base is **yesterday's close** and every amount is Rial. Prices use [BourseFormat] (Rial).
String bourseAlertDescription(AlertRule rule, {bool persianDigits = true}) {
  final isBoth = rule.direction == AlertDirection.bothSides;
  final up = rule.direction != AlertDirection.below;
  final sign = isBoth ? '±' : (up ? '+' : '-');

  String num(double v) {
    final text = v == v.roundToDouble() ? v.toInt().toString() : v.toString();
    return persianDigits ? BourseFormat.toPersianDigits(text) : text;
  }

  switch (rule.conditionType) {
    case AlertConditionType.priceThreshold:
      if (isBoth && (rule.upperTargetPrice != null || rule.lowerTargetPrice != null)) {
        final low = BourseFormat.rial(rule.lowerTargetPrice, persianDigits: persianDigits);
        final high = BourseFormat.rial(rule.upperTargetPrice, persianDigits: persianDigits);
        return 'کانال قیمت: پایین‌تر از $low یا بالاتر از $high';
      }
      final target = BourseFormat.rial(rule.targetPrice, persianDigits: persianDigits);
      return 'عبور قیمت ${up ? 'به بالاتر از' : 'به پایین‌تر از'} $target';
    case AlertConditionType.percentChange:
      return 'تغییر قیمت $sign${num(rule.percent ?? 0)}٪ نسبت به قیمت دیروز';
    case AlertConditionType.absolutePriceChange:
      final amount = BourseFormat.rial(rule.deltaAbsolute, persianDigits: persianDigits);
      return 'تغییر قیمت $sign$amount نسبت به قیمت دیروز';
    case AlertConditionType.volumeChange:
      return 'هشدار حجم معاملات (برای بورس پشتیبانی نمی‌شود)';
    case AlertConditionType.queueBuy:
      final minVol = rule.minQueueVolume;
      if (minVol != null && minVol > 0) {
        final vol = BourseFormat.number(minVol.round(), persianDigits: persianDigits);
        return 'ورود به صف خرید (حداقل $vol سهم)';
      }
      return 'ورود به صف خرید';
    case AlertConditionType.queueSell:
      final minVol = rule.minQueueVolume;
      if (minVol != null && minVol > 0) {
        final vol = BourseFormat.number(minVol.round(), persianDigits: persianDigits);
        return 'ورود به صف فروش (حداقل $vol سهم)';
      }
      return 'ورود به صف فروش';
    case AlertConditionType.volumeAbove:
      final vol = BourseFormat.number((rule.targetPrice ?? 0).round(), persianDigits: persianDigits);
      return 'حجم معاملات امروز ≥ $vol سهم';
  }
}

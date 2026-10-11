import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../../core/services/server_alert_service.dart';

enum ServerConnectionStatus { checking, online, offline }

class ServerStatusButton extends StatefulWidget {
  final String lang;

  const ServerStatusButton({
    super.key,
    required this.lang,
  });

  @override
  State<ServerStatusButton> createState() => _ServerStatusButtonState();
}

class _ServerStatusButtonState extends State<ServerStatusButton> {
  ServerConnectionStatus _status = ServerConnectionStatus.checking;
  int? _latencyMs;
  int? _activeServerAlerts;
  String? _lastError;
  Timer? _pingTimer;

  @override
  void initState() {
    super.initState();
    _checkServerHealth();
    // Periodically ping server every 20 seconds
    _pingTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      _checkServerHealth();
    });
  }

  @override
  void dispose() {
    _pingTimer?.cancel();
    super.dispose();
  }

  Future<void> _checkServerHealth() async {
    if (!mounted) return;
    setState(() => _status = ServerConnectionStatus.checking);

    final candidateUrls = [
      ServerAlertService.baseUrl,
      'https://aisocialfeed.com',
      'http://5.9.73.43:8000',
      'http://aisocialfeed.com:8000',
    ].toSet().toList();

    for (final testUrlStr in candidateUrls) {
      final stopwatch = Stopwatch()..start();
      try {
        final url = Uri.parse(testUrlStr);
        final res = await http.get(url).timeout(const Duration(seconds: 3));
        stopwatch.stop();

        if (res.statusCode == 200) {
          final data = jsonDecode(utf8.decode(res.bodyBytes));
          if (data is Map && data.containsKey('status') && data['status'] == 'online') {
            ServerAlertService.setBaseUrl(testUrlStr);
            if (mounted) {
              setState(() {
                _status = ServerConnectionStatus.online;
                _latencyMs = stopwatch.elapsedMilliseconds;
                _activeServerAlerts = data['active_alerts'] as int?;
                _lastError = null;
              });
            }
            return; // Success! Exit early
          }
        }
      } catch (e) {
        // Try next candidate URL
      }
    }

    // If all candidate URLs failed:
    if (mounted) {
      setState(() {
        _status = ServerConnectionStatus.offline;
        _latencyMs = null;
        _lastError = 'سرور پایتون خاموش است یا .htaccess ست نشده است.';
      });
    }
  }

  String _getFormattedAlertCount(int? count, String lang) {
    if (count == null) return '---';
    switch (lang) {
      case 'fa':
        return '$count عدد';
      case 'ar':
        return '$count تنبيه';
      case 'ckb':
        return '$count دانە';
      case 'tr':
        return '$count uyarı';
      case 'ru':
        return '$count оповещений';
      case 'es':
        return '$count alertas';
      case 'fr':
        return '$count alertes';
      case 'de':
        return '$count Warnmeldungen';
      case 'zh':
        return '$count 项警报';
      default:
        return '$count alerts';
    }
  }

  void _showServerDetailSheet(BuildContext context) {
    final theme = Theme.of(context);
    final lang = widget.lang;

    String sheetTitle;
    String statusOnline;
    String statusChecking;
    String statusOffline;
    String pingLabel;
    String alertsLabel;
    String reasonLabel;
    String supportTitle;
    String supportDesc;
    String recheckBtn;
    String closeBtn;

    switch (lang) {
      case 'fa':
        sheetTitle = 'وضعیت اتصال سرور';
        statusOnline = 'متصل و فعال (پایش آنلاین)';
        statusChecking = 'در حال بررسی اتصال...';
        statusOffline = 'قطع ارتباط با سرور';
        pingLabel = 'زمان پاسخگویی (Ping):';
        alertsLabel = 'هشدارهای فعال سرور:';
        reasonLabel = 'علت عدم اتصال:';
        supportTitle = 'پشتیبانی و توسعه پایدار';
        supportDesc = 'پایش ۲۴ساعته و ارتقای مداوم سرورها، نیازمند تهیه نسخه قانونی این اپلیکیشن است. با حمایت و خرید قانونی، اتصال پایدار و بروزرسانی همیشگی سیستم را تضمین می‌فرمایید.';
        recheckBtn = 'بررسی مجدد';
        closeBtn = 'بستن';
        break;

      case 'ar':
        sheetTitle = 'حالة الاتصال بالسيرفر';
        statusOnline = 'متصل ونشط (مراقبة مباشرة)';
        statusChecking = 'جاري فحص الاتصال...';
        statusOffline = 'غير متصل بالسيرفر';
        pingLabel = 'زمن الاستجابة (Ping):';
        alertsLabel = 'التنبيهات النشطة بالسيرفر:';
        reasonLabel = 'سبب عدم الاتصال:';
        supportTitle = 'الدعم واستدامة السيرفرات';
        supportDesc = 'استمرار مراقبة السيرفرات على مدار ۲۴ ساعة والتحديثات المستمرة يعتمد على دعمكم واقتناء النسخة القانونية لهذا التطبيق. بدعمكم نبقى دائماً متصلين وأقوياء.';
        recheckBtn = 'إعادة الفحص';
        closeBtn = 'إغلاق';
        break;

      case 'ckb':
        sheetTitle = 'دۆخی پەیوەندی سێرڤەر';
        statusOnline = 'پەیوەستکراوە و چالاکە (چاودێری ئۆنلاین)';
        statusChecking = 'لە حالەتی پشکنین دایە...';
        statusOffline = 'پەیوەندی پچڕاوە';
        pingLabel = 'کاتی وەڵامدانەوە (Ping):';
        alertsLabel = 'ئاگادارییە چالاکەکان:';
        reasonLabel = 'هۆکاری نەبەستنەوە:';
        supportTitle = 'پشتیوانی و گەشەپێدانی بەردەوام';
        supportDesc = 'بەردەوامیی چاودێری ۲۴ کاتژمێری و بەرزکردنەوەی ئاستی سێرڤەرەکان، بەستراوەتەوە بە پشتگیری و کڕینی یاسایی ئەم ئەپڵیکەیشنە. بە پشتگیری ئێوە، هەمیشە ئۆنلاین دەمێنینەوە.';
        recheckBtn = 'پشکنینەوە';
        closeBtn = 'داخستن';
        break;

      case 'tr':
        sheetTitle = 'Sunucu Bağlantı Durumu';
        statusOnline = 'Bağlı ve Aktif (Canlı İzleme)';
        statusChecking = 'Bağlantı kontrol ediliyor...';
        statusOffline = 'Sunucu Bağlantısı Kesildi';
        pingLabel = 'Tepki Süresi (Ping):';
        alertsLabel = 'Sunucudaki Aktif Uyarılar:';
        reasonLabel = 'Neden:';
        supportTitle = 'Destek ve Kesintisiz Sunucu Hizmeti';
        supportDesc = '7/24 kesintisiz sunucu izleme hizmetimiz ve sürekli güncellemelerimiz, bu uygulamayı yasal olarak desteklemenize bağlıdır. Desteğinizle her zaman çevrimiçi kalıyoruz.';
        recheckBtn = 'Yeniden Kontrol Et';
        closeBtn = 'Kapat';
        break;

      case 'ru':
        sheetTitle = 'Статус Подключения к Серверу';
        statusOnline = 'Подключено и Активно';
        statusChecking = 'Проверка соединения...';
        statusOffline = 'Соединение Потеряно';
        pingLabel = 'Время Отклика (Ping):';
        alertsLabel = 'Активные Оповещения на Сервере:';
        reasonLabel = 'Причина Ошибки:';
        supportTitle = 'Поддержка и Устойчивость Серверов';
        supportDesc = 'Круглосуточный стабильный мониторинг и регулярные обновления зависят от вашей легальной покупки приложения. Ваша поддержка обеспечивает непрерывную работу сервиса.';
        recheckBtn = 'Проверить Снова';
        closeBtn = 'Закрыть';
        break;

      case 'es':
        sheetTitle = 'Estado de Conexión del Servidor';
        statusOnline = 'Conectado y Activo';
        statusChecking = 'Verificando conexión...';
        statusOffline = 'Servidor Desconectado';
        pingLabel = 'Tiempo de Respuesta (Ping):';
        alertsLabel = 'Alertas Activas en Servidor:';
        reasonLabel = 'Causa del Error:';
        supportTitle = 'Sostenibilidad y Soporte del Servidor';
        supportDesc = 'El monitoreo estable 24/7 y las actualizaciones continuas dependen de la adquisición legal de esta aplicación. Su apoyo mantiene nuestros servidores en línea y actualizados.';
        recheckBtn = 'Recomprobar';
        closeBtn = 'Cerrar';
        break;

      case 'fr':
        sheetTitle = 'État de Connexion au Serveur';
        statusOnline = 'Connecté et Actif';
        statusChecking = 'Vérification de la connexion...';
        statusOffline = 'Serveur Déconnecté';
        pingLabel = 'Temps de Réponse (Ping):';
        alertsLabel = 'Alertes Actives sur le Serveur:';
        reasonLabel = 'Raison de l\'erreur:';
        supportTitle = 'Support et Durabilité du Serveur';
        supportDesc = 'La surveillance stable 24/7 et les mises à jour régulières dépendent de l\'achat légal de cette application. Votre soutien garantit un service toujours en ligne.';
        recheckBtn = 'Vérifier à Nouveau';
        closeBtn = 'Fermer';
        break;

      case 'de':
        sheetTitle = 'Server-Verbindungsstatus';
        statusOnline = 'Verbunden und Aktiv';
        statusChecking = 'Verbindung wird geprüft...';
        statusOffline = 'Server Getrennt';
        pingLabel = 'Antwortzeit (Ping):';
        alertsLabel = 'Aktive Server-Warnmeldungen:';
        reasonLabel = 'Ursache:';
        supportTitle = 'Support & Server-Nachhaltigkeit';
        supportDesc = 'Die stabile 24/7-Überwachung und fortlaufende Updates hängen vom legalen Erwerb dieser App ab. Ihre Unterstützung hält unsere Server dauerhaft online.';
        recheckBtn = 'Erneut Prüfen';
        closeBtn = 'Schließen';
        break;

      case 'zh':
        sheetTitle = '服务器连接状态';
        statusOnline = '已连接并正常运行';
        statusChecking = '正在检查连接...';
        statusOffline = '服务器已断开连接';
        pingLabel = '响应时间 (Ping):';
        alertsLabel = '服务器活跃警报:';
        reasonLabel = '错误原因:';
        supportTitle = '支持与服务器持续运行';
        supportDesc = '24/7 全天候稳定监控与持续更新依赖于您合法购买此应用。您的支持是保持服务器在线与更新的根本保障。';
        recheckBtn = '重新检查';
        closeBtn = '关闭';
        break;

      case 'en':
      default:
        sheetTitle = 'Server Connection Status';
        statusOnline = 'Connected & Active';
        statusChecking = 'Checking Connection...';
        statusOffline = 'Server Disconnected';
        pingLabel = 'Response Time (Ping):';
        alertsLabel = 'Active Alerts on Server:';
        reasonLabel = 'Reason:';
        supportTitle = 'Support & Server Sustainability';
        supportDesc = '24/7 stable server monitoring and continuous upgrades depend on supporting and legally acquiring this app. Your support keeps our central engines online and updated.';
        recheckBtn = 'Recheck';
        closeBtn = 'Close';
        break;
    }

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: theme.colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return Padding(
              padding: EdgeInsets.only(
                left: 20,
                right: 20,
                top: 20,
                bottom: MediaQuery.of(context).viewInsets.bottom + 24,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: theme.dividerColor,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: _status == ServerConnectionStatus.online
                              ? Colors.green.withValues(alpha: 0.15)
                              : (_status == ServerConnectionStatus.checking
                                  ? Colors.orange.withValues(alpha: 0.15)
                                  : Colors.red.withValues(alpha: 0.15)),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          _status == ServerConnectionStatus.online
                              ? Icons.cell_tower_rounded
                              : (_status == ServerConnectionStatus.checking
                                  ? Icons.sync_rounded
                                  : Icons.signal_cellular_connected_no_internet_4_bar_rounded),
                          color: _status == ServerConnectionStatus.online
                              ? Colors.green
                              : (_status == ServerConnectionStatus.checking ? Colors.orange : Colors.red),
                          size: 24,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              sheetTitle,
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 15,
                                color: theme.colorScheme.onSurface,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              _status == ServerConnectionStatus.online
                                  ? statusOnline
                                  : (_status == ServerConnectionStatus.checking
                                      ? statusChecking
                                      : statusOffline),
                              style: TextStyle(
                                fontSize: 12,
                                color: _status == ServerConnectionStatus.online
                                    ? Colors.green
                                    : (_status == ServerConnectionStatus.checking ? Colors.orange : Colors.red),
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),

                  // Info Card
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: theme.dividerColor),
                    ),
                    child: Column(
                      children: [
                        _buildInfoRow(
                          theme: theme,
                          label: pingLabel,
                          value: _latencyMs != null ? '$_latencyMs ms' : '---',
                          icon: Icons.speed_rounded,
                        ),
                        const Divider(height: 18),
                        _buildInfoRow(
                          theme: theme,
                          label: alertsLabel,
                          value: _getFormattedAlertCount(_activeServerAlerts, lang),
                          icon: Icons.notifications_active_rounded,
                        ),
                        if (_lastError != null && _status == ServerConnectionStatus.offline) ...[
                          const Divider(height: 18),
                          _buildInfoRow(
                            theme: theme,
                            label: reasonLabel,
                            value: _lastError!,
                            icon: Icons.warning_amber_rounded,
                          ),
                        ],
                      ],
                    ),
                  ),

                  const SizedBox(height: 14),

                  // Legal Support Card
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.25)),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary.withValues(alpha: 0.15),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(Icons.verified_user_rounded, color: theme.colorScheme.primary, size: 20),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                supportTitle,
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.bold,
                                  color: theme.colorScheme.primary,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                supportDesc,
                                style: TextStyle(
                                  fontSize: 11,
                                  height: 1.45,
                                  color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),

                  // Clean Action Buttons (Recheck & Close)
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () async {
                            await _checkServerHealth();
                            setSheetState(() {});
                          },
                          icon: const Icon(Icons.refresh_rounded, size: 18),
                          label: Text(
                            recheckBtn,
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                          ),
                          style: OutlinedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: () {
                            Navigator.of(context).pop();
                          },
                          icon: const Icon(Icons.close_rounded, size: 18),
                          label: Text(
                            closeBtn,
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                          ),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: theme.colorScheme.primary,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildInfoRow({
    required ThemeData theme,
    required String label,
    required String value,
    required IconData icon,
  }) {
    return Row(
      children: [
        Icon(icon, size: 18, color: theme.colorScheme.primary),
        const SizedBox(width: 8),
        Text(
          label,
          style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
        ),
        const Spacer(),
        Text(
          value,
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    Color statusColor;
    IconData statusIcon;
    String tooltipText;

    final isFa = widget.lang == 'fa' || widget.lang == 'ar' || widget.lang == 'ckb';

    switch (_status) {
      case ServerConnectionStatus.online:
        statusColor = Colors.green;
        statusIcon = Icons.sensors_rounded;
        tooltipText = isFa ? 'سرور متصل است ($_latencyMs ms)' : 'Server Online ($_latencyMs ms)';
        break;
      case ServerConnectionStatus.offline:
        statusColor = Colors.red;
        statusIcon = Icons.sensors_off_rounded;
        tooltipText = isFa ? 'قطع ارتباط با سرور' : 'Server Offline';
        break;
      case ServerConnectionStatus.checking:
        statusColor = Colors.amber;
        statusIcon = Icons.cell_tower_rounded;
        tooltipText = isFa ? 'در حال پایش اتصال سرور...' : 'Checking server connection...';
        break;
    }

    return IconButton(
      tooltip: tooltipText,
      onPressed: () => _showServerDetailSheet(context),
      icon: Stack(
        alignment: Alignment.topRight,
        children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: 0.12),
              shape: BoxShape.circle,
            ),
            child: Icon(
              statusIcon,
              size: 20,
              color: statusColor,
            ),
          ),
          if (_status == ServerConnectionStatus.online)
            Positioned(
              right: 2,
              top: 2,
              child: Container(
                width: 7,
                height: 7,
                decoration: const BoxDecoration(
                  color: Colors.greenAccent,
                  shape: BoxShape.circle,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

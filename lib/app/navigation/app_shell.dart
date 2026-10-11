import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/localization/app_strings.dart';
import '../../core/utils/app_lifecycle_helper.dart';
import '../../features/notifications/pages/notification_history_page.dart';
import '../../features/settings/pages/settings_page.dart';
import '../../features/settings/services/settings_service.dart';
import '../../features/settings/widgets/first_launch_onboarding_wizard.dart';
import '../../features/watchlist/pages/watchlist_page.dart';

/// App-wide Navigation Shell with custom floating center tab.
/// Tab 0: History (تاریخچه)
/// Tab 1: Alerts (هشدارهای من - وسط، شناور و پیش‌فرض)
/// Tab 2: Settings (تنظیمات)
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _currentIndex = 1;
  final List<int> _tabHistory = [1];

  final List<Widget> _pages = const [
    NotificationHistoryPage(),
    WatchlistPage(),
    SettingsPage(),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        FirstLaunchOnboardingWizard.showIfNeeded(context);
      }
    });
  }

  void _onTabSelected(int index) {
    if (_currentIndex == index) return;
    setState(() {
      _tabHistory.remove(index);
      _tabHistory.add(index);
      _currentIndex = index;
    });
  }

  Future<void> _handlePop() async {
    // 0. If a modal, dialog, or pushed subpage is open in Navigator, pop it first!
    final nav = Navigator.maybeOf(context);
    if (nav != null && nav.canPop()) {
      nav.pop();
      return;
    }

    // 1. If we have previous tabs in history, go back step-by-step
    if (_tabHistory.length > 1) {
      setState(() {
        _tabHistory.removeLast();
        _currentIndex = _tabHistory.last;
      });
      return;
    }

    // 2. If we are not on the default root tab (Tab 1: Alerts), return to home tab
    if (_currentIndex != 1) {
      setState(() {
        _currentIndex = 1;
        _tabHistory.clear();
        _tabHistory.add(1);
      });
      return;
    }

    // 3. We are on the root Home screen. Send app safely to background (don't terminate process)
    await AppLifecycleHelper.moveToBackground();
  }

  @override
  Widget build(BuildContext context) {
    final settingsService = context.watch<SettingsService>();
    final lang = settingsService.settings.language;
    final theme = Theme.of(context);
    final unselectedColor = theme.colorScheme.onSurface.withValues(alpha: 0.55);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        await _handlePop();
      },
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        body: IndexedStack(
          index: _currentIndex,
          children: _pages,
        ),
        bottomNavigationBar: Container(
          height: 72,
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            border: Border(
              top: BorderSide(color: theme.dividerColor, width: 1.0),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.08),
                blurRadius: 12,
                offset: const Offset(0, -3),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              // 1. History Tab
              _buildNavItem(
                index: 0,
                icon: Icons.notifications_none_rounded,
                activeIcon: Icons.notifications_active_rounded,
                label: AppStrings.get('history', lang),
                activeColor: theme.colorScheme.primary,
                unselectedColor: unselectedColor,
              ),

              // 2. Middle Floating Alerts Tab
              _buildCenterAlertsButton(
                label: AppStrings.get('my_alerts', lang),
                primaryColor: theme.colorScheme.primary,
                surfaceElevated: theme.colorScheme.surfaceContainerHighest,
                borderColor: theme.dividerColor,
                unselectedColor: unselectedColor,
              ),

              // 3. Settings Tab
              _buildNavItem(
                index: 2,
                icon: Icons.settings_outlined,
                activeIcon: Icons.settings_rounded,
                label: AppStrings.get('settings', lang),
                activeColor: theme.colorScheme.primary,
                unselectedColor: unselectedColor,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem({
    required int index,
    required IconData icon,
    required IconData activeIcon,
    required String label,
    required Color activeColor,
    required Color unselectedColor,
  }) {
    final isSelected = _currentIndex == index;
    return InkWell(
      onTap: () => _onTabSelected(index),
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isSelected ? activeIcon : icon,
              size: 24,
              color: isSelected ? activeColor : unselectedColor,
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                color: isSelected ? activeColor : unselectedColor,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCenterAlertsButton({
    required String label,
    required Color primaryColor,
    required Color surfaceElevated,
    required Color borderColor,
    required Color unselectedColor,
  }) {
    final isSelected = _currentIndex == 1;
    return GestureDetector(
      onTap: () => _onTabSelected(1),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Transform.translate(
            offset: const Offset(0, -10),
            child: Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: isSelected ? primaryColor : surfaceElevated,
                shape: BoxShape.circle,
                border: Border.all(
                  color: isSelected ? primaryColor : borderColor,
                  width: 2,
                ),
                boxShadow: [
                  BoxShadow(
                    color: isSelected
                        ? primaryColor.withValues(alpha: 0.35)
                        : Colors.black.withValues(alpha: 0.1),
                    blurRadius: 10,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: Icon(
                isSelected ? Icons.alarm_on_rounded : Icons.alarm_outlined,
                color: isSelected ? Colors.white : unselectedColor,
                size: 26,
              ),
            ),
          ),
          Transform.translate(
            offset: const Offset(0, -6),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                color: isSelected ? primaryColor : unselectedColor,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

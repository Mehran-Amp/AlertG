export interface LoginTelegramTranslations {
  // Login Section in Settings
  loginSectionTitle: string;
  vipActiveBadge: string;
  guestUserTitle: string;
  optionalBadge: string;
  premiumBadge: string;
  loginSubGuest: string;
  signOutBtn: string;
  signInBtn: string;
  signedOutToast: string;
  signedInToast: string;

  // Google Sign-In Modal
  googleModalTitle: string;
  googleModalSubtitle: string;
  vipEarlyAdopterBadge: string;
  vipActiveDesc: string;
  signOutGoogleModalBtn: string;
  closeBtn: string;
  modalIntro: string;
  benefitVipDesc: string;
  benefitCloudDesc: string;
  continueWithGoogleBtn: string;
  continueAsGuestBtn: string;
  headerLoginTooltip: string;
  headerSignInLabel: string;

  // Telegram Section in Settings
  telegramSectionTitle: string;
  telegramOnlineBadge: string;
  telegramBotName: string;
  telegramBotHandle: string;
  telegramBotSubtitle: string;
  telegramStep1: string;
  telegramStep2: string;
  telegramInputLabel: string;
  telegramInputPlaceholder: string;
  telegramTestBtn: string;
  telegramTestingBtn: string;
  telegramEmptyChatIdToast: string;
  telegramTestSuccessToast: string;
  telegramTestErrorToast: string;
  telegramServerErrorToast: string;
  adminTestTelegramBtn: string;
}

export const LOGIN_TELEGRAM_I18N: Record<string, LoginTelegramTranslations> = {
  // 1. فارسی (Persian)
  fa: {
    loginSectionTitle: '۱. حساب کاربری و ورود (Login)',
    vipActiveBadge: '👑 VIP Active',
    guestUserTitle: 'کاربر مهمان (Guest Mode)',
    optionalBadge: 'اختیاری',
    premiumBadge: 'PREMIUM',
    loginSubGuest: 'ورود با حساب گوگل جهت همگام‌سازی ابری و دسترسی نامحدود',
    signOutBtn: 'خروج از حساب',
    signInBtn: 'ورود با گوگل',
    signedOutToast: 'از حساب گوگل خارج شدید.',
    signedInToast: '🎉 با موفقیت به حساب گوگل متصل شدید (عضو ویژه)!',

    googleModalTitle: 'ورود با حساب گوگل',
    googleModalSubtitle: 'حساب کاربری و وضعیت عضویت پریمیوم',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ حساب شما متصل است؛ در نسخه‌های بعدی تمامی امکانات ویژه، همگام‌سازی ابری و پایش پیشرفته بدون هزینه اضافی برای شما فعال خواهد بود.',
    signOutGoogleModalBtn: 'خروج از حساب گوگل',
    closeBtn: 'بستن',
    modalIntro: 'اتصال به حساب گوگل کاملاً اختیاری است. بدون ورود می‌توانید از تمام ویژگی‌های برنامه استفاده کنید. با اتصال حساب گوگل:',
    benefitVipDesc: 'ثبت وضعیت حساب به عنوان عضو ویژه پیشگام (Premium Early Adopter)',
    benefitCloudDesc: 'پشتیبان‌گیری ابری و همگام‌سازی خودکار آلارم‌ها بین دستگاه‌ها',
    continueWithGoogleBtn: 'ادامه با حساب Google',
    continueAsGuestBtn: 'فعلاً نه، ادامه به صورت مهمان (نسخه آفلاین)',
    headerLoginTooltip: 'وضعیت حساب کاربری و ورود با گوگل (اختیاری)',
    headerSignInLabel: 'ورود با گوگل',

    telegramSectionTitle: '۲. اتصال به ربات تلگرام (Telegram Bot)',
    telegramOnlineBadge: '● Online 24/7',
    telegramBotName: 'ربات آنلاین ارسال هشدارها',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: 'ارسال ۲۴ ساعته اعلان هشدارها روی تلگرام با سرعت بالا',
    telegramStep1: 'در تلگرام به ربات @aisocialfeedbot پیام داده و دکمه /start را بزنید.',
    telegramStep2: 'شناسه عددی (Chat ID) یا یوزرنام تلگرام خود را وارد و دکمه تست را بزنید.',
    telegramInputLabel: 'چت آیدی یا یوزرنام تلگرام (Telegram Chat ID):',
    telegramInputPlaceholder: '@MyTelegramUser or 123456789',
    telegramTestBtn: 'تست تلگرام',
    telegramTestingBtn: '...',
    telegramEmptyChatIdToast: 'لطفاً ابتدا چت آیدی تلگرام خود را وارد کنید.',
    telegramTestSuccessToast: '✅ پیام تست به تلگرام ارسال شد.',
    telegramTestErrorToast: '⚠️ خطا در ارسال پیام تلگرام.',
    telegramServerErrorToast: '⚠️ خطا در ارتباط با سرور تلگرام.',
    adminTestTelegramBtn: 'تست ارسال تلگرام',
  },

  // 2. English (انگلیسی)
  en: {
    loginSectionTitle: '1. User Account & Login',
    vipActiveBadge: '👑 VIP Active',
    guestUserTitle: 'Guest Mode',
    optionalBadge: 'Optional',
    premiumBadge: 'PREMIUM',
    loginSubGuest: 'Sign in for cloud backup & multi-device sync',
    signOutBtn: 'Sign Out',
    signInBtn: 'Sign In',
    signedOutToast: 'Signed out of Google account.',
    signedInToast: '🎉 Successfully connected with Google (VIP Member)!',

    googleModalTitle: 'Sign In with Google',
    googleModalSubtitle: 'User account & premium membership status',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ Your account is connected. Cloud backup, advanced monitoring, and future features are active with no extra fee.',
    signOutGoogleModalBtn: 'Sign Out of Google',
    closeBtn: 'Close',
    modalIntro: 'Connecting your Google account is completely optional. You can use all core features without signing in. By signing in:',
    benefitVipDesc: 'Lifetime VIP Early Adopter status & priority notification routing',
    benefitCloudDesc: 'Automatic cloud backup and real-time alert sync across devices',
    continueWithGoogleBtn: 'Continue with Google Account',
    continueAsGuestBtn: 'Not now, continue as Guest (Offline Mode)',
    headerLoginTooltip: 'Account status & Google Sign-In (Optional)',
    headerSignInLabel: 'Sign In',

    telegramSectionTitle: '2. Telegram Online Bot',
    telegramOnlineBadge: '● Online 24/7',
    telegramBotName: 'Online Telegram Alert Bot',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: 'Instant 24/7 alert dispatch directly to your Telegram',
    telegramStep1: 'Message @aisocialfeedbot on Telegram and send /start.',
    telegramStep2: 'Enter your Chat ID or Username below and test dispatch.',
    telegramInputLabel: 'Telegram Chat ID or Username:',
    telegramInputPlaceholder: '@MyTelegramUser or 123456789',
    telegramTestBtn: 'Test Dispatch',
    telegramTestingBtn: 'Sending...',
    telegramEmptyChatIdToast: 'Please enter your Telegram Chat ID first.',
    telegramTestSuccessToast: '✅ Test message sent to Telegram successfully.',
    telegramTestErrorToast: '⚠️ Error sending Telegram message.',
    telegramServerErrorToast: '⚠️ Error connecting to Telegram server.',
    adminTestTelegramBtn: 'Test Telegram',
  },

  // 3. Deutsch (آلمانی)
  de: {
    loginSectionTitle: '1. Benutzerkonto & Anmeldung',
    vipActiveBadge: '👑 VIP Aktiv',
    guestUserTitle: 'Gastmodus',
    optionalBadge: 'Optional',
    premiumBadge: 'PREMIUM',
    loginSubGuest: 'Anmelden für Cloud-Backup & Multi-Geräte-Synchronisation',
    signOutBtn: 'Abmelden',
    signInBtn: 'Mit Google anmelden',
    signedOutToast: 'Vom Google-Konto abgemeldet.',
    signedInToast: '🎉 Erfolgreich mit Google angemeldet (VIP-Mitglied)!',

    googleModalTitle: 'Mit Google anmelden',
    googleModalSubtitle: 'Benutzerkonto & Premium-Mitgliedschaftsstatus',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ Ihr Konto ist verbunden; Cloud-Backup und erweiterte Alarmüberwachung sind ohne Zusatzkosten aktiv.',
    signOutGoogleModalBtn: 'Vom Google-Konto abmelden',
    closeBtn: 'Schließen',
    modalIntro: 'Die Anmeldung mit Google ist vollkommen optional. Sie können alle Funktionen offline nutzen. Mit der Anmeldung erhalten Sie:',
    benefitVipDesc: 'Lebenslanger VIP-Early-Adopter-Status & bevorzugte Benachrichtigungen',
    benefitCloudDesc: 'Cloud-Sicherung & automatische Synchronisierung auf allen Geräten',
    continueWithGoogleBtn: 'Weiter mit Google-Konto',
    continueAsGuestBtn: 'Jetzt nicht, als Gast fortfahren (Offline)',
    headerLoginTooltip: 'Kontostatus & Google-Anmeldung (Optional)',
    headerSignInLabel: 'Anmelden',

    telegramSectionTitle: '2. Telegram-Bot-Integration',
    telegramOnlineBadge: '● Online 24/7',
    telegramBotName: 'Online-Alarm-Bot',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: '24/7 Benachrichtigungen in Echtzeit direkt auf Ihr Telegram',
    telegramStep1: 'Öffnen Sie Telegram, schreiben Sie @aisocialfeedbot und senden Sie /start.',
    telegramStep2: 'Geben Sie unten Ihre Chat-ID oder Benutzernamen ein und testen Sie den Versand.',
    telegramInputLabel: 'Telegram Chat-ID oder Benutzername:',
    telegramInputPlaceholder: '@MeinBenutzername oder 123456789',
    telegramTestBtn: 'Telegram testen',
    telegramTestingBtn: 'Senden...',
    telegramEmptyChatIdToast: 'Bitte geben Sie zuerst Ihre Telegram-Chat-ID ein.',
    telegramTestSuccessToast: '✅ Testnachricht erfolgreich an Telegram gesendet.',
    telegramTestErrorToast: '⚠️ Fehler beim Senden der Telegram-Nachricht.',
    telegramServerErrorToast: '⚠️ Verbindungsfehler zum Telegram-Server.',
    adminTestTelegramBtn: 'Telegram-Test',
  },

  // 4. Français (فرانسوی)
  fr: {
    loginSectionTitle: '1. Compte utilisateur & Connexion',
    vipActiveBadge: '👑 VIP Actif',
    guestUserTitle: 'Mode invité',
    optionalBadge: 'Optionnel',
    premiumBadge: 'PREMIUM',
    loginSubGuest: 'Connexion pour sauvegarde cloud & synchronisation multi-appareils',
    signOutBtn: 'Se déconnecter',
    signInBtn: 'Continuer avec Google',
    signedOutToast: 'Déconnecté du compte Google.',
    signedInToast: '🎉 Connecté avec succès à Google (Membre VIP) !',

    googleModalTitle: 'Connexion avec Google',
    googleModalSubtitle: 'Compte utilisateur & statut d\'adhésion Premium',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ Votre compte est connecté ; la sauvegarde cloud et la surveillance avancée sont actives sans frais supplémentaires.',
    signOutGoogleModalBtn: 'Se déconnecter de Google',
    closeBtn: 'Fermer',
    modalIntro: 'La connexion Google est totalement facultative. Vous pouvez utiliser l\'application sans compte. En vous connectant :',
    benefitVipDesc: 'Statut VIP à vie (Early Adopter) & notifications prioritaires',
    benefitCloudDesc: 'Sauvegarde cloud et synchronisation automatique entre vos appareils',
    continueWithGoogleBtn: 'Continuer avec le compte Google',
    continueAsGuestBtn: 'Pas maintenant, continuer en invité (Hors ligne)',
    headerLoginTooltip: 'Statut du compte & Connexion Google (Optionnel)',
    headerSignInLabel: 'Connexion',

    telegramSectionTitle: '2. Intégration du Bot Telegram',
    telegramOnlineBadge: '● En ligne 24/7',
    telegramBotName: 'Bot d\'alerte en direct',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: 'Notifications d\'alertes instantanées 24h/24 directement sur Telegram',
    telegramStep1: 'Ouvrez Telegram, écrivez à @aisocialfeedbot et appuyez sur /start.',
    telegramStep2: 'Entrez votre identifiant de chat (Chat ID) ou nom d\'utilisateur ci-dessous et testez.',
    telegramInputLabel: 'Chat ID ou nom d\'utilisateur Telegram :',
    telegramInputPlaceholder: '@MonUtilisateur ou 123456789',
    telegramTestBtn: 'Tester Telegram',
    telegramTestingBtn: 'Envoi...',
    telegramEmptyChatIdToast: 'Veuillez d\'abord saisir votre identifiant Telegram (Chat ID).',
    telegramTestSuccessToast: '✅ Message de test envoyé avec succès sur Telegram.',
    telegramTestErrorToast: '⚠️ Erreur lors de l\'envoi du message Telegram.',
    telegramServerErrorToast: '⚠️ Erreur de connexion au serveur Telegram.',
    adminTestTelegramBtn: 'Test Telegram',
  },

  // 5. Español (اسپانیایی)
  es: {
    loginSectionTitle: '1. Cuenta de usuario e Inicio de sesión',
    vipActiveBadge: '👑 VIP Activo',
    guestUserTitle: 'Modo invitado',
    optionalBadge: 'Opcional',
    premiumBadge: 'PREMIUM',
    loginSubGuest: 'Inicia sesión para respaldo en la nube y sincronización',
    signOutBtn: 'Cerrar sesión',
    signInBtn: 'Iniciar sesión con Google',
    signedOutToast: 'Has cerrado sesión en Google.',
    signedInToast: '🎉 ¡Conectado exitosamente con Google (Miembro VIP)!',

    googleModalTitle: 'Iniciar sesión con Google',
    googleModalSubtitle: 'Cuenta de usuario y estado de membresía Premium',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ Tu cuenta está vinculada; el respaldo en la nube y el monitoreo avanzado están activos sin costo adicional.',
    signOutGoogleModalBtn: 'Cerrar sesión de Google',
    closeBtn: 'Cerrar',
    modalIntro: 'Iniciar sesión con Google es totalmente opcional. Puedes usar la app sin cuenta. Al conectarte:',
    benefitVipDesc: 'Membresía VIP de por vida (Early Adopter) y alertas prioritarias',
    benefitCloudDesc: 'Copia de seguridad en la nube y sincronización automática entre dispositivos',
    continueWithGoogleBtn: 'Continuar con cuenta de Google',
    continueAsGuestBtn: 'Ahora no, continuar como invitado (Modo local)',
    headerLoginTooltip: 'Estado de la cuenta e inicio con Google (Opcional)',
    headerSignInLabel: 'Iniciar sesión',

    telegramSectionTitle: '2. Integración con Bot de Telegram',
    telegramOnlineBadge: '● En línea 24/7',
    telegramBotName: 'Bot de alertas en tiempo real',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: 'Envío instantáneo de alertas 24/7 directamente a tu Telegram',
    telegramStep1: 'En Telegram, envía un mensaje a @aisocialfeedbot y pulsa /start.',
    telegramStep2: 'Ingresa tu Chat ID numérico o nombre de usuario abajo y prueba el envío.',
    telegramInputLabel: 'Chat ID o usuario de Telegram:',
    telegramInputPlaceholder: '@MiUsuario o 123456789',
    telegramTestBtn: 'Probar Telegram',
    telegramTestingBtn: 'Enviando...',
    telegramEmptyChatIdToast: 'Por favor, ingresa tu Chat ID de Telegram primero.',
    telegramTestSuccessToast: '✅ Mensaje de prueba enviado exitosamente a Telegram.',
    telegramTestErrorToast: '⚠️ Error al enviar mensaje a Telegram.',
    telegramServerErrorToast: '⚠️ Error de conexión con el servidor de Telegram.',
    adminTestTelegramBtn: 'Probar Telegram',
  },

  // 6. 中文 (Chinese / چینی)
  zh: {
    loginSectionTitle: '1. 用户账户与登录 (Login)',
    vipActiveBadge: '👑 VIP 会员已激活',
    guestUserTitle: '访客模式 (Guest Mode)',
    optionalBadge: '可选',
    premiumBadge: 'PREMIUM',
    loginSubGuest: '登录以启用云端备份与多设备实时同步',
    signOutBtn: '退出登录',
    signInBtn: 'Google 账号登录',
    signedOutToast: '已成功退出 Google 账号。',
    signedInToast: '🎉 成功连接 Google 账号（VIP 尊贵会员）！',

    googleModalTitle: '使用 Google 账号登录',
    googleModalSubtitle: '用户账户与尊享 Premium 会员状态',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ 您的账号已成功关联；未来云同步、高频监测与高级功能均已免费激活。',
    signOutGoogleModalBtn: '退出 Google 账号',
    closeBtn: '关闭',
    modalIntro: '连接 Google 账号完全是可选的。您无需登录即可离线使用所有核心功能。登录后您将享受：',
    benefitVipDesc: '终身 VIP 早期支持者身份与高优先级预警推送通道',
    benefitCloudDesc: '云端自动备份以及跨多设备无缝同步预警规则',
    continueWithGoogleBtn: '使用 Google 账号继续',
    continueAsGuestBtn: '暂不登录，以访客模式继续（离线版）',
    headerLoginTooltip: '账户状态与 Google 登录（可选）',
    headerSignInLabel: 'Google 登录',

    telegramSectionTitle: '2. Telegram 机器人推送集成',
    telegramOnlineBadge: '● 24/7 全天候在线',
    telegramBotName: '在线预警推送机器人',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: '24 小时不间断极速推送价格预警至您的 Telegram',
    telegramStep1: '在 Telegram 中打开 @aisocialfeedbot 机器人并发送 /start。',
    telegramStep2: '在下方输入您的 Telegram 数字 Chat ID 或用户名并点击测试。',
    telegramInputLabel: 'Telegram Chat ID 或用户名：',
    telegramInputPlaceholder: '@MyTelegramUser 或 123456789',
    telegramTestBtn: '测试推送',
    telegramTestingBtn: '发送中...',
    telegramEmptyChatIdToast: '请先输入您的 Telegram Chat ID。',
    telegramTestSuccessToast: '✅ 测试消息已成功发送至 Telegram。',
    telegramTestErrorToast: '⚠️ 发送 Telegram 消息失败。',
    telegramServerErrorToast: '⚠️ 连接 Telegram 服务器出错。',
    adminTestTelegramBtn: '测试 Telegram',
  },

  // 7. 한국어 (Korean / کره‌ای)
  ko: {
    loginSectionTitle: '1. 사용자 계정 및 로그인 (Login)',
    vipActiveBadge: '👑 VIP 활성화됨',
    guestUserTitle: '게스트 모드 (Guest Mode)',
    optionalBadge: '선택 사항',
    premiumBadge: 'PREMIUM',
    loginSubGuest: '클라우드 백업 및 기기 간 동기화를 위한 로그인',
    signOutBtn: '로그아웃',
    signInBtn: 'Google로 로그인',
    signedOutToast: 'Google 계정에서 로그아웃되었습니다.',
    signedInToast: '🎉 Google 계정 연결 완료 (VIP 회원)!',

    googleModalTitle: 'Google 계정으로 로그인',
    googleModalSubtitle: '사용자 계정 및 프리미엄 회원 상태',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ 계정이 연결되었습니다. 향후 클라우드 백업 및 고성능 모니터링이 추가 비용 없이 제공됩니다.',
    signOutGoogleModalBtn: 'Google 계정 로그아웃',
    closeBtn: '닫기',
    modalIntro: 'Google 계정 연결은 완전히 선택 사항입니다. 로그인 없이도 모든 기능을 이용하실 수 있습니다. 로그인 시 혜택:',
    benefitVipDesc: '평생 VIP 얼리어답터 자격 및 최우선 알림 라우팅',
    benefitCloudDesc: '클라우드 자동 백업 및 다중 기기 알림 동기화',
    continueWithGoogleBtn: 'Google 계정으로 계속',
    continueAsGuestBtn: '지금 안 함, 게스트로 계속 (오프라인 모드)',
    headerLoginTooltip: '계정 상태 및 Google 로그인 (선택 사항)',
    headerSignInLabel: 'Google 로그인',

    telegramSectionTitle: '2. 텔레그램 봇 연동 (Telegram Bot)',
    telegramOnlineBadge: '● 24/7 온라인',
    telegramBotName: '실시간 알림 발송 봇',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: '텔레그램으로 24시간 연중무휴 즉각적인 가격 알림 전송',
    telegramStep1: '텔레그램에서 @aisocialfeedbot 검색 후 /start 를 전송하세요.',
    telegramStep2: '아래에 텔레그램 Chat ID 또는 유저네임을 입력하고 테스트 발송을 누르세요.',
    telegramInputLabel: '텔레그램 Chat ID 또는 유저네임:',
    telegramInputPlaceholder: '@내유저네임 또는 123456789',
    telegramTestBtn: '텔레그램 테스트',
    telegramTestingBtn: '전송 중...',
    telegramEmptyChatIdToast: '먼저 텔레그램 Chat ID를 입력해주세요.',
    telegramTestSuccessToast: '✅ 텔레그램으로 테스트 메시지가 성공적으로 전송되었습니다.',
    telegramTestErrorToast: '⚠️ 텔레그램 메시지 전송 중 오류가 발생했습니다.',
    telegramServerErrorToast: '⚠️ 텔레그램 서버 연결 오류입니다.',
    adminTestTelegramBtn: '텔레그램 테스트',
  },

  // 8. کوردی سۆرانی (Kurdish Sorani)
  ku: {
    loginSectionTitle: '١. هەژماری بەکارهێنەر و چوونەژوورەوە (Login)',
    vipActiveBadge: '👑 VIP چالاکە',
    guestUserTitle: 'بەکارهێنەری میوان (Guest Mode)',
    optionalBadge: 'ئارەزوومەندانە',
    premiumBadge: 'PREMIUM',
    loginSubGuest: 'چوونەژوورەوە بۆ پاشەکەوتی هەوری و هاوکاتکردنی ئامێرەکان',
    signOutBtn: 'چوونەدەرەوە لە هەژمار',
    signInBtn: 'چوونەژوورەوە لە ڕێگەی گووگڵ',
    signedOutToast: 'لە هەژماری گووگڵ چوویتەدەرەوە.',
    signedInToast: '🎉 بە سەرکەوتوویی بەستراوە بە هەژماری گووگڵ (ئەندامی تایبەت)!',

    googleModalTitle: 'چوونەژوورەوە لە ڕێگەی گووگڵ',
    googleModalSubtitle: 'هەژماری بەکارهێنەر و دۆخی بەشداری پریمیۆم',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ هەژمارەکەت بەستراوەتەوە؛ لە وەشانەکانی داهاتوودا هەموو تایبەتمەندییە هەورییەکان بێ بەرامەر چالاک دەبن.',
    signOutGoogleModalBtn: 'چوونەدەرەوە لە گووگڵ',
    closeBtn: 'داخستن',
    modalIntro: 'بەستنەوە بە گووگڵ بە تەواوی ئارەزوومەندانەیە. بەبێ چوونەژوورەوەش دەتوانیت کار بکەیت. بە بەستنەوەی گووگڵ:',
    benefitVipDesc: 'ئەندامێتی VIP هەمیشەیی پێشەنگ و وەرگرتنی ئاگادارییە پێشینەدارەکان',
    benefitCloudDesc: 'پاشەکەوتکردنی هەوری و هاوکاتکردنی ئۆتۆماتیکی ئاگادارییەکان لەنێوان ئامێرەکان',
    continueWithGoogleBtn: 'بەردەوامبوون بە هەژماری گووگڵ',
    continueAsGuestBtn: 'ئێستا نا، بەردەوامبوون وەک میوان (ئۆفلاین)',
    headerLoginTooltip: 'دۆخی هەژمار و چوونەژوورەوەی گووگڵ (ئارەزوومەندانە)',
    headerSignInLabel: 'چوونەژوورەوە بە گووگڵ',

    telegramSectionTitle: '٢. بەستنەوە بە بۆتی تێلێگرام (Telegram Bot)',
    telegramOnlineBadge: '● ئۆنلاین ٢٤/٧',
    telegramBotName: 'بۆتی ئۆنلاینی ناردنی ئاگادارییەکان',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: 'ناردنی خێرای ئاگادارییەکان بۆ سەر تێلێگرام بە شێوەی ٢٤ کاتژمێری',
    telegramStep1: 'لە تێلێگرام نامە بۆ بۆتی @aisocialfeedbot بنێرە و دوگمەی /start دابگرە.',
    telegramStep2: 'ژمارەی Chat ID یان ناوی بەکارهێنەری تێلێگرام بنووسە و دوگمەی تاقیکردنەوە دابگرە.',
    telegramInputLabel: 'چات ئایدی یان ناوی بەکارهێنەری تێلێگرام:',
    telegramInputPlaceholder: '@MyUsername یان 123456789',
    telegramTestBtn: 'تاقیکردنەوەی تێلێگرام',
    telegramTestingBtn: 'لە ناردندایە...',
    telegramEmptyChatIdToast: 'تکایە سەرەتا چات ئایدی تێلێگرام بنووسە.',
    telegramTestSuccessToast: '✅ پەیامی تاقیکردنەوە بە سەرکەوتوویی بۆ تێلێگرام نێردرا.',
    telegramTestErrorToast: '⚠️ هەڵە لە ناردنی پەیامی تێلێگرام ڕوویدا.',
    telegramServerErrorToast: '⚠️ هەڵە لە پەیوەندی لەگەڵ سێرڤەری تێلێگرام.',
    adminTestTelegramBtn: 'تاقیکردنەوەی تێلێگرام',
  },

  // 9. العربية (Arabic / عربی)
  ar: {
    loginSectionTitle: '١. حساب المستخدم وتسجيل الدخول (Login)',
    vipActiveBadge: '👑 عضوية VIP نشطة',
    guestUserTitle: 'وضع الزائر (Guest Mode)',
    optionalBadge: 'اختياري',
    premiumBadge: 'PREMIUM',
    loginSubGuest: 'تسجيل الدخول للمزامنة السحابية والنسخ الاحتياطي متعدد الأجهزة',
    signOutBtn: 'تسجيل الخروج',
    signInBtn: 'تسجيل الدخول عبر Google',
    signedOutToast: 'تم تسجيل الخروج من حساب Google بنجاح.',
    signedInToast: '🎉 تم الاتصال بحساب Google بنجاح (عضوية VIP)!',

    googleModalTitle: 'تسجيل الدخول بحساب Google',
    googleModalSubtitle: 'حساب المستخدم وحالة العضوية المميزة',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ حسابك متصل الآن؛ في التحديثات القادمة ستعمل المزامنة السحابية والتنبيهات المتقدمة مجاناً دون تكلفة إضافية.',
    signOutGoogleModalBtn: 'تسجيل الخروج من Google',
    closeBtn: 'إغلاق',
    modalIntro: 'الاتصال بحساب Google اختياري تماماً. يمكنك استخدام كافة ميزات التطبيق دون تسجيل دخول. عند تسجيل الدخول:',
    benefitVipDesc: 'عضوية VIP مبكرة مدى الحياة وإشعارات تنبيهية ذات أولوية قصوى',
    benefitCloudDesc: 'نسخ احتياطي سحابي ومزامنة تلقائية للتنبيهات بين كافة أجهزتك',
    continueWithGoogleBtn: 'المتابعة باستخدام حساب Google',
    continueAsGuestBtn: 'ليس الآن، المتابعة كزائر (وضع غير متصل)',
    headerLoginTooltip: 'حالة الحساب وتسجيل الدخول عبر Google (اختياري)',
    headerSignInLabel: 'دخول Google',

    telegramSectionTitle: '٢. ربط بوت تيليجرام (Telegram Bot)',
    telegramOnlineBadge: '● متصل 24/7',
    telegramBotName: 'بوت إرسال التنبيهات الفورية',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: 'إرسال التنبيهات على مدار 24 ساعة مباشرة وسريعاً إلى تيليجرام',
    telegramStep1: 'في تطبيق تيليجرام، افتح البوت @aisocialfeedbot واضغط /start.',
    telegramStep2: 'أدخل معرف المحادثة (Chat ID) أو اسم المستخدم أدناه واضغط زر التجربة.',
    telegramInputLabel: 'معرف تيليجرام (Telegram Chat ID أو اسم المستخدم):',
    telegramInputPlaceholder: '@MyTelegramUser أو 123456789',
    telegramTestBtn: 'تجربة تيليجرام',
    telegramTestingBtn: 'جاري الإرسال...',
    telegramEmptyChatIdToast: 'يرجى إدخال معرف محادثة تيليجرام أولاً.',
    telegramTestSuccessToast: '✅ تم إرسال رسالة الاختبار إلى تيليجرام بنجاح.',
    telegramTestErrorToast: '⚠️ حدث خطأ أثناء إرسال رسالة تيليجرام.',
    telegramServerErrorToast: '⚠️ خطأ في الاتصال بخادم تيليجرام.',
    adminTestTelegramBtn: 'تجربة إرسال تيليجرام',
  },

  // 10. Türkçe (Turkish / ترکی)
  tr: {
    loginSectionTitle: '1. Kullanıcı Hesabı & Giriş (Login)',
    vipActiveBadge: '👑 VIP Aktif',
    guestUserTitle: 'Misafir Modu (Guest Mode)',
    optionalBadge: 'İsteğe Bağlı',
    premiumBadge: 'PREMIUM',
    loginSubGuest: 'Bulut yedekleme ve cihazlar arası senkronizasyon için giriş yapın',
    signOutBtn: 'Çıkış Yap',
    signInBtn: 'Google ile Giriş Yap',
    signedOutToast: 'Google hesabından çıkış yapıldı.',
    signedInToast: '🎉 Google hesabına başarıyla bağlanıldı (VIP Üye)!',

    googleModalTitle: 'Google Hesabı ile Giriş Yap',
    googleModalSubtitle: 'Kullanıcı hesabı ve Premium üyelik durumu',
    vipEarlyAdopterBadge: 'PREMIUM EARLY ADOPTER',
    vipActiveDesc: '✨ Hesabınız bağlandı; bulut yedekleme ve gelişmiş izleme ek ücret olmadan aktif.',
    signOutGoogleModalBtn: 'Google Hesabından Çıkış Yap',
    closeBtn: 'Kapat',
    modalIntro: 'Google hesabıyla bağlanmak tamamen isteğe bağlıdır. Giriş yapmadan da tüm özellikleri kullanabilirsiniz. Giriş yaptığınızda:',
    benefitVipDesc: 'Ömür boyu VIP Erken Benimseyen statüsü ve öncelikli bildirim yönlendirmesi',
    benefitCloudDesc: 'Bulut yedekleme ve tüm cihazlarınız arasında otomatik alarm senkronizasyonu',
    continueWithGoogleBtn: 'Google Hesabı ile Devam Et',
    continueAsGuestBtn: 'Şimdi Değil, Misafir Olarak Devam Et (Çevrimdışı)',
    headerLoginTooltip: 'Hesap durumu ve Google ile Giriş (İsteğe Bağlı)',
    headerSignInLabel: 'Google Girişi',

    telegramSectionTitle: '2. Telegram Bot Entegrasyonu',
    telegramOnlineBadge: '● 7/24 Çevrimiçi',
    telegramBotName: 'Çevrimiçi Alarm Bildirim Botu',
    telegramBotHandle: '@aisocialfeedbot',
    telegramBotSubtitle: 'Telegram hesabınıza 7/24 anlık ve kesintisiz fiyat alarmları',
    telegramStep1: 'Telegram\'da @aisocialfeedbot botunu açın ve /start komutunu gönderin.',
    telegramStep2: 'Aşağıya Telegram Sohbet Kimliğinizi (Chat ID) veya kullanıcı adınızı girip test edin.',
    telegramInputLabel: 'Telegram Sohbet Kimliği (Chat ID) veya Kullanıcı Adı:',
    telegramInputPlaceholder: '@KullaniciAdim veya 123456789',
    telegramTestBtn: 'Telegram\'ı Test Et',
    telegramTestingBtn: 'Gönderiliyor...',
    telegramEmptyChatIdToast: 'Lütfen önce Telegram Sohbet Kimliğinizi (Chat ID) girin.',
    telegramTestSuccessToast: '✅ Test mesajı Telegram\'a başarıyla gönderildi.',
    telegramTestErrorToast: '⚠️ Telegram mesajı gönderilirken hata oluştu.',
    telegramServerErrorToast: '⚠️ Telegram sunucusuna bağlanırken hata oluştu.',
    adminTestTelegramBtn: 'Telegram Testi',
  },
};

export const getLoginTelegramI18n = (lang: string): LoginTelegramTranslations => {
  return LOGIN_TELEGRAM_I18N[lang] || LOGIN_TELEGRAM_I18N.fa;
};

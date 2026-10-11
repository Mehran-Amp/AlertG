<?php
/**
 * SignalAlert - Iran Market Data Bridge & Proxy (v2.5.0)
 * Host: https://aegkala.com/market-bridge.php
 *
 * Config: env SIGNALALERT_BRIDGE_TOKEN, or market-bridge.config.php (one folder above, or next to this file):
 *   <?php return [
 *     'token'         => '...',                       // required, >= 16 chars
 *     'cache_dir'     => '/private/path',             // optional
 *     'tse_days'      => [6, 0, 1, 2, 3],             // optional, PHP "w": Sat=6 ... Wed=3
 *     'tse_open'      => '09:00',                     // optional, Tehran time
 *     'tse_close'     => '12:30',                     // optional
 *     'tse_holidays'  => ['2026-10-12'],              // optional, Gregorian Y-m-d, edit by hand
 *   ];
 */

const BRIDGE_VERSION     = '2.5.0';
const CACHE_TTL          = 60;        // seconds
const REFRESH_MIN_AGE    = 10;        // ?refresh=1 ignored if cache is younger
const HTTP_TIMEOUT       = 3;         // exchanges
const TSE_TIMEOUT        = 8;         // TSETMC market watch is a big response
const TOTAL_BUDGET       = 14;        // seconds, only used when curl_multi is unavailable
const LAST_KNOWN_MAX_AGE = 1209600;   // 14 days

define('REQ_START', microtime(true));

@ini_set('display_errors', '0');
error_reporting(E_ALL);
@ini_set('log_errors', '1');
@ini_set('serialize_precision', '-1'); // clean floats (150.9, not 150.90000000000001)
@ini_set('default_charset', 'UTF-8');
if (function_exists('mb_internal_encoding')) {
    @mb_internal_encoding('UTF-8');
}
@set_time_limit(30);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Bridge-Version: ' . BRIDGE_VERSION);

function respond(array $payload, int $code = 200): void {
    http_response_code($code);
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

// ---------------------------------------------------------------- config ---
$cfg = [];
foreach ([dirname(__DIR__), __DIR__] as $dir) {
    $cfgFile = $dir . '/market-bridge.config.php';
    if (is_file($cfgFile)) {
        $loaded = @include $cfgFile;
        if (is_array($loaded)) { $cfg = $loaded; break; }
    }
}
$secret = getenv('SIGNALALERT_BRIDGE_TOKEN') ?: ($cfg['token'] ?? '');
$secret = is_string($secret) ? trim($secret) : '';
if (strlen($secret) < 16) {
    error_log('[market-bridge] secret token not configured');
    respond(['success' => false, 'message' => 'Server configuration error: Bridge token not set or invalid.'], 500);
}
$cacheDir = $cfg['cache_dir'] ?? (sys_get_temp_dir() . '/sigbridge_' . substr(hash('sha256', __FILE__), 0, 12));
if (!is_dir($cacheDir) && !@mkdir($cacheDir, 0700, true) && !is_dir($cacheDir)) {
    error_log('[market-bridge] cannot create cache dir: ' . $cacheDir);
    respond(['success' => false, 'message' => 'Server configuration error: cache directory.'], 500);
}
$cacheFile     = $cacheDir . '/market_cache_v8.json';
$lastKnownFile = $cacheDir . '/last_known_v2.json';
$lockFile      = $cacheDir . '/market_cache.lock';

$tseDays     = is_array($cfg['tse_days'] ?? null) ? array_map('intval', $cfg['tse_days']) : [6, 0, 1, 2, 3];
$tseOpen     = is_string($cfg['tse_open'] ?? null) ? $cfg['tse_open'] : '09:00';
$tseClose    = is_string($cfg['tse_close'] ?? null) ? $cfg['tse_close'] : '12:30';
$tseHolidays = is_array($cfg['tse_holidays'] ?? null) ? $cfg['tse_holidays'] : [];

// ------------------------------------------------------------------ auth ---
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'GET') {
    header('Allow: GET');
    respond(['success' => false, 'message' => 'Method Not Allowed. Only GET requests are accepted.'], 405);
}
$authHeader = $_SERVER['HTTP_AUTHORIZATION'] ?? ($_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '');
$provided = preg_match('/^Bearer\s+(\S+)\s*$/i', $authHeader, $m) ? $m[1] : '';
if ($provided === '' || !hash_equals($secret, $provided)) {
    respond(['success' => false, 'message' => 'Unauthorized'], 401);
}

// ----------------------------------------------------------------- cache ---
function readJsonFile(string $file): ?array {
    $raw = @file_get_contents($file);
    if (!$raw) return null;
    $d = json_decode($raw, true);
    return is_array($d) ? $d : null;
}
function readCache(string $file): ?array {
    $d = readJsonFile($file);
    return ($d && isset($d['timestamp'], $d['data'])) ? $d : null;
}
function writeJsonAtomic(string $file, array $data): bool {
    $tmp = $file . '.' . getmypid() . '.tmp';
    if (@file_put_contents($tmp, json_encode($data, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE)) === false) return false;
    return @rename($tmp, $file);
}
function serveCache(array $c, int $now, bool $stale = false): void {
    $c['cached'] = true;
    $c['stale'] = $stale;
    $c['age_seconds'] = $now - $c['timestamp'];
    if ($stale && isset($c['data']) && is_array($c['data'])) {
        foreach ($c['data'] as $k => $v) {
            if (is_array($v)) $c['data'][$k]['alert_eligible'] = false;
        }
    }
    respond($c);
}

$now = time();
$debug = ($_GET['debug'] ?? '') === '1';
$forceRefresh = ($_GET['refresh'] ?? '') === '1';
$cached = readCache($cacheFile);

if (!$debug && $cached) {
    $age = $now - $cached['timestamp'];
    if ($age < CACHE_TTL && !($forceRefresh && $age >= REFRESH_MIN_AGE)) {
        serveCache($cached, $now);
    }
}

// Single refresher: other requests get the (stale) cache instead of stampeding upstreams.
$lock = @fopen($lockFile, 'c');
if ($lock && !flock($lock, LOCK_EX | LOCK_NB)) {
    if ($cached) serveCache($cached, $now, true);
    flock($lock, LOCK_EX);
    $cached = readCache($cacheFile);
    if (!$debug && $cached && ($now - $cached['timestamp']) < CACHE_TTL) serveCache($cached, $now);
}

// ------------------------------------------------------------------ HTTP ---
function makeHandle(array $r) {
    $ch = curl_init($r['url']);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => $r['timeout'] ?? HTTP_TIMEOUT,
        CURLOPT_CONNECTTIMEOUT => 2,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_ENCODING       => '',
        CURLOPT_USERAGENT      => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        CURLOPT_HTTPHEADER     => array_merge(
            ['Accept: application/json, text/plain, */*', 'Accept-Language: fa,en-US;q=0.9'],
            $r['headers'] ?? []
        ),
    ]);
    return $ch;
}

function finishResult(string $id, $body, $ch): array {
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    $ok = ($code === 200 && is_string($body) && $body !== '');
    if (!$ok) error_log("[market-bridge] upstream '$id' failed: http=$code err=$err");
    return ['body' => $ok ? $body : null, 'code' => $code, 'bytes' => is_string($body) ? strlen($body) : 0, 'err' => $err];
}

/** @return array<string,array{body:?string,code:int,bytes:int,err:string}> */
function fetchMulti(array $requests): array {
    $out = [];
    if (!function_exists('curl_init')) {
        error_log('[market-bridge] curl extension missing');
        foreach ($requests as $id => $_) $out[$id] = ['body' => null, 'code' => 0, 'bytes' => 0, 'err' => 'no curl'];
        return $out;
    }

    // Hosts without curl_multi: sequential, with a total time budget.
    if (!function_exists('curl_multi_init')) {
        foreach ($requests as $id => $r) {
            if (microtime(true) - REQ_START > TOTAL_BUDGET) {
                error_log("[market-bridge] upstream '$id' skipped: time budget exceeded");
                $out[$id] = ['body' => null, 'code' => 0, 'bytes' => 0, 'err' => 'budget'];
                continue;
            }
            $ch = makeHandle($r);
            $body = curl_exec($ch);
            $out[$id] = finishResult($id, $body, $ch);
            curl_close($ch);
        }
        return $out;
    }

    $mh = curl_multi_init();
    $handles = [];
    foreach ($requests as $id => $r) {
        $ch = makeHandle($r);
        curl_multi_add_handle($mh, $ch);
        $handles[$id] = $ch;
    }
    do {
        $st = curl_multi_exec($mh, $running);
        if ($running && curl_multi_select($mh, 0.5) === -1) usleep(10000);
    } while ($running && $st === CURLM_OK);

    foreach ($handles as $id => $ch) {
        $out[$id] = finishResult($id, curl_multi_getcontent($ch), $ch);
        curl_multi_remove_handle($mh, $ch);
        curl_close($ch);
    }
    curl_multi_close($mh);
    return $out;
}

// --------------------------------------------------------------- helpers ---
function jsonOf(?string $raw): array {
    $d = $raw ? json_decode($raw, true) : null;
    return is_array($d) ? $d : [];
}
function numPos($v): ?float {
    if (is_string($v)) $v = str_replace(',', '', $v);
    return (is_numeric($v) && (float)$v > 0) ? (float)$v : null;
}
function firstPos(array $arr, array $keys): ?float {
    foreach ($keys as $k) {
        if (isset($arr[$k]) && ($p = numPos($arr[$k])) !== null) return $p;
    }
    return null;
}
/** Normalize Persian/Arabic text so tickers match regardless of ي/ی, ك/ک, spaces, ZWNJ, digits. */
function normFa(string $s): string {
    $s = strtr($s, [
        'ي' => 'ی', 'ى' => 'ی', 'ك' => 'ک', 'ة' => 'ه', 'ۀ' => 'ه',
        'أ' => 'ا', 'إ' => 'ا', 'آ' => 'ا', 'ٱ' => 'ا',
        "\u{200C}" => '', "\u{200F}" => '', "\u{200E}" => '', ' ' => '', "\u{00A0}" => '',
        '۰' => '0', '۱' => '1', '۲' => '2', '۳' => '3', '۴' => '4', '۵' => '5', '۶' => '6', '۷' => '7', '۸' => '8', '۹' => '9',
        '٠' => '0', '١' => '1', '٢' => '2', '٣' => '3', '٤' => '4', '٥' => '5', '٦' => '6', '٧' => '7', '٨' => '8', '٩' => '9',
    ]);
    return (string)preg_replace('/[\x{064B}-\x{065F}\x{0670}]/u', '', $s);
}
function displayFa(string $s): string {
    $s = strtr($s, ['ي' => 'ی', 'ى' => 'ی', 'ك' => 'ک', "\u{200F}" => '', "\u{200E}" => '']);
    $s = (string)preg_replace('/\s+/u', ' ', $s);   // collapse newlines/tabs inside names
    return trim((string)preg_replace('/^[\s\x{200C}]+|[\s\x{200C}]+$/u', '', $s));
}
function faDigits(string $s): string {
    return strtr($s, ['0' => '۰', '1' => '۱', '2' => '۲', '3' => '۳', '4' => '۴', '5' => '۵', '6' => '۶', '7' => '۷', '8' => '۸', '9' => '۹']);
}

/** "امروز ۰۹:۰۰" / "فردا ۰۹:۰۰" / "شنبه ۰۹:۰۰" for a future moment. */
function faWhen(?string $iso, DateTimeImmutable $now): ?string {
    if ($iso === null) return null;
    try {
        $t = new DateTimeImmutable($iso);
    } catch (Exception $e) {
        return null;
    }
    $t = $t->setTimezone($now->getTimezone());
    $names = ['یکشنبه', 'دوشنبه', "سه\u{200C}شنبه", 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه'];
    if ($t->format('Y-m-d') === $now->format('Y-m-d')) {
        $day = 'امروز';
    } elseif ($t->format('Y-m-d') === $now->modify('+1 day')->format('Y-m-d')) {
        $day = 'فردا';
    } else {
        $day = $names[(int)$t->format('w')];
    }
    return $day . ' ' . faDigits($t->format('H:i'));
}

/** Market schedule (no official holiday calendar: use 'tse_holidays' in the config file). */
function tseStatus(DateTimeImmutable $t, array $days, string $open, string $close, array $holidays): array {
    $isOpenDay = function (DateTimeImmutable $d) use ($days, $holidays): bool {
        return in_array((int)$d->format('w'), $days, true) && !in_array($d->format('Y-m-d'), $holidays, true);
    };
    $hm = $t->format('H:i');
    $status = 'closed';
    $reason = null;
    if (!$isOpenDay($t)) {
        $reason = in_array($t->format('Y-m-d'), $holidays, true) ? 'holiday' : 'weekend';
    } elseif ($hm < $open) {
        $reason = 'before_open';
    } elseif ($hm >= $close) {
        $reason = 'after_close';
    } else {
        $status = 'open';
    }
    $next = null;
    if ($status === 'closed') {
        for ($i = 0; $i < 21; $i++) {
            $d = $t->modify("+$i day");
            if (!$isOpenDay($d)) continue;
            $cand = new DateTimeImmutable($d->format('Y-m-d') . " $open:00", $t->getTimezone());
            if ($cand > $t) { $next = $cand; break; }
        }
    }
    return [
        'name_fa'      => 'بورس و فرابورس',
        'status'       => $status,
        'reason'       => $reason,
        'schedule_fa'  => 'شنبه تا چهارشنبه، ' . faDigits($open) . ' تا ' . faDigits($close) . ' (وقت تهران)',
        'next_open'    => $next ? $next->format('c') : null,
        'holiday_aware' => !empty($holidays),
    ];
}

$tz = new DateTimeZone('+03:30'); // Iran has no DST since 2022
$tehranNow = (new DateTimeImmutable('@' . $now))->setTimezone($tz);
$tse = tseStatus($tehranNow, $tseDays, $tseOpen, $tseClose, $tseHolidays);
$tse['next_open_fa'] = faWhen($tse['next_open'] ?? null, $tehranNow);
$tseOpenNow = $tse['status'] === 'open';

// ------------------------------------------------------------- catalogue ---
// [Persian ticker, output key, category]. Tickers that don't exist on TSETMC are simply skipped.
$catalog = [
    // Gold funds
    ['عیار', 'AYAR', 'gold_fund'], ['طلا', 'TALA', 'gold_fund'], ['زر', 'ZAR', 'gold_fund'],
    ['کهربا', 'KAHROBA', 'gold_fund'], ['گوهر', 'GOHAR', 'gold_fund'], ['ناب', 'NAAB', 'gold_fund'],
    ['نفیس', 'NAFIS', 'gold_fund'], ['آلتون', 'ALTUN', 'gold_fund'], ['مثقال', 'MESGHAL_ETF', 'gold_fund'],
    ['جواهر', 'JAVAHER', 'gold_fund'], ['زرفام', 'ZARFAM', 'gold_fund'], ['اطلس', 'ATLAS', 'equity_fund'],
    ['لوتوس', 'LOTUS', 'stock'],
    // Leveraged funds
    ['اهرم', 'AHRAM', 'leveraged_fund'], ['توان', 'TAVAN', 'leveraged_fund'], ['جهش', 'JAHESH', 'leveraged_fund'],
    ['شتاب', 'SHETAB', 'leveraged_fund'], ['موج', 'MOJ', 'leveraged_fund'], ['بیدار', 'BIDAR', 'leveraged_fund'],
    // Equity / index / fixed-income funds
    ['پالایش', 'PALAYESH', 'equity_fund'], ['دارا', 'DARA1', 'equity_fund'], ['فیروزه', 'FIRUZEH', 'equity_fund'],
    ['سرو', 'SERVO', 'equity_fund'], ['تمشک', 'TEMESHK', 'equity_fund'], ['کارآمد', 'KARAMAD', 'fixed_income_fund'],
    // Leading stocks
    ['فولاد', 'FOOLAD', 'stock'], ['فملی', 'FEMELLI', 'stock'], ['فارس', 'FARES', 'stock'],
    ['شپنا', 'SHEPNA', 'stock'], ['شتران', 'SHETRAN', 'stock'], ['وبملت', 'VEBMELAT', 'stock'],
    ['خودرو', 'KHODRO', 'stock'], ['خساپا', 'KHASAPA', 'stock'], ['وبصادر', 'VEBSADER', 'stock'],
    ['وتجارت', 'VETEJARAT', 'stock'], ['شبندر', 'SHABANDAR', 'stock'], ['شپدیس', 'SHEPDIS', 'stock'],
    ['کگل', 'KEGOL', 'stock'], ['کچاد', 'KECHAD', 'stock'], ['فخوز', 'FAKHOOZ', 'stock'],
    ['ومعادن', 'VEMAADEN', 'stock'], ['حتوکا', 'HATOKA', 'stock'], ['اخابر', 'AKHABER', 'stock'],
    ['همراه', 'HAMRAH', 'stock'], ['شستا', 'SHASTA', 'stock'], ['وغدیر', 'VEGHADIR', 'stock'],
    ['وپاسار', 'VEPASAR', 'stock'], ['خگستر', 'KHEGOSTAR', 'stock'], ['فاسمین', 'FASMIN', 'stock'],
    ['زاگرس', 'ZAGROS', 'stock'], ['تاپیکو', 'TAPICO', 'stock'], ['وسپه', 'VESEPAH', 'stock'],
    ['وبانک', 'VEBANK', 'stock'], ['ختور', 'KHATOUR', 'stock'], ['خاور', 'KHAVAR', 'stock'],
    ['شسپا', 'SHESEPA', 'stock'], ['فایرا', 'FAYRA', 'stock'], ['کرمان', 'KERMAN', 'stock'],
    ['شبریز', 'SHABRIZ', 'stock'], ['پارسان', 'PARSAN', 'stock'], ['نوری', 'NOURI', 'stock'],
];
$wanted = [];
foreach ($catalog as [$fa, $key, $cat]) {
    $wanted[normFa($fa)] = ['key' => $key, 'cat' => $cat, 'fa' => $fa];
}

// symbol => [insCode, Persian name]
$indices = [
    'TEDPIX'       => ['32097828799138116', 'شاخص کل بورس'],
    'TEDPIX_EQUAL' => ['67130298613737946', 'شاخص هم‌وزن بورس'],
    'IFX'          => ['43685683301327984', 'شاخص کل فرابورس'],
];

// Last-resort per-instrument codes (verified by search from the host)
$goldFundCodes = [
    'AYAR'    => ['34144395039913458', 'عیار',  'صندوق طلای عیار مفید'],
    'TALA'    => ['46700660505281786', 'طلا',   'صندوق س. کالای پارسیان'],
    'ZAR'     => ['33254899395816171', 'زر',    'صندوق س.کالای امید ثروت ایران'],
    'KAHROBA' => ['25559236668122210', 'کهربا', 'صندوق س. کالای کهربا'],
    'GOHAR'   => ['12390706505809150', 'گوهر',  'صندوق س.کالای کیان'],
];

// -------------------------------------------------------------- requests ---
$tseHdr = ['Referer: https://main.tsetmc.com/', 'Origin: https://main.tsetmc.com'];
$mwBase = 'https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch?';
$mwAll  = $mwBase . 'market=0&industrialGroup=&' . implode('&', array_map(
    function ($i) { return 'paperTypes%5B' . $i . '%5D=' . ($i + 1); }, range(0, 8)
)) . '&showTraded=false&withBestLimits=true&hEven=0&RefID=0';
$mwAlt  = $mwBase . 'market=1&industrialGroup=&paperTypes%5B0%5D=8&showTraded=false&withBestLimits=true&hEven=0&RefID=0';

$raw = fetchMulti([
    'Nobitex'    => ['url' => 'https://apiv2.nobitex.ir/market/stats', 'headers' => ['Referer: https://nobitex.ir/']],
    'Wallex'     => ['url' => 'https://api.wallex.ir/v1/markets'],
    'Tetherland' => ['url' => 'https://api.tetherland.com/currencies'],
    'Tabdeal'    => ['url' => 'https://api1.tabdeal.org/r/api/v1/depth?symbol=USDTIRT'],
    'TSETMC MarketWatch' => ['url' => $mwAll, 'headers' => $tseHdr, 'timeout' => TSE_TIMEOUT],
    'TSETMC Overview 1'  => ['url' => 'https://cdn.tsetmc.com/api/MarketData/GetMarketOverview/1', 'headers' => $tseHdr, 'timeout' => 5],
    'TSETMC Overview 2'  => ['url' => 'https://cdn.tsetmc.com/api/MarketData/GetMarketOverview/2', 'headers' => $tseHdr, 'timeout' => 5],
]);

// --------------------------------------------------------------- parsing ---
$rates = [];
$failedSources = [];
$dbg = [];
$add = function (string $sym, float $price, string $source, string $market) use (&$rates): void {
    $rates[$sym] = ['price' => $price, 'unit' => 'تومان', 'source' => $source, 'market' => $market];
};

// --- Crypto exchanges
$nobitex = jsonOf($raw['Nobitex']['body']);
if (isset($nobitex['stats']) && is_array($nobitex['stats'])) {
    $s = $nobitex['stats'];
    $irtOrRls = function (string $base) use ($s): ?float {
        $v = numPos($s["$base-irt"]['latest'] ?? null);
        if ($v !== null) return $v;
        $r = numPos($s["$base-rls"]['latest'] ?? null);
        return $r !== null ? $r / 10.0 : null;
    };
    if (($v = $irtOrRls('usdt')) !== null) {
        $add('USDT_NOBITEX', $v, 'Nobitex', 'crypto');
        $add('USD_TMN', $v, 'Nobitex Tether', 'crypto');
    }
    if (($v = $irtOrRls('pm')) !== null) $add('GOLD_NOBITEX', $v, 'Nobitex Gold', 'crypto');
    if (($v = $irtOrRls('btc')) !== null) $add('BTC_NOBITEX', $v, 'Nobitex', 'crypto');
    if (($v = $irtOrRls('eth')) !== null) $add('ETH_NOBITEX', $v, 'Nobitex', 'crypto');
} else {
    $failedSources[] = $raw['Nobitex']['body'] === null ? 'Nobitex' : 'Nobitex (Invalid structure)';
}

$wallex = jsonOf($raw['Wallex']['body']);
if ($raw['Wallex']['body'] === null) {
    $failedSources[] = 'Wallex';
} else {
    $sy = $wallex['result']['symbols'] ?? [];
    foreach (['USDT_WALLEX' => 'USDTTMN', 'GOLD_WALLEX' => 'PAXGTMN', 'BTC_WALLEX' => 'BTCTMN', 'ETH_WALLEX' => 'ETHTMN'] as $sym => $pair) {
        if (($v = numPos($sy[$pair]['stats']['lastPrice'] ?? null)) !== null) $add($sym, $v, 'Wallex', 'crypto');
    }
}

if ($raw['Tetherland']['body'] === null) {
    $failedSources[] = 'Tetherland';
} elseif (($v = numPos(jsonOf($raw['Tetherland']['body'])['data']['currencies']['USDT']['price'] ?? null)) !== null) {
    $add('USDT_TETHERLAND', $v, 'Tetherland', 'crypto');
}

if ($raw['Tabdeal']['body'] === null) {
    $failedSources[] = 'Tabdeal';
} elseif (($v = numPos(jsonOf($raw['Tabdeal']['body'])['bids'][0][0] ?? null)) !== null) {
    $add('USDT_TABDEAL', $v, 'Tabdeal', 'crypto');
}

// --- TSETMC market watch (one request for all stocks and funds)
function mwRecords(array $j): array {
    foreach (['marketwatch', 'marketWatch', 'data'] as $k) {
        if (isset($j[$k]) && is_array($j[$k])) return $j[$k];
    }
    return (isset($j[0]) && is_array($j[0])) ? $j : [];
}

function sLen(string $s): int {
    return function_exists('mb_strlen') ? mb_strlen($s) : strlen($s);
}
function sCut(string $s, int $n): string {
    return function_exists('mb_substr') ? mb_substr($s, 0, $n) : substr($s, 0, $n);
}

/** Find the wanted ticker of a market-watch record; TSETMC uses different key names across API versions. */
function recordTicker(array $r, array $wanted): ?string {
    foreach (['lVal18AFC', 'lva'] as $k) {
        if (isset($r[$k]) && is_string($r[$k])) {
            $n = normFa($r[$k]);
            if (isset($wanted[$n])) return $n;
        }
    }
    foreach ($r as $v) {   // unknown layout: any short string field that equals a wanted ticker
        if (is_string($v) && $v !== '' && sLen($v) <= 14) {
            $n = normFa($v);
            if (isset($wanted[$n])) return $n;
        }
    }
    return null;
}

function recordName(array $r): string {
    $best = '';
    foreach (['lVal30', 'lvc', 'lva'] as $k) {
        if (isset($r[$k]) && is_string($r[$k]) && sLen($r[$k]) > sLen($best)) $best = $r[$k];
    }
    return displayFa($best);
}

function parseMarketWatch(array $records, array $wanted, bool $marketOpen): array {
    $found = [];
    foreach ($records as $r) {
        if (!is_array($r)) continue;
        $norm = recordTicker($r, $wanted);
        if ($norm === null || isset($found[$wanted[$norm]['key']])) continue;
        $w = $wanted[$norm];
        // This API returns the same data under short names (pdv, pcl, py, qtj, ztt, ...); long names may be 0.
        $last  = firstPos($r, ['pDrCotVal', 'pdv']);     // last trade
        $close = firstPos($r, ['pClosing', 'pcl']);      // closing (final) price
        $prev  = firstPos($r, ['priceYesterday', 'py']); // yesterday's final price
        $p = $last ?? $close ?? $prev;
        if ($p === null) continue;
        $e = [
            'price'       => $p / 10.0,
            'unit'        => 'تومان',
            'source'      => 'TSETMC',
            'market'      => 'tse',
            'category'    => $w['cat'],
            'ticker'      => $w['fa'],
            'name'        => recordName($r),
            'market_open' => $marketOpen,
        ];
        $vol = firstPos($r, ['qTotTran5J', 'qtj']);
        $trd = firstPos($r, ['zTotTran', 'ztt']);
        $traded = ($vol !== null || $trd !== null);   // false = no trade yet today: price is the last (older) trade
        $e['traded_today'] = $traded;
        if ($close !== null) $e['close'] = $close / 10.0;
        if ($prev !== null) {
            $e['prev_close'] = $prev / 10.0;
            if ($traded) $e['change_pct'] = round(($p / $prev - 1) * 100, 2);
        }
        if (($hi = firstPos($r, ['pmx', 'priceMax'])) !== null) $e['high'] = $hi / 10.0;
        if (($lo = firstPos($r, ['pmn', 'priceMin'])) !== null) $e['low'] = $lo / 10.0;
        if ($vol !== null) $e['volume'] = $vol;
        if ($trd !== null) $e['trades'] = (int)$trd;
        if (($val = firstPos($r, ['qTotCap', 'qtc'])) !== null) $e['value'] = $val / 10.0;
        $found[$w['key']] = $e;
    }
    return $found;
}

$tseFresh = [];
$mwRecs = [];
if ($raw['TSETMC MarketWatch']['body'] === null) {
    $failedSources[] = 'TSETMC MarketWatch';
} else {
    $mwRecs = mwRecords(jsonOf($raw['TSETMC MarketWatch']['body']));
    $tseFresh = parseMarketWatch($mwRecs, $wanted, $tseOpenNow);
}
$dbg['marketwatch_primary'] = [
    'http' => $raw['TSETMC MarketWatch']['code'], 'bytes' => $raw['TSETMC MarketWatch']['bytes'],
    'records' => count($mwRecs), 'matched' => count($tseFresh),
    'sample_keys' => $mwRecs ? array_keys((array)reset($mwRecs)) : [],
];
if ($debug && $mwRecs) {
    $trim = function ($rec) {
        return array_map(function ($v) { return is_string($v) ? sCut($v, 40) : $v; }, (array)$rec);
    };
    $dbg['marketwatch_primary']['sample_record'] = $trim(reset($mwRecs));
    foreach ($mwRecs as $rec) {
        if (is_array($rec) && recordTicker($rec, ['فولاد' => 1, normFa('فولاد') => 1]) !== null) {
            $dbg['marketwatch_primary']['foolad_record'] = $trim($rec);
            break;
        }
    }
}

// ?debug=1&find=<text>: search market-watch tickers/names (URL-encode Persian text).
if ($debug && $mwRecs && isset($_GET['find']) && is_string($_GET['find']) && $_GET['find'] !== '') {
    $needle = normFa($_GET['find']);
    $hits = [];
    foreach ($mwRecs as $rec) {
        if (!is_array($rec)) continue;
        $a = (string)($rec['lva'] ?? ($rec['lVal18AFC'] ?? ''));
        $b = (string)($rec['lvc'] ?? ($rec['lVal30'] ?? ''));
        if (strpos(normFa($a), $needle) !== false || strpos(normFa($b), $needle) !== false) {
            $hits[] = [displayFa($a), displayFa($b), (string)($rec['insCode'] ?? ''), $rec['py'] ?? null, $rec['pdv'] ?? null];
            if (count($hits) >= 40) break;
        }
    }
    $dbg['find'] = $hits;
}

// Second chance: alternative market-watch query, then per-fund calls.
if (!$tseFresh && !$mwRecs) {
    $r2 = fetchMulti(['alt' => ['url' => $mwAlt, 'headers' => $tseHdr, 'timeout' => TSE_TIMEOUT]])['alt'];
    $recs2 = $r2['body'] !== null ? mwRecords(jsonOf($r2['body'])) : [];
    $tseFresh = parseMarketWatch($recs2, $wanted, $tseOpenNow);
    $dbg['marketwatch_alt'] = ['http' => $r2['code'], 'bytes' => $r2['bytes'], 'records' => count($recs2), 'matched' => count($tseFresh)];
}
if (!$tseFresh) {
    $req = [];
    foreach ($goldFundCodes as $sym => [$code]) {
        $req[$sym] = ['url' => "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/$code", 'headers' => $tseHdr, 'timeout' => 4];
    }
    $fund = fetchMulti($req);
    foreach ($fund as $sym => $res) {
        $info = jsonOf($res['body'])['closingPriceInfo'] ?? [];
        $p = is_array($info) ? firstPos($info, ['pDrCotVal', 'pClosing']) : null;
        if ($p !== null) {
            $tseFresh[$sym] = [
                'price' => $p / 10.0, 'unit' => 'تومان', 'source' => 'TSETMC', 'market' => 'tse',
                'category' => 'gold_fund', 'ticker' => $goldFundCodes[$sym][1], 'name' => $goldFundCodes[$sym][2],
                'market_open' => $tseOpenNow,
            ];
        }
    }
    $dbg['gold_fund_fallback'] = ['matched' => count($tseFresh), 'http' => array_map(function ($x) { return $x['code']; }, $fund)];
}

// --- TSETMC indices: market overview (live), then daily history as a fallback
$valueKeys = ['xNivInuClMresIbs', 'xNivInuPbMresIbs', 'xNivInIdxPb', 'xNivInIdx', 'indexValue', 'lastValue'];
$ovOf = function (string $id) use ($raw, &$failedSources): array {
    if ($raw[$id]['body'] === null) { $failedSources[] = $id; return []; }
    $o = jsonOf($raw[$id]['body'])['marketOverview'] ?? [];
    return is_array($o) ? $o : [];
};
$ov1 = $ovOf('TSETMC Overview 1');   // Tehran Stock Exchange
$ov2 = $ovOf('TSETMC Overview 2');   // Iran Fara Bourse
$fromOverview = function (array $ov, string $valKey, string $chgKey, string $sym) use (&$tseFresh, $indices, $tseOpenNow): void {
    if (isset($tseFresh[$sym])) return;
    $v = numPos($ov[$valKey] ?? null);
    if ($v === null) return;
    $e = ['price' => $v, 'unit' => 'واحد', 'source' => 'TSETMC', 'market' => 'tse', 'category' => 'index',
          'name' => $indices[$sym][1], 'market_open' => $tseOpenNow, 'daily_close' => !$tseOpenNow];
    if (isset($ov[$chgKey]) && is_numeric($ov[$chgKey])) {
        $chg = (float)$ov[$chgKey];
        $prev = $v - $chg;
        $e['change'] = $chg;
        if ($prev > 0) {
            $e['prev_close'] = round($prev, 2);
            $e['change_pct'] = round($chg / $prev * 100, 2);
        }
    }
    $tseFresh[$sym] = $e;
};
$fromOverview($ov1, 'indexLastValue', 'indexChange', 'TEDPIX');
$fromOverview($ov1, 'indexEqualWeightedLastValue', 'indexEqualWeightedChange', 'TEDPIX_EQUAL');
$fromOverview($ov2, 'indexLastValue', 'indexChange', 'IFX');
if (isset($ov1['marketStateTitle']) && is_string($ov1['marketStateTitle'])) {
    $tse['exchange_state_fa'] = displayFa($ov1['marketStateTitle']);   // as reported by TSETMC
}
$dEven = (int)($ov1['marketActivityDEven'] ?? 0);
if ($dEven >= 20000101 && $dEven <= 29991231) {
    $hEven = str_pad((string)(int)($ov1['marketActivityHEven'] ?? 0), 6, '0', STR_PAD_LEFT);
    $tse['last_activity'] = [   // date/time of the last market activity (Gregorian, Tehran time)
        'date' => substr((string)$dEven, 0, 4) . '-' . substr((string)$dEven, 4, 2) . '-' . substr((string)$dEven, 6, 2),
        'time' => substr($hEven, 0, 2) . ':' . substr($hEven, 2, 2) . ':' . substr($hEven, 4, 2),
    ];
}
$dbg['overview'] = [
    '1' => ['http' => $raw['TSETMC Overview 1']['code'], 'sample' => $raw['TSETMC Overview 1']['body'] !== null ? sCut($raw['TSETMC Overview 1']['body'], 500) : null],
    '2' => ['http' => $raw['TSETMC Overview 2']['code'], 'sample' => $raw['TSETMC Overview 2']['body'] !== null ? sCut($raw['TSETMC Overview 2']['body'], 500) : null],
];

// Indices still missing: daily history (last close).
if (array_diff(array_keys($indices), array_keys($tseFresh)) || $debug) {
    $req = [];
    foreach ($indices as $sym => [$code]) {
        if (!isset($tseFresh[$sym])) {
            $req["hist_$sym"] = ['url' => "https://cdn.tsetmc.com/api/Index/GetIndexB2History/$code", 'headers' => $tseHdr, 'timeout' => 5];
        }
    }
    $hist = $req ? fetchMulti($req) : [];
    foreach ($indices as $sym => [$code, $nameFa]) {
        $res = $hist["hist_$sym"] ?? null;
        if ($res === null) continue;
        $j = jsonOf($res['body']);
        $recs = [];
        foreach (['indexB2', 'indexB1', 'data'] as $k) {
            if (isset($j[$k]) && is_array($j[$k])) { $recs = $j[$k]; break; }
        }
        $best = null;
        $bestD = -1;
        $second = null;
        $secondD = -1;
        foreach ($recs as $r) {
            if (!is_array($r)) continue;
            $d = (int)($r['dEven'] ?? 0);
            if ($d >= $bestD) {
                $second = $best; $secondD = $bestD;
                $best = $r; $bestD = $d;
            } elseif ($d >= $secondD) {
                $second = $r; $secondD = $d;
            }
        }
        if ($debug) {
            $dbg['index_history'][$sym] = ['http' => $res['code'], 'bytes' => $res['bytes'], 'records' => count($recs)];
        }
        $v = $best ? firstPos($best, $valueKeys) : null;
        if ($v === null) continue;
        $e = ['price' => $v, 'unit' => 'واحد', 'source' => 'TSETMC (daily close)', 'market' => 'tse',
              'category' => 'index', 'name' => $nameFa, 'market_open' => $tseOpenNow, 'daily_close' => true,
              'data_date' => $bestD];
        $pv = $second ? firstPos($second, $valueKeys) : null;
        if ($pv !== null) {
            $e['prev_close'] = $pv;
            $e['change_pct'] = round(($v / $pv - 1) * 100, 2);
        }
        $tseFresh[$sym] = $e;
    }
}

foreach ($tseFresh as $sym => $e) {
    $rates[$sym] = $e;
}

// Nothing fresh at all: last cached answer (flagged stale), or 503.
if (!$rates) {
    if ($cached && !$debug) serveCache($cached, $now, true);
    respond(['success' => false, 'message' => 'All upstream market sources are currently unavailable.', 'failed_sources' => $failedSources], 503);
}

// --- Every supported symbol always gets a row (never hidden), with a state the app can display.
$cryptoKeys = ['USDT_NOBITEX', 'USD_TMN', 'GOLD_NOBITEX', 'BTC_NOBITEX', 'ETH_NOBITEX', 'USDT_WALLEX', 'GOLD_WALLEX',
               'BTC_WALLEX', 'ETH_WALLEX', 'USDT_TETHERLAND', 'USDT_TABDEAL'];
$supported = [];
foreach ($cryptoKeys as $k) {
    $supported[$k] = ['market' => 'crypto', 'unit' => 'تومان'];
}
foreach ($catalog as [$fa, $key, $cat]) {
    $supported[$key] = ['market' => 'tse', 'unit' => 'تومان', 'category' => $cat, 'ticker' => $fa];
}
foreach ($indices as $k => [, $nameFa]) {
    $supported[$k] = ['market' => 'tse', 'unit' => 'واحد', 'category' => 'index', 'name' => $nameFa];
}

// Last known values for symbols that have no fresh value right now.
$lastKnown = readJsonFile($lastKnownFile) ?: [];
foreach ($supported as $sym => $meta) {
    if (isset($rates[$sym])) continue;
    $old = $lastKnown[$sym] ?? null;
    if (is_array($old) && isset($old['as_of'], $old['price']) && $now - (int)$old['as_of'] <= LAST_KNOWN_MAX_AGE) {
        $old['carried_over'] = true;   // old value, not a live price
        $rates[$sym] = $old;
    }
}

$nextOpenIso = $tse['next_open'] ?? null;
$nextOpenFa  = $tse['next_open_fa'] ?? null;
$persist = [];
$stateCounts = [];
foreach ($supported as $sym => $meta) {
    if (isset($rates[$sym])) {
        $e = $rates[$sym];
    } else {
        $e = ['price' => null, 'unit' => $meta['unit'], 'source' => null, 'market' => $meta['market']];
        foreach (['category', 'ticker', 'name'] as $f) {
            if (isset($meta[$f])) $e[$f] = $meta[$f];
        }
    }
    $isTse = $meta['market'] === 'tse';
    $hasPrice = isset($e['price']);
    $carriedOver = !empty($e['carried_over']);

    if (!$hasPrice) {
        $state = 'no_data';
    } elseif ($carriedOver) {
        $state = ($isTse && !$tseOpenNow) ? 'closed' : 'no_data';
    } elseif (!$isTse) {
        $state = 'live';
    } elseif (!$tseOpenNow) {
        $state = 'closed';
    } elseif (!empty($e['daily_close'])) {
        $state = 'no_data';
    } elseif (($e['category'] ?? '') === 'index' || !empty($e['traded_today'])) {
        $state = 'live';
    } else {
        $state = 'no_trade_today';
    }

    if ($state === 'live') {
        $stateFa = 'زنده';
    } elseif ($state === 'closed') {
        $stateFa = 'بازار بسته' . ($nextOpenFa ? '؛ بازگشایی ' . $nextOpenFa : '');
    } elseif ($state === 'no_trade_today') {
        $stateFa = 'امروز معامله نشده';
    } else {
        $stateFa = $hasPrice ? 'فعلاً داده‌ای نیست؛ آخرین قیمت شناخته‌شده' : 'فعلاً داده‌ای نیست';
    }

    $e['state'] = $state;
    $e['state_fa'] = $stateFa;
    $e['alert_eligible'] = ($state === 'live');
    if ($isTse) {
        $e['market_open'] = $tseOpenNow;
        if ($state === 'closed' && $nextOpenIso) $e['next_open'] = $nextOpenIso;
    }
    if ($hasPrice && !$carriedOver) {
        $e['as_of'] = $now;   // when the bridge observed this value
        $persist[$sym] = $e;
    }
    $rates[$sym] = $e;
    $stateCounts[$state] = ($stateCounts[$state] ?? 0) + 1;
}

// Remember the latest real values so closed-market / outage responses can still show a price.
if ($persist && !$debug) {
    foreach ($persist as $sym => $e) {
        unset($e['market_open'], $e['carried_over'], $e['state'], $e['state_fa'], $e['alert_eligible'], $e['next_open']);
        $persist[$sym] = $e;
    }
    $merged = array_merge(array_filter($lastKnown, 'is_array'), $persist);
    if (!writeJsonAtomic($lastKnownFile, $merged)) error_log('[market-bridge] last-known write failed');
}

$tseMissing = [];
$tseFreshCount = 0;
$tseCarriedCount = 0;
$withPrice = 0;
foreach ($rates as $sym => $e) {
    if (isset($e['price'])) $withPrice++;
    if (($e['market'] ?? '') !== 'tse') continue;
    if (!isset($e['price'])) {
        $tseMissing[] = $sym;
    } elseif (!empty($e['carried_over'])) {
        $tseCarriedCount++;
    } else {
        $tseFreshCount++;
    }
}

// ---------------------------------------------------------------- output ---
$payload = [
    'success'        => true,
    'timestamp'      => $now,
    'datetime'       => date('Y-m-d H:i:s'),
    'cached'         => false,
    'stale'          => false,
    'failed_sources' => $failedSources,
    'source'         => 'aegkala_iran_bridge',
    'symbols_count'  => count($rates),
    'symbols_with_price' => $withPrice,
    'state_counts'   => $stateCounts,
    'markets'        => [
        'tse'    => $tse,
        'crypto' => ['name_fa' => 'صرافی‌های ارز دیجیتال', 'status' => 'open', 'reason' => null, 'schedule_fa' => '۲۴ ساعته', 'next_open' => null],
    ],
    'tse_fresh_count'   => $tseFreshCount,
    'tse_carried_count' => $tseCarriedCount,
    'tse_missing'       => $tseMissing,
    'data'           => $rates,
];

if ($debug) {
    $payload['debug'] = $dbg;
    respond($payload);
}

if (!writeJsonAtomic($cacheFile, $payload)) {
    error_log('[market-bridge] cache write failed: ' . $cacheFile);
}
respond($payload);

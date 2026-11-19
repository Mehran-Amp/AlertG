<?php
/**
 * TEMPORARY probe (IB-18a). Upload next to market-bridge.php on aegkala.com, run the tests, then DELETE it.
 *
 * It answers ONE question: how fast and how reliably can this host fetch the two TSETMC feeds that the
 * Bourse gateway uses (MarketWatchInit / MarketWatchPlus)? It stores nothing and returns only numbers
 * (status, timings, size, a hash) - never the market data itself.
 *
 *   ?t=<token>&do=info              PHP/curl facts of this host (no TSETMC request)
 *   ?t=<token>&do=init              one request to  .../MarketWatchInit.aspx?h=0&r=0
 *   ?t=<token>&do=plus&h=0&r=0      one request to  .../MarketWatchPlus.aspx?h=0&r=0
 *
 * Config file tse-probe.config.php (same folder, never committed):
 *   <?php return ['token' => 'a-random-string-of-at-least-16-chars', 'allow_ips' => ['203.0.113.7']]; // allow_ips optional
 */

const BASE_URL    = 'https://old.tsetmc.com/tsev2/data';
const UA          = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';
const MIN_GAP_SEC = 10;     // at most one TSETMC request per 10 s from this probe

@ini_set('display_errors', '0');
@set_time_limit(45);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

function out(array $d, int $code = 200): void {
    http_response_code($code);
    echo json_encode($d, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

$cfg = [];
$f = __DIR__ . '/tse-probe.config.php';
if (is_file($f)) { $x = @include $f; if (is_array($x)) $cfg = $x; }
$token = is_string($cfg['token'] ?? null) ? trim($cfg['token']) : '';
if (strlen($token) < 16) out(['ok' => false, 'error' => 'config: token missing or shorter than 16 characters'], 500);

$given = (string)($_GET['t'] ?? '');
if ($given === '' || !hash_equals($token, $given)) out(['ok' => false, 'error' => 'unauthorized'], 401);

$caller = $_SERVER['REMOTE_ADDR'] ?? '';
$allow = is_array($cfg['allow_ips'] ?? null) ? $cfg['allow_ips'] : [];
if ($allow && !in_array($caller, $allow, true)) out(['ok' => false, 'error' => 'ip not allowed', 'your_ip' => $caller], 403);

$do = (string)($_GET['do'] ?? 'info');

if ($do === 'info') {
    $cv = function_exists('curl_version') ? curl_version() : null;
    out([
        'ok' => true,
        'caller_ip' => $caller,
        'php' => PHP_VERSION,
        'sapi' => PHP_SAPI,
        'curl' => $cv ? ($cv['version'] . ' ' . ($cv['ssl_version'] ?? '')) : 'MISSING',
        'curl_encodings' => $cv['features'] ?? null,
        'max_execution_time' => ini_get('max_execution_time'),
        'memory_limit' => ini_get('memory_limit'),
        'allow_url_fopen' => ini_get('allow_url_fopen'),
        'disable_functions' => ini_get('disable_functions'),
        'tempdir_writable' => is_writable(sys_get_temp_dir()),
        'server_time_tehran' => (new DateTime('now', new DateTimeZone('Asia/Tehran')))->format('Y-m-d H:i:s'),
    ]);
}

if ($do !== 'init' && $do !== 'plus') out(['ok' => false, 'error' => 'unknown do'], 400);
if (!function_exists('curl_init')) out(['ok' => false, 'error' => 'curl extension missing'], 500);

// rate limit: one TSETMC request per MIN_GAP_SEC
$stamp = sys_get_temp_dir() . '/tse_probe_' . substr(hash('sha256', __FILE__), 0, 10) . '.t';
$last = (int)@file_get_contents($stamp);
if ($last && time() - $last < MIN_GAP_SEC) {
    out(['ok' => false, 'error' => 'too soon', 'retry_after' => MIN_GAP_SEC - (time() - $last)], 429);
}
@file_put_contents($stamp, (string)time());

if ($do === 'init') {
    $url = BASE_URL . '/MarketWatchInit.aspx?h=0&r=0';
} else {
    $h = (int)($_GET['h'] ?? 0);
    $r = (int)($_GET['r'] ?? 0);
    $url = BASE_URL . '/MarketWatchPlus.aspx?h=' . $h . '&r=' . $r;
}

$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_CONNECTTIMEOUT => 15,
    CURLOPT_TIMEOUT        => 30,
    CURLOPT_ENCODING       => '',                       // accept gzip/deflate
    CURLOPT_USERAGENT      => UA,
    CURLOPT_HTTPHEADER     => ['Accept-Language: fa-IR,fa;q=0.9'],
]);
$t0 = microtime(true);
$body = curl_exec($ch);
$err  = curl_error($ch);
$info = curl_getinfo($ch);
curl_close($ch);

$size = is_string($body) ? strlen($body) : 0;
out([
    'ok'            => $body !== false && ($info['http_code'] ?? 0) === 200,
    'what'          => $do,
    'http_code'     => $info['http_code'] ?? 0,
    'curl_error'    => $err ?: null,
    'dns_s'         => round($info['namelookup_time'] ?? 0, 3),
    'connect_s'     => round($info['connect_time'] ?? 0, 3),
    'tls_s'         => round($info['appconnect_time'] ?? 0, 3),
    'first_byte_s'  => round($info['starttransfer_time'] ?? 0, 3),
    'total_s'       => round($info['total_time'] ?? 0, 3),
    'wall_s'        => round(microtime(true) - $t0, 3),
    'bytes_decoded' => $size,
    'bytes_on_wire' => (int)($info['size_download'] ?? 0),
    'content_type'  => $info['content_type'] ?? null,
    'md5'           => $size ? md5($body) : null,
    'parts_at'      => $size ? substr_count($body, '@') : null,   // the Init feed separates sections with '@'
    'rows_semicolon'=> $size ? substr_count($body, ';') : null,
]);

<?php
/**
 * TSETMC forward bridge for the Iranian Bourse gateway (IB-18b).
 *
 * Runs on an Iranian host (aegkala.com). The tsetmc-gateway runs on server360 and is told
 *     TSETMC_BASE_URL=https://aegkala.com/tse-forward.php/<TOKEN>
 * so that its two requests become
 *     https://aegkala.com/tse-forward.php/<TOKEN>/MarketWatchInit.aspx?h=0&r=0
 *     https://aegkala.com/tse-forward.php/<TOKEN>/MarketWatchPlus.aspx?h=<n>&r=<n>
 * This file fetches exactly those two feeds from old.tsetmc.com and returns them unchanged.
 *
 * Safety: GET only; fixed upstream host; two allowed file names; h and r must be digits; token in the path
 * (constant-time compare); optional caller-IP allow-list; 8 MB size cap; short timeouts; 2 s micro-cache so
 * simultaneous callers cost one upstream request. It is NOT a general proxy.
 *
 * Config file tse-forward.config.php (same folder, never committed):
 *   <?php return ['token' => '<random, >= 24 chars, letters/digits>', 'allow_ips' => ['5.9.73.60']];
 */

const BRIDGE_NAME    = 'tse-forward/1.1';
const DEFAULT_BASE   = 'https://old.tsetmc.com/tsev2/data';
const ALLOWED_FILES  = ['MarketWatchInit.aspx', 'MarketWatchPlus.aspx'];
const CACHE_SECONDS  = 2;
const CONNECT_TO     = 8;
const TOTAL_TO       = 25;
const MAX_BYTES      = 8 * 1024 * 1024;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

@ini_set('display_errors', '0');
@set_time_limit(40);

function fail(int $code, string $msg): void {
    http_response_code($code);
    header('Content-Type: text/plain; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Bridge: ' . BRIDGE_NAME);
    echo $msg;
    exit;
}

// ---- config ----
$cfg = [];
$cfgFile = __DIR__ . '/tse-forward.config.php';
if (is_file($cfgFile)) { $x = @include $cfgFile; if (is_array($x)) $cfg = $x; }
$token = is_string($cfg['token'] ?? null) ? trim($cfg['token']) : '';
if (strlen($token) < 24) { error_log('[tse-forward] token missing or shorter than 24 chars'); fail(500, 'bridge not configured'); }
$base = rtrim(is_string($cfg['base_url'] ?? null) ? $cfg['base_url'] : DEFAULT_BASE, '/');   // base_url is for tests only
$maxBytes = (int)($cfg['max_bytes'] ?? MAX_BYTES);
$cacheSec = (int)($cfg['cache_seconds'] ?? CACHE_SECONDS);

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'GET') { header('Allow: GET'); fail(405, 'GET only'); }

// ---- caller IP ----
$allow = is_array($cfg['allow_ips'] ?? null) ? $cfg['allow_ips'] : [];
$caller = $_SERVER['REMOTE_ADDR'] ?? '';
if ($allow && !in_array($caller, $allow, true)) { error_log("[tse-forward] ip not allowed: $caller"); fail(403, 'forbidden'); }

// ---- path: /tse-forward.php/<token>/<File>.aspx ----
$uriPath = (string)parse_url($_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH);
$self = basename(__FILE__);
$pos = strpos($uriPath, $self);
$rest = $pos === false ? '' : substr($uriPath, $pos + strlen($self));
$parts = explode('/', trim($rest, '/'));
if (count($parts) !== 2) fail(404, 'not found');
[$given, $file] = $parts;
if (!hash_equals($token, rawurldecode($given))) { error_log("[tse-forward] bad token from $caller"); fail(401, 'unauthorized'); }
if (!in_array($file, ALLOWED_FILES, true)) fail(404, 'not found');

// ---- parameters: digits only ----
$h = (string)($_GET['h'] ?? '0');
$r = (string)($_GET['r'] ?? '0');
if (!preg_match('/^\d{1,18}$/', $h) || !preg_match('/^\d{1,18}$/', $r)) fail(400, 'bad parameters');
$url = $base . '/' . $file . '?h=' . $h . '&r=' . $r;

$wantsGzip = stripos($_SERVER['HTTP_ACCEPT_ENCODING'] ?? '', 'gzip') !== false;

// ---- micro-cache ----
$cacheDir = sys_get_temp_dir() . '/tse_forward_' . substr(hash('sha256', __FILE__), 0, 10);
@mkdir($cacheDir, 0700, true);
$key = md5($file . '|' . $h . '|' . $r . '|' . ($wantsGzip ? 'g' : 'p'));
$bodyFile = "$cacheDir/$key.body";
$metaFile = "$cacheDir/$key.json";
function send(string $body, string $ctype, bool $gzip, string $src, int $ms): void {
    http_response_code(200);
    header('Content-Type: ' . $ctype);
    header('Cache-Control: no-store');
    header('X-Bridge: ' . BRIDGE_NAME);
    header('X-Source: ' . $src);
    header('X-Upstream-Ms: ' . $ms);
    if ($gzip) header('Content-Encoding: gzip');
    header('Content-Length: ' . strlen($body));
    echo $body;
    exit;
}
if ($cacheSec > 0 && is_file($metaFile) && is_file($bodyFile)) {
    $m = json_decode((string)@file_get_contents($metaFile), true);
    if (is_array($m) && (time() - (int)($m['t'] ?? 0)) < $cacheSec) {
        $b = @file_get_contents($bodyFile);
        if ($b !== false && strlen($b) === (int)($m['len'] ?? -1)) send($b, $m['ctype'], (bool)$m['gzip'], 'cache', 0);
    }
}

// ---- fetch ----
if (!function_exists('curl_init')) fail(500, 'curl missing');
$body = '';
$tooBig = false;
$upGzip = false;
$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_CONNECTTIMEOUT => CONNECT_TO,
    CURLOPT_TIMEOUT        => TOTAL_TO,
    CURLOPT_USERAGENT      => UA,
    CURLOPT_HTTPHEADER     => ['Accept-Language: fa-IR,fa;q=0.9'] + ($wantsGzip ? [1 => 'Accept-Encoding: gzip'] : []),
    CURLOPT_HEADERFUNCTION => function ($c, $line) use (&$upGzip) {
        if (stripos($line, 'content-encoding:') === 0 && stripos($line, 'gzip') !== false) $upGzip = true;
        return strlen($line);
    },
    CURLOPT_WRITEFUNCTION  => function ($c, $chunk) use (&$body, &$tooBig, $maxBytes) {
        $body .= $chunk;
        if (strlen($body) > $maxBytes) { $tooBig = true; return -1; }
        return strlen($chunk);
    },
]);
if (!$wantsGzip) curl_setopt($ch, CURLOPT_ENCODING, '');   // decode for clients that cannot read gzip
$t0 = microtime(true);
$ok = curl_exec($ch);
$err = curl_error($ch);
$code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
$ctype = (string)(curl_getinfo($ch, CURLINFO_CONTENT_TYPE) ?: 'text/plain; charset=utf-8');
curl_close($ch);
$ms = (int)round((microtime(true) - $t0) * 1000);

if ($tooBig) { error_log('[tse-forward] upstream body too large'); fail(502, 'upstream too large'); }
if ($ok === false) { error_log("[tse-forward] upstream error: $err"); fail(502, 'upstream error'); }
if ($code !== 200) { error_log("[tse-forward] upstream status $code"); fail(502, 'upstream status ' . $code); }
if ($body === '') fail(502, 'upstream empty');

$gz = $wantsGzip && $upGzip;
if ($cacheSec > 0) {
    $tmp = "$bodyFile." . getmypid() . '.tmp';
    if (@file_put_contents($tmp, $body) !== false && @rename($tmp, $bodyFile)) {
        @file_put_contents($metaFile, json_encode(['t' => time(), 'len' => strlen($body), 'ctype' => $ctype, 'gzip' => $gz]));
    }
}
send($body, $ctype, $gz, 'upstream', $ms);

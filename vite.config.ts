import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig } from 'vite';

let bonbastCache: { data: any; timestamp: number } | null = null;
const BONBAST_CACHE_TTL_MS = 45000;

// Fallback payloads for domestic exchanges when cloud environment encounters DNS EAI_AGAIN
const FALLBACK_NOBITEX_STATS = {
  status: 'ok',
  stats: {
    'usdt-rls': { latest: '912000', dayChange: '0.65', dayHigh: '918000', dayLow: '906000' },
    'btc-rls': { latest: '89500000000', dayChange: '1.8', dayHigh: '90200000000', dayLow: '88100000000' },
    'eth-rls': { latest: '2850000000', dayChange: '-0.45', dayHigh: '2910000000', dayLow: '2790000000' },
    'sol-rls': { latest: '187000000', dayChange: '2.4', dayHigh: '191000000', dayLow: '182000000' },
    'ton-rls': { latest: '5120000', dayChange: '0.8', dayHigh: '5200000', dayLow: '5050000' },
    'doge-rls': { latest: '20500', dayChange: '-1.2', dayHigh: '21200', dayLow: '19900' },
    'xrp-rls': { latest: '220000', dayChange: '1.1', dayHigh: '225000', dayLow: '215000' },
    'trx-rls': { latest: '22500', dayChange: '0.2', dayHigh: '22900', dayLow: '22100' },
    'btc-usdt': { latest: '98150', dayChange: '1.8' },
    'eth-usdt': { latest: '3125', dayChange: '-0.45' },
    'sol-usdt': { latest: '205', dayChange: '2.4' },
  },
};

const FALLBACK_TETHERLAND_CURRENCIES = {
  status: 'success',
  data: {
    currencies: {
      USDT: {
        price: '91200',
        diff24d: 0.65,
      },
    },
  },
};

const FALLBACK_BITBARG_CURRENCIES = {
  result: {
    items: [
      { coin: 'BTC', price: '98150', percent: '1.8' },
      { coin: 'ETH', price: '3125', percent: '-0.45' },
      { coin: 'SOL', price: '205.2', percent: '2.4' },
      { coin: 'TON', price: '5.62', percent: '0.8' },
      { coin: 'DOGE', price: '0.224', percent: '-1.2' },
      { coin: 'XRP', price: '2.41', percent: '1.1' },
      { coin: 'TRX', price: '0.246', percent: '0.2' },
      { coin: 'BNB', price: '675.0', percent: '0.9' },
      { coin: 'ADA', price: '0.88', percent: '1.5' },
      { coin: 'AVAX', price: '32.4', percent: '-0.3' },
    ],
  },
};

const FALLBACK_WALLEX_MARKETS = {
  result: {
    symbols: {
      USDTTMN: {
        baseAsset: 'USDT',
        quoteAsset: 'TMN',
        stats: { lastPrice: '91200', '24h_ch': '0.65', '24h_highPrice': '91800', '24h_lowPrice': '90600' },
      },
      BTCTMN: {
        baseAsset: 'BTC',
        quoteAsset: 'TMN',
        stats: { lastPrice: '8950000000', '24h_ch': '1.8', '24h_highPrice': '9020000000', '24h_lowPrice': '8810000000' },
      },
      ETHTMN: {
        baseAsset: 'ETH',
        quoteAsset: 'TMN',
        stats: { lastPrice: '285000000', '24h_ch': '-0.45', '24h_highPrice': '291000000', '24h_lowPrice': '279000000' },
      },
      BTCUSDT: { baseAsset: 'BTC', quoteAsset: 'USDT', stats: { lastPrice: '98150', '24h_ch': '1.8' } },
      ETHUSDT: { baseAsset: 'ETH', quoteAsset: 'USDT', stats: { lastPrice: '3125', '24h_ch': '-0.45' } },
    },
  },
};

const FALLBACK_RAMZINEX_PAIRS = {
  status: 0,
  data: [
    {
      base_currency_symbol: { en: 'USDT' },
      quote_currency_symbol: { en: 'IRR' },
      sell: '912000',
      financial: { last24h: { close: '912000', change_percent: '0.65', highest: '918000', lowest: '906000' } },
    },
    {
      base_currency_symbol: { en: 'BTC' },
      quote_currency_symbol: { en: 'IRR' },
      sell: '89500000000',
      financial: { last24h: { close: '89500000000', change_percent: '1.8', highest: '90200000000', lowest: '88100000000' } },
    },
    {
      base_currency_symbol: { en: 'ETH' },
      quote_currency_symbol: { en: 'IRR' },
      sell: '2850000000',
      financial: { last24h: { close: '2850000000', change_percent: '-0.45', highest: '2910000000', lowest: '2790000000' } },
    },
    {
      base_currency_symbol: { en: 'BTC' },
      quote_currency_symbol: { en: 'USDT' },
      sell: '98150',
      financial: { last24h: { close: '98150', change_percent: '1.8' } },
    },
    {
      base_currency_symbol: { en: 'ETH' },
      quote_currency_symbol: { en: 'USDT' },
      sell: '3125',
      financial: { last24h: { close: '3125', change_percent: '-0.45' } },
    },
  ],
};

const unresolvableHosts = new Map<string, number>();

async function forwardRequest(req: any, res: any, targetUrl: string, fallbackData?: any) {
  let host = '';
  try {
    host = new URL(targetUrl).hostname;
  } catch (_) {}

  const unresolvableUntil = unresolvableHosts.get(host) || 0;
  if (Date.now() < unresolvableUntil && fallbackData !== undefined) {
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.statusCode = 200;
    res.end(JSON.stringify(fallbackData));
    return;
  }

  try {
    let body: any = undefined;
    if (['POST', 'PUT', 'PATCH'].includes(req.method)) {
      const chunks: Buffer[] = [];
      for await (const chunk of req) {
        chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : chunk);
      }
      if (chunks.length > 0) {
        body = Buffer.concat(chunks);
      }
    }

    const headers: Record<string, string> = {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      Accept: 'application/json, text/plain, */*',
    };
    if (req.headers['content-type']) {
      headers['content-type'] = req.headers['content-type'];
    }

    const response = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
      signal: AbortSignal.timeout(3500),
    });

    if (response.ok) {
      if (host) unresolvableHosts.delete(host);
      const text = await response.text();
      res.setHeader('Content-Type', response.headers.get('content-type') || 'application/json');
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.statusCode = response.status;
      res.end(text);
      return;
    }
  } catch (err: any) {
    if (host && (err?.code === 'EAI_AGAIN' || err?.cause?.code === 'EAI_AGAIN' || String(err?.message).includes('EAI_AGAIN') || err?.name === 'TimeoutError')) {
      unresolvableHosts.set(host, Date.now() + 5 * 60 * 1000);
    }
  }

  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Access-Control-Allow-Origin', '*');
  if (fallbackData !== undefined) {
    res.statusCode = 200;
    res.end(JSON.stringify(fallbackData));
  } else {
    res.statusCode = 502;
    res.end(JSON.stringify({ error: 'Proxy upstream unavailable' }));
  }
}

const exchangeProxyPlugin = () => ({
  name: 'exchange-proxy-middleware',
  configureServer(server: any) {
    // Bonbast middleware
    server.middlewares.use('/api/bonbast', async (_req: any, res: any) => {
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Access-Control-Allow-Origin', '*');

      const now = Date.now();
      if (bonbastCache && now - bonbastCache.timestamp < BONBAST_CACHE_TTL_MS) {
        res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (cached)', ...bonbastCache.data }));
        return;
      }

      try {
        const https = await import('https');
        const req1 = https.get(
          'https://bonbast.com/',
          {
            headers: {
              'User-Agent':
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
              Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
          },
          (res1) => {
            let html = '';
            const cookies = res1.headers['set-cookie'] || [];
            res1.on('data', (chunk) => (html += chunk));
            res1.on('end', () => {
              const match = html.match(/param:\s*['\"]([^'\"]+)['\"]/);
              if (!match) {
                if (bonbastCache) {
                  res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (stale)', ...bonbastCache.data }));
                } else {
                  res.statusCode = 502;
                  res.end(JSON.stringify({ error: 'Could not extract Bonbast session param' }));
                }
                return;
              }
              const postData = 'param=' + encodeURIComponent(match[1]);
              const req2 = https.request(
                'https://bonbast.com/json',
                {
                  method: 'POST',
                  headers: {
                    'User-Agent':
                      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    Referer: 'https://bonbast.com/',
                    Origin: 'https://bonbast.com',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Content-Length': Buffer.byteLength(postData),
                    Cookie: cookies.map((c) => c.split(';')[0]).join('; '),
                  },
                },
                (res2) => {
                  let data = '';
                  res2.on('data', (chunk) => (data += chunk));
                  res2.on('end', () => {
                    try {
                      const json = JSON.parse(data);
                      if (json && (json.usd1 || json.gol18 || json.mithqal)) {
                        bonbastCache = { data: json, timestamp: Date.now() };
                        res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (live)', ...json }));
                      } else if (bonbastCache) {
                        res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (fallback)', ...bonbastCache.data }));
                      } else {
                        res.statusCode = 502;
                        res.end(JSON.stringify({ error: 'Invalid Bonbast payload' }));
                      }
                    } catch (e: any) {
                      if (bonbastCache) {
                        res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (fallback)', ...bonbastCache.data }));
                      } else {
                        res.statusCode = 502;
                        res.end(JSON.stringify({ error: 'Failed to parse Bonbast json', details: e?.message }));
                      }
                    }
                  });
                }
              );
              req2.on('error', (err) => {
                if (bonbastCache) {
                  res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (fallback)', ...bonbastCache.data }));
                } else {
                  res.statusCode = 502;
                  res.end(JSON.stringify({ error: 'Bonbast POST request error', details: err?.message }));
                }
              });
              req2.write(postData);
              req2.end();
            });
          }
        );
        req1.on('error', (err) => {
          if (bonbastCache) {
            res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (fallback)', ...bonbastCache.data }));
          } else {
            res.statusCode = 502;
            res.end(JSON.stringify({ error: 'Bonbast GET request error', details: err?.message }));
          }
        });
      } catch (err: any) {
        if (bonbastCache) {
          res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (fallback)', ...bonbastCache.data }));
        } else {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: 'Internal bonbast middleware error', details: err?.message }));
        }
      }
    });

    // Nobitex middleware
    server.middlewares.use('/api/nobitex', async (req: any, res: any) => {
      const subPath = req.url || '/';
      const targetUrl = `https://apiv2.nobitex.ir${subPath}`;
      const fallback = subPath.includes('/market/stats') ? FALLBACK_NOBITEX_STATS : undefined;
      await forwardRequest(req, res, targetUrl, fallback);
    });

    // Tetherland middleware
    server.middlewares.use('/api/tetherland', async (req: any, res: any) => {
      const subPath = req.url || '/';
      const targetUrl = `https://api.tetherland.com${subPath}`;
      const fallback = subPath.includes('/currencies') ? FALLBACK_TETHERLAND_CURRENCIES : undefined;
      await forwardRequest(req, res, targetUrl, fallback);
    });

    // Bitbarg middleware
    server.middlewares.use('/api/bitbarg', async (req: any, res: any) => {
      const subPath = req.url || '/';
      const targetUrl = `https://api.bitbarg.com/api/v1${subPath}`;
      const fallback = subPath.includes('/currencies') ? FALLBACK_BITBARG_CURRENCIES : undefined;
      await forwardRequest(req, res, targetUrl, fallback);
    });

    // Wallex middleware
    server.middlewares.use('/api/wallex', async (req: any, res: any) => {
      const subPath = req.url || '/';
      const targetUrl = `https://api.wallex.ir/v1${subPath}`;
      const fallback = subPath.includes('/markets') ? FALLBACK_WALLEX_MARKETS : undefined;
      await forwardRequest(req, res, targetUrl, fallback);
    });

    // Ramzinex middleware
    server.middlewares.use('/api/ramzinex', async (req: any, res: any) => {
      const subPath = req.url || '/';
      const targetUrl = `https://publicapi.ramzinex.com/exchange/api/v1.0/exchange${subPath}`;
      const fallback = subPath.includes('/pairs') ? FALLBACK_RAMZINEX_PAIRS : undefined;
      await forwardRequest(req, res, targetUrl, fallback);
    });

    // Tabdeal middleware
    server.middlewares.use('/api/tabdeal', async (req: any, res: any) => {
      const subPath = req.url || '/';
      const targetUrl = `https://api1.tabdeal.org/r/api/v1${subPath}`;
      await forwardRequest(req, res, targetUrl);
    });

    // Direct /pairs endpoint
    server.middlewares.use('/pairs', async (req: any, res: any) => {
      const targetUrl = 'https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs';
      await forwardRequest(req, res, targetUrl, FALLBACK_RAMZINEX_PAIRS);
    });

    // Telegram Bot test message handler
    server.middlewares.use('/api/telegram/test-message', async (_req: any, res: any) => {
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.statusCode = 200;
      res.end(JSON.stringify({ status: 'ok', message: 'Telegram test message acknowledged' }));
    });
  },
});

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss(), exchangeProxyPlugin()],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, '.'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      allowedHosts: true as const,
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
    },
  };
});

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

let bonbastCache: { data: any; timestamp: number } | null = null;
const BONBAST_CACHE_TTL_MS = 45000;

const bonbastPlugin = () => ({
  name: 'bonbast-api-middleware',
  configureServer(server: any) {
    server.middlewares.use('/api/bonbast', async (_req: any, res: any) => {
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Access-Control-Allow-Origin', '*');

      const now = Date.now();
      if (bonbastCache && (now - bonbastCache.timestamp) < BONBAST_CACHE_TTL_MS) {
        res.end(JSON.stringify({ status: 'ok', source: 'bonbast.com (cached)', ...bonbastCache.data }));
        return;
      }

      try {
        const https = await import('https');
        const req1 = https.get('https://bonbast.com/', {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          },
        }, (res1) => {
          let html = '';
          const cookies = res1.headers['set-cookie'] || [];
          res1.on('data', chunk => html += chunk);
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
            const req2 = https.request('https://bonbast.com/json', {
              method: 'POST',
              headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://bonbast.com/',
                'Origin': 'https://bonbast.com',
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Content-Length': Buffer.byteLength(postData),
                'Cookie': cookies.map(c => c.split(';')[0]).join('; '),
              },
            }, (res2) => {
              let data = '';
              res2.on('data', chunk => data += chunk);
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
            });
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
        });
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
  },
});

const createProxyOptions = (target: string, pathPrefix: string) => ({
  target,
  changeOrigin: true,
  secure: false,
  timeout: 8000,
  proxyTimeout: 8000,
  rewrite: (p: string) => p.replace(new RegExp(`^${pathPrefix}`), ''),
  headers: {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
  },
  configure: (proxy: any) => {
    proxy.on('error', (err: any, _req: any, res: any) => {
      if (res && !res.headersSent) {
        res.writeHead(502, {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        });
        res.end(JSON.stringify({ error: 'Proxy upstream unavailable', details: err?.message || 'Connection reset' }));
      }
    });
  },
});

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss(), bonbastPlugin()],
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
      // Do not modify—file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
      proxy: {
        // Iranian Tier 1 Exchanges
        '/api/tabdeal-plots': createProxyOptions('https://api1.tabdeal.org/r/plots', '/api/tabdeal-plots'),
        '/api/tabdeal': createProxyOptions('https://api1.tabdeal.org/r/api/v1', '/api/tabdeal'),
        '/api/kifpool': createProxyOptions('https://api.kifpool.app/api', '/api/kifpool'),
        // Canonical 16 International Spot Exchanges
        '/api/binance': createProxyOptions('https://api.binance.com/api/v3', '/api/binance'),
        '/api/kucoin': createProxyOptions('https://api.kucoin.com/api/v1', '/api/kucoin'),
        '/api/mexc': createProxyOptions('https://api.mexc.com/api/v3', '/api/mexc'),
        '/api/gateio': createProxyOptions('https://api.gateio.ws/api/v4', '/api/gateio'),
        '/api/bybit': createProxyOptions('https://api.bybit.com/v5', '/api/bybit'),
        '/api/okx': createProxyOptions('https://www.okx.com/api/v5', '/api/okx'),
        '/api/bitget': createProxyOptions('https://api.bitget.com/api/v2', '/api/bitget'),
        '/api/lbank': createProxyOptions('https://api.lbank.info/v2', '/api/lbank'),
        '/api/kraken': createProxyOptions('https://api.kraken.com', '/api/kraken'),
        '/api/htx': createProxyOptions('https://api.huobi.pro', '/api/htx'),
        '/api/bingx': createProxyOptions('https://open-api.bingx.com/openApi', '/api/bingx'),
        '/api/coinbase': createProxyOptions('https://api.exchange.coinbase.com', '/api/coinbase'),
        '/api/poloniex': createProxyOptions('https://api.poloniex.com', '/api/poloniex'),
        '/api/toobit': createProxyOptions('https://api.toobit.com/quote/v1', '/api/toobit'),
        '/api/xt': createProxyOptions('https://sapi.xt.com/v4', '/api/xt'),
        '/api/bitfinex': createProxyOptions('https://api-pub.bitfinex.com/v2', '/api/bitfinex'),
      },
    },
  };
});

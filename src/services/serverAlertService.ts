/**
 * ServerAlertService for React/TypeScript Frontend
 * Manages communication with the Python Alert Engine backend
 */

export interface AlertPayload {
  user_id: string;
  exchange: string;
  symbol: string;
  target_price: number;
  condition: 'ABOVE' | 'BELOW';
  fcm_token: string;
  check_interval_seconds: number; // Interval in seconds (seconds, minutes, or hours converted)
  note?: string;
}

export interface ServerAlertResponse extends AlertPayload {
  id: string;
  is_active: boolean;
  created_at: string;
}

let BASE_URL = 'https://aisocialfeed.com';
let API_KEY = '';

export const setServerBaseUrl = (url: string) => {
  if (url) {
    BASE_URL = url.endsWith('/') ? url.slice(0, -1) : url;
  }
};

export const setServerApiKey = (key: string) => {
  if (key) {
    API_KEY = key;
  }
};

export const getServerBaseUrl = () => BASE_URL;

const buildHeaders = (extra?: Record<string, string>) => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }
  return { ...headers, ...extra };
};

/**
 * Convert check frequency unit value + unit into seconds
 */
export const convertIntervalToSeconds = (value: number, unit: 'seconds' | 'minutes' | 'hours'): number => {
  const val = value > 0 ? value : 10;
  switch (unit) {
    case 'seconds':
      return val;
    case 'minutes':
      return val * 60;
    case 'hours':
      return val * 3600;
    default:
      return val;
  }
};

/**
 * Register a new alert on the Python server
 */
export async function createAlertOnServer(payload: AlertPayload): Promise<ServerAlertResponse | null> {
  try {
    const res = await fetch(`${BASE_URL}/api/alerts`, {
      method: 'POST',
      headers: buildHeaders(),
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const data = await res.json();
      console.log('✅ Alert registered on Python server:', data);
      return data;
    }
  } catch (err) {
    console.error('❌ Error creating alert on Python server:', err);
  }
  return null;
}

/**
 * Fetch all user alerts from Python server
 */
export async function fetchUserAlertsFromServer(userId: string): Promise<ServerAlertResponse[]> {
  try {
    const res = await fetch(`${BASE_URL}/api/alerts/${userId}`, {
      headers: buildHeaders(),
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.error('❌ Error fetching user alerts:', err);
  }
  return [];
}

/**
 * Delete alert from Python server
 */
export async function deleteAlertFromServer(alertId: string): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/api/alerts/${alertId}`, {
      method: 'DELETE',
      headers: buildHeaders(),
    });
    return res.ok;
  } catch (err) {
    console.error('❌ Error deleting alert:', err);
  }
  return false;
}

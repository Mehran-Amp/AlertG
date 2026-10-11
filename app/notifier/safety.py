import ipaddress
import socket
import asyncio
from urllib.parse import urlparse
from app.config import MAX_WEBHOOK_LEN

def _ip_is_public(ip) -> bool:
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast

def is_safe_webhook_url(url_str: str) -> bool:
    if not url_str or not url_str.startswith('https://'):
        return False
    try:
        parsed = urlparse(url_str)
        hostname = (parsed.hostname or '').lower().strip()
        if not hostname or hostname in ['localhost', '0.0.0.0']:
            return False

        # Parse directly if IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if not _ip_is_public(ip):
                return False
        except ValueError:
            if hostname.endswith('.local') or hostname.endswith('.internal'):
                return False

        return True
    except Exception:
        return False

async def is_safe_webhook_url_async(url_str: str) -> bool:
    """Static checks + DNS resolution: every resolved address must be public (blocks internal-host SSRF)."""
    if not url_str or len(url_str) > MAX_WEBHOOK_LEN or not is_safe_webhook_url(url_str):
        return False
    host = (urlparse(url_str).hostname or '').strip()
    try:
        ipaddress.ip_address(host)
        return True  # literal IP already vetted by is_safe_webhook_url
    except ValueError:
        pass
    try:
        loop = asyncio.get_running_loop()
        infos = await asyncio.wait_for(loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM), timeout=3.0)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            if not _ip_is_public(ipaddress.ip_address(info[4][0].split('%')[0])):
                return False
        except ValueError:
            return False
    return True

import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.notifier import telegram
from app.state import METRICS


class TestTelegramRetry(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_metrics = dict(METRICS)

    async def asyncTearDown(self):
        METRICS.clear()
        METRICS.update(self._orig_metrics)

    async def test_retry_on_429_then_200_success(self):
        """1. HTTP 429 response waits retry_after and succeeds on second attempt (Phase 2C-1)."""
        mock_client = AsyncMock()

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"retry-after": "5"}
        resp_429.json.return_value = {"ok": False, "parameters": {"retry_after": 5}}

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}

        mock_client.post.side_effect = [resp_429, resp_200]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await telegram.send_telegram_alert(
                client=mock_client,
                chat_id="chat_123",
                message="Test alert",
                bot_token="test_token"
            )

        self.assertTrue(result)
        self.assertEqual(mock_client.post.call_count, 2)
        mock_sleep.assert_called_once_with(5.0)

    async def test_retry_on_5xx_three_times_then_false(self):
        """2. HTTP 5xx fails after 3 attempts with backoff and returns False (Phase 2C-1)."""
        mock_client = AsyncMock()

        resp_502 = MagicMock(spec=httpx.Response)
        resp_502.status_code = 502
        resp_502.text = "Bad Gateway"
        mock_client.post.return_value = resp_502

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await telegram.send_telegram_alert(
                client=mock_client,
                chat_id="chat_123",
                message="Test alert",
                bot_token="test_token"
            )

        self.assertFalse(result)
        self.assertEqual(mock_client.post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        # Backoff intervals between the 3 attempts: 1.0s, 3.0s
        self.assertEqual(mock_sleep.call_args_list[0][0][0], 1.0)
        self.assertEqual(mock_sleep.call_args_list[1][0][0], 3.0)

    async def test_error_400_fails_immediately_without_retry(self):
        """3. HTTP 400 Bad Request fails immediately without retry (Phase 2C-1)."""
        mock_client = AsyncMock()

        resp_400 = MagicMock(spec=httpx.Response)
        resp_400.status_code = 400
        resp_400.text = "Bad Request: chat not found"
        mock_client.post.return_value = resp_400

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await telegram.send_telegram_alert(
                client=mock_client,
                chat_id="chat_123",
                message="Test alert",
                bot_token="test_token"
            )

        self.assertFalse(result)
        self.assertEqual(mock_client.post.call_count, 1)
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()

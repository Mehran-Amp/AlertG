import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.notifier import telegram
from app.state import METRICS


class TestTelegramRetry(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_metrics = dict(METRICS)
        if "telegram_sent" not in METRICS:
            METRICS["telegram_sent"] = 0

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

    async def test_400_html_parse_error_retries_with_plain_text_and_succeeds(self):
        """3. HTTP 400 HTML parse failure retries with plain text (parse_mode=None) and returns True on 200 (FIX-2)."""
        mock_client = AsyncMock()

        resp_400 = MagicMock(spec=httpx.Response)
        resp_400.status_code = 400
        resp_400.text = "Bad Request: can't parse entities in message text"

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}

        mock_client.post.side_effect = [resp_400, resp_200]

        result = await telegram.send_telegram_alert(
            client=mock_client,
            chat_id="chat_123",
            message="<b>Alert</b>: Target < 50000 & wait",
            bot_token="test_token"
        )

        self.assertTrue(result)
        self.assertEqual(mock_client.post.call_count, 2)
        # Verify second call used parse_mode=None and stripped tags
        second_payload = mock_client.post.call_args_list[1][1]["json"]
        self.assertIsNone(second_payload.get("parse_mode"))
        self.assertEqual(second_payload.get("text"), "Alert: Target < 50000 & wait")

    async def test_400_on_plain_text_fails_with_only_one_retry(self):
        """4. HTTP 400 for plain text also fails and stops after exactly one retry (FIX-2)."""
        mock_client = AsyncMock()

        resp_400 = MagicMock(spec=httpx.Response)
        resp_400.status_code = 400
        resp_400.text = "Bad Request: chat not found"
        mock_client.post.return_value = resp_400

        result = await telegram.send_telegram_alert(
            client=mock_client,
            chat_id="chat_123",
            message="<b>Alert</b>: Target < 50000",
            bot_token="test_token"
        )

        self.assertFalse(result)
        # First call with HTML, second call with plain text, then aborts (call_count == 2)
        self.assertEqual(mock_client.post.call_count, 2)


if __name__ == "__main__":
    unittest.main()

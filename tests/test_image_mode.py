import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

if "loguru" not in sys.modules:
    class _DummyLogger:
        def __getattr__(self, _name):
            return lambda *args, **kwargs: self

    sys.modules["loguru"] = types.SimpleNamespace(logger=_DummyLogger())

from cli import build_parser  # noqa: E402
from gemini_webapi import GeminiClient  # noqa: E402
from gemini_webapi.constants import (  # noqa: E402
    Endpoint,
    GRPC,
    IMAGE_MODE_ID,
    LAST_SELECTED_MODE_INDEX,
)


class TestImageMode(unittest.IsolatedAsyncioTestCase):
    async def test_set_generation_mode_uses_har_mode_slot(self):
        client = GeminiClient("psid", "psidts")
        client._batch_execute = AsyncMock()

        await client._set_generation_mode(IMAGE_MODE_ID)

        client._batch_execute.assert_awaited_once()
        payloads = client._batch_execute.await_args.args[0]
        self.assertEqual(len(payloads), 1)

        rpc = payloads[0]
        self.assertEqual(rpc.rpcid, GRPC.MODE_PREFERENCES)

        payload = json.loads(rpc.payload)
        self.assertEqual(len(payload[0]), LAST_SELECTED_MODE_INDEX + 1)
        self.assertEqual(payload[0][LAST_SELECTED_MODE_INDEX], IMAGE_MODE_ID)
        self.assertEqual(payload[1], [["last_selected_mode_id_on_web"]])

    async def test_cli_parser_accepts_image_mode(self):
        parser = build_parser()
        args = parser.parse_args(["ask", "draw a fox", "--image-mode"])

        self.assertTrue(args.image_mode)

    async def test_prepare_image_surface_uses_images_surface(self):
        client = GeminiClient("psid", "psidts")
        client._refresh_surface_context = AsyncMock()
        client._send_bard_settings_for_source = AsyncMock()
        client._send_bard_activity_for_source = AsyncMock()

        await client._prepare_image_surface()

        client._refresh_surface_context.assert_awaited_once_with(Endpoint.IMAGES)
        client._send_bard_settings_for_source.assert_awaited_once_with("/images")
        client._send_bard_activity_for_source.assert_awaited_once_with("/images")

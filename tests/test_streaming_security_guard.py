"""Unit tests for SmartRAGService streaming leakage protection."""

import pytest

from app.core.smart_rag_service import SmartRAGService


async def _collect_stream(async_iter):
    chunks = []
    async for chunk in async_iter:
        chunks.append(chunk)
    return chunks


class TestStreamingLeakageGuard:
    @pytest.mark.asyncio
    async def test_blocks_split_signature_before_client_emission(self):
        async def leaking_stream():
            yield "query intent "
            yield "detection (critical)"

        chunks = await _collect_stream(
            SmartRAGService._iter_safe_stream_chunks(leaking_stream(), "en")
        )

        full_text = "".join(chunks)
        assert "query intent detection (critical" not in full_text.lower()
        assert full_text == SmartRAGService._security_fallback("en")

    @pytest.mark.asyncio
    async def test_preserves_normal_stream_output(self):
        async def normal_stream():
            yield "I recommend "
            yield "Blue Dream for "
            yield "relaxation."

        chunks = await _collect_stream(
            SmartRAGService._iter_safe_stream_chunks(normal_stream(), "en")
        )

        assert "".join(chunks) == "I recommend Blue Dream for relaxation."

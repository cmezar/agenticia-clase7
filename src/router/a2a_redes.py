"""Cliente A2A para consultar el agente de inteligencia de redes."""

from __future__ import annotations

import os

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import get_stream_response_text, new_text_message
from a2a.types import Role, SendMessageRequest


async def preguntar_redes(texto: str, hilo: str) -> str:
    """Pregunta al agente de redes usando A2A y devuelve su texto completo."""
    intel_url = os.getenv("INTEL_URL", "").strip()
    intel_token = os.getenv("INTEL_TOKEN", "").strip()
    if not intel_url or not intel_token:
        raise RuntimeError("INTEL_URL o INTEL_TOKEN no están configuradas")

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {intel_token}"},
        timeout=60.0,
    ) as http:
        client = await create_client(
            intel_url,
            client_config=ClientConfig(httpx_client=http, streaming=False),
        )
        try:
            request = SendMessageRequest(
                message=new_text_message(texto, role=Role.ROLE_USER, context_id=hilo)
            )
            partes: list[str] = []
            async for response in client.send_message(request):
                respuesta = get_stream_response_text(response)
                if respuesta and (not partes or respuesta != partes[-1]):
                    partes.append(respuesta)
            return "\n".join(partes).strip()
        finally:
            await client.close()

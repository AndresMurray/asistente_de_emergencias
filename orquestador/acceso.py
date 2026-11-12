"""Pase de entrada al orquestador: lo que en LiveKit era el token de la sala.

El servidor web (que tiene el secreto) firma un pase que vence a los pocos
minutos y se lo da al navegador; el orquestador lo verifica al abrir la
conexión. El secreto nunca llega al navegador.

Formato: «<vence>.<firma>», con vence en segundos Unix y
firma = HMAC-SHA256(secreto, vence) en hexadecimal. Es simple a propósito, para
poder firmarlo igual desde Next.js (app/api/orquestador/route.ts).
"""

from __future__ import annotations

import hashlib
import hmac
import time


def firmar(secreto: str, vence: int) -> str:
    firma = hmac.new(secreto.encode(), str(vence).encode(), hashlib.sha256).hexdigest()
    return f"{vence}.{firma}"


def nuevo_pase(secreto: str, dura_s: int = 300) -> str:
    return firmar(secreto, int(time.time()) + dura_s)


def verificar(secreto: str, pase: object, ahora: float | None = None) -> bool:
    if not isinstance(pase, str) or "." not in pase:
        return False
    vence_txt, _, _ = pase.partition(".")
    if not vence_txt.isdigit():
        return False
    if int(vence_txt) < (time.time() if ahora is None else ahora):
        return False
    return hmac.compare_digest(pase, firmar(secreto, int(vence_txt)))

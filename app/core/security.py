"""Внутренняя аутентификация между сервисами."""
from fastapi import Header, HTTPException, status

from app.core.config import settings


async def verify_internal_token(authorization: str | None = Header(None)) -> None:
    """Проверяет Bearer-токен для межсервисных вызовов.

    Если токен не задан в конфигурации (пустая строка) — пропускает запрос
    (backward compatibility при развёртывании без токена).
    """
    expected = settings.api_token
    if not expected:
        return
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

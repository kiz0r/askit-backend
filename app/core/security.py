import hashlib
import uuid

from app.redis import get_redis_client

MAX_LOGIN_ATTEMPTS = 10
LOGIN_LOCKOUT_TTL = 900
_WS_TOKEN_TTL = 4 * 3600  # 4 hours — survives reconnects for a full game session

_WS_TOKEN_KEY = "ws_token:{}"
_BLACKLIST_KEY = "blacklist:refresh:{}"
_LOGIN_ATTEMPTS_KEY = "login_attempts:{}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def blacklist_refresh_token(token: str, ttl: int) -> None:
    client = get_redis_client()
    await client.set(_BLACKLIST_KEY.format(_hash_token(token)), "1", ex=ttl)


async def is_refresh_token_blacklisted(token: str) -> bool:
    client = get_redis_client()
    exists: int = await client.exists(_BLACKLIST_KEY.format(_hash_token(token)))
    return exists > 0


async def create_ws_token(player_id: str) -> str:
    token = str(uuid.uuid4())
    client = get_redis_client()
    await client.set(_WS_TOKEN_KEY.format(token), player_id, ex=_WS_TOKEN_TTL)
    return token


async def verify_ws_token(token: str) -> str | None:
    client = get_redis_client()
    value: str | None = await client.get(_WS_TOKEN_KEY.format(token))
    return value


async def revoke_ws_token(token: str) -> None:
    client = get_redis_client()
    await client.delete(_WS_TOKEN_KEY.format(token))


def _login_attempts_key(email: str) -> str:
    # Normalize so lockout counting cannot be bypassed by changing the
    # casing or surrounding whitespace of the email address.
    return _LOGIN_ATTEMPTS_KEY.format(email.strip().lower())


async def record_failed_login(email: str) -> int:
    client = get_redis_client()
    key = _login_attempts_key(email)
    count: int = int(await client.incr(key))
    if count == 1:
        await client.expire(key, LOGIN_LOCKOUT_TTL)
    return count


async def reset_login_attempts(email: str) -> None:
    client = get_redis_client()
    await client.delete(_login_attempts_key(email))


async def get_login_attempts(email: str) -> int:
    client = get_redis_client()
    val = await client.get(_login_attempts_key(email))
    return int(val) if val else 0

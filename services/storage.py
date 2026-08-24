import os
import random
import string
import time
from typing import Optional, List, Tuple, Union

import asyncpg

ALPHABET = ''.join(c for c in string.ascii_uppercase + string.digits if c not in 'O0I1')
_pool: Optional[asyncpg.Pool] = None


async def init_pool(dsn: str):
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vault (
                code TEXT PRIMARY KEY,
                owner_id BIGINT NOT NULL,
                file_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('photo', 'video')),
                created_at TIMESTAMPTZ DEFAULT now(),
                expires_at TIMESTAMPTZ
            );
            CREATE INDEX IF NOT EXISTS idx_vault_owner ON vault (owner_id);
            CREATE TABLE IF NOT EXISTS group_settings (
                chat_id BIGINT PRIMARY KEY,
                welcome_text TEXT,
                welcome_on BOOLEAN DEFAULT TRUE
            );
        """)


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def save_media(owner_id: int, file_id: str, kind: str, ttl_seconds: Optional[int] = None) -> str:
    assert _pool is not None, "Pool not initialized"
    expires_at = None
    if ttl_seconds is not None and ttl_seconds > 0:
        expires_at = time.time() + ttl_seconds

    async with _pool.acquire() as conn:
        while True:
            code = ''.join(random.choices(ALPHABET, k=4))
            try:
                await conn.execute(
                    "INSERT INTO vault (code, owner_id, file_id, kind, expires_at) VALUES ($1, $2, $3, $4, $5)",
                    code, owner_id, file_id, kind, expires_at
                )
                return code
            except asyncpg.UniqueViolationError:
                continue


async def get_media(code: str) -> Optional[Tuple]:
    assert _pool is not None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT code, owner_id, file_id, kind, created_at, expires_at FROM vault WHERE upper(code) = $1",
            code.upper()
        )
        if row is None:
            return None
        if row['expires_at'] is not None and row['expires_at'].timestamp() <= time.time():
            return None
        return tuple(row)


async def list_media(owner_id: int) -> List[Tuple]:
    assert _pool is not None
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT code, kind, created_at, expires_at FROM vault "
            "WHERE owner_id = $1 AND (expires_at IS NULL OR expires_at > now()) "
            "ORDER BY created_at DESC",
            owner_id
        )
        return [tuple(r) for r in rows]


async def purge_expired() -> int:
    assert _pool is not None
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM vault WHERE expires_at IS NOT NULL AND expires_at <= now()"
        )
        return int(result.split()[-1])


async def set_welcome(chat_id: int, text: Optional[str], enabled: bool = True):
    assert _pool is not None
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO group_settings (chat_id, welcome_text, welcome_on) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (chat_id) DO UPDATE SET welcome_text = $2, welcome_on = $3",
            chat_id, text, enabled
        )


async def get_welcome(chat_id: int) -> Optional[str]:
    assert _pool is not None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT welcome_text, welcome_on FROM group_settings WHERE chat_id = $1",
            chat_id
        )
        if row and row['welcome_on']:
            return row['welcome_text']
        return None


async def delete_media(code: str) -> bool:
    assert _pool is not None
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM vault WHERE code = $1",
            code
        )
        return result == "DELETE 1"
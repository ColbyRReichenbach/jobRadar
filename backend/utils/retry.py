import asyncio
import httpx

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds


async def with_retry(coro_fn, *args, retries=MAX_RETRIES, **kwargs):
    for attempt in range(retries):
        try:
            return await coro_fn(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:  # rate limited
                retry_after = int(e.response.headers.get("Retry-After", BACKOFF_BASE**attempt))
                await asyncio.sleep(retry_after)
            elif status >= 500:  # server error — retry
                await asyncio.sleep(BACKOFF_BASE**attempt)
            else:  # 4xx client error — do not retry
                raise
        except (httpx.RequestError, asyncio.TimeoutError):
            if attempt == retries - 1:
                raise
            await asyncio.sleep(BACKOFF_BASE**attempt)
    raise RuntimeError(f"Exhausted {retries} retries")

---
id: kb_004
title: API rate limits and how to handle 429 errors
category: Developer / API
---

The Northwind Cloud REST API enforces rate limits per API token:

- Free and Pro plans: 60 requests/minute
- Business plan: 300 requests/minute
- Enterprise plan: 1,200 requests/minute, with the option to request a custom limit

When you exceed your limit, the API returns HTTP 429 with a `Retry-After` header (in seconds). Clients should implement exponential backoff and respect the `Retry-After` value rather than retrying immediately.

Rate limit status is also returned on every response via headers:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset` (unix timestamp)

Bulk operations (e.g. creating more than 100 records) should use the batch endpoints (`/api/v2/batch/*`) instead of looping individual calls — batch endpoints count as a single request against your rate limit regardless of batch size, up to 500 records per batch.

If you consistently hit rate limits during normal usage (not a burst/retry loop), contact support to request a limit increase — include your average requests/minute and use case.

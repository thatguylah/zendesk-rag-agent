---
id: kb_005
title: Setting up outbound webhooks
category: Developer / API
---

Webhooks let your systems receive real-time notifications when events happen in Northwind Cloud (e.g. task created, task completed, project archived).

To configure a webhook:

1. Go to Workspace Settings > Integrations > Webhooks > Add Webhook.
2. Enter the destination URL (must be HTTPS).
3. Select the events to subscribe to.
4. Northwind Cloud signs every webhook payload with an HMAC-SHA256 signature in the `X-Northwind-Signature` header, computed using your webhook's signing secret (shown once at creation — store it securely).
5. Your endpoint must respond with a 2xx status within 5 seconds, or the delivery is marked failed.

Failed deliveries are retried with exponential backoff up to 5 times over 24 hours, then dropped. You can view delivery history and manually replay failed events from the Webhooks dashboard.

We strongly recommend verifying the HMAC signature on every request to confirm payloads genuinely originate from Northwind Cloud before processing them.

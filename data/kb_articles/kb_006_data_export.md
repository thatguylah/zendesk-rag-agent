---
id: kb_006
title: Exporting your workspace data
category: Data & Privacy
---

Workspace Admins can export all workspace data (projects, tasks, comments, attachments, and user list) at any time.

1. Go to Workspace Settings > Data > Export Workspace Data.
2. Choose the export scope: Full workspace, or a specific project.
3. Choose the format: JSON (full fidelity, recommended for migration) or CSV (tasks and comments only, flattened).
4. Exports are generated asynchronously. For workspaces under 10,000 tasks, this typically completes in under 5 minutes; larger workspaces may take up to an hour.
5. You'll receive an email with a secure, time-limited download link (valid for 72 hours) when the export is ready.

Exports include attachments as a separate .zip of files referenced by ID in the JSON/CSV — attachment files are not embedded inline.

Data exports are logged in the workspace audit log with the requesting admin's identity and timestamp, per our SOC 2 compliance requirements.

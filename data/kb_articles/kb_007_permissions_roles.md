---
id: kb_007
title: Understanding workspace roles and permissions
category: Account & Access
---

Northwind Cloud has four workspace-level roles:

- **Workspace Admin**: full control, including billing, SSO, and data export. Can add/remove other admins.
- **Billing Admin**: can view and manage billing/invoices only; no access to project data settings.
- **Member**: can create and edit projects/tasks they have been given project-level access to.
- **Guest**: limited, external collaborator access to specific projects only; cannot see the full workspace member list or other projects.

Project-level permissions (Owner, Editor, Commenter, Viewer) are layered on top of workspace roles and are set per-project by that project's Owner.

A user's *effective* permission on a project is the more restrictive of their workspace role and their project role — e.g. a workspace Member who is only a project Viewer cannot edit tasks in that project, even though Members can generally edit projects they have access to.

Only Workspace Admins can change another user's workspace role. Project Owners can change project-level roles for members already in the workspace.

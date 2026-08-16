---
id: kb_002
title: Setting up Single Sign-On (SSO) for your workspace
category: Account & Access
---

Northwind Cloud supports SAML 2.0 SSO on the Business and Enterprise plans.

Only a Workspace Admin can configure SSO. To set it up:

1. Go to Workspace Settings > Security > Single Sign-On.
2. Select your identity provider (Okta, Azure AD, Google Workspace, or "Custom SAML").
3. Upload your IdP metadata XML, or manually enter the Entity ID, SSO URL, and X.509 certificate.
4. Northwind Cloud will generate an Assertion Consumer Service (ACS) URL and SP Entity ID — enter these into your identity provider's app configuration.
5. Send a test SSO login to one internal user before enforcing SSO workspace-wide.
6. Once verified, enable "Require SSO for all members" to disable password-based login for the workspace.

Common issue: if users see "SAML response signature invalid," the IdP certificate uploaded to Northwind Cloud does not match the one currently signing assertions — re-download and re-upload the current signing certificate from your IdP.

SSO changes can take up to 10 minutes to propagate across all regions.

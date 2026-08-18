---
name: Restored-user credentials
description: Login behavior after restoring an imported PostgreSQL dump.
---

After restoring an imported database dump, the user rows may be present and active while their passwords do not match credentials previously used in the development workspace.

**Why:** Password hashes are part of the dump, so restoring data also restores the dump's authentication state.

**How to apply:** Verify user presence and authorization separately after every restore. If the user cannot provide the original password, recover access through an explicitly approved admin-password reset or account-creation flow; never store the password in memory.
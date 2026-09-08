---
name: Unicode search on SQLite
description: Why Cyrillic case-insensitive search needs application-level normalization in this project.
---

Do not rely on Django `icontains` for case-insensitive Cyrillic vehicle-name search when the project runs on SQLite. Match normalized strings with Unicode `casefold()` or use a database/collation with verified Unicode behavior.

**Why:** SQLite's default case-insensitive comparison handles ASCII but can fail when Russian text differs only by letter case, producing inconsistent search results across environments.

**How to apply:** Use the shared Unicode-aware vehicle search path for page filters and exports, and include mixed-case Cyrillic examples in regression tests.
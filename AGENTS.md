# GitHub-first project workflow

At the start of project work, read the GitHub default branch or fetch origin before reading project data. Check local status first; never overwrite uncommitted changes or use a destructive reset. In a clean working copy, fast-forward only. If the remote cannot be read, say so and label local data as an offline copy.

Keep all MOMONOKI / 桃鬼 Unreal and Blender work in the MOMONOKI repository. Read codex/README.md for the snapshot index. Source snapshots preserve historical paths and do not assert which version is production-ready.

Keep credentials, session history, local Codex state, caches, logs, virtual environments and binary build outputs out of Git. Stage explicit reviewed paths and run the secret/size gate before publishing. Use sparse, shallow working copies for current work. No automatic deletion or moving of the original user .codex directory; obtain explicit user approval for cleanup.

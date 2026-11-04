# Handover (for any coding agent)

- Read `PROJECT_STATUS.md` first, then `docs/DECISIONS.md`.
- Treat docs as intent, code as truth: inspect the repo and tests before changing anything.
- Do not read from or modify other project folders (especially CellWise-X / IVForge).
- Do not use paid or hosted APIs without explicit owner approval; never commit secrets.
- Keep ngspice/PDK/LLM files in `.tools/` (git-ignored).
- One milestone at a time: implement, test, run, update docs/status, commit. Separate branches for major changes.
- Never report a component complete beyond its true status level (IMPLEMENTED / MOCK-TESTED / NGSPICE-TESTED / VERIFIED).
- Ask before architectural changes.

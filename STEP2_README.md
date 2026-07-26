# Step 2 of 9 — Repeat P0/P1 measured experiment

This package creates session02 and session03 templates and validation tooling. It does not contain fabricated measured binaries. Each session becomes measured evidence only after a new physical acquisition.

Copy the package contents into the repository root, perform the physical target and background captures, then validate each session with:

```powershell
python scripts\validate_repeat_session.py data\measured\challenge-feasibility\session02
python scripts\validate_repeat_session.py data\measured\challenge-feasibility\session03
```

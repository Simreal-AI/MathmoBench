# Contributing

1. Make your change and add or update tests under `tests/`.
2. If you change `configs/protocol.json`, copy it to `src/mathbench/protocol.json`
   (the packaged copy must stay byte-identical; a test enforces this).
3. Regenerate the integrity manifest: `python scripts/update_manifest.py`
4. Run `python verify.py --run-tests` — CI runs the same command on Python 3.11–3.13.
5. Never commit hidden-track families, seeds, bindings, or reference submissions.
   `examples/private/` and `*binding*.json` are git-ignored for this reason.

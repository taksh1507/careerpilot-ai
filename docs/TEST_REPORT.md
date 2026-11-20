# Test report

## Verified results

- The original 67-test baseline remains included in the current suite.
- Full suite in Ubuntu 24.04 WSL2, Python 3.12.3, with the real local Sentence Transformer required: `80 passed in 20.88s`.
- GitHub Actions CI for commit `962049660d4ed7e579a50be1588e20bd4850b382` passed all install, model-cache, compile, and full-test steps in 1m20s: [run 44743628472](https://github.com/taksh1507/careerpilot-ai/actions/runs/44743628472).
- FastAPI integration tests ran as part of that suite; none were skipped.
- Separate real-model integration test also passed: `1 passed in 251.25s` on first model download and initialization.
- `python -m compileall -q adapters api cli filters matching models resume storage verification` passed on Windows Python 3.14.
- Live Uvicorn smoke used temporary WSL databases and a synthetic candidate/job. `/health`, `/ready`, `/api/jobs`, `/api/profile`, `/api/profile/review`, `/api/matches` (POST and GET), and `/` responded successfully. Matching before profile approval returned HTTP 409. After review, the recommendation returned a real `all-MiniLM-L6-v2` semantic score and match history.
- The HTML dashboard route returned HTTP 200 and includes an auto-fit responsive grid. No screenshot or visual browser QA is claimed.

## Windows FastAPI blocker

Python 3.11 and 3.14 are both 64-bit. Tested FastAPI 0.165.0/Pydantic 2.14.4/pydantic-core 2.50.5 and FastAPI 0.115.14/Pydantic 1.10.24. Windows Code Integrity logs (events 3077/3033) state that the native Pydantic extension did not meet enterprise signing requirements. No security policy was bypassed. The API and full test suite were verified using Ubuntu 24.04 WSL2 instead.

## Reproducible test commands

Windows compile check:

```powershell
python -m compileall -q adapters api cli filters matching models resume storage verification
```

Ubuntu 24.04 WSL2 full suite (the model must already be downloaded, or network access must be available):

```bash
JOBCARE_REQUIRE_REAL_MODEL_TEST=1 python -m pytest -q
```

The required-model flag makes missing model files or model execution errors fail rather than silently skip. The standard suite may skip the semantic model test when its weights are not cached. Set `JOBCARE_RUN_REAL_MODEL_TEST=1` to allow downloading the model for the test.

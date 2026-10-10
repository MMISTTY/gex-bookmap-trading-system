# Working with the published repository

The source is published at https://github.com/MMISTTY/gex-bookmap-trading-system and pinned to the owner's profile. The initial publication is commit b2f5f01.

## Existing VS Code checkout

From the project terminal, inspect local changes and retrieve remote updates:

```bash
git status
git pull --ff-only
```

If you have uncommitted work, commit or stash it first. If Git reports divergent history, inspect and reconcile the commits; do not force push or reinitialize the repository.

## New checkout

```bash
git clone https://github.com/MMISTTY/gex-bookmap-trading-system.git
cd gex-bookmap-trading-system
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` in Windows PowerShell, or `source .venv/bin/activate` on macOS/Linux. Select this interpreter in VS Code.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m streamlit run app.py --server.address 127.0.0.1
```

## Publish a reviewed change

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
git status
git add <specific-reviewed-files>
git diff --cached
git commit -m "Describe the verified change"
git push origin main
```

Replace the placeholder with the intended file paths. Review staged content before committing. Private options files belong under ignored `data/private/`; account settings and generated reports belong under ignored `runtime/`. Never commit tokens, credentials, proprietary feeds or account details. Use your normal GitHub authentication; never paste secrets into chat.

The connected application previously permitted reads but denied Contents API writes. Local authenticated Git successfully published the source; browser commits can maintain documentation. This connector limitation does not mean the repository is empty.

See README.md for the daily paper-research workflow and docs/BOOKMAP.md for the unverified Java capture integration.

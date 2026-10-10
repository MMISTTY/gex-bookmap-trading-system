# Publish the prepared source

The public repository MMISTTY/gex-bookmap-trading-system was created, but remains empty.
The connected GitHub application's Contents API denied writes with 403. Browser folder
upload failed and the subsequent file upload was interrupted. No code push is claimed.

Extract the source archive and open its folder in VS Code. Using your own authenticated
Git environment, publish without private runtime or options files:

```bash
git init -b main
git add .
git diff --cached --stat
git commit -m "Add verified GEX and Bookmap paper research MVP"
git remote add origin https://github.com/MMISTTY/gex-bookmap-trading-system.git
git push -u origin main
```

Review staged files before the commit. The project ignore rules exclude runtime,
credentials and data/private. If the repository already has commits when you publish,
fetch and reconcile them first; do not force push. Alternatively, restore write access
to this repository through your GitHub app configuration and resume publication here.
Never paste a token or password into chat.

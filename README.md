# Growth Portfolio — Private Research

Private, password-protected investment research dashboard.

## Setup (GitHub Pages)

1. Push this repo to GitHub (private repo recommended)
2. Go to **Settings → Pages → Source → Deploy from branch** → select `main` / `root`
3. Your site will be live at `https://yourusername.github.io/repo-name/`

## Security

- Client-side SHA-256 password gate (no backend required)
- Password is never stored in plaintext in source code
- Session persists per browser tab only (sessionStorage)
- **Important:** GitHub Pages serves files publicly even from private repos when Pages is enabled. The password gate provides the access control layer.

## Updating Content

Replace `index.html` with updated versions as new analysis is completed. The password gate wraps the report automatically.

## To Change Password

1. Generate new SHA-256 hash: `echo -n 'yournewpassword' | sha256sum`
2. Replace the `HASH` value in the `<script>` section at the bottom of `index.html`

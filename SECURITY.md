# Publication and credential boundaries

Jevision prototype is a loopback-only local app, not an authenticated public service. Each clone supplies its own credentials in an ignored `.env`. TypeSafe authorization is added by Python; credentials are not injected into frontend modules or builds.

Model operations send selected images/crops and questions to TypeSafe. Count automatically analyzes selected photos; HTML preview stays local until validation. See the [tool guides](README.md#tools) for processing details.

## Before creating commits or publishing

```sh
pnpm build
pnpm check:public
git status --short
git diff --cached
```

The check inspects tracked/nonignored candidates, index content, history reachable from branches/tags/current HEAD, and `dist`. It reports locations—not secret values—for known credential patterns, exact configured credentials, personal paths/usernames, private files, external symlinks, and binary content needing review.

It also checks commit-email configuration/history. Before committing, choose your public identity:

```sh
git config --local user.name "YOUR_PUBLIC_DISPLAY_NAME"
git config --local user.email "YOUR_GITHUB_NOREPLY_ADDRESS"
```

Find your address in [GitHub email settings](https://github.com/settings/emails). The check requires a GitHub noreply email; it cannot judge whether your display name identifies you. `pnpm check:public --files-only` defers identity checks without changing Git configuration.

## Keep local data private

`.gitignore` covers credentials, photos/datasets, library metadata, raw evaluations, reports, local agent settings, dependencies, and builds. Store raw runs under `.jev-image-data/` and measured reports in its `private-docs/` directory. Shared skills and portable internal symlinks are public.

Ignores do not remove tracked files or history, and force-adding bypasses them. A passing scan cannot recognize every private image, encoded secret, or unknown credential format. Review staged files and history yourself.

Local tools may create private snapshot refs such as `refs/codex/`. They can retain old content outside normal branch/tag history. Audit them with `pnpm check:public --all-refs --files-only` when needed. Push only the reviewed branch and intended tags; never use `git push --mirror`, copy `.git`, or upload the whole working directory.

If a credential was pushed, revoke/rotate it and remove it from reachable history before republishing. Deleting the latest copy alone is insufficient. GitHub account/profile privacy is separate from repository checks.

## Runtime protections

- Vite and Python bind to loopback; the API rejects nonlocal Host and cross-origin browser requests.
- Vite serves files from `web/`; environment injection, including the usual `VITE_` prefix, is disabled.
- The library API omits absolute photo-root paths, but local image names/relative paths remain visible.
- HTML renders in an offline isolated Chromium context, with external resources and local-file access blocked.

These protections are not public-user authentication. Setup downloads contact upstream dataset hosts; model operations contact TypeSafe. Neither publishes local files to GitHub.

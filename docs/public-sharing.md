# Public sharing

**Status:** Required release procedure
**Last reviewed:** 2026-08-21

The current tree removes known local paths and generated state.

Git history still contains removed files.

Use trusted access until a clean-history release passes this procedure.

## Before release

Confirm these items with the repository owners:

- All retained code and documents can be public.
- Retained notebooks contain no restricted data.
- Hardware names and experiment details can be public.
- Each repository has an acceptable license.
- External application repositories have separate approval.

## Create a clean-history export

Commit the approved cleanup before you create the export.

Create a source archive from the approved commit.

```powershell
git archive --format=zip --output ..\rax-labscript-public.zip HEAD
```

Extract the archive into an empty directory.

Initialize a new Git repository only after the final scan.

Do not copy the old `.git` directory.

## Scan the export

Search for these categories:

- personal paths and user names
- private host names and network addresses
- credentials and access tokens
- generated logs, databases, caches, and editor state
- restricted research data
- obsolete plans, handoffs, and operator notes

Run the installation and test gates from [INSTALL.md](../INSTALL.md).

Publish only the scanned clean-history repository.

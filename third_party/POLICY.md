# Third-Party Component Policy

Legend Lore is proprietary software, but every dependency, binary, model
weight, tokenizer, and other asset shipped with it must use a permissive,
redistributable license.

## Allowed licenses

The default allowlist is Apache-2.0, MIT, ISC, BSD-2-Clause,
BSD-3-Clause, Zlib, HPND, and public-domain dedications. A component outside
this list requires an explicit business and legal decision before it can ship.

AGPL, GPL, LGPL, SSPL, non-commercial, research-only, source-available, and
custom model licenses are not approved by default. This applies equally to
model weights and tokenizers: a permissively licensed inference runtime does
not make restricted model assets distributable.

## Inventory and release gate

`third_party/components.json` is the source of truth for direct shipped
components and model assets. Each entry records its version or revision,
upstream source, SPDX identifier, distribution role, review status, and any
replacement work.

Run `python scripts/check-third-party.py` to validate the inventory.
`python scripts/check-third-party.py --release` refuses while any shipped
component is blocked or awaiting license review. Release builds do not run it
since 2026-09-24: the app is for personal use only, with no distribution
planned, so the AGPL PyMuPDF stack ships as-is. Restore the gate in
`release.yml` before any public or commercial release.

The inventory is intentionally conservative. A `review_required` entry is not
an approval, even if its likely license appears compatible. Before a release,
verify the exact version or model revision and add every required notice.

## Local-only rule

The application must not require a remote service to index, retrieve, rerank,
or answer a query. User-initiated installation of a model asset may download
that static asset, but the installed application must use only locally
available assets at query time.

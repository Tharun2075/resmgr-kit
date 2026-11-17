# Submission checklist

Tick a line only after running its command and reading the output. Save outputs under [evidence](evidence). Replace `<owner>` with the GitHub account that holds the repository.

## T1 Eligibility (owner initials each line)

- [ ] Entrant is 18 or older. Initials: ____
- [ ] Country of residence is not on the contest exclusion list. Initials: ____
- [ ] No tie to the sponsor, the administrator or a judge. Initials: ____
- [ ] One Representative is named for the project. Initials: ____

## Repository and build

- [ ] T2 Repo rules: `gh repo view <owner>/resmgr-kit --json createdAt,isPrivate,licenseInfo` shows createdAt after 2026-11-02T16:00Z, isPrivate false, licence Apache-2.0; the About box shows the licence.
- [ ] T3 Fresh clone: `git clone <url> && cd resmgr-kit && python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/pytest tests/host -q` exits 0 on a clean machine with SDP 8.0 set up per [HOST-SETUP](HOST-SETUP.md); the README names QNX 8.0, QEMU x86_64 and `qcc`.
- [ ] T4 Runs on QNX 8.0: `.venv/bin/resmgr-kit test examples/vsensor/vsensor.yaml` three times; each log has `uname -a` with `QNX` and `8.0` and pytest `passed` with 0 failures.
- [ ] T5 QNX evidence: `grep -l "resmgr_attach\|iofunc_attr_init\|MsgDeliverEvent\|dispatch_create" src/resmgr_kit/templates/*.j2` lists at least 2 files; the Devpost text links those files and the secpol and build-file templates.

## Submission form

- [ ] T6 Video under 3:00 (`yt-dlp --get-duration <url>`), public, plays logged out, shows the QEMU console with `uname -a` printing `QNX noname 8.0.0 ... x86pc x86_64` and the generated `/dev` path working, no music, no third-party logos.
- [ ] T7 Category is exactly "Developer Tooling & Host Tools"; the description says it is a host tool that produces and tests QNX 8.0 software.
- [ ] T8 Codelab: a fresh person on a clean machine follows the codelab URL alone and reaches the final green test in under 30 minutes; the URL is in the Best Codelab field.

## Text and wording

- [ ] T9 Guardrail text: `grep -c "research and demo prototype, not a production product\|QNX Everywhere Non-Commercial licence\|no personal data is collected or stored" README.md` prints 3 or more lines matched; [THIRD-PARTY](../THIRD-PARTY.md) matches `pip freeze`.
- [ ] T10 AI mode (only if the `ai` command is kept): with `LLM_API_KEY` unset, `resmgr-kit gen` and `resmgr-kit test` work and `resmgr-kit ai` prints a clear "no key" message and exits 2. If it is not kept, mark this line n/a.
- [ ] T11 Submitted: Devpost shows "Submitted" by 2026-12-13 23:59 ET; screenshot saved in `docs/evidence/`.
- [ ] T12 Determinism evidence honesty: `docs/evidence/latency.md` reports measured pulse-period jitter on QEMU with the method and the caveat "QEMU, not hardware"; the banned-word greps print nothing: `git grep -niE "certifie[d]|complian[t]|AS[I]L|IEC 6230[4]|CDSC[O]"` and `git grep -nwE "S[I]L|C[E]|FD[A]"` (brackets keep this line from matching itself).
- [ ] T13 Marks: repo name, video and text use "QNX" only descriptively ("for QNX 8.0"); no QNX or BlackBerry logos as own branding; checked by eye.

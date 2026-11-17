"""`resmgr-kit ai`: let a language model write the body of each `impl: ai` region.

gen emits every `impl: ai` handler as a marked stub region. This command asks the
model for the body of that region only, puts it in, builds, deploys and runs the
generated live tests on the target, and feeds compiler errors or failing test
output back, up to --max-iter rounds. Text outside the markers is never changed:
a reply that would change it, or that carries a marker, is refused.

Provider settings come from the environment only:

  LLM_PROVIDER  anthropic (default), openai-compatible or claude-cli
  LLM_API_KEY   required for anthropic and openai-compatible; never printed
  LLM_MODEL     default claude-sonnet-5-5 for anthropic; required for openai-compatible
  LLM_BASE_URL  default https://api.anthropic.com for anthropic; required for openai-compatible

claude-cli needs no key: it pipes the prompt to the locally logged-in Claude Code CLI
(`claude -p --output-format text`, tools off, project settings and MCP servers
ignored, run from an empty folder) and uses its login.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from . import render, runner, spec as specmod

DEFAULT_MODEL = "claude-sonnet-5-5"
NO_KEY = ("LLM_API_KEY is not set, so `resmgr-kit ai` cannot call a model. Set LLM_API_KEY "
          "(and optionally LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL), or add --dry-run to see "
          "the prompt. gen and test do not need a key.")

BEGIN = "/* resmgr-kit:ai-begin {name} */"
END = "/* resmgr-kit:ai-end {name} */"

# QNX 8.0 resource manager rules the body must keep (see research notes, PITFALLS-TECH 15-19).
RULES = """\
- Write C11 for QNX SDP 8.0 (qcc). Output only the statements that go between the markers,
  in one ```c fenced block. No #include, no #define, no new functions, no marker comments.
- Do not touch anything outside the region; use only names already declared in the file.
- devctl: the data area is msg->i.nbytes bytes at `data`, sized for the larger of input and
  output. Reject a short request with `return EINVAL;` when msg->i.nbytes or
  ctp->info.msglen - sizeof(msg->i) is smaller than the input type.
- devctl: copy the input out of `data` with memcpy before writing the reply over it; set
  `nbytes` to the reply size and end with `break;` so the shared code after the switch
  fills msg->o and returns _RESMGR_NPARTS(1). Return an errno (EINVAL, ERANGE, ...) on error.
- write: read the payload with resmgr_msgget() into a bounded buffer, never past BUFSZ;
  call _IO_SET_WRITE_NBYTES(ctp, n) and return _RESMGR_NPARTS(0) on success.
- Use the generated check_<field>() helper for range handling (it clamps or rejects as the
  spec says) and set_<field>() to store; hold state_lock (pthread_mutex_lock/unlock) around
  every access to `st`, and never return with the lock held.
- No dynamic memory, no blocking calls, no printf in the handler."""

SYSTEM = ("You write the body of one QNX 8.0 resource manager handler in C. "
          "Reply with exactly one ```c fenced block and nothing else.")


class AIError(Exception):
    """A setup problem (no key, bad provider settings): exit 2."""


Provider = Callable[[str, str], str]
Checker = Callable[[dict, Path, dict], tuple[int, str]]


# ---- regions -------------------------------------------------------------

def _markers(src: str, name: str) -> tuple[int, int, str]:
    """(start of body, end of body, indent) for region `name`; body excludes the marker lines."""
    b, e = BEGIN.format(name=name), END.format(name=name)
    if src.count(b) != 1 or src.count(e) != 1:
        raise ValueError(f"region {name}: expected one begin and one end marker")
    bi, ei = src.index(b), src.index(e)
    if ei < bi:
        raise ValueError(f"region {name}: end marker before begin marker")
    start = src.index("\n", bi) + 1
    end = src.rindex("\n", 0, ei) + 1
    indent = src[end:ei]
    return start, end, indent


def region_body(src: str, name: str) -> str:
    start, end, _ = _markers(src, name)
    return src[start:end]


# One left-to-right pass, like a C lexer: a "/*" inside a string is not a comment,
# and a quote inside a comment is not a string.
_C_TOKENS = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|/\*.*?\*/|//[^\n]*', re.S)


def _strip_c(text: str) -> str:
    return _C_TOKENS.sub(lambda m: '""' if m.group(0)[0] in "\"'" else " ", text)


def check_body(body: str) -> None:
    """Refuse a body that could reach outside its region."""
    if "resmgr-kit:ai-" in body:
        raise ValueError("the body must not contain region markers")
    if re.search(r"\\[ \t]*\n", body) or "??" in body:
        raise ValueError("the body must not use line continuations or trigraphs")
    code = _strip_c(body)
    if '"' in code.replace('""', "") or "'" in code:
        raise ValueError("the body has an unterminated string or character literal")
    if re.search(r"^\s*#", code, flags=re.M):
        raise ValueError("the body must not contain preprocessor lines")
    if "/*" in code or "*/" in code:
        raise ValueError("the body has an unterminated comment")
    for o, c in ("{}", "()", "[]"):
        depth = 0
        for ch in code:
            depth += (ch == o) - (ch == c)
            if depth < 0:
                break
        if depth != 0:
            raise ValueError(f"unbalanced '{o}{c}' in the body")


def replace_region(src: str, name: str, body: str) -> str:
    """Return src with region `name` holding `body`; everything else byte-identical."""
    check_body(body)
    start, end, indent = _markers(src, name)
    lines = textwrap.dedent(body.strip("\n")).splitlines()
    new_body = "".join((indent + ln).rstrip() + "\n" for ln in lines)
    out = src[:start] + new_body + src[end:]
    if out[:start] != src[:start] or out[start + len(new_body):] != src[end:]:
        raise ValueError("internal: text outside the region changed")
    return out


def extract_code(reply: str) -> str:
    """The first fenced block of the reply (or the whole reply if there is none)."""
    m = re.search(r"```[a-zA-Z]*\n(.*?)```", reply, flags=re.S)
    return (m.group(1) if m else reply).strip("\n") + "\n"


# ---- prompt and providers ------------------------------------------------

def _behaviour(spec: dict, name: str) -> str:
    if name == "io_write":
        return spec["write"]["behaviour"]
    return next(d["behaviour"] for d in spec["devctls"] if d["name"] == name)


def build_prompt(spec_text: str, spec: dict, src: str, name: str, feedback: str = "") -> str:
    parts = [
        f"Fill region {name} of the generated resource manager below.",
        f"Behaviour (from the spec): {_behaviour(spec, name)}",
        "Rules:\n" + RULES,
        "Spec (YAML):\n```yaml\n" + spec_text.rstrip() + "\n```",
        f"Generated C file; the region is between `{BEGIN.format(name=name)}` and "
        f"`{END.format(name=name)}`:\n```c\n" + src.rstrip() + "\n```",
    ]
    if feedback:
        parts.append("Your last body failed. Build or test output (tail):\n```\n"
                     + feedback.rstrip() + "\n```\nFix it.")
    parts.append("Reply with only the body, in one ```c block.")
    return "\n\n".join(parts) + "\n"


def _post(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read(300).decode(errors="replace")
        raise runner.RunError(f"model request failed: HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise runner.RunError(f"model request failed: {e.reason}") from None


def _claude_cli(model: str, env) -> Provider:
    """Provider that pipes the prompt to the logged-in `claude` CLI; no key, no network code here."""
    exe = shutil.which("claude", path=env.get("PATH"))
    if not exe:
        raise AIError("LLM_PROVIDER=claude-cli needs the Claude Code CLI, but no `claude` "
                      "binary is on PATH. Install it and log in once (`claude`), or pick "
                      "another LLM_PROVIDER.")
    # tools off, no project settings or MCP servers, run from an empty folder: text in, text out
    cmd = [exe, "-p", "--output-format", "text", "--tools", "", "--setting-sources", "user",
           "--strict-mcp-config"]
    if model:
        cmd += ["--model", model]

    def call(system: str, prompt: str) -> str:
        try:
            with tempfile.TemporaryDirectory(prefix="resmgr-kit-ai-") as cwd:
                done = subprocess.run(cmd + ["--system-prompt", system], input=prompt,
                                      text=True, capture_output=True, timeout=600, cwd=cwd,
                                      env=dict(env))
        except subprocess.TimeoutExpired:
            raise runner.RunError("model request failed: claude CLI timed out") from None
        if done.returncode != 0:
            detail = (done.stderr or done.stdout).strip()[-300:]
            raise runner.RunError(f"model request failed: claude CLI exit {done.returncode}: "
                                  f"{detail}")
        return done.stdout

    return call


def make_provider(env: dict | None = None) -> tuple[Provider, str]:
    """(call(system, prompt) -> reply text, short description) from LLM_* settings."""
    env = os.environ if env is None else env
    kind = env.get("LLM_PROVIDER") or "anthropic"
    model, base = env.get("LLM_MODEL", ""), env.get("LLM_BASE_URL", "").rstrip("/")
    if kind == "claude-cli":
        return _claude_cli(model, env), f"claude-cli model {model or '(CLI default)'}"
    key = env.get("LLM_API_KEY", "")
    if not key:
        raise AIError(NO_KEY)
    if kind == "anthropic":
        model, base = model or DEFAULT_MODEL, base or "https://api.anthropic.com"

        def call(system: str, prompt: str) -> str:
            data = _post(f"{base}/v1/messages",
                         {"x-api-key": key, "anthropic-version": "2023-06-01"},
                         {"model": model, "max_tokens": 2048, "system": system,
                          "messages": [{"role": "user", "content": prompt}]})
            return "".join(b.get("text", "") for b in data.get("content", []))
    elif kind == "openai-compatible":
        if not model or not base:
            raise AIError("LLM_PROVIDER=openai-compatible needs LLM_MODEL and LLM_BASE_URL")

        def call(system: str, prompt: str) -> str:
            data = _post(f"{base}/chat/completions", {"authorization": f"Bearer {key}"},
                         {"model": model, "messages": [{"role": "system", "content": system},
                                                       {"role": "user", "content": prompt}]})
            return data["choices"][0]["message"]["content"] or ""
    else:
        raise AIError("LLM_PROVIDER must be anthropic, openai-compatible or claude-cli, "
                      f"not {kind!r}")
    return call, f"{kind} model {model}"


# ---- loop ----------------------------------------------------------------

def _diff(old: str, new: str, path: str, limit: int = 60) -> str:
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                      f"a/{path}", f"b/{path}", n=1, lineterm=""))
    if len(lines) > limit:
        lines = lines[:limit] + [f"... ({len(lines) - limit} more diff lines)"]
    return "\n".join(lines)


def _feedback_from(text: str, n: int = 60) -> str:
    keep = [ln for ln in text.splitlines()
            if re.search(r"FAILED|Error|error|assert|^E |passed|failed", ln)]
    return "\n".join((keep or text.splitlines())[-n:])


def run(spec_path: str, outdir: str | None = None, config: str | None = None,
        max_iter: int = 3, dry_run: bool = False, provider: Provider | None = None,
        checker: Checker | None = None) -> int:
    spec = specmod.load(spec_path)
    regions = specmod.ai_regions(spec)
    if not regions:
        raise AIError("the spec has no `impl: ai` handler, so there is nothing to fill")
    spec_text = Path(spec_path).read_text()
    name = spec["name"]
    cfile = f"{name}.c"

    if dry_run:
        src = render.render(spec, Path(spec_path).name)[cfile]
        for r in regions:
            print(f"== prompt for region {r} (dry run, nothing sent)")
            print("-- system --\n" + SYSTEM)
            print("-- user --\n" + build_prompt(spec_text, spec, src, r), end="")
        return 0

    if provider is None:
        provider, desc = make_provider()
        print(f"== model: {desc}", flush=True)
    if max_iter < 1:
        raise AIError("--max-iter must be at least 1")
    cfg = runner.load_config(config)
    out = Path(outdir or Path("build") / name).resolve()
    runner.step(f"gen {spec_path} -> {out}")
    render.write(spec, out, Path(spec_path).name)
    cpath = out / cfile
    src = cpath.read_text()
    checker = checker or runner.check
    feedback = ""

    for it in range(1, max_iter + 1):
        runner.step(f"ai iteration {it}/{max_iter}")
        new = src
        try:
            for r in regions:
                reply = provider(SYSTEM, build_prompt(spec_text, spec, new, r, feedback))
                new = replace_region(new, r, extract_code(reply))
        except ValueError as e:
            feedback = f"the reply was refused: {e}"
            print(f"iteration {it}: REFUSED ({e})", flush=True)
            continue
        print(_diff(src, new, cfile) or "(no change)", flush=True)
        src = new
        cpath.write_text(src)
        try:
            rc, text = checker(spec, out, cfg)
        except runner.RunError as e:
            msg = str(e)
            if not msg.startswith(("build failed", "build did not produce")) \
                    and "did not appear" not in msg:
                raise
            rc, text = 1, msg
        if rc == 0:
            keep = out / "ai_regions"
            keep.mkdir(exist_ok=True)
            for r in regions:
                (keep / f"{r}.c").write_text(region_body(src, r))
            print(f"iteration {it}: PASS, all live tests green. Review the region(s) in {cpath};"
                  f" the bodies are also in {keep}", flush=True)
            return 0
        feedback = _feedback_from(text)
        print(f"iteration {it}: FAIL\n{_feedback_from(text, 12)}", flush=True)

    print(f"not green after {max_iter} iteration(s); the last attempt is left in {cpath} "
          "for review. It has not passed on the target, so do not use it.", flush=True)
    return 1

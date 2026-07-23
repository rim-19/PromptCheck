# PromptCheck

**Catch it when your AI prompt quietly stops working — before your users do.**

Most teams write a prompt, get it working, and move on. But prompts break silently:
a teammate reworks the wording, or the AI provider ships a new model version, and
suddenly the thing that worked for months starts giving wrong answers. Nobody
notices until a customer complains.

PromptCheck treats your prompts like real code: you write test cases for them, run
those tests against any model, and get told the moment something breaks.

Think of it as a quick quiz you give your AI before you trust it. You already know
the right answers. If it aces the quiz, ship it. If it flunks, you find out now —
not after it messes up something that matters.

---

## What it does

- **Test your prompts.** Write down inputs and the answers you expect, in a simple
  file. Run them whenever you want.
- **Check exact *and* fuzzy answers.** Some tests need an exact match. Others just
  need to be "roughly right" — those get graded by another AI acting as a judge.
- **Compare models side by side.** Thinking of switching from one model to another?
  See exactly which tests each one passes and fails first.
- **Notice when things drift.** Save a baseline, then re-run later. PromptCheck
  tells you if the pass rate dropped and *which* tests broke — and flags it if the
  model's version changed, so you know who to blame.
- **Run on autopilot.** Drop it into GitHub so tests run on every change, plus a
  nightly check that opens an issue the moment something regresses.
- **See it at a glance.** A simple web dashboard shows a pass-rate chart over time
  and a clear "what broke" view — no coding needed to read it.

---

## Quick start

You'll need **Python 3.11+** and at least one free API key.

```bash
# 1. install
python -m venv .venv
.venv\Scripts\activate          # Windows  (use: source .venv/bin/activate on Mac/Linux)
pip install -e .

# 2. add a key
#    copy .env.example to .env and paste in a free key:
#    Gemini -> https://aistudio.google.com/apikey
#    Groq   -> https://console.groq.com/keys

# 3. try it
promptcheck init                                  # makes a sample test file
promptcheck run examples/refund_classifier.yaml   # runs it
```

If everything passes you get green ticks. If something fails, PromptCheck exits with
an error — which is exactly what makes it work in automated checks.

---

## Writing a test file

A test file is just readable YAML. Here's the whole idea:

```yaml
name: refund-email-classifier
prompt: |
  Sort this email into one of: refund, bug, question.
  {{ input }}
models:
  - gemini/gemini-flash-lite-latest
  - groq/llama-3.1-8b-instant
judge: gemini/gemini-flash-lite-latest   # grades the "fuzzy" checks
tests:
  - input: "I want my money back!"
    assert:
      - type: equals            # must match exactly
        value: refund
  - input: "Where's my order?"
    assert:
      - type: llm_rubric        # roughly right, judged by the AI
        value: "The label is 'question', not 'refund' or 'bug'."
```

Check types you can use: `equals`, `contains`, `not_contains`, `regex`, and
`llm_rubric` (the AI-judged one).

---

## The commands

Every command takes a single file, a **whole folder**, or a glob — so you can
check one prompt or your entire prompt library in one go.

```bash
promptcheck run <file|folder>          # run the tests, see pass/fail
promptcheck compare <file|folder>      # run across all its models, side by side
promptcheck baseline set <file|folder> # remember how things look right now
promptcheck watch <file|folder>        # re-run and compare to that baseline
promptcheck history <file|folder>      # pass rate over time (little trend chart)
promptcheck serve                      # open the web dashboard
```

### Catching drift (the main point)

```bash
promptcheck baseline set examples/   # save today's behavior for every prompt
promptcheck watch examples/          # later: did anything break?
```

`watch` only complains about **real** regressions — tests that used to pass and
now fail. If the model's version changed too, it says so, so a sudden drop points
straight at the cause. The first `watch` just remembers the current state as the
baseline.

One thing it deliberately does **not** do: if a test couldn't run at all because
the API was rate-limited or the judge call failed, that is reported separately as
"could not evaluate" — never as a regression. A failed network call tells you
nothing about your prompt, and false alarms are how people learn to ignore alerts.

---

## Running it automatically (GitHub)

The project ships a ready GitHub Actions workflow (`.github/workflows/promptcheck.yml`)
that does two things:

1. **On every pull request** that touches your prompts — runs the tests and blocks
   the merge if anything fails.
2. **Every night** — quietly re-runs and **opens a GitHub issue** if something
   regressed. This is your free, always-on watchman for silent model updates.

To turn it on: add your `GEMINI_KEY` and `GROQ_API_KEY` as repository secrets, point
the workflow at your test file, and commit. That's it.

---

## The dashboard

For a visual view anyone can read:

```bash
pip install -e ".[server]"
cd web && npm install && npm run build && cd ..
promptcheck serve            # then open http://127.0.0.1:8000
```

You get a pass-rate chart over time, a list of every run, and a "what changed"
diff view — so a product manager can see "it broke on the 3rd" without asking an
engineer.

---

## What it's built with

Everything here runs on free tiers — no bill to try it.

- **Python** command-line tool (Typer + Rich)
- **Gemini** and **Groq** free API tiers for running the models
- **SQLite** to store history locally
- **FastAPI + React** (Recharts) for the dashboard
- **GitHub Actions** for the automated checks

---

## Running the tests

PromptCheck has its own test suite (no API calls needed):

```bash
pip install -e ".[dev]"
pytest
```

---

## License

MIT — free to use, change, and build on. See [LICENSE](LICENSE).

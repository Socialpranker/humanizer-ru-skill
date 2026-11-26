# humanizer-ru

A [Claude Code](https://claude.com/claude-code) skill for Russian prose that people will read: letters, notes, reports, posts, slides, READMEs. It gives the agent writing rules before the first draft, measures the draft with a deterministic scanner, and edits existing text to remove the tells by which readers recognise a language model, while keeping the author's facts, register and voice.

![Claude Code](https://img.shields.io/badge/Claude_Code-skill-D97757)
![License](https://img.shields.io/badge/license-MIT-1F1F21)

The skill text is in Russian, because the rules are about Russian and were measured on Russian texts. The scanner also has a short English mode for PR descriptions and letters.

## How readers spot a model

The rules follow the order in which readers described noticing generated text: first the look of the document (a title with a subtitle and a date, boilerplate sections such as "Summary" and "Key takeaways", label lines like "Risk: …"), then punctuation (the em dash, and the colon a model puts in its place once dashes are banned), then the opening phrases ("not X but Y", announcements like "there are two reasons"), then filler. A blind reader on Opus still called otherwise clean texts machine-written because of their structure and their endings, so the skill also covers how a text is built: the main point first and in detail, no grid of equal parts, names and numbers from the source material instead of generalisations.

## What the agent does with it

There are two modes. For a new text the agent reads `references/generation.md` before drafting, writes, runs the scanner, fixes what it finds in at most two rounds, and for text going to an outside reader hands the draft to a context-free subagent that lists empty sentences and broken links between sentences. For an existing text the agent works as an editor: it scans the text, fixes the paragraphs where three or more markers cluster, then compares before and after so that no number or name is lost.

A single marker is not evidence. Most of them occur in human writing too, so the agent edits a paragraph when three or more appear together. The exceptions are tells that human corpora almost never contain (chatbot phrases, "не просто X, а Y", unnamed "experts say"), which are fixed on the first hit.

## What is inside

- `SKILL.md` holds the two modes, the editing order and the limits: what not to touch (code, quotes, legal wording, conversational text) and why chasing a zero score makes text sterile.
- `references/generation.md` is the one page the agent reads before writing, with rules and good and bad examples per genre.
- `references/patterns.md` is the marker catalogue with calibration tables: how often each marker fires in human texts (Habr, CyberLeninka, Lenta.ru, company annual reports) and in Claude's texts.
- `references/style.md` covers normative Russian style: verbs instead of nominalisations, government of prepositions, theme and rheme.
- `references/evaluation.md` describes how to check a batch of texts without human readers: style metrics against a human reference corpus, and a blind judge with a control set.
- `scripts/slop_scan.py` is the scanner, standard library only. It reads `.md`, `.txt`, `.html`, `.docx`, `.pptx` and, with `pdftotext` installed, `.pdf`.
- `scripts/human_eval.py` runs the evaluation from `evaluation.md`.
- `agents/human-reader.md` is a subagent that reads a batch as an ordinary addressee and says, text by text, whether a person or a model wrote it.
- `hooks/` holds two optional hooks described below, and `evals/` has trigger cases and behaviour scenarios for testing the skill itself.

## Install

```bash
git clone https://github.com/Socialpranker/humanizer-ru-skill ~/.claude/skills/humanizer-ru
```

The scanner needs Python 3 and nothing else. Try it on any file:

```bash
python3 ~/.claude/skills/humanizer-ru/scripts/slop_scan.py draft.md
python3 ~/.claude/skills/humanizer-ru/scripts/slop_scan.py --compare before.md after.md
```

Useful flags: `--genre legal|tech|science|business|news` mutes markers that are normal for the genre (officialese in a contract, for example), `--foreign` applies the softer limits for someone else's text, and `--lang en` runs the English check.

To use the blind reader, copy `agents/human-reader.md` to `~/.claude/agents/`.

### Hooks

The skill works without hooks, but in practice the agent sometimes forgets to scan its own output. Two hooks close that gap; both need `python3` and never fail the tool call they wrap.

`humanizer-postwrite.sh` runs after a document is written (Edit, Write, or a Bash command that builds a `.docx`, `.pptx` or HTML deck), scans it and tells the agent what to fix. On the next write of the same file it reports before and after, and lost numbers and names.

`humanizer-outbound.sh` runs before text leaves the machine: an email draft, a Claude artifact, a GitHub PR, issue or release body sent through `gh`, or long text typed in a browser. On a hard tell it denies the call with the reason. Sending the same text a second time within an hour passes, so a quote or text the user dictated goes through unchanged.

Add them to `~/.claude/settings.json`. The outbound matcher below lists the tool names of Gmail-style connectors, Claude artifacts and the browser tools; adjust it to the tools you have.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/skills/humanizer-ru/hooks/humanizer-postwrite.sh" }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "^(mcp__.+__(send_message|create_draft|update_draft|reply|forward)|mcp__claude-artifacts__(publish_version|edit_version|publish_files)|mcp__claude-in-chrome__(computer|browser_batch|form_input))$",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/skills/humanizer-ru/hooks/humanizer-outbound.sh" }]
      },
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/skills/humanizer-ru/hooks/humanizer-outbound.sh" }]
      }
    ]
  }
}
```

Both hooks keep their state in `~/.claude/logs/`.

## Tests

```bash
python3 -B -m unittest discover -s scripts/tests
bash hooks/tests/test-humanizer-outbound.sh
bash hooks/tests/test-humanizer-postwrite.sh
```

A test checks that every scanner label is documented in `references/patterns.md`, so a new marker needs a line there.

## Limits

The research behind the thresholds is not in this repository, because its corpora consist of other people's texts. Paths such as `research/…` and `PLAN-redesign.md` in the references point to it and are kept so the numbers have a stated origin. For `human_eval.py` you need your own reference corpus: a JSONL file with one human text per line in a `text` field, at least 20 texts of the same genre.

The marker list goes stale. Models move away from phrases that give them away and people pick them up, so the date of the list is in `references/patterns.md`. The scanner is a set of regular expressions: it helps a reader, it does not replace one, and passing it does not make text undetectable by AI detectors, which is not the goal.

Sources the catalogue builds on include [blader/humanizer](https://github.com/blader/humanizer), [hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop), [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru), [chipizubovdima/stop-slop-ru](https://github.com/chipizubovdima/stop-slop-ru), Wikipedia's "Signs of AI writing" and the papers cited in the references.

## License

MIT

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What I want

I forked this repo from github to make a product of mine.

## What this repo is

video-use is an agent **skill**, not an application. `SKILL.md` is the runtime instruction set an agent follows when editing a user's footage; `helpers/*.py` are the standalone CLI scripts it calls. `install.md` is the first-time setup procedure for end users. There is no build step, no console entry point, and no package — helpers are run as `uv run --project <repo> python <repo>/helpers/<name>.py`. `--project` matters: agents run helpers from the user's footage folder, where a bare `uv run` or plain `python` can't see the repo's `.venv/` and fails with `ModuleNotFoundError`.

When changing behavior, keep `SKILL.md` (and `README.md` where relevant) in sync with the helpers: SKILL.md documents helper flags, defaults (e.g. the subtitle `SUB_FORCE_STYLE`, `chunk_words` rules), and the EDL format, and agents trust it over the code.

## Commands

```bash
uv sync                                                               # deps pinned in uv.lock, installed to .venv/
uv run python -m unittest discover -s tests                           # all tests
uv run python -m unittest tests.test_render_fps                       # one file
uv run python -m unittest tests.test_render_fps.ParseFpsTests         # one class
```

There is no linter or formatter configured. Runtime requires `ffmpeg`/`ffprobe` on PATH; transcription requires `ELEVENLABS_API_KEY` (env var, or `.env` at the repo root — see `.env.example`). Transcription calls cost real money; don't run them to verify changes.

## Architecture

Pipeline: **transcribe → pack → (LLM picks cuts) → EDL → render → self-eval**. All session artifacts go to `<videos_dir>/edit/`, never inside this repo.

- `transcribe.py` — extracts mono 16 kHz audio, calls ElevenLabs Scribe (verbatim, diarized, word-level, audio events), writes raw JSON to `edit/transcripts/<stem>.json`. Cached: skips if the file exists. Selects an audio track and refuses to upload silent audio. `transcribe_batch.py` imports `transcribe_one` from it and runs a thread pool.
- `pack_transcripts.py` — turns `transcripts/*.json` into `takes_packed.md`, phrase lines broken on silence ≥ 0.5 s or speaker change. This is the agent's primary reading view.
- `timeline_view.py` — filmstrip + waveform + word-label PNG for a time range; on-demand drill-down only.
- `grade.py` — ffmpeg color grade: auto mode (bounded per-clip correction from sampled frame stats), named presets, or raw `--filter`. `render.py` imports `get_preset` / `auto_grade_for_clip` from it via a sibling import with a no-op fallback.
- `render.py` — the core. Reads `edl.json` and enforces the render-order hard rules from SKILL.md:
  1. Per-segment extract with grade + 30 ms audio fades baked in (handles HDR, rotation-aware portrait detection, source fps preserved unless `--fps`).
  2. Lossless `-c copy` concat into a base file.
  3. One final filtergraph: overlays shifted with `setpts=PTS-STARTPTS+T/TB`, then `subtitles` applied **last**.
  4. Optional two-pass loudnorm.
  `--build-subtitles` builds `master.srt` from the cached transcripts using output-timeline offsets (`word.start - segment_start + segment_offset`) and phrase-aware `chunk_words` chunking. A missing subtitles file is an error, not a silent skip.

Helpers import each other by bare module name (`from transcribe import ...`, `from grade import ...`), so they must stay as siblings in `helpers/` and be run from there by path. Tests load `helpers/render.py` with `importlib.util.spec_from_file_location` rather than importing a package, and mock `subprocess` instead of invoking ffmpeg.

`skills/manim-video/` is a vendored sub-skill, read only when an animation slot uses Manim.

## Invariants worth protecting

The 12 "Hard Rules" in `SKILL.md` are production-correctness constraints that `render.py` implements (subtitles last, per-segment extract + copy concat, 30 ms fades, PTS-shifted overlays, output-timeline SRT offsets, word-boundary cuts, transcript caching, outputs only in `<videos_dir>/edit/`). Changes to `render.py` or the transcribe helpers must not break them.

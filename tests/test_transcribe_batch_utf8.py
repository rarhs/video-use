import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HELPERS_DIR = Path(__file__).parents[1] / "helpers"

# Runs transcribe_batch.main() in a child process with Scribe stubbed out, so the
# stdout reconfigure at import time and the progress print are the real ones.
DRIVER = """
import sys
sys.path.insert(0, sys.argv[1])
import transcribe_batch as tb

def fake_transcribe_one(video, edit_dir, **kwargs):
    out = tb.transcript_path(edit_dir, video)
    out.write_text("{}")
    return out

tb.transcribe_one = fake_transcribe_one
tb.load_api_key = lambda: "test-key"
sys.argv = ["transcribe_batch.py", sys.argv[2]]
tb.main()
"""


class ProgressLineEncodingTests(unittest.TestCase):
    def test_non_ascii_name_survives_legacy_codepage(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "café.mp4").write_bytes(b"")
            env = dict(os.environ)
            # cp1252 is what Windows gives a piped stdout; force it on every OS so
            # this fails anywhere if the UTF-8 reconfigure in transcribe_batch is lost.
            env["PYTHONIOENCODING"] = "cp1252"
            env.pop("PYTHONUTF8", None)
            proc = subprocess.run(
                [sys.executable, "-c", DRIVER, str(HELPERS_DIR), tmp],
                capture_output=True,
                env=env,
            )
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            # main() catches per-file errors, so an encode failure shows up as a
            # "FAILED" line on stdout and exit code 1, not a traceback on stderr.
            self.assertEqual(proc.returncode, 0, stdout + stderr)
            self.assertIn("+ café  →  café.json", stdout)
            self.assertTrue((Path(tmp) / "edit" / "transcripts" / "café.json").exists())


if __name__ == "__main__":
    unittest.main()

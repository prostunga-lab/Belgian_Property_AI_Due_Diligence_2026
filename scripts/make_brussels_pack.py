"""Write the fictional Brussels test pack (PDF) to ./pack-bruxelles/{coherent,problematique}. Usage: python scripts/make_brussels_pack.py [outdir]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.brussels_fixtures import COHERENT, PROBLEM  # noqa: E402
from tests.fixtures import pdf  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "pack-bruxelles")
for name, docs in (("coherent", COHERENT), ("problematique", PROBLEM)):
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    for fn, text in docs.items():
        (d / fn).write_bytes(pdf(text))
print(f"pack written to {out}")

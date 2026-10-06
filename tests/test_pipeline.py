from app.classify import classify
from app.extract import extract
from app.rules import DocView, run_rules
from app.scoring import score
from tests.fixtures import ASB, DEED, ELEC, EPC


def views():
    out = []
    for i, (name, txt) in enumerate([("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC)], 1):
        pages = [txt]
        t, _ = classify(pages, name)
        out.append(DocView(i, name, t, pages, extract(t, pages)))
    return out


def test_classification():
    assert [v.doc_type for v in views()] == ["deed", "epc", "asbestos", "electrical"]


def test_extraction_has_sources():
    v = {d.doc_type: d for d in views()}
    assert v["deed"].fields["surface_m2"]["value"] == 185
    assert v["epc"].fields["surface_m2"]["value"] == 240
    assert v["epc"].fields["extension_m2"]["value"] == 32
    assert v["asbestos"].fields["asbestos_present"]["value"] is True
    assert v["electrical"].fields["electrical_conform"]["value"] is False
    assert v["deed"].fields["cadastral_ref"]["value"] == "A 123/B"
    assert all(f["page"] == 1 and f["excerpt"] for d in v.values() for f in d.fields.values())


def test_rules_detect_known_issues():
    ids = {f.rule_id for f in run_rules(views())}
    assert {"X-SURFACE", "ASB-PRESENT", "ELEC-NONCONFORM", "ELEC-OLD", "EPC-POOR", "URB-EXT-NOPERMIT"} <= ids
    assert ids & {"DOC-EPC", "DOC-ASBESTOS", "DOC-ELECTRICAL", "DOC-DEED"} == set()  # only the soil attest is absent here


def test_missing_docs_and_score():
    docs = [d for d in views() if d.doc_type == "deed"]
    fs = run_rules(docs)
    assert {"DOC-EPC", "DOC-ASBESTOS", "DOC-ELECTRICAL"} <= {f.rule_id for f in fs}
    s = score(type("X", (), {}) and [type("F", (), {"kind": f.kind, "severity": f.severity, "domain": f.domain})() for f in run_rules(views())])
    assert s["level"] == "high" and 0 <= s["overall"] <= 100

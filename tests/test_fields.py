"""Offline contract checks for Markdown extraction, storage, and batch isolation."""

import copy
import hashlib
import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from doclayout.field_store import FieldStore
from doclayout.fields import compact, extract_fields, ground_records, load_definition
from doclayout.ui.batch import (
    load_conversion,
    process_batch,
    process_file,
    retry_fields,
)


def blank(schema):
    kind = schema["type"]
    if kind == "object":
        return {key: blank(value) for key, value in schema["properties"].items()}
    if kind == "array":
        return []
    return None


def payload():
    schema = load_definition().schema["properties"]["records"]["items"]["properties"][
        "fields"
    ]
    fields = blank(schema)
    fields["member"]["member_id"] = "00042"
    return {
        "records": [
            {
                "fields": fields,
                "evidence": [
                    {"field_path": "/member/member_id", "quote": "Member ID: 00042"}
                ],
                "issues": [],
            }
        ],
        "document_issues": [],
    }


def client_for(*values):
    responses = [
        SimpleNamespace(
            status="completed", output=[], output_text=json.dumps(value), usage=None
        )
        for value in values
    ]
    return SimpleNamespace(
        responses=SimpleNamespace(create=Mock(side_effect=responses))
    )


def chunks():
    return {
        "blocks": [
            {
                "id": "page/0/Text/1",
                "page": 0,
                "html": "<p>Member ID: 00042</p>",
                "bbox": [10, 10, 90, 30],
            }
        ],
        "page_info": {"0": {"bbox": [0, 0, 100, 100]}},
    }


def test_markdown_only_one_call_and_grounding():
    definition = load_definition(enabled=False)
    client = client_for(payload())
    usage = []
    result = extract_fields(
        "Member ID: 00042", chunks(), definition, client=client, usage=usage
    )
    assert result["status"] == "success"
    assert result["classification"] == {"status": "disabled"}
    assert client.responses.create.call_count == 1
    request = client.responses.create.call_args.kwargs
    assert request["input"][1] == {"role": "user", "content": "Member ID: 00042"}
    assert request["model"] == "gpt-6-sol" and request["reasoning"] == {
        "effort": "medium"
    }
    assert request["store"] is False and "tools" not in request
    assert result["records"][0]["evidence"][0]["locations"][0]["page"] == 1
    assert len(usage) == 1
    assert usage[0]["model"] == "gpt-6-sol"


@pytest.mark.parametrize(
    "score,status,calls",
    [
        (0.7499, "fallout", 1),
        (0.75, "success", 2),
        (0.9, "success", 2),
        (float("nan"), "fallout", 1),
    ],
)
def test_classification_threshold(score, status, calls):
    definition = replace(
        load_definition(), enabled=True, categories=("target", "other"), target="target"
    )
    classified = {
        "category": "target",
        "score": score,
        "ambiguous": False,
        "reason": "matched",
        "quotes": ["Member ID: 00042"],
    }
    client = client_for(classified, payload())
    result = extract_fields("Member ID: 00042", chunks(), definition, client=client)
    assert result["status"] == status and client.responses.create.call_count == calls
    request = client.responses.create.call_args_list[0].kwargs
    assert request["model"] == "gpt-6-luna"
    assert request["reasoning"] == {"effort": "medium"}
    assert request["input"][1] == {"role": "user", "content": "Member ID: 00042"}
    assert request["text"]["format"]["strict"] is True
    schema = request["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(classified)
    assert schema["properties"]["quotes"]["maxItems"] == 1
    if status == "fallout":
        assert "score" in result["document_issues"][0]
    if calls == 2:
        extracted = client.responses.create.call_args_list[1].kwargs
        assert extracted["model"] == "gpt-6-sol"
        assert extracted["reasoning"] == {"effort": "medium"}


@pytest.mark.parametrize(
    "updates,status",
    [
        ({"category": "other"}, "classified_no_extraction"),
        ({"category": None}, "fallout"),
        ({"ambiguous": True}, "fallout"),
        ({"quotes": ["invented"]}, "fallout"),
        ({"quotes": []}, "fallout"),
        ({"quotes": [" "]}, "fallout"),
        ({"reason": "unknown"}, "fallout"),
        ({"reason": "ambiguous"}, "fallout"),
        ({"reason": "insufficient_evidence"}, "fallout"),
    ],
)
def test_classification_routing(updates, status):
    definition = replace(
        load_definition(), enabled=True, categories=("target", "other"), target="target"
    )
    classified = {
        "category": "target",
        "score": 0.99,
        "ambiguous": False,
        "reason": "matched",
        "quotes": ["Member ID: 00042"],
        **updates,
    }
    client = client_for(classified)
    result = extract_fields("Member ID: 00042", chunks(), definition, client=client)
    assert result["status"] == status and client.responses.create.call_count == 1
    assert result["document_issues"]
    assert all(issue.endswith(".") for issue in result["document_issues"])


@pytest.mark.parametrize(
    "updates",
    [
        {"reason": "A free-text explanation"},
        {"category": "not-configured"},
        {"quotes": ["Member ID: 00042", "Member ID: 00042"]},
        {"explanation": "Extra property"},
        {"score": 1.1},
    ],
)
def test_classification_rejects_invalid_json_contract(updates):
    definition = replace(
        load_definition(), enabled=True, categories=("target",), target="target"
    )
    classified = {
        "category": "target",
        "score": 0.99,
        "ambiguous": False,
        "reason": "matched",
        "quotes": ["Member ID: 00042"],
        **updates,
    }
    client = client_for(classified)
    result = extract_fields("Member ID: 00042", chunks(), definition, client=client)
    assert result["status"] == "failed" and not result["records"]
    assert client.responses.create.call_count == 1


def test_classification_template_and_snapshot(tmp_path, monkeypatch):
    from doclayout.fields import DEFINITIONS

    for path in DEFINITIONS.iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    before = load_definition(tmp_path, enabled=False)
    with pytest.raises(ValueError, match="Classification needs"):
        load_definition(tmp_path, enabled=True)
    (tmp_path / "classification.md").write_text(
        "## Extraction target\ntarget\n## Categories\n### target\nRequest form\n### other\nOther document\n",
        encoding="utf-8",
    )
    assert not load_definition(tmp_path, enabled=False).enabled
    configured = load_definition(tmp_path, enabled=True)
    assert (
        configured.categories == ("target", "other") and configured.target == "target"
    )
    assert configured.version != before.version
    for definition in (load_definition(tmp_path, enabled=False), configured):
        legacy_snapshot = compact(
            [
                definition.prompt,
                definition.schema,
                definition.classification,
                definition.enabled,
                "fields-v1",
            ]
        )
        legacy_version = hashlib.sha256(legacy_snapshot.encode()).hexdigest()
        assert definition.version != legacy_version
    disabled_version = load_definition(tmp_path, enabled=False).version
    monkeypatch.setattr("doclayout.fields.CLASSIFICATION_MODEL", "changed-model")
    assert load_definition(tmp_path, enabled=False).version == disabled_version
    assert load_definition(tmp_path, enabled=True).version != configured.version


def test_extraction_model_and_effort_are_snapshotted(monkeypatch, tmp_path):
    definition = load_definition(enabled=False)
    monkeypatch.setattr("doclayout.fields.EXTRACTION_MODEL", "another-model")
    changed_model = load_definition(enabled=False)
    assert changed_model.version != definition.version
    monkeypatch.setattr("doclayout.fields.EXTRACTION_REASONING_EFFORT", "high")
    assert load_definition(enabled=False).version != changed_model.version
    client = client_for(payload())
    usage = []
    outcome = extract_fields(
        "Member ID: 00042", chunks(), definition, client=client, usage=usage
    )
    assert client.responses.create.call_args.kwargs["model"] == "gpt-6-sol"
    assert client.responses.create.call_args.kwargs["reasoning"] == {"effort": "medium"}
    assert usage[0]["model"] == "gpt-6-sol"
    store = FieldStore(tmp_path)
    document_id = "d" * 64
    store.save_document(document_id, "example.pdf", {})
    old_id = store.save_result(
        document_id,
        replace(definition, extraction_model="gpt-6-luna", version="historical-luna"),
        outcome,
        [],
    )
    new_id = store.save_result(document_id, definition, outcome, usage)
    assert store.run(old_id)["records"][0]["model"] == "gpt-6-luna"
    saved = store.run(new_id)["records"][0]
    assert saved["model"] == "gpt-6-sol" and saved["reasoning_effort"] == "medium"
    exported = json.loads(
        (
            store.document_dir(document_id) / "runs" / new_id / "example_001.json"
        ).read_text("utf-8")
    )
    assert exported == saved


@pytest.mark.parametrize("reason", ["Historical free-text reason.", "matched"])
def test_saved_classifications_remain_readable(tmp_path, reason):
    store = FieldStore(tmp_path)
    document_id = "a" * 64
    store.save_document(document_id, "source.pdf", {})
    classification = {
        "category": "other",
        "score": 0.9,
        "ambiguous": False,
        "reason": reason,
        "quotes": ["Source quote"],
    }
    run_id = store.save_result(
        document_id,
        load_definition(),
        {
            "status": "classified_no_extraction",
            "records": [],
            "document_issues": ["Category is outside the extraction target."],
            "classification": classification,
        },
        [],
    )
    assert (
        FieldStore(tmp_path).run(run_id)["result"]["classification"] == classification
    )


@pytest.mark.parametrize(
    "change", ["quote", "path", "missing", "ambiguous", "geometry"]
)
def test_bad_evidence_requires_review(change):
    value, blocks = payload(), chunks()
    if change == "quote":
        value["records"][0]["evidence"][0]["quote"] = "invented"
    elif change == "path":
        value["records"][0]["evidence"][0]["field_path"] = "/missing"
    elif change == "missing":
        value["records"][0]["evidence"] = []
    elif change == "ambiguous":
        blocks["blocks"].append(copy.deepcopy(blocks["blocks"][0]))
    else:
        blocks["blocks"][0]["bbox"] = [0, 0, float("nan"), 10]
    result = ground_records(value, "Member ID: 00042", blocks)
    assert result["records"][0]["status"] == "needs_review"
    assert result["records"][0]["issues"]


def test_table_quote_and_false_value():
    value = payload()
    value["records"][0]["evidence"][0]["quote"] = "| Member ID: | 00042 |"
    blocks = chunks()
    blocks["blocks"][0]["html"] = (
        "<table><tr><td>Member ID:</td><td>00042</td></tr></table>"
    )
    result = ground_records(value, "| Member ID: | 00042 |", blocks)
    assert result["records"][0]["status"] == "success"
    blocks["blocks"][0]["page"] = 19
    result = ground_records(payload(), "Member ID: 00042", blocks)
    assert result["records"][0]["evidence"][0]["locations"][0]["page"] == 1
    value = payload()
    value["records"][0]["fields"]["expedited_requested"] = False
    result = ground_records(value, "Member ID: 00042", chunks())
    assert any(
        i["field_path"] == "/expedited_requested"
        for i in result["records"][0]["issues"]
    )


def test_rejected_quote_has_one_warning_and_preserves_independent_issues():
    value = payload()
    record = value["records"][0]
    record["evidence"][0]["quote"] = "Invented quote"
    record["evidence"].append(copy.deepcopy(record["evidence"][0]))
    record["issues"] = [
        {"field_path": "/member/member_id", "reason": "Unresolved source conflict."}
    ]
    record["fields"]["member"]["first_name"] = "Sam"
    result = ground_records(value, "Member ID: 00042", chunks())
    issues = copy.deepcopy(result["records"][0]["issues"])
    assert issues == [
        {"field_path": "/member/member_id", "reason": "Unresolved source conflict."},
        {
            "field_path": "/member/member_id",
            "reason": "Evidence quote/path does not match source Markdown.",
        },
        {
            "field_path": "/member/first_name",
            "reason": "Populated field has no verified source quote.",
        },
    ]
    assert (
        ground_records(result, "Member ID: 00042", chunks())["records"][0]["issues"]
        == issues
    )
    assert result["records"][0]["status"] == "needs_review"


@pytest.mark.parametrize("exact", [True, False])
def test_html_quotes_must_preserve_tag_order(exact):
    source = "<p><u><strong>Code</strong></u>:<br/>00042</p>"
    blocks = chunks()
    blocks["blocks"][0]["html"] = source
    value = payload()
    quote = "Code</strong></u>:<br/>00042"
    value["records"][0]["evidence"][0]["quote"] = (
        quote if exact else quote.replace("</strong></u>", "</u></strong>")
    )
    record = ground_records(value, source, blocks)["records"][0]
    assert record["evidence"][0]["verified"] is exact
    assert len(record["issues"]) == (0 if exact else 1)


@pytest.mark.parametrize("include_role", [True, False])
def test_role_headings_disambiguate_participation(include_role):
    roles = {
        "referring_provider": "Referring provider",
        "servicing_provider": "Servicing provider",
        "servicing_facility": "Servicing facility",
    }
    value = payload()
    record = value["records"][0]
    record["fields"]["member"]["member_id"] = None
    record["evidence"] = []
    blocks = chunks()
    blocks["blocks"] = []
    markdown = []
    for index, (key, label) in enumerate(roles.items()):
        row = f"| {label} | Participating: | ■ | Nonparticipating: | □ |"
        markdown.append(row)
        blocks["blocks"].append(
            {
                "id": f"/page/0/Table/{index}",
                "bbox": [0, index * 20, 100, index * 20 + 10],
                "html": f"<table><tr><td>{label}</td><td>Participating:</td><td>■</td><td>Nonparticipating:</td><td>□</td></tr></table>",
            }
        )
        record["fields"][key]["participation_status"] = "Participating"
        record["evidence"].append(
            {
                "field_path": f"/{key}/participation_status",
                "quote": row
                if include_role
                else "Participating: | ■ | Nonparticipating: | □",
            }
        )
    result = ground_records(value, "\n\n".join(markdown), blocks)["records"][0]
    assert len(result["issues"]) == (0 if include_role else 3)
    assert all(item["verified"] for item in result["evidence"])
    if include_role:
        assert [e["locations"][0]["block_id"] for e in result["evidence"]] == [
            f"/page/0/Table/{i}" for i in range(3)
        ]


@pytest.mark.parametrize("support_first", [True, False])
def test_priority_prompt_and_synthetic_evidence_contract(support_first):
    # Mocked responses test the prompt/input and grounding contract, not LLM reasoning.
    primary = "Prior Authorization Request Form\nToday's date: 04/01/2025\nDate/date range of service: 05/02/2025\nMember ID: 00042\nReferring phone: 111-222-3333\nServicing provider: Same As Above"
    support = "Precertification Form\nDate Initiated: 04/03/2025\nProvider phone: 444-555-6666\nContact: Jamie Brown\nAddress: 12 Oak Avenue West, Suite 3\nFacility: Central Hospital (formerly North Hospital)"
    pages = [support, primary] if support_first else [primary, support]
    source = "\n\n".join(pages)
    value = payload()
    record = value["records"][0]
    record["fields"]["request"]["request_date"] = "05/02/2025"
    for role in ("referring_provider", "servicing_provider"):
        record["fields"][role]["phone"] = "111-222-3333"
        record["evidence"].append(
            {"field_path": f"/{role}/phone", "quote": "Referring phone: 111-222-3333"}
        )
    record["evidence"].extend(
        [
            {
                "field_path": "/request/request_date",
                "quote": "Date/date range of service: 05/02/2025",
            },
            {
                "field_path": "/servicing_provider/phone",
                "quote": "Servicing provider: Same As Above",
            },
        ]
    )
    blocks = {
        "blocks": [
            {
                "id": f"/page/{i}/Text/1",
                "html": f"<p>{page}</p>",
                "bbox": [0, 0, 100, 90],
            }
            for i, page in enumerate(pages)
        ],
        "page_info": {str(i): {"bbox": [0, 0, 100, 100]} for i in range(2)},
    }
    definition = load_definition(enabled=False)
    client = client_for(value)
    result = extract_fields(source, blocks, definition, client=client)
    assert result["status"] == "success"
    sent = client.responses.create.call_args.kwargs
    assert sent["input"][1]["content"] == source
    prompt = sent["input"][0]["content"]
    for rule in (
        "not by page order",
        "requested service date",
        "Use the fuller stated contact name",
        "Retain the primary form's name",
        "copy those resolved fields",
        "Never guess corrections",
    ):
        assert rule in prompt
    assert (
        "Never today's date"
        in definition.schema["properties"]["records"]["items"]["properties"]["fields"][
            "properties"
        ]["request"]["properties"]["request_date"]["description"]
    )


def test_oversize_and_response_failures():
    client = client_for(payload())
    result = extract_fields(
        "long", {}, replace(load_definition(), max_input_bytes=1), client=client
    )
    assert result["status"] == "needs_review" and not client.responses.create.called
    for status, text, output in [
        ("incomplete", "{}", []),
        ("completed", "not json", []),
        ("completed", "{}", []),
        (
            "completed",
            "{}",
            [SimpleNamespace(content=[SimpleNamespace(type="refusal")])],
        ),
    ]:
        client.responses.create.side_effect = None
        client.responses.create.return_value = SimpleNamespace(
            status=status, output_text=text, output=output, usage=None
        )
        result = extract_fields(
            "Member ID: 00042", chunks(), load_definition(), client=client
        )
        assert result["status"] in {"failed", "needs_review"} and not result["records"]
    client.responses.create.side_effect = ValueError("private secret source")
    result = extract_fields("text", {}, load_definition(), client=client)
    assert "secret" not in json.dumps(result)


def test_sqlite_ten_columns_multi_records_and_export_retry(tmp_path, monkeypatch):
    store = FieldStore(tmp_path)
    document_id = "a" * 64
    store.save_document(document_id, "Original File.pdf", {})
    value = payload()
    value["records"].append(copy.deepcopy(value["records"][0]))
    grounded = ground_records(value, "Member ID: 00042", chunks())
    grounded.update(status="success", classification={"status": "disabled"})
    run_id = store.save_result(document_id, load_definition(), grounded, [])
    run = store.run(run_id)
    assert [r["name"] for r in run["records"]] == [
        "Original File_001",
        "Original File_002",
    ]
    with store.connection() as db:
        assert len(db.execute("PRAGMA table_info(extraction_results)").fetchall()) == 10
    directory = store.document_dir(document_id) / "runs" / run_id
    for record in run["records"]:
        assert (
            json.loads((directory / (record["name"] + ".json")).read_text("utf-8"))
            == record
        )
    with monkeypatch.context() as patch:
        patch.setattr("doclayout.field_store.atomic_write", Mock(side_effect=OSError))
        assert store.export_run(run_id)
    assert store.export_run(run_id) is None
    assert len(FieldStore(tmp_path).run(run_id)["records"]) == 2


def test_pipeline_reuses_conversion_and_retry(
    tmp_path, temp_doc, model_dict, extraction_service, monkeypatch
):
    data = Path(temp_doc.name).read_bytes()
    definition = load_definition()
    client = client_for({"records": [], "document_issues": ["No request"]})
    first = process_file(
        "source.pdf",
        data,
        {"page_range": "0-0"},
        model_dict,
        definition,
        root=tmp_path / "store",
        client=client,
    )
    assert "run_id" in first
    second = process_file(
        "source.pdf",
        data,
        {"page_range": "0-0"},
        model_dict,
        definition,
        root=tmp_path / "store",
        client=client,
    )
    assert second["reused"] and extraction_service.call_count == 1
    store = FieldStore(tmp_path / "store")
    upload, result = load_conversion(store, first["document_id"])
    assert upload.count == 2 and result["markdown"] and result["zip"]
    forbidden = Mock(side_effect=AssertionError("Field retry must not reconvert"))
    monkeypatch.setattr("doclayout.layout.get_layout_engine", forbidden)
    monkeypatch.setattr("doclayout.ui.batch.get_layout_engine", forbidden)
    monkeypatch.setattr("doclayout.ui.batch.run_document", forbidden)
    retry_fields(
        store,
        first["document_id"],
        definition,
        client=client_for({"records": [], "document_issues": ["Still no request"]}),
    )
    assert extraction_service.call_count == 1 and len(store.runs()) == 2
    forbidden.assert_not_called()


@pytest.mark.parametrize("historical", ["legacy-sol-only", "sol-layout-v3/v1"])
def test_new_prior_conversion_preserves_historical_save(
    tmp_path, temp_doc, model_dict, extraction_service, monkeypatch, historical
):
    from doclayout import layout

    data = Path(temp_doc.name).read_bytes()
    definition = load_definition()
    outcome = {"records": [], "document_issues": ["No request"]}
    root = tmp_path / "store"
    options = {"page_range": "0-0"}
    # Seed a historical fixture, not production artifacts.
    with monkeypatch.context() as old:
        old.setattr(layout, "PIPELINE", historical)
        first = process_file(
            "source.pdf",
            data,
            options,
            model_dict,
            definition,
            root=root,
            client=client_for(outcome),
        )
    assert "run_id" in first
    store = FieldStore(root)
    info = store.document(first["document_id"])
    if historical == "legacy-sol-only":
        info["manifest"].pop("pipeline")
        store.save_document(first["document_id"], "source.pdf", info["manifest"])
    directory = store.document_dir(first["document_id"])
    before = {
        p.relative_to(directory): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }
    saved_manifest = store.document(first["document_id"])
    current = process_file(
        "source.pdf",
        data,
        options,
        model_dict,
        definition,
        root=root,
        client=client_for(outcome),
    )
    assert "run_id" in current and current["document_id"] != first["document_id"]
    assert extraction_service.call_count == 2
    assert before == {
        p.relative_to(directory): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }
    assert store.document(first["document_id"]) == saved_manifest
    again = process_file(
        "source.pdf",
        data,
        options,
        model_dict,
        definition,
        root=root,
        client=client_for(outcome),
    )
    assert again["reused"] and extraction_service.call_count == 2
    forbidden = Mock(side_effect=AssertionError("Saved field retry invoked conversion"))
    monkeypatch.setattr("doclayout.layout.get_layout_engine", forbidden)
    monkeypatch.setattr("doclayout.ui.batch.get_layout_engine", forbidden)
    monkeypatch.setattr("doclayout.ui.batch.run_document", forbidden)
    _, restored = load_conversion(store, first["document_id"])
    assert restored["pipeline"] == historical
    retry_fields(store, first["document_id"], definition, client=client_for(outcome))
    forbidden.assert_not_called()
    # A field retry adds a run but leaves the conversion source untouched.
    assert (directory / "raw.md").read_bytes() == before[Path("raw.md")]
    assert (directory / "chunks.json").read_bytes() == before[Path("chunks.json")]
    for image in [
        *restored["images"].values(),
        *restored["annotations"]["pages"].values(),
    ]:
        image.close()


def test_batch_concurrency_and_failure_isolation(monkeypatch, tmp_path):
    from doclayout.ui import batch

    active = maximum = 0
    lock = threading.Lock()

    def work(name, *args, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return {"filename": name, "status": "failed" if name == "bad" else "success"}

    monkeypatch.setattr(batch, "process_file", work)
    results = list(
        process_batch(
            [(name, b"") for name in ["a", "b", "bad", "d", "e"]],
            {},
            {},
            load_definition(),
            root=tmp_path,
        )
    )
    assert len(results) == 5 and maximum == 3
    assert sum(r["status"] == "success" for r in results) == 4


def test_duplicate_jobs_do_not_repeat_calls(
    tmp_path, temp_doc, model_dict, extraction_service, monkeypatch
):
    extract = Mock(
        return_value={
            "status": "needs_review",
            "records": [],
            "document_issues": ["No requests"],
            "classification": {"status": "disabled"},
        }
    )
    monkeypatch.setattr("doclayout.ui.batch.extract_fields", extract)
    data = Path(temp_doc.name).read_bytes()
    results = list(
        process_batch(
            [("same.pdf", data)] * 4,
            {"page_range": "0-0"},
            model_dict,
            load_definition(),
            root=tmp_path / "store",
        )
    )
    assert len({r["run_id"] for r in results}) == 1
    assert extraction_service.call_count == 1 and extract.call_count == 1


def test_same_filename_different_documents_keep_distinct_exports(tmp_path):
    store = FieldStore(tmp_path)
    outcome = ground_records(payload(), "Member ID: 00042", chunks())
    outcome.update(status="success", classification={"status": "disabled"})
    ids = []
    for document_id in ("a" * 64, "b" * 64):
        store.save_document(document_id, "source.pdf", {})
        run_id = store.save_result(document_id, load_definition(), outcome, [])
        ids.append(store.run(run_id)["records"][0]["id"])
        assert (
            store.document_dir(document_id) / "runs" / run_id / "source_001.json"
        ).exists()
    assert len(set(ids)) == 2

from engine.content_diff import diff_locks


def test_diff_packs_added_removed():
    old = {
        "packs": [{"id": "core", "version": "1.0"}],
        "overrides": {},
        "content_files": {}
    }
    new = {
        "packs": [{"id": "core", "version": "1.0"}, {"id": "mod", "version": "0.1"}],
        "overrides": {},
        "content_files": {}
    }

    diff = diff_locks(old, new)
    assert len(diff["packs"]["added"]) == 1
    assert diff["packs"]["added"][0]["id"] == "mod"
    assert len(diff["packs"]["removed"]) == 0

    diff_rev = diff_locks(new, old)
    assert len(diff_rev["packs"]["removed"]) == 1
    assert diff_rev["packs"]["removed"][0]["id"] == "mod"

def test_diff_pack_version_changed():
    old = {
        "packs": [{"id": "core", "version": "1.0"}],
        "overrides": {},
        "content_files": {}
    }
    new = {
        "packs": [{"id": "core", "version": "1.1"}],
        "overrides": {},
        "content_files": {}
    }

    diff = diff_locks(old, new)
    assert len(diff["packs"]["version_changed"]) == 1
    change = diff["packs"]["version_changed"][0]
    assert change["id"] == "core"
    assert change["old"] == "1.0"
    assert change["new"] == "1.1"

def test_diff_overrides():
    old = {
        "packs": [],
        "overrides": {"a": "b"},
        "content_files": {}
    }
    new = {
        "packs": [],
        "overrides": {"a": "c", "x": "y"},
        "content_files": {}
    }

    diff = diff_locks(old, new)
    assert diff["overrides"]["total_delta"] == 1 # 2 - 1
    assert "x" in diff["overrides"]["added"]
    assert len(diff["overrides"]["changed"]) == 1
    assert diff["overrides"]["changed"][0]["key"] == "a"

def test_diff_content_files():
    old = {
        "packs": [],
        "overrides": {},
        "content_files": {"f1": "h1"}
    }
    new = {
        "packs": [],
        "overrides": {},
        "content_files": {"f1": "h2", "f2": "h3"}
    }

    diff = diff_locks(old, new)
    assert "f1" in diff["content_files"]["changed"]
    assert "f2" in diff["content_files"]["added"]

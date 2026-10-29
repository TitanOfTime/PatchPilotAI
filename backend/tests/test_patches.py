from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from app import patches
from app.safety import git


@pytest.fixture
def pinned_repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "money.py").write_text("def cents(x):\n    return round(x * 100)\n")
    git(["init"], root)
    git(["add", "."], root)
    git(["-c", "user.name=Fixture", "-c", "user.email=fixture@localhost", "commit", "-m", "seed"], root)
    sha = git(["rev-parse", "HEAD"], root)

    @contextmanager
    def fake_session():
        yield SimpleNamespace(get=lambda *_: SimpleNamespace(sha=sha))

    monkeypatch.setattr(patches, "repo_root", lambda _: root)
    monkeypatch.setattr(patches, "session", fake_session)
    monkeypatch.setattr(patches, "DATA", tmp_path)
    return root


def test_real_unified_diff_application_without_modifying_original(pinned_repo):
    result = patches.validate_edits(
        "fixture", [{"path": "money.py", "old": "round(x * 100)", "new": "int(x * 100 + 0.5)"}], {"money.py"}
    )
    assert result["validation"] == "git apply --check passed"
    assert "+    return int" in result["diff"]
    assert "round(x * 100)" in (pinned_repo / "money.py").read_text()


@pytest.mark.parametrize("path", ["../money.py", ".env", "build.gradle", "unrelated.py"])
def test_patch_scope_rejections(pinned_repo, path):
    with pytest.raises(ValueError):
        patches.validate_edits("fixture", [{"path": path, "old": "round(x * 100)", "new": "0"}], {"money.py"})


def test_patch_ambiguous_original_is_rejected(pinned_repo):
    with pytest.raises(ValueError, match="exactly once"):
        patches.validate_edits(
            "fixture", [{"path": "money.py", "old": "missing content", "new": "0"}], {"money.py"}
        )

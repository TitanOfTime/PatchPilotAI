import pytest
from app.indexing import chunk_source
from app.safety import eligible, github_url, safe_path, secret_content


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://github.com@evil.com/a/b",
        "https://github.com/a/b?x=1",
        "https://localhost/a/b",
        "https://github.com/a/../b",
        "https://github.com/a/b/tree/main",
        "file:///etc/passwd",
        "https://github.com:443/a/b",
    ],
)
def test_url_rejects_unsafe_inputs(url):
    with pytest.raises(ValueError):
        github_url(url)


def test_url_normalization():
    assert (
        github_url("https://github.com/TitanOfTime/TestBankingApp.git/")[0]
        == "https://github.com/TitanOfTime/TestBankingApp"
    )


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "/etc/passwd",
        "C:/Windows/file",
        ".git/config",
        ".env",
        "app/.env.local",
        "..\\secret",
        "foo/../../secret",
    ],
)
def test_path_containment(tmp_path, path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, path)


def test_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside-test"
    outside.mkdir(exist_ok=True)
    try:
        (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError):
        safe_path(tmp_path, "escape/file.java")


@pytest.mark.parametrize(
    "path",
    [
        "node_modules/x.ts",
        ".git/config",
        ".env",
        "backend/.env.local",
        "target/Foo.java",
        "package-lock.json",
        "bundle.min.js",
    ],
)
def test_index_filters(path):
    assert not eligible(path)


def test_secret_detection():
    assert secret_content("-----BEGIN RSA PRIVATE KEY-----")
    assert secret_content("AIza" + "a" * 35)
    assert not secret_content("public class PaymentService {}")


def test_java_chunks_keep_exact_lines_and_declarations():
    source = "package demo;\nclass Bank {\n  int balance() {\n    return 1;\n  }\n}\n"
    chunks = list(chunk_source("Bank.java", source))
    assert any("int balance()" in c["content"] for c in chunks)
    for chunk in chunks:
        assert chunk["content"] == "\n".join(source.splitlines()[chunk["start_line"] - 1 : chunk["end_line"]])


def test_large_windows_overlap():
    source = "\n".join(str(i) for i in range(200))
    chunks = list(chunk_source("data.py", source))
    assert chunks[0]["end_line"] == 80
    assert chunks[1]["start_line"] == 65

from pathlib import Path

import pytest

from docfunnel.sources import FetchPolicy, SourceError, fetch_url, open_source, sniff_suffix

from helpers import REPO_ROOT, US_RECEIPT, DocServer

PDF = (REPO_ROOT / "examples" / "invoice_multipage.pdf").read_bytes()
LOCAL = FetchPolicy(allow_private_hosts=True)  # the test server runs on 127.0.0.1


# ---- local paths and bytes -------------------------------------------------------------


def test_local_path_is_used_in_place(tmp_path: Path) -> None:
    path = tmp_path / "receipt.txt"
    path.write_text(US_RECEIPT)
    with open_source(str(path)) as resolved:
        assert resolved.path == path
        assert resolved.name == "receipt"
        assert resolved.origin == str(path)


def test_local_path_errors(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="file not found"):
        open_source(str(tmp_path / "missing.pdf")).__enter__()
    (tmp_path / "notes.docx").write_bytes(b"x")
    with pytest.raises(SourceError, match=r"unsupported file type '\.docx'"):
        open_source(str(tmp_path / "notes.docx")).__enter__()
    with pytest.raises(SourceError, match="local files are disabled"):
        open_source("x.pdf", FetchPolicy(allow_local_files=False)).__enter__()


def test_base_dir_confines_local_paths(tmp_path: Path) -> None:
    inside = tmp_path / "inbox"
    inside.mkdir()
    (inside / "r.txt").write_text(US_RECEIPT)
    (tmp_path / "secret.txt").write_text("secret")
    policy = FetchPolicy(base_dir=inside)
    with open_source("r.txt", policy) as resolved:
        assert resolved.path == (inside / "r.txt").resolve()
    with pytest.raises(SourceError, match="must stay inside"):
        open_source("../secret.txt", policy).__enter__()
    with pytest.raises(SourceError, match="must stay inside"):
        open_source(str(tmp_path / "secret.txt"), policy).__enter__()


def test_bytes_go_to_a_temporary_file_that_is_removed() -> None:
    with open_source(PDF) as resolved:
        assert resolved.path.suffix == ".pdf"
        assert resolved.path.read_bytes() == PDF
        assert resolved.origin == "<bytes>"
        temporary = resolved.path
    assert not temporary.exists()


@pytest.mark.parametrize(
    ("data", "suffix"),
    [
        (b"%PDF-1.7\n", ".pdf"),
        (b"\x89PNG\r\n\x1a\n....", ".png"),
        (b"\xff\xd8\xff\xe0....", ".jpg"),
        (b"II*\x00....", ".tiff"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", ".webp"),
        (b"BM\x36\x00\x0c\x00\x00\x00\x00\x00", ".bmp"),
        (b"BMW Service Center\nTOTAL 12.00", ".txt"),  # starts with "BM", but is text
        ("Café 1,50 €".encode(), ".txt"),
    ],
)
def test_sniff_suffix(data: bytes, suffix: str) -> None:
    assert sniff_suffix(data) == suffix


def test_unknown_binary_is_rejected() -> None:
    with pytest.raises(SourceError, match="unknown document type"):
        sniff_suffix(b"\x00\x01\x02\xff\xfe")


def test_other_url_schemes_are_rejected() -> None:
    with pytest.raises(SourceError, match="unsupported URL scheme"):
        open_source("ftp://example.com/a.pdf").__enter__()
    with pytest.raises(SourceError, match="unsupported URL scheme"):
        open_source("file:///etc/passwd").__enter__()


# ---- URLs ---------------------------------------------------------------------------


def test_private_hosts_are_blocked_by_default(doc_server: DocServer) -> None:
    url = doc_server.serve("/invoice.pdf", PDF)
    with pytest.raises(SourceError, match="non-public address"):
        fetch_url(url)


def test_url_download_with_suffix_from_the_path(doc_server: DocServer) -> None:
    url = doc_server.serve("/files/invoice%20march.pdf", PDF)
    with open_source(url, LOCAL) as resolved:
        assert resolved.path.suffix == ".pdf"
        assert resolved.path.read_bytes() == PDF
        assert resolved.name == "invoice march"
        assert resolved.origin == url


def test_url_suffix_from_content_type_then_from_content(doc_server: DocServer) -> None:
    typed = doc_server.serve("/download?id=7", PDF, headers={"Content-Type": "application/pdf"})
    untyped = doc_server.serve(
        "/blob", US_RECEIPT.encode(), headers={"Content-Type": "application/octet-stream"}
    )
    with open_source(typed, LOCAL) as resolved:
        assert resolved.path.suffix == ".pdf"
    with open_source(untyped, LOCAL) as resolved:
        assert resolved.path.suffix == ".txt"


def test_redirects_are_followed_and_checked(doc_server: DocServer) -> None:
    target = doc_server.serve("/real.pdf", PDF)
    hop = doc_server.serve("/go", b"", status=302, headers={"Location": "/real.pdf"})
    body, _, final = fetch_url(hop, LOCAL)
    assert body == PDF
    assert final == target

    elsewhere = target.replace("127.0.0.1", "localhost")
    doc_server.serve("/away", b"", status=301, headers={"Location": elsewhere})
    pinned = FetchPolicy(allow_private_hosts=True, allowed_hosts=frozenset({"127.0.0.1"}))
    with pytest.raises(SourceError, match="'localhost' is not in the allowed hosts"):
        fetch_url(doc_server.base + "/away", pinned)


def test_redirect_loops_stop(doc_server: DocServer) -> None:
    loop = doc_server.serve("/loop", b"", status=302, headers={"Location": "/loop"})
    with pytest.raises(SourceError, match="too many redirects"):
        fetch_url(loop, FetchPolicy(allow_private_hosts=True, max_redirects=2))


def test_size_limit_from_header_and_while_streaming(doc_server: DocServer) -> None:
    declared = doc_server.serve("/big.pdf", PDF)
    streamed = doc_server.serve("/stream.pdf", PDF, headers={"X-Stream": "1"})
    small = FetchPolicy(allow_private_hosts=True, max_bytes=1000)
    with pytest.raises(SourceError, match="larger than the 1,000-byte limit"):
        fetch_url(declared, small)
    with pytest.raises(SourceError, match="larger than the 1,000-byte limit"):
        fetch_url(streamed, small)


def test_http_errors_and_disabled_urls(doc_server: DocServer) -> None:
    with pytest.raises(SourceError, match="HTTP 404"):
        fetch_url(doc_server.base + "/missing.pdf", LOCAL)
    with pytest.raises(SourceError, match="URL input is disabled"):
        fetch_url(doc_server.base + "/x.pdf", FetchPolicy(allow_urls=False))

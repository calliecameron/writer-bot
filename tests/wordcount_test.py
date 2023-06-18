import subprocess


def test_no_args() -> None:
    assert subprocess.call(["bin/wordcount.sh"]) != 0


def test_one_arg() -> None:
    assert subprocess.call(["bin/wordcount.sh", "testdata/test.txt"]) != 0


def test_bad_content_type() -> None:
    assert subprocess.call(["bin/wordcount.sh", "testdata/test.txt", "foo"]) != 0


def test_txt() -> None:
    p = subprocess.run(
        ["bin/wordcount.sh", "testdata/test.txt", "text/plain"],
        capture_output=True,
        check=True,
        encoding="utf-8",
    )
    assert p.stdout.strip() == "4"


def test_pdf() -> None:
    p = subprocess.run(
        ["bin/wordcount.sh", "testdata/test.pdf", "application/pdf"],
        capture_output=True,
        check=True,
        encoding="utf-8",
    )
    assert p.stdout.strip() == "230"

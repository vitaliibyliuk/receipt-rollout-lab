"""Reconstruct a verified archive using byte-identical portions of a cached archive."""

import gzip
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path


def tar_spans(raw, offset=0, nested=True):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
        for item in tar:
            if not item.isfile() or item.size < 512:
                continue
            start = item.offset_data
            data = raw[start:start + item.size]
            children = []
            if nested and item.name.startswith("blobs/sha256/") and item.size > 10240:
                try:
                    children = list(tar_spans(data, offset + start, nested=False))
                except tarfile.ReadError:
                    pass
            yield offset + start, item.size, hashlib.sha256(data).hexdigest(), children


def create(basis, source, folder):
    index = {}
    for start, size, digest, children in tar_spans(basis):
        index[size, digest] = start
        for child_start, child_size, child_digest, _ in children:
            index[child_size, child_digest] = child_start

    spans = []
    for start, size, digest, children in tar_spans(source):
        if (size, digest) in index:
            spans.append([start, size, index[size, digest]])
        else:
            spans.extend([at, length, index[length, digest]]
                         for at, length, digest, _ in children if (length, digest) in index)
    spans.sort()
    remaining = io.BytesIO()
    cursor = 0
    for start, length, _ in spans:
        assert start >= cursor
        remaining.write(source[cursor:start])
        cursor = start + length
    remaining.write(source[cursor:])
    folder.mkdir(exist_ok=True)
    (folder / "transfer.json").write_text(json.dumps({
        "basis_sha256": hashlib.sha256(basis).hexdigest(),
        "target_sha256": hashlib.sha256(source).hexdigest(),
        "spans": spans,
    }, separators=(",", ":")))
    (folder / "transfer.bin.gz").write_bytes(gzip.compress(remaining.getvalue(), compresslevel=1))
    print(f"Reused {sum(size for _, size, _ in spans):,} of {len(source):,} bytes")


def restore(basis, folder, output):
    recipe = json.loads((folder / "transfer.json").read_text())
    assert hashlib.sha256(basis).hexdigest() == recipe["basis_sha256"]
    remaining = io.BytesIO(gzip.decompress((folder / "transfer.bin.gz").read_bytes()))
    offset = 0
    digest = hashlib.sha256()
    with output.open("wb") as restored:
        def emit(data):
            restored.write(data)
            digest.update(data)
        for start, length, old in recipe["spans"]:
            emit(remaining.read(start - offset))
            emit(basis[old:old + length])
            offset = start + length
        emit(remaining.read())
    assert digest.hexdigest() == recipe["target_sha256"]


if __name__ == "__main__":
    mode, base, second, third = sys.argv[1:]
    basis = gzip.decompress(Path(base).read_bytes())
    if mode == "create":
        create(basis, gzip.decompress(Path(second).read_bytes()), Path(third))
    else:
        restore(basis, Path(second), Path(third))

#!/usr/bin/env bash
set -euo pipefail

artifact=$1
environment=$2
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
archive_tag="$(cat "$artifact/release.txt")"
case "$archive_tag" in
    v1.0.0|v1.0.0-ci) release=v1.0.0;;
    v2.0.0) release=v2.0.0;;
    *) printf 'Unknown release %s\n' "$archive_tag" >&2; exit 2;;
esac
image="receipt-lab:$release"
archive_image="receipt-lab:$archive_tag"

python3 - "$artifact" <<'PY'
import hashlib
import sys
from pathlib import Path

folder = Path(sys.argv[1])
expected = (folder / "image.sha256").read_text().split()[0]
with (folder / "image.tar.gz").open("rb") as archive:
    actual = hashlib.file_digest(archive, "sha256").hexdigest()
if actual != expected:
    raise SystemExit("Image archive checksum mismatch")
print(f"SHA-256 OK {actual}")
PY
docker load -i "$artifact/image.tar.gz"
id="$(docker image inspect --format '{{.Id}}' "$archive_image")"
if [[ "$id" != "$(cat "$artifact/image-id.txt")" ]]; then
    printf 'Image ID mismatch for %s\n' "$image" >&2
    exit 1
fi
if [[ "$archive_image" != "$image" ]]; then docker tag "$archive_image" "$image"; fi
printf 'Image ID OK %s %s\n' "$archive_tag" "$id"

opts=(--no-build --pull never --wait --wait-timeout 25 -d)
case "$environment" in
    staging)
        STAGING_IMAGE="$image" docker compose -f "$root/compose.yaml" -p receipt-stage up "${opts[@]}" stage
        ;;
    working)
        case "$release" in
            v1.0.0) service=v1;;
            v2.0.0) service=v2;;
        esac
        docker compose -f "$root/compose.yaml" -p receipt-work up "${opts[@]}" "$service"
        ;;
    *)
        printf 'Use staging or working\n' >&2
        exit 2
        ;;
esac

"""Fetch the openly licensed versioned archive with bounded, verified HTTP ranges."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import math
import time
import urllib.request
import zipfile

URL = "https://zenodo.org/api/records/15814468/files/Dataset_Aalborg.zip/content"
SIZE = 390936036
MD5 = "18f16d53a10f1b89d1dbcbfc5c89bc3d"


def file_hash(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_archive(path):
    path = Path(path)
    if path.stat().st_size != SIZE or file_hash(path, "md5") != MD5:
        raise ValueError("Archive size/MD5 does not match the versioned Zenodo deposit")


def fetch(destination):
    """Four concurrent connections; no protected data or authentication required."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "Dataset_Aalborg.zip"
    if archive.exists():
        verify_archive(archive)
    else:
        parts = destination / ".download-parts"
        parts.mkdir(exist_ok=True)
        width = math.ceil(SIZE / 16)

        def one_part(i):
            start, end = i * width, min((i + 1) * width, SIZE) - 1
            target = parts / f"{i:02d}.part"
            if target.exists() and target.stat().st_size == end - start + 1:
                return target
            for attempt in range(3):
                try:
                    request = urllib.request.Request(URL, headers={
                        "Range": f"bytes={start}-{end}",
                        "User-Agent": "Open-TMS-EEG-reanalysis/1.0",
                    })
                    with urllib.request.urlopen(request, timeout=180) as response:
                        expected = f"bytes {start}-{end}/{SIZE}"
                        if response.status != 206 or response.headers.get("Content-Range") != expected:
                            raise ValueError("Server did not honor the exact public HTTP byte range")
                        content = response.read()
                    if len(content) != end - start + 1:
                        raise ValueError("Incomplete archive range")
                    target.write_bytes(content)
                    return target
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)

        with ThreadPoolExecutor(max_workers=4) as pool:
            paths = list(pool.map(one_part, range(16)))
        temporary = destination / "Dataset_Aalborg.zip.partial"
        with temporary.open("wb") as handle:
            for path in paths:
                handle.write(path.read_bytes())
        verify_archive(temporary)
        temporary.replace(archive)

    with zipfile.ZipFile(archive) as handle:
        expected = {"Dataset_Aalborg/"} | {f"Dataset_Aalborg/S{i:02d}_epo.fif" for i in range(1, 23)}
        if set(handle.namelist()) != expected:
            raise ValueError("Unexpected archive members; refusing extraction")
        if handle.testzip() is not None:
            raise ValueError("ZIP CRC verification failed")
        # The exact allowed names above exclude traversal and unrelated files.
        handle.extractall(destination)
    return archive, destination / "Dataset_Aalborg"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", default="data/raw")
    args = parser.parse_args()
    print(fetch(args.destination))

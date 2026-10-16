"""Download the hash-pinned Linux x64 CPU runtime and 2B model (about 1.3 GB)."""

import argparse
import hashlib
import tarfile
import urllib.request
from pathlib import Path

DOWNLOADS = (
    ("llama-b11687-bin-ubuntu-x64.tar.gz",
     "https://github.com/ggml-org/llama.cpp/releases/download/b11687/llama-b11687-bin-ubuntu-x64.tar.gz",
     "97f18b24b251bef2d0f28e0a767a7e08f07368d7b45df0009f41551fceaecfd1"),
    ("Qwen3.5-2B-Q4_K_M.gguf",
     "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/f6d5376be1edb4d416d56da11e5397a961aca8ae/Qwen3.5-2B-Q4_K_M.gguf",
     "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"),
)


def verify(path, expected):
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime_dir)
    runtime.mkdir(parents=True, exist_ok=True)
    for name, url, digest in DOWNLOADS:
        destination = runtime / name
        if not destination.exists():
            partial = runtime / (name + ".partial")
            with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
                while chunk := response.read(4 * 1024 * 1024):
                    output.write(chunk)
            verify(partial, digest)
            partial.replace(destination)
        verify(destination, digest)
        print(name, "hash verified", flush=True)
        if name.endswith(".tar.gz"):
            with tarfile.open(destination) as archive:
                archive.extractall(runtime, filter="data")


if __name__ == "__main__":
    main()

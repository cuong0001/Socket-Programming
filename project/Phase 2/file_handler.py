import hashlib
import os

CHUNK_SIZE = 4096

def read_chunks(filepath, start_offset = 0):
    with open(filepath, "rb") as f:
        f.seek(start_offset)
        offset = start_offset
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            yield offset, chunk
            offset += len(chunk)

def sha256_file(filepath) -> bytes:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.digest()

def sha256_incremental():
    return hashlib.sha256()

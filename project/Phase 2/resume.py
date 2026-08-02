import os, json, time

PART_SUFFIX = ".part" # Extension for incomplete data files during transfer
SIDECAR_SUFFIX = ".part.json" # Extension for the metadata sidecar used for resume validation

def sidecar_path(storage_dir: str, filename: str) -> str:
    return os.path.join(storage_dir, filename + SIDECAR_SUFFIX)

def write_sidecar(storage_dir: str, filename: str, total_size: int, sha256: bytes) -> None:
    # Prepare metadata dictionary for resume validation
    data = {
        "total_size": total_size,
        "expected_sha256": sha256.hex() if sha256 else "",
        "timestamp": time.time(),
        "protocol_version": 2,
    }

    # Atomic write: Save to a temporary file first, then replace to prevent corruption on crash
    target_path = sidecar_path(storage_dir, filename)
    tmp_path = target_path + ".tmp"
    
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    os.replace(tmp_path, target_path)

def validate_sidecar(storage_dir: str, filename: str, total_size: int, sha256: bytes) -> bool:
    """
    Returns True if the sidecar file exists and its metadata matches the current transfer request.
    If it doesn't match (e.g. file changed on server), we must discard the staging file and restart.
    """
    try:
        with open(sidecar_path(storage_dir, filename), encoding="utf-8") as f:
            meta = json.load(f)
        # TTL check: Discard the staging file if it is older than 7 days (604800 seconds)
        old_timestamp = meta.get("timestamp", 0)
        if time.time() - old_timestamp > 604800:
            print(f"[WARN] Staging file for {filename} has expired. Forcing full restart.")
            return False
        # Verify if total size and expected hash match the original file
        size_ok = meta.get("total_size") == total_size
        hash_ok = (not sha256) or meta.get("expected_sha256") == sha256.hex()
        
        return size_ok and hash_ok
    except (OSError, KeyError, json.JSONDecodeError, ValueError) as e:
        # Log the exact reason why sidecar validation failed for easier debugging
        print(f"[ERROR] Invalid or corrupted sidecar for {filename}. Reason: {e}")
        return False

def get_upload_offset(storage_dir: str, filename: str) -> int:
    # Returns the current size of the incomplete .part file on the server
    part = os.path.join(storage_dir, filename + PART_SUFFIX)
    return os.path.getsize(part) if os.path.exists(part) else 0

def get_download_offset(download_dir: str, filename: str) -> int:
    # Returns the current size of the incomplete .part file on the client
    part = os.path.join(download_dir, filename + PART_SUFFIX)
    return os.path.getsize(part) if os.path.exists(part) else 0

def commit_download(download_dir: str, filename: str) -> None:
    # Renames the .part file to the actual filename upon successful transfer completio
    os.replace(
        os.path.join(download_dir, filename + PART_SUFFIX),
        os.path.join(download_dir, filename)
    )

def cleanup_staging(storage_dir: str, filename: str) -> None:
    # Deletes both the .part and sidecar files if a checksum mismatch occurs
    for suffix in (PART_SUFFIX, SIDECAR_SUFFIX):
        try:
            os.remove(os.path.join(storage_dir, filename + suffix))
        except OSError:
            # Ignore error if the file does not exist
            pass
        
# Phase 2 File Transfer Protocol (Mini-RFC)

Status: implemented by `protocol.py`, `client.py`, `server.py`, and
`session.py`.

## 1. Scope and conventions

This protocol runs over TCP and provides login, per-user file namespaces,
binary upload/download, offset-based resume, checksums, deletion, and
structured errors. TCP is a byte stream, so every application packet uses a
length prefix. Receivers must call `recv_exact`/`read_packet`; they must not
assume that one `send` corresponds to one `recv`.

All integer fields are unsigned and use network byte order (big-endian).
Sizes and offsets count bytes. SHA-256 values are the raw 32 digest bytes,
not hexadecimal text. Binary file data is never decoded as text and may
contain `0x00`.

Notation:

- `u16`, `u32`, `u64`: unsigned 2-, 4-, and 8-byte integers.
- `text`: `byte_length:u16 + UTF-8 bytes`.
- `sha256`: exactly 32 raw bytes when present.
- `data`: arbitrary binary bytes.

## 2. Packet framing

Every packet has this layout:

```text
  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                         LENGTH:u32                            |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |          OPCODE:u16           |          USER_ID:u16          |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                     PAYLOAD (variable) ...                    |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

`LENGTH` counts all bytes after the four-byte length field:

```text
LENGTH = 2 (opcode) + 2 (user_id) + payload length
```

Therefore, an empty-payload packet has `LENGTH=4` and occupies eight bytes on
the wire. The implementation rejects a body larger than 1 MiB. Individual
file chunks are 4096 bytes in the current client and server.

Before login, the client sends `USER_ID=0`. A successful LOGIN response
assigns a non-zero ID. Every later client packet must carry that ID; a
mismatch receives `USER_ID_MISMATCH`.

## 3. Opcode table

| Name | Hex | Direction | Payload |
|---|---:|---|---|
| `LOGIN` | `0x01` | C -> S | `username:text` |
| `LOGOUT` | `0x02` | C -> S | empty |
| `FILE_LIST` | `0x10` | C -> S | empty |
| `FILE_LIST_RESP` | `0x11` | S -> C | `count:u32 + entries` |
| `FILE_UPLOAD` | `0x12` | C -> S | upload metadata |
| `FILE_DOWNLOAD` | `0x13` | C -> S | download metadata |
| `FILE_CHUNK` | `0x14` | C <-> S | `offset:u64 + data` |
| `FILE_DELETE` | `0x15` | C -> S | `filename:text` |
| `ACK` | `0x20` | S -> C | acknowledgement |
| `ERROR` | `0xFF` | S -> C | structured error |

Unknown opcodes receive `UNKNOWN_OPCODE` when the current session state can
safely continue.

## 4. Payload formats

### 4.1 LOGIN and filenames

`LOGIN` uses one length-prefixed UTF-8 username:

```text
name_length:u16 + username:name_length bytes
```

`FILE_DELETE` uses the same representation for a filename. Empty names,
invalid UTF-8, path separators, `..`, drive separators, trailing dots/spaces,
and Windows device names are rejected by the server.

### 4.2 FILE_LIST_RESP

```text
count:u32
repeat count times:
    name_length:u16
    filename:name_length bytes
    size:u64
```

The response contains only completed files in the authenticated user's
storage directory. Staging sidecars and partial/quarantined files are hidden.

### 4.3 FILE_UPLOAD

```text
name_length:u16
filename:name_length bytes
total_size:u64
proposed_offset:u64
sha256:32 bytes (optional for legacy packets; required by the Phase 2 client)
```

The current client proposes offset zero and sends the full-file SHA-256.
The server decides the real resume point from its compatible `.part` file and
sidecar, then returns that position in an ACK. `proposed_offset` and the
server-selected offset must not exceed `total_size`.

### 4.4 FILE_DOWNLOAD

```text
name_length:u16
filename:name_length bytes
requested_offset:u64
```

The offset is the size of the client's validated local `.part` file. The
server rejects an offset beyond the completed file size.

### 4.5 FILE_CHUNK

```text
offset:u64
data:remaining payload bytes
```

Chunks must arrive at the exact next expected offset. For upload, a chunk may
not extend beyond the `total_size` declared by FILE_UPLOAD. The receiver
writes and hashes `data` as raw bytes.

### 4.6 ACK

```text
acked_opcode:u16
next_offset:u64
sha256:32 bytes (optional)
```

The receiver must verify that `acked_opcode` matches the operation it is
waiting for. Uses of `next_offset` are operation-specific:

| Acknowledged operation | `next_offset` meaning | SHA-256 |
|---|---|---|
| `LOGIN` | assigned user ID | absent |
| initial `FILE_UPLOAD` | server resume position | absent |
| final `FILE_UPLOAD` | completed total size | server digest |
| `FILE_DOWNLOAD` | total file size | server digest |
| `FILE_DELETE` | zero | absent |
| `LOGOUT` | zero | absent |

### 4.7 ERROR

```text
error_code:u16
message_length:u16
message:message_length UTF-8 bytes
```

The byte length, not the Unicode character count, is stored in
`message_length`.

## 5. Error codes

| Decimal | Hex | Name | Meaning |
|---:|---:|---|---|
| 100 | `0x0064` | `MALFORMED` | Packet or payload cannot be parsed |
| 101 | `0x0065` | `UNKNOWN_OPCODE` | Opcode is not implemented |
| 102 | `0x0066` | `INVALID_USERNAME` | Username is invalid or unsafe |
| 103 | `0x0067` | `NOT_LOGGED_IN` | LOGIN is required first |
| 104 | `0x0068` | `USER_ID_MISMATCH` | Packet ID differs from the session ID |
| 105 | `0x0069` | `USERNAME_IN_USE` | Username already has an active session |
| 110 | `0x006E` | `INVALID_FILENAME` | Filename is invalid or unsafe |
| 111 | `0x006F` | `NOT_FOUND` | Completed file does not exist |
| 112 | `0x0070` | `FILE_EXISTS` | Upload target already exists |
| 113 | `0x0071` | `OFFSET_MISMATCH` | Chunk/resume offset is invalid |
| 114 | `0x0072` | `CHECKSUM_MISMATCH` | Final SHA-256 does not match |
| 115 | `0x0073` | `RESUME_CONFLICT` | Resume metadata is incompatible |
| 120 | `0x0078` | `SERVER_BUSY` | Maximum active-client capacity reached |
| 121 | `0x0079` | `FILE_BUSY` | File lock could not be acquired |
| 130 | `0x0082` | `INTERNAL_ERROR` | Logged internal server failure |

Most semantic errors leave the connection usable. A truncated frame or lost
TCP connection cannot be recovered because packet alignment is no longer
known; the peer reconnects instead.

## 6. Session state machine

```text
CONNECTED --LOGIN--> AUTHENTICATED

AUTHENTICATED --FILE_UPLOAD--> UPLOADING --FILE_CHUNK x N--> AUTHENTICATED
AUTHENTICATED --FILE_DOWNLOAD--> DOWNLOADING --FILE_CHUNK x N--> AUTHENTICATED
AUTHENTICATED --FILE_LIST / FILE_DELETE--> AUTHENTICATED
AUTHENTICATED --LOGOUT--> CLOSED
```

Only LOGIN is accepted before authentication. In `AUTHENTICATED`, the server
accepts LIST, UPLOAD, DOWNLOAD, DELETE, and LOGOUT. During an upload, only the
expected FILE_CHUNK stream (or LOGOUT) is valid. The server drives downloads;
the client receives until the byte count from the opening ACK is reached.

## 7. Operation sequences

### 7.1 Login

```text
C -> S  LOGIN(user_id=0, username)
S -> C  ACK(acked_opcode=LOGIN, next_offset=assigned_user_id)
```

The client uses the assigned ID in all later packets.

### 7.2 Upload and upload resume

```text
C -> S  FILE_UPLOAD(filename, total_size, offset=0, full_sha256)
S -> C  ACK(FILE_UPLOAD, server_offset)
C -> S  FILE_CHUNK(server_offset, data) x N
S -> C  ACK(FILE_UPLOAD, total_size, actual_sha256)
```

If the connection drops, the server keeps `.part` plus `.part.json`. On the
next FILE_UPLOAD for the same username/filename, it validates `total_size`
and SHA-256 against the sidecar. A compatible staging file resumes from its
current byte size; incompatible staging is cleared rather than mixed with a
different source file. The completed file is promoted atomically only after
the full digest matches.

An already completed filename returns `FILE_EXISTS`; the explicit update
policy is DELETE followed by a new UPLOAD.

### 7.3 Download and download resume

```text
C -> S  FILE_DOWNLOAD(filename, local_part_size)
S -> C  ACK(FILE_DOWNLOAD, total_size, full_sha256)
S -> C  FILE_CHUNK(local_part_size, data) x N
```

There is no trailing download ACK. The client already knows `total_size` and
the expected digest from the opening ACK. After receiving exactly that many
bytes, it hashes the whole `.part` file and atomically renames it only when
the digest matches. A sidecar mismatch clears local staging and requires a
new request.

### 7.4 Delete and logout

```text
C -> S  FILE_DELETE(filename)
S -> C  ACK(FILE_DELETE, 0) | ERROR(...)

C -> S  LOGOUT
S -> C  ACK(LOGOUT, 0)
```

## 8. Golden upload packet

This is the golden vector enforced by `tests/test_protocol.py` for:

- opcode `FILE_UPLOAD` (`0x0012`)
- user ID `7`
- filename `data.bin`
- total size `10,000,000` (`0x0000000000989680`)
- proposed offset `0`
- SHA-256 bytes `0x11` repeated 32 times

```text
00 00 00 3E  00 12  00 07
00 08  64 61 74 61 2E 62 69 6E
00 00 00 00 00 98 96 80
00 00 00 00 00 00 00 00
11 11 11 11 11 11 11 11
11 11 11 11 11 11 11 11
11 11 11 11 11 11 11 11
11 11 11 11 11 11 11 11
```

The body contains 62 bytes (`0x3E`): four bytes for opcode/user ID, 10 bytes
for the encoded filename, 16 bytes for size/offset, and 32 digest bytes. The
complete packet occupies 66 bytes including the four-byte length prefix.

## 9. Verification commands

From `project/Phase 2`:

```powershell
python -m unittest tests.test_protocol -v
python -m unittest discover -s tests -t tests -p test_framing.py -v
python -m unittest discover -s tests -t tests -p test_stress_clients.py -v
```

With a server already listening on port 9000:

```powershell
python tools/stress_clients.py --host 127.0.0.1 --port 9000 --clients 12 --rounds 20 --seed 2026
```

The stress command writes `docs/test-results/stress.json` and
`docs/test-results/stress.csv` and exits non-zero if any logical client fails.

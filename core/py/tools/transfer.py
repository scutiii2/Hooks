"""Back up the hooks' local state to a zip file and restore it: `.data/` (logs, state, stats) and
`.memory/` (labeled examples).

Export writes `hooks-backup-<time>.zip` into a folder, or `.hbk` when a password is given. A zip has
`data/` and `memory/` inside. Import takes that file, or a folder (newest backup file in it, else the
older plain `data/` + `memory/` copy), overwrites same-named files and keeps the rest.

Encrypted file (.hbk), stdlib only: b"HKBK1" + salt(16) + nonce(16) + ciphertext + tag(32).
Keys: scrypt(password, salt) -> 64 bytes (cipher key, MAC key). Cipher: HMAC-SHA256 in counter mode as a
stream cipher. Tag: HMAC-SHA256 over everything before it (encrypt-then-MAC), checked before any decrypt.
"""
import glob
import hashlib
import hmac
import io
import os
import secrets
import shutil
import subprocess
import sys
import time
import zipfile

from .. import paths

PARTS = (("data", "DATA"), ("memory", "MEMORY"))  # folder name in the backup, attribute of paths
MAGIC = b"HKBK1"
PREFIX = "hooks-backup-"


def _keys(password: str, salt: bytes) -> tuple[bytes, bytes]:
    key = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=64)
    return key[:32], key[32:]


def _xor_stream(key: bytes, nonce: bytes, data: bytes) -> bytes:
    blocks = (len(data) + 31) // 32
    stream = b"".join(hmac.digest(key, nonce + i.to_bytes(8, "big"), "sha256") for i in range(blocks))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(len(data), "big")


def encrypt(data: bytes, password: str) -> bytes:
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    enc_key, mac_key = _keys(password, salt)
    body = MAGIC + salt + nonce + _xor_stream(enc_key, nonce, data)
    return body + hmac.digest(mac_key, body, "sha256")


def decrypt(blob: bytes, password: str) -> bytes:
    head = len(MAGIC) + 32
    if len(blob) < head + 32 or not blob.startswith(MAGIC):
        raise ValueError("not an encrypted hooks backup")
    salt, nonce = blob[len(MAGIC):len(MAGIC) + 16], blob[len(MAGIC) + 16:head]
    enc_key, mac_key = _keys(password, salt)
    if not hmac.compare_digest(hmac.digest(mac_key, blob[:-32], "sha256"), blob[-32:]):
        raise ValueError("wrong password, or the file is damaged")
    return _xor_stream(enc_key, nonce, blob[head:-32])


def _copy(src: str, dst: str) -> int:
    """Copy every file under src into dst, overwriting; return the file count."""
    count = 0
    for root, _, files in os.walk(src):
        target = os.path.join(dst, os.path.relpath(root, src))
        os.makedirs(target, exist_ok=True)
        for name in files:
            shutil.copy2(os.path.join(root, name), os.path.join(target, name))
            count += 1
    return count


def _check(path: str, must_exist: bool) -> str:
    path = path.strip().strip("\"'")
    if not path:
        raise ValueError("pick a folder first")
    path = os.path.abspath(path)
    if must_exist and not os.path.exists(path):
        raise ValueError(f"not found: {path}")
    return path


def export_to(folder: str, password: str = "") -> dict:
    """Write one backup file into folder; return file counts and the file path."""
    folder = _check(folder, False)
    os.makedirs(folder, exist_ok=True)
    buf, counts = io.BytesIO(), {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, attr in PARTS:
            src, counts[name] = getattr(paths, attr), 0
            for root, _, files in os.walk(src):
                for f in files:
                    full = os.path.join(root, f)
                    z.write(full, f"{name}/{os.path.relpath(full, src).replace(os.sep, '/')}")
                    counts[name] += 1
    data = encrypt(buf.getvalue(), password) if password else buf.getvalue()
    out = os.path.join(folder, PREFIX + time.strftime("%Y%m%d-%H%M%S") + (".hbk" if password else ".zip"))
    with open(out, "wb") as f:
        f.write(data)
    return {**counts, "file": out}


def _newest_backup(folder: str) -> str | None:
    found = glob.glob(os.path.join(folder, PREFIX + "*.zip")) + glob.glob(os.path.join(folder, PREFIX + "*.hbk"))
    return max(found, key=os.path.getmtime) if found else None


def _import_zip(path: str, password: str) -> dict:
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith(MAGIC):
        if not password:
            raise ValueError("this backup is encrypted: enter its password")
        data = decrypt(data, password)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("not a hooks backup file") from None
    counts = {name: 0 for name, _ in PARTS}
    roots = {name: os.path.abspath(getattr(paths, attr)) for name, attr in PARTS}
    with z:
        for info in z.infolist():
            part, _, rel = info.filename.partition("/")
            if info.is_dir() or part not in roots:
                continue
            target = os.path.abspath(os.path.join(roots[part], rel))
            if os.path.commonpath([roots[part], target]) != roots[part]:
                raise ValueError(f"unsafe path in backup: {info.filename}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            counts[part] += 1
    if not any(counts.values()):
        raise ValueError("no data/ or memory/ files in there: not a hooks backup")
    return counts


def import_from(path: str, password: str = "") -> dict:
    """Restore from a backup file, or a folder holding one (or an older plain copy)."""
    path = _check(path, True)
    if os.path.isfile(path):
        return {**_import_zip(path, password), "file": path}
    newest = _newest_backup(path)
    if newest:
        return {**_import_zip(newest, password), "file": newest}
    if not any(os.path.isdir(os.path.join(path, n)) for n, _ in PARTS):
        raise ValueError("no backup file, data/ or memory/ folder in there: not a hooks export")
    counts = {}
    for name, attr in PARTS:
        src = os.path.join(path, name)
        counts[name] = _copy(src, getattr(paths, attr)) if os.path.isdir(src) else 0
    return {**counts, "file": path}


_DIALOG = ("import tkinter as t, tkinter.filedialog as f; r = t.Tk(); r.withdraw(); r.attributes('-topmost', True); "
           "print(f.askdirectory(title='Select folder'))")


def pick_folder() -> str:
    """Native folder dialog on the machine running this server (it is localhost only); '' when cancelled."""
    done = subprocess.run([sys.executable, "-c", _DIALOG], capture_output=True, text=True, timeout=300)
    return os.path.normpath(done.stdout.strip()) if done.stdout.strip() else ""

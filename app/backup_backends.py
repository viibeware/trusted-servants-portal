# SPDX-License-Identifier: AGPL-3.0-or-later
"""Off-site backup destinations.

Each backend implements the same minimal interface so the scheduler in
``app.backup_scheduler`` can treat FTP, SFTP, and Dropbox uniformly:

    open()                              — context-manager-ish; raises on auth failure
    put(local_path, remote_name)        — upload one file
    list() -> list[(name, size, mtime)] — list export archives at remote_path
    delete(remote_name)                 — delete one file by name
    fetch(remote_name, local_path)      — download one file
    close()

Backends never delete-then-upload; they upload first and only prune
older files after a successful put, so a transient failure can never
leave the remote without a recent backup.

Heavy imports (paramiko, dropbox) are deferred inside each class so the
app boots cleanly even if one of those wheels is missing — only the
backend the user actually picks needs its dep installed.
"""
import contextlib
import io
import logging
import os
import posixpath
import re
import socket
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from .backup import EXPORT_PREFIX

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _prefer_ipv4():
    """Force urllib3 connections opened inside this block to use IPv4.

    Docker's default bridge network is IPv4-only; getaddrinfo can still
    return AAAA records that the kernel then can't route ("Network is
    unreachable", errno 101). Patching urllib3's family selector for the
    Dropbox SDK call window avoids that without affecting other HTTP
    consumers (e.g. the WordPress importer pulling from a v6-only site)
    that may genuinely want IPv6.
    """
    try:
        from urllib3.util import connection as _uc
    except ImportError:
        yield
        return
    original = getattr(_uc, "allowed_gai_family", None)
    _uc.allowed_gai_family = lambda: socket.AF_INET
    try:
        yield
    finally:
        if original is not None:
            _uc.allowed_gai_family = original


@dataclass
class RemoteFile:
    name: str
    size: int
    mtime: float  # unix epoch; 0 if backend doesn't expose it


class BackendError(Exception):
    """Raised for any backend-layer failure (auth, network, IO).

    The wizard's "Test connection" handler and the scheduler both catch
    this and surface ``str(e)`` to the admin — keep messages user-readable.
    """


def _is_export_name(name: str) -> bool:
    """Only act on files we know we wrote.

    Guards every list/delete operation: even though ``remote_path`` is
    set by the admin, we still refuse to enumerate or prune anything
    outside our prefix so a misconfigured target pointing at /home or
    Dropbox root can't sweep the user's other files.
    """
    base = posixpath.basename(name)
    return base.startswith(EXPORT_PREFIX) and (base.endswith(".zip") or base.endswith(".zip.enc"))


# ─────────────────────────────────────────────────────────────────────
# FTP / FTPS
# ─────────────────────────────────────────────────────────────────────

class FTPBackend:
    def __init__(self, host, port, username, password, remote_path, use_tls=True):
        self.host = host
        self.port = int(port or (21 if not use_tls else 21))
        self.username = username
        self.password = password
        self.remote_path = remote_path or "/"
        self.use_tls = use_tls
        self._ftp = None

    def open(self):
        import ftplib
        try:
            if self.use_tls:
                ftp = ftplib.FTP_TLS()
                ftp.connect(self.host, self.port, timeout=30)
                ftp.login(self.username, self.password)
                ftp.prot_p()  # encrypt the data channel too
            else:
                ftp = ftplib.FTP()
                ftp.connect(self.host, self.port, timeout=30)
                ftp.login(self.username, self.password)
            self._cd(ftp, self.remote_path)
            self._ftp = ftp
        except ftplib.all_errors as e:
            raise BackendError(f"FTP connect failed: {e}") from e

    def _cd(self, ftp, path):
        """cd into path, creating directories along the way if needed."""
        import ftplib
        if not path or path == "/":
            ftp.cwd("/")
            return
        # Always start absolute so we don't accumulate relative chdirs
        # across reconnects to the same target.
        ftp.cwd("/")
        for part in [p for p in path.strip("/").split("/") if p]:
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                try:
                    ftp.mkd(part)
                    ftp.cwd(part)
                except ftplib.error_perm as e:
                    raise BackendError(f"cannot create FTP directory {part!r}: {e}") from e

    def put(self, local_path, remote_name):
        import ftplib
        try:
            with open(local_path, "rb") as f:
                self._ftp.storbinary(f"STOR {remote_name}", f)
        except ftplib.all_errors as e:
            raise BackendError(f"FTP upload failed: {e}") from e

    def list(self) -> list[RemoteFile]:
        import ftplib
        out: list[RemoteFile] = []
        try:
            # MLSD is the modern, parseable listing; fall back to NLST.
            try:
                for name, facts in self._ftp.mlsd():
                    if not _is_export_name(name):
                        continue
                    size = int(facts.get("size") or 0)
                    out.append(RemoteFile(name=name, size=size, mtime=0))
            except (ftplib.error_perm, AttributeError):
                for name in self._ftp.nlst():
                    if not _is_export_name(name):
                        continue
                    try:
                        size = self._ftp.size(name) or 0
                    except ftplib.error_perm:
                        size = 0
                    out.append(RemoteFile(name=name, size=size, mtime=0))
        except ftplib.all_errors as e:
            raise BackendError(f"FTP list failed: {e}") from e
        # No reliable mtime on every server — sort by embedded timestamp
        # in the filename (tsp-export-YYYYMMDD-HHMMSS.zip[.enc]).
        out.sort(key=lambda r: r.name, reverse=True)
        return out

    def delete(self, remote_name):
        import ftplib
        if not _is_export_name(remote_name):
            raise BackendError(f"refusing to delete non-export file {remote_name!r}")
        try:
            self._ftp.delete(remote_name)
        except ftplib.all_errors as e:
            raise BackendError(f"FTP delete failed: {e}") from e

    def fetch(self, remote_name, local_path):
        import ftplib
        try:
            with open(local_path, "wb") as f:
                self._ftp.retrbinary(f"RETR {remote_name}", f.write)
        except ftplib.all_errors as e:
            raise BackendError(f"FTP fetch failed: {e}") from e

    def close(self):
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except Exception:
                try: self._ftp.close()
                except Exception: pass
            self._ftp = None


# ─────────────────────────────────────────────────────────────────────
# SFTP (SSH)
# ─────────────────────────────────────────────────────────────────────

class SFTPBackend:
    def __init__(self, host, port, username, password=None, private_key=None, remote_path="/"):
        self.host = host
        self.port = int(port or 22)
        self.username = username
        self.password = password or None
        self.private_key = private_key or None
        self.remote_path = remote_path or "/"
        self._sftp = None
        self._transport = None

    def open(self):
        try:
            import paramiko
        except ImportError as e:
            raise BackendError("SFTP backend requires the 'paramiko' package") from e
        try:
            transport = paramiko.Transport((self.host, self.port))
            pkey = None
            if self.private_key:
                pkey = self._load_private_key(self.private_key)
            transport.connect(username=self.username, password=self.password, pkey=pkey)
            sftp = paramiko.SFTPClient.from_transport(transport)
            self._mkdir_p(sftp, self.remote_path)
            sftp.chdir(self.remote_path)
            self._sftp = sftp
            self._transport = transport
        except Exception as e:
            raise BackendError(f"SFTP connect failed: {e}") from e

    def _load_private_key(self, key_text):
        """Try common key formats since paramiko has separate classes per algo."""
        import paramiko
        for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey, paramiko.DSSKey):
            try:
                return cls.from_private_key(io.StringIO(key_text))
            except paramiko.SSHException:
                continue
        raise BackendError("unrecognized private key format (tried Ed25519, ECDSA, RSA, DSA)")

    def _mkdir_p(self, sftp, path):
        if not path or path == "/":
            return
        parts = [p for p in path.strip("/").split("/") if p]
        cur = ""
        for p in parts:
            cur = cur + "/" + p
            try:
                sftp.stat(cur)
            except FileNotFoundError:
                try:
                    sftp.mkdir(cur)
                except Exception as e:
                    raise BackendError(f"cannot create remote directory {cur!r}: {e}") from e

    def put(self, local_path, remote_name):
        try:
            self._sftp.put(local_path, remote_name)
        except Exception as e:
            raise BackendError(f"SFTP upload failed: {e}") from e

    def list(self) -> list[RemoteFile]:
        try:
            out: list[RemoteFile] = []
            for attr in self._sftp.listdir_attr():
                if not _is_export_name(attr.filename):
                    continue
                out.append(RemoteFile(name=attr.filename, size=attr.st_size or 0,
                                      mtime=float(attr.st_mtime or 0)))
            out.sort(key=lambda r: r.name, reverse=True)
            return out
        except Exception as e:
            raise BackendError(f"SFTP list failed: {e}") from e

    def delete(self, remote_name):
        if not _is_export_name(remote_name):
            raise BackendError(f"refusing to delete non-export file {remote_name!r}")
        try:
            self._sftp.remove(remote_name)
        except Exception as e:
            raise BackendError(f"SFTP delete failed: {e}") from e

    def fetch(self, remote_name, local_path):
        try:
            self._sftp.get(remote_name, local_path)
        except Exception as e:
            raise BackendError(f"SFTP fetch failed: {e}") from e

    def close(self):
        if self._sftp is not None:
            try: self._sftp.close()
            except Exception: pass
            self._sftp = None
        if self._transport is not None:
            try: self._transport.close()
            except Exception: pass
            self._transport = None


# ─────────────────────────────────────────────────────────────────────
# Dropbox
# ─────────────────────────────────────────────────────────────────────

class DropboxBackend:
    """Uses the Dropbox HTTP SDK.

    Tokens are issued via the wizard's OAuth flow — the SDK call below
    uploads to ``<remote_path>/<remote_name>``. We always normalize the
    path to start with "/" because Dropbox rejects relative paths.

    The 150 MB chunked-upload threshold is the SDK's documented cutoff
    where ``files_upload`` stops being safe; below it we use the simple
    one-shot call, above it ``files_upload_session_*``.
    """
    CHUNK = 8 * 1024 * 1024
    SIMPLE_UPLOAD_LIMIT = 150 * 1024 * 1024

    def __init__(self, oauth_token, remote_path="/"):
        self.token = oauth_token
        self.remote_path = self._normalize(remote_path)
        self._dbx = None

    @staticmethod
    def _normalize(p):
        p = (p or "/").strip()
        if not p.startswith("/"):
            p = "/" + p
        # Dropbox does not want a trailing slash on a folder when joining;
        # collapse "//foo" -> "/foo" and strip trailing "/" (except root).
        while "//" in p:
            p = p.replace("//", "/")
        if len(p) > 1 and p.endswith("/"):
            p = p[:-1]
        return p

    def open(self):
        try:
            import dropbox
        except ImportError as e:
            raise BackendError("Dropbox backend requires the 'dropbox' package") from e
        try:
            # Patch urllib3's family selector while the SDK constructs its
            # HTTP pool — that pool gets reused for all subsequent calls
            # on this client, so v4-only resolution sticks.
            with _prefer_ipv4():
                self._dbx = dropbox.Dropbox(self.token, timeout=60)
                # check_user is the cheapest authenticated call — fails fast
                # if the token was revoked. Also forces the pool to open
                # its first connection while the patch is active.
                self._dbx.users_get_current_account()
        except dropbox.exceptions.AuthError as e:
            raise BackendError(f"Dropbox auth failed: {e}") from e
        except Exception as e:
            raise BackendError(f"Dropbox connect failed: {e}") from e

    def _full(self, name):
        return f"{self.remote_path}/{name}" if self.remote_path != "/" else f"/{name}"

    def put(self, local_path, remote_name):
        import dropbox
        from dropbox.files import WriteMode, CommitInfo, UploadSessionCursor
        full = self._full(remote_name)
        size = os.path.getsize(local_path)
        try:
            with _prefer_ipv4(), open(local_path, "rb") as f:
                if size <= self.SIMPLE_UPLOAD_LIMIT:
                    self._dbx.files_upload(f.read(), full, mode=WriteMode.overwrite)
                    return
                # Chunked session for large archives.
                session = self._dbx.files_upload_session_start(f.read(self.CHUNK))
                cursor = UploadSessionCursor(session_id=session.session_id, offset=f.tell())
                commit = CommitInfo(path=full, mode=WriteMode.overwrite)
                while f.tell() < size - self.CHUNK:
                    self._dbx.files_upload_session_append_v2(f.read(self.CHUNK), cursor)
                    cursor.offset = f.tell()
                self._dbx.files_upload_session_finish(f.read(self.CHUNK), cursor, commit)
        except dropbox.exceptions.ApiError as e:
            raise BackendError(f"Dropbox upload failed: {e}") from e
        except Exception as e:
            raise BackendError(f"Dropbox upload failed: {e}") from e

    def list(self) -> list[RemoteFile]:
        import dropbox
        out: list[RemoteFile] = []
        path = "" if self.remote_path == "/" else self.remote_path
        try:
            with _prefer_ipv4():
                res = self._dbx.files_list_folder(path)
                while True:
                    for entry in res.entries:
                        if not hasattr(entry, "size"):
                            continue  # folder
                        if not _is_export_name(entry.name):
                            continue
                        mtime = entry.client_modified.timestamp() if entry.client_modified else 0
                        out.append(RemoteFile(name=entry.name, size=entry.size, mtime=mtime))
                    if not res.has_more:
                        break
                    res = self._dbx.files_list_folder_continue(res.cursor)
        except dropbox.exceptions.ApiError as e:
            # If the folder doesn't exist yet, that's not an error —
            # just return empty. The first upload will create it.
            from dropbox.files import ListFolderError
            err = getattr(e, "error", None)
            if isinstance(err, ListFolderError) and err.is_path() and err.get_path().is_not_found():
                return []
            raise BackendError(f"Dropbox list failed: {e}") from e
        except Exception as e:
            raise BackendError(f"Dropbox list failed: {e}") from e
        out.sort(key=lambda r: r.name, reverse=True)
        return out

    def delete(self, remote_name):
        import dropbox
        if not _is_export_name(remote_name):
            raise BackendError(f"refusing to delete non-export file {remote_name!r}")
        try:
            with _prefer_ipv4():
                self._dbx.files_delete_v2(self._full(remote_name))
        except dropbox.exceptions.ApiError as e:
            raise BackendError(f"Dropbox delete failed: {e}") from e

    def fetch(self, remote_name, local_path):
        import dropbox
        try:
            with _prefer_ipv4():
                self._dbx.files_download_to_file(local_path, self._full(remote_name))
        except dropbox.exceptions.ApiError as e:
            raise BackendError(f"Dropbox fetch failed: {e}") from e

    def close(self):
        if self._dbx is not None:
            try: self._dbx.close()
            except Exception: pass
            self._dbx = None


# ─────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────

def make_backend(target):
    """Build a backend instance from a BackupTarget row.

    Decrypts credentials with the app's Fernet key at call time — we
    deliberately don't cache the plaintext on the model so a credential
    rotation takes effect the next time the scheduler picks the target up.
    """
    from .crypto import decrypt
    kind = target.kind
    if kind == "ftp":
        return FTPBackend(
            host=target.host,
            port=target.port or (21 if not target.use_tls else 21),
            username=target.username or "",
            password=decrypt(target.password_enc) if target.password_enc else "",
            remote_path=target.remote_path or "/",
            use_tls=bool(target.use_tls),
        )
    if kind == "sftp":
        return SFTPBackend(
            host=target.host,
            port=target.port or 22,
            username=target.username or "",
            password=decrypt(target.password_enc) if target.password_enc else None,
            private_key=decrypt(target.private_key_enc) if target.private_key_enc else None,
            remote_path=target.remote_path or "/",
        )
    if kind == "dropbox":
        return DropboxBackend(
            oauth_token=decrypt(target.oauth_token_enc) if target.oauth_token_enc else "",
            remote_path=target.remote_path or "/",
        )
    raise BackendError(f"unknown backup kind {kind!r}")

#!/usr/bin/env python3
"""Encrypt or decrypt the private Google Timeline archive.

Format: VITAENC1 | salt (16) | nonce (12) | plaintext SHA-256 (32) | AES-GCM.
The plaintext is gzip-compressed before encryption. The password comes from a
hidden prompt, or VITA_TIMELINE_PASSWORD for unattended local verification.
"""

from __future__ import annotations

import argparse
import getpass
import gzip
import hashlib
import hmac
import os
from pathlib import Path
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


MAGIC = b"VITAENC1"
SALT_BYTES = 16
NONCE_BYTES = 12
DIGEST_BYTES = 32
HEADER_BYTES = len(MAGIC) + SALT_BYTES + NONCE_BYTES + DIGEST_BYTES
PASSWORD_ENV = "VITA_TIMELINE_PASSWORD"


def derive_key(password: str, salt: bytes) -> bytes:
    if not password:
        raise ValueError("La password non può essere vuota.")
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(
        password.encode("utf-8")
    )


def read_password(confirm: bool) -> str:
    password = os.environ.get(PASSWORD_ENV)
    if password is not None:
        return password
    password = getpass.getpass("Password archivio: ")
    if confirm and password != getpass.getpass("Ripeti password: "):
        raise ValueError("Le password non coincidono.")
    return password


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    temporary.replace(path)


def encrypt(source: Path, destination: Path) -> str:
    plaintext = source.read_bytes()
    digest = hashlib.sha256(plaintext).digest()
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    header = MAGIC + salt + nonce + digest
    compressed = gzip.compress(plaintext, compresslevel=9, mtime=0)
    ciphertext = AESGCM(derive_key(read_password(confirm=True), salt)).encrypt(
        nonce, compressed, header
    )
    atomic_write(destination, header + ciphertext)
    return digest.hex()


def decrypt_payload(source: Path) -> tuple[bytes, str]:
    archive = source.read_bytes()
    if len(archive) <= HEADER_BYTES or archive[: len(MAGIC)] != MAGIC:
        raise ValueError("Formato archivio non riconosciuto.")

    cursor = len(MAGIC)
    salt = archive[cursor : cursor + SALT_BYTES]
    cursor += SALT_BYTES
    nonce = archive[cursor : cursor + NONCE_BYTES]
    cursor += NONCE_BYTES
    expected_digest = archive[cursor : cursor + DIGEST_BYTES]
    header = archive[:HEADER_BYTES]

    try:
        compressed = AESGCM(derive_key(read_password(confirm=False), salt)).decrypt(
            nonce, archive[HEADER_BYTES:], header
        )
    except InvalidTag as exc:
        raise ValueError("Password errata o archivio danneggiato.") from exc

    plaintext = gzip.decompress(compressed)
    actual_digest = hashlib.sha256(plaintext).digest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise ValueError("Hash del Timeline decifrato non valido.")
    return plaintext, actual_digest.hex()


def decrypt(source: Path, destination: Path) -> str:
    plaintext, digest = decrypt_payload(source)
    atomic_write(destination, plaintext)
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("encrypt", "decrypt", "verify"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--input", type=Path, required=True)
        if command != "verify":
            command_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "encrypt":
            digest = encrypt(args.input, args.output)
        elif args.command == "decrypt":
            digest = decrypt(args.input, args.output)
        else:
            _, digest = decrypt_payload(args.input)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Errore: {exc}\n")

    action = "Verificato" if args.command == "verify" else f"Creato {args.output}"
    print(f"{action} · SHA-256 originale {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

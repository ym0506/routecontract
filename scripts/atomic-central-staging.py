#!/usr/bin/env python3
"""Descriptor-anchored, no-replace finalization for local Central staging."""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import os
import stat
import sys


SUCCESS = "ROUTECONTRACT_ATOMIC_CENTRAL_STAGING_OK"
RENAME_NOREPLACE = 0x00000001
RENAME_EXCL = 0x00000004


class HoldError(RuntimeError):
    """A failure that requires read-only reconciliation rather than retry."""


def positive_decimal(value: str) -> int:
    if not value or not value.isascii() or not value.isdecimal():
        raise argparse.ArgumentTypeError("identity must be a positive decimal integer")
    parsed = int(value, 10)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("identity must be a positive decimal integer")
    return parsed


def path_component(value: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or os.path.sep in value
        or (os.path.altsep is not None and os.path.altsep in value)
    ):
        raise argparse.ArgumentTypeError("name must be one non-empty path component")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--work-name", required=True, type=path_component)
    parser.add_argument("--final-name", required=True, type=path_component)
    parser.add_argument("--expected-parent-device", required=True, type=positive_decimal)
    parser.add_argument("--expected-parent-inode", required=True, type=positive_decimal)
    parser.add_argument("--expected-work-device", required=True, type=positive_decimal)
    parser.add_argument("--expected-work-inode", required=True, type=positive_decimal)
    return parser.parse_args()


def require_absent(parent_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise HoldError("final entry is not absent")


def stat_expected_directory(
    parent_fd: int, name: str, expected_device: int, expected_inode: int
) -> os.stat_result:
    observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(observed.st_mode):
        raise HoldError("work entry is not a real directory")
    if observed.st_dev != expected_device or observed.st_ino != expected_inode:
        raise HoldError("work directory identity changed")
    return observed


def atomic_no_replace(parent_fd: int, work_name: str, final_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    encoded_work = os.fsencode(work_name)
    encoded_final = os.fsencode(final_name)
    if sys.platform.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as error:
            raise HoldError("renameat2 is unavailable") from error
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(
            parent_fd,
            encoded_work,
            parent_fd,
            encoded_final,
            RENAME_NOREPLACE,
        )
    elif sys.platform == "darwin":
        try:
            rename = libc.renameatx_np
        except AttributeError as error:
            raise HoldError("renameatx_np is unavailable") from error
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(
            parent_fd,
            encoded_work,
            parent_fd,
            encoded_final,
            RENAME_EXCL,
        )
    else:
        raise HoldError("descriptor-anchored no-replace rename is unsupported")
    if result != 0:
        error_number = ctypes.get_errno()
        error_name = errno.errorcode.get(error_number, "UNKNOWN")
        raise HoldError(f"atomic no-replace rename failed with {error_name}")


def finalize(args: argparse.Namespace) -> None:
    parent = args.parent
    if (
        not os.path.isabs(parent)
        or os.path.normpath(parent) != parent
        or os.path.realpath(parent) != parent
    ):
        raise HoldError("parent must be an absolute normalized canonical path")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    parent_fd = os.open(parent, flags)
    try:
        fcntl.flock(parent_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        parent_stat = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent_stat.st_mode):
            raise HoldError("opened parent is not a directory")
        if parent_stat.st_dev != args.expected_parent_device:
            raise HoldError("parent device changed")
        if parent_stat.st_ino != args.expected_parent_inode:
            raise HoldError("parent inode changed")
        if parent_stat.st_uid != os.geteuid():
            raise HoldError("parent is not owned by the effective user")
        if stat.S_IMODE(parent_stat.st_mode) & 0o077:
            raise HoldError("parent permissions must exclude group and other access")

        stat_expected_directory(
            parent_fd,
            args.work_name,
            args.expected_work_device,
            args.expected_work_inode,
        )
        require_absent(parent_fd, args.final_name)
        atomic_no_replace(parent_fd, args.work_name, args.final_name)

        final_stat = stat_expected_directory(
            parent_fd,
            args.final_name,
            args.expected_work_device,
            args.expected_work_inode,
        )
        if final_stat.st_uid != os.geteuid():
            raise HoldError("final directory is not owned by the effective user")
        try:
            os.stat(args.work_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise HoldError("work entry remained after atomic rename")
    finally:
        os.close(parent_fd)


def main() -> int:
    try:
        finalize(parse_args())
    except (HoldError, OSError) as error:
        print(f"HOLD: {error}; do not retry, rename or clean automatically", file=sys.stderr)
        return 1
    print(SUCCESS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

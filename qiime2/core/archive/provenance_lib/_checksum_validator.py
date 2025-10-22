# ----------------------------------------------------------------------------
# Copyright (c) 2016-2025, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------
from enum import IntEnum
import warnings
from typing import Optional, Tuple
from zipfile import ZipFile

from qiime2.core.archive.archiver import ChecksumDiff
from qiime2.sdk.result import Result

from .util import get_root_uuid, parse_version


class ValidationCode(IntEnum):
    '''
    Codes indicating the level of validation a ProvDAG has passed.

    The code that determines which ValidationCode an archive receives is by
    necessity scattered.

    INVALID:
        One or more files are known to be missing or unparseable. Occurs
        either when checksum validation fails, or when expected files are
        absent or unparseable.

    VALIDATION_OPTOUT:
        The user opted out of checksum validation. This will be overridden by
        INVALID iff a required file is missing. In this context,
        `checksums.md5` is not required. If data files, for example, have been
        manually modified, the code will remain VALIDATION_OPTOUT, but if an
        action.yaml file is missing, INVALID will result.

    PREDATES_CHECKSUMS:
        The archive format predates the creation of checksums.md5, so full
        validation is impossible. We initially assume validity. This will be
        overridden by INVALID iff an expected file is missing or unparseable.
        If data files, for example, have been manually modified, the code will
        remain PREDATES_CHECKSUMS.

    VALID:
        The archive has passed checksum validation and is "known" to be
        valid. Md5 checksums are technically falsifiable, so this is not a
        guarantee of correctness/authenticity.

    '''
    INVALID = 0
    VALIDATION_OPTOUT = 1
    PREDATES_CHECKSUMS = 2
    VALID = 3


def validate_checksums(
    archive: str,
    zf: ZipFile
) -> Tuple[ValidationCode, Optional[ChecksumDiff]]:
    '''
    Uses diff_checksums to validate the archive's provenance,
    warning the user if checksums.md5/checksums.sha512 is missing,
    or if the archive is corrupt or has been modified.

    Parameters
    ----------
    archive : str
        A path to the artifact to be parsed.
    zf : ZipFile
        The zipfile object of the archive.

    Returns
    -------
    tuple of (ValidationCode, ChecksumDiff)
        If the checksums.md5/checksums.sha512 file isn't present,
        set ChecksumDiff to None and ValidationCode to INVALID and return.

    '''
    result: Result = Result.load(archive)
    checksum_diff: Optional[ChecksumDiff]
    provenance_is_valid = ValidationCode.VALID
    checksum_ext = _parse_checksum_ext(zf)

    for fp in zf.namelist():
        if f'checksums.{checksum_ext}' in fp:
            break
    else:
        warnings.warn(
            f'The checksums.{checksum_ext} file is missing from the archive. '
            'Archive may be corrupt or provenance may be false.',
            UserWarning
        )
        return ValidationCode.INVALID, None

    checksum_diff = result._archiver.validate_checksums()
    if checksum_diff != ChecksumDiff({}, {}, {}):
        root_uuid = get_root_uuid(zf)
        warnings.warn(
            f'Checksums are invalid for Archive {root_uuid}\n'
            'Archive may be corrupt or provenance may be false.\n'
            f'Files added since archive creation: {checksum_diff.added}\n'
            'Files removed since archive creation: '
            f'{checksum_diff.removed}\n'
            'Files changed since archive creation: '
            f'{checksum_diff.changed}',
            UserWarning
        )
        provenance_is_valid = ValidationCode.INVALID

    return provenance_is_valid, checksum_diff


def _parse_checksum_ext(zf):
    archive_version, _ = parse_version(zf)

    if float(archive_version) >= 5.0 and float(archive_version) < 7.0:
        checksum_ext = 'md5'
    elif float(archive_version) >= 7.0:
        checksum_ext = 'sha512'

    return checksum_ext

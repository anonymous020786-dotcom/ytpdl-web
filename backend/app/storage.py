"""S3-backed file storage for the Lambda deployment.

Lambda has no persistent local disk shared across invocations/functions, so a
finished job's files are uploaded here (under ``jobs/{job_id}/...``) right
after the download completes, then served back to clients via short-lived
presigned URLs instead of ``FileResponse``. Only used when ``S3_BUCKET`` is
set — the docker-compose / local-disk deployment path is untouched.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

import boto3

from .config import AWS_REGION, S3_BUCKET

_client = None


def _s3():
    global _client
    if _client is None:
        _client = boto3.client("s3", region_name=AWS_REGION)
    return _client


def upload_job_dir_sync(job_id: str, local_dir: Path) -> list[dict]:
    """Uploads every file under ``local_dir`` to S3, returns the same shape
    the local-disk ``/api/jobs/{id}/files`` endpoint returns (plus ``key``)."""
    files: list[dict] = []
    if not local_dir.is_dir():
        return files
    client = _s3()
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local_dir).as_posix()
        key = f"jobs/{job_id}/{rel}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        client.upload_file(str(path), S3_BUCKET, key, ExtraArgs={"ContentType": content_type})
        files.append({"name": rel, "size": path.stat().st_size, "key": key})
    return files


def presigned_url(key: str, filename: str, expires_in: int = 3600) -> str:
    client = _s3()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=expires_in,
    )

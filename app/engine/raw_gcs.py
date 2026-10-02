"""Write-once raw snapshots in Cloud Storage.

An existing object is not replaced: the upload uses if_generation_match=0.
"""

from __future__ import annotations


def split_url(raw_dir: str) -> tuple[str, str]:
    rest = raw_dir[len("gs://") :]
    bucket, _, prefix = rest.partition("/")
    return bucket, prefix.strip("/")


def object_name(prefix: str, key: str) -> str:
    if not prefix:
        return key
    return prefix.rstrip("/") + "/" + key


def storage_client(client=None):
    if client is not None:
        return client
    from google.cloud import storage

    return storage.Client()


def upload(raw_dir: str, key: str, payload: bytes, client=None) -> str:
    bucket_name, prefix = split_url(raw_dir)
    name = object_name(prefix, key)
    blob = storage_client(client).bucket(bucket_name).blob(name)
    blob.upload_from_string(payload, content_type="application/gzip", if_generation_match=0)
    return name


def read_prefix(raw_dir: str, key_prefix: str, client=None) -> list[tuple[str, bytes]]:
    bucket_name, prefix = split_url(raw_dir)
    full = object_name(prefix, key_prefix)
    blobs = storage_client(client).list_blobs(bucket_name, prefix=full)
    found = []
    for blob in blobs:
        if str(blob.name).endswith(".json.gz"):
            found.append((str(blob.name), blob.download_as_bytes()))
    return sorted(found)

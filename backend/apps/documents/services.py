import hashlib

from django.core.files.base import ContentFile

from .models import UploadedFile


def store_upload(*, user, name: str, data: bytes, kind: str, page_count: int, purpose: str) -> UploadedFile:
    upload = UploadedFile(uploaded_by=user, purpose=purpose, original_name=(name or "upload")[:255], kind=kind,
                          size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), page_count=page_count)
    upload.file.save("upload", ContentFile(data), save=False)
    upload.save()
    return upload

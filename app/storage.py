"""Armazenamento de ficheiros de propostas/documentos.

Em produção usa Cloudflare R2 (S3-compatível); em desenvolvimento, se as
variáveis de ambiente do R2 não estiverem definidas, faz fallback para o
disco local (app/uploads/proposals) — o comportamento antigo.

Variáveis de ambiente necessárias no Render:
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
Opcional:
    R2_ENDPOINT  (caso contrário derivado do account id)
"""
import os
from flask import current_app, send_from_directory, Response


def _r2_enabled():
    return all(
        os.environ.get(k)
        for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
    )


def _bucket():
    return os.environ["R2_BUCKET"]


def _client():
    import boto3
    from botocore.config import Config as BotoConfig

    account_id = os.environ["R2_ACCOUNT_ID"]
    endpoint = os.environ.get("R2_ENDPOINT") or f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=BotoConfig(signature_version="s3v4", region_name="auto"),
    )


def _local_folder():
    folder = os.path.join(current_app.root_path, "uploads", "proposals")
    os.makedirs(folder, exist_ok=True)
    return folder


def save(key, file_storage, content_type="application/pdf"):
    """Guarda um werkzeug FileStorage sob a chave dada."""
    if _r2_enabled():
        _client().upload_fileobj(
            file_storage.stream, _bucket(), key,
            ExtraArgs={"ContentType": content_type},
        )
    else:
        file_storage.save(os.path.join(_local_folder(), key))


def delete(key):
    """Remove o ficheiro. Não falha se a chave for vazia ou não existir."""
    if not key:
        return
    if _r2_enabled():
        try:
            _client().delete_object(Bucket=_bucket(), Key=key)
        except Exception:
            pass
    else:
        path = os.path.join(_local_folder(), key)
        if os.path.exists(path):
            os.remove(path)


def serve(key, download_name=None, as_attachment=False, mimetype="application/pdf"):
    """Devolve uma resposta Flask que serve o ficheiro, ou None se não existir."""
    if not key:
        return None
    if _r2_enabled():
        from botocore.exceptions import ClientError
        try:
            obj = _client().get_object(Bucket=_bucket(), Key=key)
        except ClientError:
            return None

        def generate():
            for chunk in obj["Body"].iter_chunks(chunk_size=8192):
                yield chunk

        resp = Response(generate(), mimetype=mimetype)
        if obj.get("ContentLength") is not None:
            resp.headers["Content-Length"] = str(obj["ContentLength"])
        disposition = "attachment" if as_attachment else "inline"
        if download_name:
            resp.headers["Content-Disposition"] = f'{disposition}; filename="{download_name}"'
        return resp

    folder = _local_folder()
    if not os.path.exists(os.path.join(folder, key)):
        return None
    return send_from_directory(
        folder, key, mimetype=mimetype,
        as_attachment=as_attachment, download_name=download_name or key,
    )

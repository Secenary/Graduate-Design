from __future__ import annotations

import io
import json
import time
import zipfile
from typing import Any

import requests

MINERU_API_BASE = "https://mineru.net/api/v4"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_POLL_INTERVAL_SECONDS = 3
DEFAULT_POLL_TIMEOUT_SECONDS = 300


class MinerUError(RuntimeError):
    """Raised when the MinerU API or result parsing fails."""


def _auth_headers(token: str, include_content_type: bool = True) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "*/*",
    }
    if include_content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _request_json(
    method: str,
    url: str,
    *,
    token: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    include_content_type: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    response = requests.request(
        method,
        url,
        headers=_auth_headers(token, include_content_type=include_content_type),
        timeout=timeout,
        **kwargs,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        body_preview = response.text[:500]
        raise MinerUError(f"MinerU 请求失败，HTTP {response.status_code}: {body_preview}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise MinerUError("MinerU 返回了无法解析的 JSON 响应") from exc

    if payload.get("code") != 0:
        raise MinerUError(payload.get("msg") or "MinerU 接口返回错误")

    return payload.get("data") or {}


def _normalize_extra_formats(extra_formats: Any) -> list[str] | None:
    if not extra_formats:
        return None

    if isinstance(extra_formats, str):
        values = [part.strip() for part in extra_formats.split(",")]
    elif isinstance(extra_formats, list):
        values = [str(part).strip() for part in extra_formats]
    else:
        values = [str(extra_formats).strip()]

    normalized = [value for value in values if value]
    return normalized or None


def build_url_task_body(source_url: str, options: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "url": source_url,
        "model_version": options.get("model_version") or "vlm",
    }

    model_version = body["model_version"]
    if model_version != "MinerU-HTML":
        if options.get("language"):
            body["language"] = options["language"]
        if "enable_formula" in options:
            body["enable_formula"] = bool(options["enable_formula"])
        if "enable_table" in options:
            body["enable_table"] = bool(options["enable_table"])
        if "is_ocr" in options:
            body["is_ocr"] = bool(options["is_ocr"])

    if options.get("data_id"):
        body["data_id"] = options["data_id"]
    if options.get("page_ranges"):
        body["page_ranges"] = options["page_ranges"]
    if "no_cache" in options:
        body["no_cache"] = bool(options["no_cache"])
    if options.get("cache_tolerance") not in (None, ""):
        body["cache_tolerance"] = int(options["cache_tolerance"])

    extra_formats = _normalize_extra_formats(options.get("extra_formats"))
    if extra_formats:
        body["extra_formats"] = extra_formats

    return body


def build_file_upload_body(file_name: str, options: dict[str, Any]) -> dict[str, Any]:
    file_entry: dict[str, Any] = {"name": file_name}

    model_version = options.get("model_version") or "vlm"
    if model_version != "MinerU-HTML" and "is_ocr" in options:
        file_entry["is_ocr"] = bool(options["is_ocr"])

    if options.get("data_id"):
        file_entry["data_id"] = options["data_id"]
    if options.get("page_ranges"):
        file_entry["page_ranges"] = options["page_ranges"]

    body: dict[str, Any] = {
        "files": [file_entry],
        "model_version": model_version,
    }

    if model_version != "MinerU-HTML":
        if options.get("language"):
            body["language"] = options["language"]
        if "enable_formula" in options:
            body["enable_formula"] = bool(options["enable_formula"])
        if "enable_table" in options:
            body["enable_table"] = bool(options["enable_table"])

    extra_formats = _normalize_extra_formats(options.get("extra_formats"))
    if extra_formats:
        body["extra_formats"] = extra_formats

    return body


def _wait_for_done_state(
    poller,
    *,
    timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_result: dict[str, Any] = {}

    while time.time() < deadline:
        result = poller()
        last_result = result
        state = result.get("state")

        if state == "done":
            return result
        if state == "failed":
            raise MinerUError(result.get("err_msg") or "MinerU 解析失败")

        time.sleep(poll_interval_seconds)

    raise MinerUError(
        f"MinerU 解析超时，最后状态为 {last_result.get('state', 'unknown')}"
    )


def wait_for_task_result(
    token: str,
    task_id: str,
    *,
    timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    return _wait_for_done_state(
        lambda: _request_json(
            "GET",
            f"{MINERU_API_BASE}/extract/task/{task_id}",
            token=token,
        ),
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def wait_for_batch_result(
    token: str,
    batch_id: str,
    *,
    file_name: str | None = None,
    timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    def poll() -> dict[str, Any]:
        data = _request_json(
            "GET",
            f"{MINERU_API_BASE}/extract-results/batch/{batch_id}",
            token=token,
        )
        results = data.get("extract_result") or []
        if not results:
            return {"state": "waiting-file", "batch_id": batch_id}

        if file_name:
            for item in results:
                if item.get("file_name") == file_name:
                    return item

        return results[0]

    return _wait_for_done_state(
        poll,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def download_result_archive(full_zip_url: str) -> bytes:
    response = requests.get(full_zip_url, timeout=120)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise MinerUError(f"下载 MinerU 结果压缩包失败，HTTP {response.status_code}") from exc
    return response.content


def _read_text_from_zip(archive: zipfile.ZipFile, *suffixes: str) -> str | None:
    suffix_set = tuple(suffixes)
    for name in archive.namelist():
        if name.endswith("/"):
            continue
        lowered = name.lower()
        if any(lowered.endswith(suffix.lower()) for suffix in suffix_set):
            with archive.open(name) as handle:
                return handle.read().decode("utf-8", errors="ignore")
    return None


def _read_json_from_zip(archive: zipfile.ZipFile, *suffixes: str) -> Any | None:
    raw_text = _read_text_from_zip(archive, *suffixes)
    if raw_text is None:
        return None
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None


def extract_payload_from_archive(archive_bytes: bytes, *, full_zip_url: str = "") -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        files = [name for name in archive.namelist() if not name.endswith("/")]
        payload: dict[str, Any] = {
            "source_format": "mineru_v4_zip",
            "archive_files": files,
        }

        if full_zip_url:
            payload["full_zip_url"] = full_zip_url

        markdown = _read_text_from_zip(archive, "full.md")
        if markdown:
            payload["markdown"] = markdown

        content_list = _read_json_from_zip(archive, "_content_list.json", "content_list.json")
        if content_list is not None:
            payload["content_list"] = content_list

        model_json = _read_json_from_zip(archive, "_model.json", "model.json")
        if model_json is not None:
            payload["model_json"] = model_json

        middle_json = _read_json_from_zip(archive, "_middle.json", "middle.json", "layout.json")
        if middle_json is not None:
            payload["middle_json"] = middle_json

        main_html = _read_text_from_zip(archive, "main.html")
        if main_html:
            payload["main_html"] = main_html

        return payload


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    content_list = payload.get("content_list")
    return {
        "archive_file_count": len(payload.get("archive_files") or []),
        "markdown_chars": len(payload.get("markdown") or ""),
        "content_blocks": len(content_list) if isinstance(content_list, list) else 0,
        "has_model_json": payload.get("model_json") is not None,
        "has_middle_json": payload.get("middle_json") is not None,
        "has_main_html": bool(payload.get("main_html")),
    }


def parse_url_document(
    token: str,
    source_url: str,
    *,
    options: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    request_body = build_url_task_body(source_url, options or {})
    create_result = _request_json(
        "POST",
        f"{MINERU_API_BASE}/extract/task",
        token=token,
        json=request_body,
    )
    task_id = str(create_result.get("task_id", "")).strip()
    if not task_id:
        raise MinerUError("MinerU 未返回 task_id")

    task_result = wait_for_task_result(
        token,
        task_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    full_zip_url = str(task_result.get("full_zip_url", "")).strip()
    if not full_zip_url:
        raise MinerUError("MinerU 任务已完成，但没有返回 full_zip_url")

    payload = extract_payload_from_archive(
        download_result_archive(full_zip_url),
        full_zip_url=full_zip_url,
    )

    return {
        "task_id": task_id,
        "full_zip_url": full_zip_url,
        "task_result": task_result,
        "payload": payload,
        "payload_summary": summarize_payload(payload),
    }


def parse_uploaded_file(
    token: str,
    file_name: str,
    file_bytes: bytes,
    *,
    options: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    request_body = build_file_upload_body(file_name, options or {})
    create_result = _request_json(
        "POST",
        f"{MINERU_API_BASE}/file-urls/batch",
        token=token,
        json=request_body,
    )
    batch_id = str(create_result.get("batch_id", "")).strip()
    file_urls = create_result.get("file_urls") or []
    if not batch_id or not file_urls:
        raise MinerUError("MinerU 未返回有效的批量上传地址")

    upload_response = requests.put(file_urls[0], data=file_bytes, timeout=120)
    if upload_response.status_code not in (200, 201):
        raise MinerUError(f"上传文件到 MinerU 失败，HTTP {upload_response.status_code}")

    batch_result = wait_for_batch_result(
        token,
        batch_id,
        file_name=file_name,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    full_zip_url = str(batch_result.get("full_zip_url", "")).strip()
    if not full_zip_url:
        raise MinerUError("MinerU 批量任务已完成，但没有返回 full_zip_url")

    payload = extract_payload_from_archive(
        download_result_archive(full_zip_url),
        full_zip_url=full_zip_url,
    )

    return {
        "batch_id": batch_id,
        "full_zip_url": full_zip_url,
        "task_result": batch_result,
        "payload": payload,
        "payload_summary": summarize_payload(payload),
    }

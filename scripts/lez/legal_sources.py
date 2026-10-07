"""Archive the explicitly identified official PDF attachments; do not infer GIS polygons."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .common import WORK, atomic_bytes, atomic_json, event, file_hash, now, relative


def archive_sources(work=WORK, refresh=False):
    import requests
    work = Path(work)
    registry = json.loads((work / "config/legal_pdf_sources.json").read_text())
    folder = work / "data/raw/legal"
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    with requests.Session() as session:
        session.headers["User-Agent"] = "Hanoi-LEZ-research/0.3 (official PDF archive; sequential)"
        for source in registry["sources"]:
            path = folder / (source["source_id"] + ".pdf")
            manifest_path = path.with_suffix(".manifest.json")
            if not refresh:
                try:
                    previous = json.loads(manifest_path.read_text())
                    if previous.get("requested_url") == source["url"] and previous.get("sha256") == file_hash(path):
                        results.append(previous)
                        continue
                except (OSError, ValueError, TypeError):
                    pass
            result = dict(source, requested_url=source["url"], captured_at=now(), gis_geometry_extracted=False)
            result['attempts'] = []
            urls = [source['url'], *source.get('fallback_urls', [])]
            for url in dict.fromkeys(urls):
                for attempt in range(2):
                    retry_delay = 2
                    try:
                        response = session.get(url, timeout=(10, 30), stream=True)
                        try:
                            if response.status_code == 429:
                                result['deferred_due_to_rate_limit'] = True
                                header = response.headers.get('Retry-After', '')
                                try:
                                    retry_delay = max(2., float(header))
                                except ValueError:
                                    from email.utils import parsedate_to_datetime
                                    try:
                                        retry_delay = max(2., (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds())
                                    except (TypeError, ValueError, OverflowError):
                                        retry_delay = 5
                                # Do not evade the server's limit by immediately switching mirrors.
                                if retry_delay > 60:
                                    raise ValueError('Server requested a wait longer than this run budget; retry on a later run')
                            response.raise_for_status()
                            chunks, size = [], 0
                            for chunk in response.iter_content(128 * 1024):
                                size += len(chunk)
                                if size > 25 * 1024 * 1024:
                                    raise ValueError('PDF exceeds 25 MiB')
                                chunks.append(chunk)
                            raw = b''.join(chunks)
                            if not raw.startswith(b'%PDF-'):
                                raise ValueError('Expected a PDF signature, not an HTML error page')
                            atomic_bytes(path, raw)
                            result.update(status='captured', final_url=response.url, retrieved_url=url,
                                          http_status=response.status_code, sha256=file_hash(path),
                                          local_file=relative(path, work), bytes=len(raw))
                            result.pop('error', None)
                            result.pop('deferred_due_to_rate_limit', None)
                            result['attempts'].append({'url':url,'attempt':attempt + 1,'status':'captured'})
                            break
                        finally:
                            response.close()
                    except (requests.RequestException, ValueError) as exc:
                        result.update(status='fetch_failed', error=str(exc))
                        result['attempts'].append({'url':url,'attempt':attempt + 1,'error':str(exc)})
                        if 'Server requested a wait' in str(exc):
                            break
                        if attempt == 0:
                            time.sleep(retry_delay)
                if result.get('status') == 'captured' or result.get('deferred_due_to_rate_limit'):
                    break
            atomic_json(manifest_path, result)
            results.append(result)
            event("sources", "Lưu PDF nguồn chính thức", source_id=source["source_id"], status=result["status"])
            time.sleep(1)
    atomic_json(work / "reports/boundaries/legal_pdf_capture.json", {"recorded_at":now(),"sources":results})
    return results

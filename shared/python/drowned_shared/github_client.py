from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from urllib.parse import quote

import requests

from .constants import GITHUB_API, GITHUB_UPLOADS, GITHUB_API_VERSION
from .errors import AuthenticationError, NetworkError, RateLimitError, ReleaseConflictError


class GitHubClient:
    def __init__(self, token: str, owner: str, repo: str, branch: str = "main"):
        self.owner = owner.strip()
        self.repo = repo.strip()
        self.branch = branch.strip() or "main"
        self.token = token.strip()

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "Drowned-Distribution-Suite/0.3",
        }
        self.s = requests.Session()
        self.s.headers.update(headers)

        self.raw_s = requests.Session()
        self.raw_s.headers.update({
            "User-Agent": "Drowned-Distribution-Suite/0.3",
            "Accept": "application/octet-stream",
            "Cache-Control": "no-cache",
        })

        if self.token:
            auth = f"Bearer {self.token}"
            self.s.headers["Authorization"] = auth
            # Authentication is harmless for raw endpoints and is useful if the
            # repository is made private later. Public metadata does not depend on it.
            self.raw_s.headers["Authorization"] = auth

    @staticmethod
    def _permission_help(status: int, body: str) -> str:
        body_lower = body.lower()
        if status == 403 and (
            "resource not accessible by personal access token" in body_lower
            or "resource not accessible" in body_lower
        ):
            return (
                "GitHub bu Personal Access Token ile işlemi reddetti (HTTP 403).\n\n"
                "Fine-grained PAT ayarlarını kontrol et:\n"
                "• Repository access: dağıtım repository'si seçili olmalı\n"
                "• Contents: Read and write\n"
                "• Workflows: Read and write (repository workflow dosyaları içeriyor veya "
                "hedef commit workflow değişikliği taşıyorsa gerekebilir)\n\n"
                "Token izinleri GitHub hesabından değiştirildikten sonra uygulamada token'ı "
                "yeniden kaydet."
            )
        if status == 403:
            return f"GitHub işlemi yasakladı (HTTP 403): {body[:500]}"
        return f"GitHub HTTP {status}: {body[:800]}"

    def _request(self, method, url, **kw):
        timeout = kw.pop("timeout", 60)
        for attempt in range(5):
            try:
                r = self.s.request(method, url, timeout=timeout, **kw)
            except requests.RequestException as exc:
                if attempt == 4:
                    raise NetworkError(str(exc)) from exc
                time.sleep(2 ** attempt)
                continue

            if r.status_code in (401, 403) and r.headers.get("X-RateLimit-Remaining") == "0":
                raise RateLimitError("GitHub API rate limit reached")
            if r.status_code == 401:
                raise AuthenticationError("GitHub authentication failed. Token geçersiz veya süresi dolmuş.")
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            if not r.ok:
                message = self._permission_help(r.status_code, r.text)
                if r.status_code == 403:
                    raise AuthenticationError(message)
                raise NetworkError(message)
            if r.status_code == 204:
                return None
            return r.json() if "json" in r.headers.get("content-type", "") else r.content

    def repo_info(self):
        return self._request("GET", f"{GITHUB_API}/repos/{self.owner}/{self.repo}")

    def raw_url(self, path: str) -> str:
        encoded = "/".join(quote(x, safe="") for x in path.strip("/").split("/"))
        return (
            f"https://raw.githubusercontent.com/{quote(self.owner, safe='')}/"
            f"{quote(self.repo, safe='')}/{quote(self.branch, safe='')}/{encoded}"
        )

    def raw_content(self, path: str):
        try:
            r = self.raw_s.get(self.raw_url(path), timeout=45)
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc
        if r.status_code == 404:
            return None
        if not r.ok:
            raise NetworkError(f"raw GitHub HTTP {r.status_code}: {r.text[:500]}")
        return r.content

    def raw_json(self, path: str):
        raw = self.raw_content(path)
        return None if raw is None else json.loads(raw.decode("utf-8"))

    def release_by_tag(self, tag):
        r = self.s.get(
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/releases/tags/{quote(tag, safe='')}",
            timeout=30,
        )
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403) and r.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimitError("GitHub API rate limit reached")
        if r.status_code == 401:
            raise AuthenticationError("GitHub authentication failed")
        if not r.ok:
            message = self._permission_help(r.status_code, r.text)
            if r.status_code == 403:
                raise AuthenticationError(message)
            raise NetworkError(message)
        return r.json()

    def create_release(self, tag, name, body, prerelease=False):
        if self.release_by_tag(tag):
            raise ReleaseConflictError(tag)
        return self._request(
            "POST",
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/releases",
            json={
                "tag_name": tag,
                "target_commitish": self.branch,
                "name": name,
                "body": body,
                "draft": True,
                "prerelease": prerelease,
            },
        )

    def publish_release(self, rid, prerelease=False):
        return self._request(
            "PATCH",
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/releases/{rid}",
            json={"draft": False, "prerelease": prerelease},
        )

    def delete_release(self, rid: int) -> bool:
        r = self.s.delete(
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/releases/{rid}",
            timeout=60,
        )
        if r.status_code == 404:
            return False
        if r.status_code in (401, 403) and r.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimitError("GitHub API rate limit reached")
        if r.status_code == 401:
            raise AuthenticationError("GitHub authentication failed")
        if r.status_code != 204:
            message = self._permission_help(r.status_code, r.text)
            if r.status_code == 403:
                raise AuthenticationError(message)
            raise NetworkError(message)
        return True

    def delete_tag_ref(self, tag: str) -> bool:
        url = f"{GITHUB_API}/repos/{self.owner}/{self.repo}/git/refs/tags/{quote(tag, safe='')}"
        r = self.s.delete(url, timeout=60)
        if r.status_code == 404:
            return False
        if r.status_code in (401, 403) and r.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimitError("GitHub API rate limit reached")
        if r.status_code == 401:
            raise AuthenticationError("GitHub authentication failed")
        if r.status_code != 204:
            message = self._permission_help(r.status_code, r.text)
            if r.status_code == 403:
                raise AuthenticationError(message)
            raise NetworkError(message)
        return True

    def upload_asset(self, rid, name, path: Path, content_type="application/octet-stream", progress=None):
        total = path.stat().st_size

        class Reader:
            def __init__(self, fp):
                self.fp = fp
                self.sent = 0

            def read(self, n=-1):
                block = self.fp.read(n)
                if block:
                    self.sent += len(block)
                    if progress:
                        progress(self.sent, total)
                return block

            def __getattr__(self, attr):
                return getattr(self.fp, attr)

        with path.open("rb") as handle:
            r = self.s.post(
                f"{GITHUB_UPLOADS}/repos/{self.owner}/{self.repo}/releases/{rid}/assets",
                params={"name": name},
                headers={"Content-Type": content_type, "Content-Length": str(total)},
                data=Reader(handle),
                timeout=(30, 12 * 60 * 60),
            )
        if not r.ok:
            message = self._permission_help(r.status_code, r.text)
            if r.status_code == 403:
                raise AuthenticationError(message)
            raise NetworkError(f"asset upload: {message}")
        return r.json()

    def content_sha(self, path: str):
        url = (
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/"
            + "/".join(quote(x, safe="") for x in path.split("/"))
        )
        r = self.s.get(url, params={"ref": self.branch}, timeout=30)
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403) and r.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimitError("GitHub API rate limit reached")
        if r.status_code == 401:
            raise AuthenticationError("GitHub authentication failed")
        if not r.ok:
            message = self._permission_help(r.status_code, r.text)
            if r.status_code == 403:
                raise AuthenticationError(message)
            raise NetworkError(message)
        return r.json()["sha"]

    def content(self, path):
        raw = self.raw_content(path)
        return raw, (self.content_sha(path) if raw is not None else None)

    def upsert_text(self, path, text, message):
        sha = self.content_sha(path)
        payload = {
            "message": message,
            "content": base64.b64encode(text.encode()).decode(),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        url = (
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/"
            + "/".join(quote(x, safe="") for x in path.split("/"))
        )
        return self._request("PUT", url, json=payload)

    def upsert_bytes(self, path, data, message):
        sha = self.content_sha(path)
        payload = {
            "message": message,
            "content": base64.b64encode(data).decode(),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        url = (
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/"
            + "/".join(quote(x, safe="") for x in path.split("/"))
        )
        return self._request("PUT", url, json=payload)

    def delete_repo_file(self, path: str, message: str) -> bool:
        sha = self.content_sha(path)
        if not sha:
            return False
        url = (
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/"
            + "/".join(quote(x, safe="") for x in path.split("/"))
        )
        self._request(
            "DELETE",
            url,
            json={"message": message, "sha": sha, "branch": self.branch},
        )
        return True

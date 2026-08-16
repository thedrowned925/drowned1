from __future__ import annotations
import base64, time
from pathlib import Path
from urllib.parse import quote
import requests
from .constants import GITHUB_API,GITHUB_UPLOADS,GITHUB_API_VERSION
from .errors import AuthenticationError, NetworkError, RateLimitError, ReleaseConflictError

class GitHubClient:
    def __init__(self, token:str, owner:str, repo:str, branch="main"):
        self.owner=owner.strip(); self.repo=repo.strip(); self.branch=branch.strip() or "main"
        self.s=requests.Session(); self.s.headers.update({"Accept":"application/vnd.github+json","X-GitHub-Api-Version":GITHUB_API_VERSION,"User-Agent":"Drowned-Distribution-Suite/0.1"})
        if token: self.s.headers["Authorization"]=f"Bearer {token.strip()}"
    def _request(self, method,url,**kw):
        for attempt in range(5):
            try: r=self.s.request(method,url,timeout=kw.pop("timeout",60),**kw)
            except requests.RequestException as e:
                if attempt==4: raise NetworkError(str(e)) from e
                time.sleep(2**attempt); continue
            if r.status_code in (401,403) and r.headers.get("X-RateLimit-Remaining") == "0": raise RateLimitError("GitHub API rate limit reached")
            if r.status_code == 401: raise AuthenticationError("GitHub authentication failed")
            if r.status_code in (429,500,502,503,504) and attempt<4: time.sleep(2**attempt); continue
            if not r.ok: raise NetworkError(f"GitHub HTTP {r.status_code}: {r.text[:800]}")
            if r.status_code==204: return None
            return r.json() if "json" in r.headers.get("content-type","") else r.content
    def repo_info(self): return self._request("GET",f"{GITHUB_API}/repos/{self.owner}/{self.repo}")
    def release_by_tag(self, tag):
        r=self.s.get(f"{GITHUB_API}/repos/{self.owner}/{self.repo}/releases/tags/{quote(tag,safe='')}",timeout=30)
        if r.status_code==404: return None
        if not r.ok: raise NetworkError(r.text[:800])
        return r.json()
    def create_release(self, tag,name,body,prerelease=False):
        if self.release_by_tag(tag): raise ReleaseConflictError(tag)
        return self._request("POST",f"{GITHUB_API}/repos/{self.owner}/{self.repo}/releases",json={"tag_name":tag,"name":name,"body":body,"draft":True,"prerelease":prerelease})
    def publish_release(self, rid, prerelease=False): return self._request("PATCH",f"{GITHUB_API}/repos/{self.owner}/{self.repo}/releases/{rid}",json={"draft":False,"prerelease":prerelease})
    def upload_asset(self,rid,name,path:Path,content_type="application/octet-stream",progress=None):
        total=path.stat().st_size
        class Reader:
            def __init__(self,fp): self.fp=fp; self.sent=0
            def read(self,n=-1):
                b=self.fp.read(n)
                if b: self.sent+=len(b); progress and progress(self.sent,total)
                return b
            def __getattr__(self,n): return getattr(self.fp,n)
        with path.open("rb") as f:
            r=self.s.post(f"{GITHUB_UPLOADS}/repos/{self.owner}/{self.repo}/releases/{rid}/assets",params={"name":name},headers={"Content-Type":content_type,"Content-Length":str(total)},data=Reader(f),timeout=(30,12*60*60))
        if not r.ok: raise NetworkError(f"asset upload {r.status_code}: {r.text[:800]}")
        return r.json()
    def content(self,path):
        url=f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/"+"/".join(quote(x,safe='') for x in path.split('/'))
        r=self.s.get(url,params={"ref":self.branch},timeout=30)
        if r.status_code==404: return None,None
        if not r.ok: raise NetworkError(r.text[:800])
        j=r.json(); return base64.b64decode(j["content"].replace("\n","")),j["sha"]
    def upsert_text(self,path,text,message):
        raw,sha=self.content(path); payload={"message":message,"content":base64.b64encode(text.encode()).decode(),"branch":self.branch}
        if sha: payload["sha"]=sha
        url=f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/"+"/".join(quote(x,safe='') for x in path.split('/'))
        return self._request("PUT",url,json=payload)
    def upsert_bytes(self,path,data,message):
        _,sha=self.content(path); payload={"message":message,"content":base64.b64encode(data).decode(),"branch":self.branch}
        if sha: payload["sha"]=sha
        url=f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/"+"/".join(quote(x,safe='') for x in path.split('/'))
        return self._request("PUT",url,json=payload)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
西瓜短剧 (m.xgshort.com) —— OK影视 / TVBox py 爬虫

适配要点（相比原版的关键改动）：
1. 不继承 base.Spider —— 原版依赖 OK影视注入的 base 模块，很多版本并不提供该模块，
   导入即失败，表现就是"源加载不出"。这里 Spider 是纯 Python 类，任何内核都能导入。
2. 不依赖 argparse / __main__ 之外的东西；所有网络请求走 requests，带重试与退避。
3. 方法签名兼容 TVBox 约定：homeContent(filter) / categoryContent(tid,pg,filter,ext)
   / searchContent(key,quick,pg) / detailContent(ids) / playerContent(flag,id,vipFlags)。
4. homeContent 返回的 list 会被部分内核当作首页推荐，这里直接给首页片单，
   避免"分类有但首页空"。
5. 返回 header 用 dict（TVBox 标准），不是 json 字符串。
"""

import json
import random
import time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

BASE = "https://m.xgshort.com"
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S9180) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
)
REFERER = BASE + "/"


class ApiError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def _headers(token: Optional[str] = None, json_body: bool = False) -> Dict[str, str]:
    h = {
        "User-Agent": MOBILE_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": REFERER,
        "Origin": BASE,
    }
    if json_body:
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = token if token.startswith("Bearer ") else "Bearer " + token
    return h


class XgShort:
    """西瓜短剧接口封装，所有方法返回接口 data 字段。"""

    def __init__(self, timeout: float = 15.0, retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._token: Optional[str] = None
        self.series_info: Dict[str, Any] = {}
        self._tags_cache: Optional[List[Dict[str, Any]]] = None

    # ---------- 基础请求 ----------
    def _request(self, method, path, params=None, body=None, auth=False):
        url = BASE + path
        last_err = None
        for attempt in range(1, self.retries + 1):
            token = self.token() if auth else None
            try:
                resp = self.session.request(
                    method, url,
                    params=params,
                    data=json.dumps(body) if body is not None else None,
                    headers=_headers(token, json_body=body is not None),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_err = exc
                time.sleep(0.5 * attempt)
                continue

            if resp.status_code == 401 and auth and attempt == 1:
                self._token = None
                continue
            if resp.status_code >= 500 or resp.status_code == 429:
                last_err = ApiError("服务端返回 %s" % resp.status_code, resp.status_code)
                time.sleep(0.5 * attempt)
                continue
            if resp.status_code not in (200, 201, 204):
                raise ApiError("HTTP %s" % resp.status_code, resp.status_code, resp.text[:300])
            try:
                data = resp.json()
            except ValueError:
                raise ApiError("返回非 JSON：%s" % resp.text[:200])
            if isinstance(data, dict) and data.get("statusCode") not in (None, 200):
                raise ApiError(str(data.get("message")), data.get("statusCode"), data)
            if isinstance(data, dict) and data.get("code") not in (None, 200, 0):
                raise ApiError(str(data.get("msg")), data.get("code"), data)
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return data
        raise ApiError("请求失败：%s" % last_err)

    def token(self) -> str:
        if self._token:
            return self._token
        data = self._request("POST", "/api/auth/guest-login", body={"guestToken": ""})
        if not isinstance(data, dict) or not data.get("access_token"):
            raise ApiError("guest-login 未返回 access_token")
        self._token = data["access_token"]
        return self._token

    # ---------- 业务接口 ----------
    def channels(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/api/home/categories")
        if not isinstance(data, list):
            raise ApiError("categories 结构异常")
        return [c for c in data if c.get("isEnabled", True)]

    def home(self, channeid: int, page: int = 1) -> Dict[str, Any]:
        data = self._request("GET", "/api/home/gethomemodules",
                             params={"channeid": channeid, "page": page})
        banners, videos = [], []
        for module in (data or {}).get("list") or []:
            mtype = module.get("type")
            if mtype == 0:
                banners.extend(module.get("banners") or [])
            elif isinstance(mtype, int) and 0 < mtype < 1000:
                videos.extend(module.get("list") or [])
        return {"banners": banners, "videos": videos}

    def filter_tags(self) -> List[Dict[str, Any]]:
        if self._tags_cache is not None:
            return self._tags_cache
        data = self._request("GET", "/api/list/getfilterstags")
        self._tags_cache = (data or {}).get("list") or []
        return self._tags_cache

    def videos(self, channeid: int, page: int = 1, size: int = 20,
               ids: str = "0,0,0,0,0,0") -> List[Dict[str, Any]]:
        data = self._request("GET", "/api/list/getfiltersdata",
                             params={"channeid": channeid, "ids": ids,
                                     "page": page, "size": size})
        return (data or {}).get("list") or []

    def search(self, keyword: str, page: int = 1, size: int = 20,
               category_id: Optional[int] = None) -> List[Dict[str, Any]]:
        params = {"keyword": keyword, "page": page, "size": size}
        if category_id:
            params["categoryId"] = category_id
        data = self._request("GET", "/api/list/fuzzysearch", params=params)
        return (data or {}).get("list") or []

    def episodes(self, series_short_id: str) -> List[Dict[str, Any]]:
        data = self._request("GET", "/api/video/episodes",
                             params={"seriesShortId": series_short_id, "page": 1, "size": 200},
                             auth=True)
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        if isinstance(data, dict):
            items = data.get("list") or data.get("episodes") or []
            self.series_info = data.get("seriesInfo") or {}
        elif isinstance(data, list):
            items = data
            self.series_info = {}
        else:
            items = []
        if not items:
            raise ApiError("未取到剧集：%s" % series_short_id)
        return items

    def play_urls(self, access_key: str) -> List[Dict[str, Any]]:
        data = self._request("POST", "/api/video/url/query",
                             body={"type": "episode", "accessKey": access_key}, auth=True)
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        urls = (data or {}).get("urls") if isinstance(data, dict) else None
        if not urls:
            raise ApiError("未返回播放地址")
        urls = [u for u in urls if u.get("url") or u.get("cdnUrl")]
        urls.sort(key=lambda u: u.get("rank") or 0, reverse=True)
        return urls


# ---------------- TVBox / OK影视 适配层 ----------------

class Spider:
    """
    纯 Python 类，不继承 base.Spider，任何内核都能导入。
    返回结构遵循 TVBox dict 约定。
    """

    def __init__(self, extend: str = ""):
        self.extend = extend or ""
        self.api = XgShort()
        self._id_map: Dict[str, str] = {}   # shortId -> 内部数字 id（备用）

    # 内核可能调用；返回 self 保证链式可用
    def init(self, extend=""):
        if extend:
            self.extend = extend
        return self

    def getName(self):
        return "西瓜短剧"

    def isVideoFormat(self, url):
        return True

    def isTextFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def setting(self):
        return {}

    # ---- 结构转换 ----
    @staticmethod
    def _vod(v: Dict[str, Any]) -> Dict[str, Any]:
        remark = str(v.get("upStatus") or "").strip()
        if v.get("upCount"):
            remark = (remark + " 共%d集" % v["upCount"]).strip()
        return {
            "vod_id": str(v.get("shortId") or v.get("url") or v.get("id") or ""),
            "vod_name": v.get("title") or "",
            "vod_pic": v.get("coverUrl") or "",
            "vod_remarks": remark,
            "vod_year": str(v.get("year") or ""),
            "vod_area": v.get("area") or "",
            "vod_director": v.get("director") or "",
            "vod_actor": v.get("author") or v.get("actor") or "",
            "vod_content": v.get("description") or v.get("intro") or "",
        }

    # ---- 首页 ----
    def homeContent(self, filter=False):
        classes, vods = [], []
        try:
            chans = self.api.channels()
            for c in chans:
                classes.append({"type_id": str(c["id"]), "type_name": c.get("name") or ""})
            if chans:
                vods = [self._vod(v) for v in self.api.home(int(chans[0]["id"]))["videos"]]
        except Exception as exc:
            return {"class": classes, "list": [], "msg": str(exc)}

        result = {"class": classes, "list": vods}
        if filter:
            result["filters"] = self._build_filters(classes)
        return result

    def _build_filters(self, classes):
        try:
            groups = self.api.filter_tags()
        except Exception:
            return {}
        filters = []
        for g in groups:
            name = g.get("name") or ""
            vals = [{"n": i.get("classifyName") or "全部", "v": str(i.get("index", 0))}
                    for i in g.get("list") or []]
            key = {"排序": "sort", "题材": "theme", "地区": "area",
                   "语言": "lang", "年份": "year", "状态": "state"}.get(name)
            if not key or not vals:
                continue
            filters.append({"key": key, "name": name, "value": vals})
        return {c["type_id"]: filters for c in classes} if filters else {}

    # ---- 分类 ----
    def categoryContent(self, tid, pg, filter=False, ext=None):
        page = int(pg or 1)
        size = 20
        ext = ext or {}
        # ids 顺序：排序,题材,地区,语言,年份,状态（与站点筛选项一致）
        order = ["sort", "theme", "area", "lang", "year", "state"]
        ids = ",".join(str(ext.get(k) or 0) for k in order)
        try:
            items = self.api.videos(int(tid), page=page, size=size, ids=ids)
        except Exception as exc:
            return {"list": [], "page": page, "pagecount": page, "limit": size,
                    "total": 0, "msg": str(exc)}
        return {
            "list": [self._vod(v) for v in items],
            "page": page,
            "pagecount": page + 1 if len(items) >= size else page,
            "limit": size,
            "total": 99999,
        }

    # ---- 搜索 ----
    def searchContent(self, key, quick=False, pg="1"):
        try:
            items = self.api.search(key, page=int(pg or 1))
        except Exception as exc:
            return {"list": [], "msg": str(exc)}
        return {"list": [self._vod(v) for v in items]}

    # ---- 详情 ----
    def detailContent(self, ids):
        short_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        if "$$$" in short_id:
            short_id = short_id.split("$$$")[0]
        try:
            eps = self.api.episodes(short_id)
        except Exception as exc:
            return {"list": [], "msg": str(exc)}

        info = self.api.series_info or {}
        first = eps[0] if eps else {}
        title = info.get("title") or first.get("seriesTitle") or short_id
        play_url = "#".join(
            "第%s集$%s" % (e.get("episodeNumber") or i + 1, e.get("episodeAccessKey") or "")
            for i, e in enumerate(eps)
        )
        vod = {
            "vod_id": short_id,
            "vod_name": title,
            "vod_pic": info.get("coverUrl") or "",
            "vod_score": str(info.get("score") or ""),
            "vod_actor": info.get("starring") or info.get("actor") or "",
            "vod_director": info.get("director") or "",
            "vod_area": info.get("area") or "",
            "vod_year": str(info.get("year") or ""),
            "vod_remarks": "共%d集" % len(eps),
            "vod_content": info.get("description") or info.get("intro") or title,
            "vod_play_from": "西瓜短剧",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    # ---- 播放 ----
    def playerContent(self, flag, id, vipFlags=None):
        key = id
        if isinstance(key, str) and "$" in key:
            key = key.split("$")[-1]
        try:
            streams = self.api.play_urls(key)
        except Exception as exc:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}, "msg": str(exc)}
        best = streams[0]
        play = best.get("url") or best.get("cdnUrl") or ""
        return {
            "parse": 0,
            "playUrl": "",
            "url": play,
            "header": {"User-Agent": MOBILE_UA, "Referer": REFERER},
        }

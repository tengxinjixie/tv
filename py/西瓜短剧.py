#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
西瓜短剧 (m.xgshort.com) —— TVBox 通用 py 爬虫

关键适配点：
1. 继承 base.spider.Spider，符合 TVBox / 影视仓 Python 爬虫加载约定。
2. playerContent 的 header 返回 JSON 字符串（TVBox 规范要求）。
3. 首页推荐走 homeVideoContent，避免部分内核不渲染 homeContent 的 list。
4. 搜索关键词原样传参，由 requests 自动 URL 编码（不要手动 quote，否则双重编码导致搜不到）。
"""

import json
import time

import requests
from requests.adapters import HTTPAdapter

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    # 兜底：极少数内核不提供 base 模块时仍能加载，但建议使用标准内核
    class BaseSpider:
        pass

BASE = "https://m.xgshort.com"
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S9180) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
)
REFERER = BASE + "/"


def _headers(token=None, json_body=False):
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


class XgShortApi:
    def __init__(self, timeout=15, retries=3):
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._token = None
        self.series_info = {}
        self._tags_cache = None

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
                last_err = RuntimeError("HTTP %s" % resp.status_code)
                time.sleep(0.5 * attempt)
                continue
            if resp.status_code not in (200, 201, 204):
                raise RuntimeError("HTTP %s" % resp.status_code)

            try:
                data = resp.json()
            except ValueError:
                raise RuntimeError("返回非 JSON")

            # 统一剥离外层
            if isinstance(data, dict):
                if data.get("statusCode") not in (None, 200):
                    raise RuntimeError(str(data.get("message")))
                if data.get("code") not in (None, 200, 0):
                    raise RuntimeError(str(data.get("msg")))
                if "data" in data:
                    return data["data"]
            return data
        raise RuntimeError("请求失败：%s" % last_err)

    def token(self):
        if self._token:
            return self._token
        data = self._request("POST", "/api/auth/guest-login", body={"guestToken": ""})
        if not isinstance(data, dict) or not data.get("access_token"):
            raise RuntimeError("guest-login 失败")
        self._token = data["access_token"]
        return self._token

    def channels(self):
        data = self._request("GET", "/api/home/categories")
        return [c for c in (data or []) if c.get("isEnabled", True)]

    def home(self, channel_id, page=1):
        data = self._request("GET", "/api/home/gethomemodules",
                             params={"channeid": channel_id, "page": page})
        videos = []
        for module in (data or {}).get("list") or []:
            mtype = module.get("type")
            if isinstance(mtype, int) and 0 < mtype < 1000:
                videos.extend(module.get("list") or [])
        return videos

    def filter_tags(self):
        if self._tags_cache is not None:
            return self._tags_cache
        data = self._request("GET", "/api/list/getfilterstags")
        self._tags_cache = (data or {}).get("list") or []
        return self._tags_cache

    def videos(self, channel_id, page=1, size=20, ids="0,0,0,0,0,0"):
        data = self._request("GET", "/api/list/getfiltersdata",
                             params={"channeid": channel_id, "ids": ids,
                                     "page": page, "size": size})
        return (data or {}).get("list") or []

    def search(self, keyword, page=1, size=20):
        # 关键词原样传参，由 requests 自动 URL 编码
        data = self._request("GET", "/api/list/fuzzysearch",
                             params={"keyword": keyword, "page": page, "size": size})
        return (data or {}).get("list") or []

    def episodes(self, series_short_id):
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
            raise RuntimeError("未取到剧集")
        return items

    def play_urls(self, access_key):
        data = self._request("POST", "/api/video/url/query",
                             body={"type": "episode", "accessKey": access_key}, auth=True)
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        urls = (data or {}).get("urls") if isinstance(data, dict) else None
        if not urls:
            raise RuntimeError("无播放地址")
        urls = [u for u in urls if u.get("url") or u.get("cdnUrl")]
        urls.sort(key=lambda u: u.get("rank") or 0, reverse=True)
        return urls


class Spider(BaseSpider):
    def __init__(self, extend=""):
        self.extend = extend or ""
        self.api = XgShortApi()

    def init(self, extend=""):
        if extend:
            self.extend = extend
        return self

    def getName(self):
        return "西瓜短剧"

    def isVideoFormat(self, url):
        return any(x in (url or "").lower() for x in (".m3u8", ".mp4", ".flv", ".ts"))

    def manualVideoCheck(self):
        return False

    @staticmethod
    def _vod(v):
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

    def homeContent(self, filter=False):
        classes = []
        try:
            for c in self.api.channels():
                classes.append({"type_id": str(c["id"]), "type_name": c.get("name") or ""})
        except Exception as e:
            return {"class": [], "list": [], "msg": str(e)}

        result = {"class": classes}
        if filter:
            try:
                groups = self.api.filter_tags()
                filters = []
                for g in groups:
                    name = g.get("name") or ""
                    vals = [{"n": i.get("classifyName") or "全部", "v": str(i.get("index", 0))}
                            for i in g.get("list") or []]
                    key = {"排序": "sort", "题材": "theme", "地区": "area",
                           "语言": "lang", "年份": "year", "状态": "state"}.get(name)
                    if key and vals:
                        filters.append({"key": key, "name": name, "value": vals})
                if filters:
                    result["filters"] = {c["type_id"]: filters for c in classes}
            except Exception:
                pass
        return result

    def homeVideoContent(self):
        """首页推荐，独立于 homeContent，兼容性更好"""
        try:
            chans = self.api.channels()
            if not chans:
                return {"list": []}
            videos = self.api.home(int(chans[0]["id"]))
            return {"list": [self._vod(v) for v in videos]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, ext=None):
        page = int(pg or 1)
        size = 20
        ext = ext or {}
        order = ["sort", "theme", "area", "lang", "year", "state"]
        ids = ",".join(str(ext.get(k) or 0) for k in order)
        try:
            items = self.api.videos(int(tid), page=page, size=size, ids=ids)
        except Exception as e:
            return {"list": [], "page": page, "pagecount": page, "limit": size,
                    "total": 0, "msg": str(e)}
        return {
            "list": [self._vod(v) for v in items],
            "page": page,
            "pagecount": page + 1 if len(items) >= size else page,
            "limit": size,
            "total": 99999,
        }

    def searchContent(self, key, quick=False, pg="1"):
        try:
            items = self.api.search(key, page=int(pg or 1))
        except Exception as e:
            return {"list": [], "msg": str(e)}
        return {"list": [self._vod(v) for v in items]}

    def detailContent(self, ids):
        short_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        if "$$$" in short_id:
            short_id = short_id.split("$$$")[0]
        try:
            eps = self.api.episodes(short_id)
        except Exception as e:
            return {"list": [], "msg": str(e)}

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

    def playerContent(self, flag, id, vipFlags=None):
        key = id.split("$")[-1] if isinstance(id, str) and "$" in id else id
        try:
            streams = self.api.play_urls(key)
        except Exception as e:
            return {"parse": 0, "playUrl": "", "url": "", "header": "{}", "msg": str(e)}

        best = streams[0]
        play = best.get("url") or best.get("cdnUrl") or ""
        # TVBox 规范：header 必须是 JSON 字符串
        header_json = json.dumps({
            "User-Agent": MOBILE_UA,
            "Referer": REFERER,
        })
        return {
            "parse": 0,
            "playUrl": "",
            "url": play,
            "header": header_json,
        }
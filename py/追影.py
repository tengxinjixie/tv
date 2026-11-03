# -*- coding: utf-8 -*-
# TVBox / 影视播放器 py 源：追影（zhuiying3.cc）
# 纯标准库实现；入口类 Spider，方法签名沿用 base.spider 约定。
# 以下接口均为 2026-11-03 在沙箱内对站点实测通过：
#   首页分类: 站点导航 /vodtype/<key>.html（本站 type key: dianying/dianshiju/zongyi/dongman/duanju）
#   分类列表: GET /vodshow/<key>-----------.html（第 1 页）
#             GET /vodshow/<key>-----------<pg>.html（第 2 页起；实测第 2 页返回该分类 10 条）
#   首页推荐: GET /index.php/ajax/data?mid=1&page=1&limit=30 （JSON；注意本站该接口忽略 tid，返回全站最新）
#   详情:     GET /video/<encoded_id>.html（HTML：标题/海报/简介/线路 tab + 选集链接）
#   搜索:     GET /vod/search/wd/<urlencoded key>.html
#   播放解析: GET /play/<encoded_id>-<sid>-<nid>.html
#             -> 取 MAC_PLAY_CONFIG 的 baseKey/requestUrl
#             -> POST /player_api.php  (url, timestamp, token=md5(baseKey+timestamp+UA))
#             -> 返回 data 先整体倒序再 base64 解码 -> JSON {jmurl, urltype}
import json
import re
import time
import base64
import hashlib
import urllib.parse
import urllib.request
import html as htmlmod

UA = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
CAT_KEYS = ["dianying", "dianshiju", "zongyi", "dongman", "duanju"]


class Spider(object):
    def __init__(self):
        self.host = "https://zhuiying3.cc"
        self.name = "追影"
        self.extend = ""

    # ---------------- 基础设施 ----------------
    def init(self, extend=""):
        self.extend = extend or ""
        m = re.search(r"https?://[^\s\"']+", self.extend)
        if m:
            self.host = m.group(0).rstrip("/")
        return

    def _get(self, url, headers=None, data=None, timeout=20):
        h = dict(HEADERS)
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
        for enc in ("utf-8", "gbk", "gb18030"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode("utf-8", "replace")

    def _get_json(self, url, headers=None, data=None, timeout=20):
        try:
            return json.loads(self._get(url, headers=headers, data=data, timeout=timeout))
        except Exception:
            return {}

    @staticmethod
    def _txt(s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", s)
        s = htmlmod.unescape(s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _norm_pic(pic, host):
        if not pic:
            return ""
        pic = pic.strip()
        if pic.startswith("mac://"):
            pic = "https://" + pic[6:]
        if pic.startswith("//"):
            pic = "https:" + pic
        elif pic.startswith("/"):
            pic = host + pic
        return pic

    def _parse_cards(self, s):
        """从列表页/搜索页 HTML 中抽出影片条目（去重、剔除热门搜索模块）。"""
        cut = s.rfind("hotsearch")
        region = s[cut:] if cut > 0 else s
        hot = set(re.findall(r'hotsearch_hot_item"\s+href="/video/([A-Za-z0-9]+)\.html"', region))
        vlist, seen = [], set()
        for m in re.finditer(r'href="/video/([A-Za-z0-9]+)\.html"', region):
            vid = m.group(1)
            if vid in seen or vid in hot:
                continue
            blk = region[m.start():m.start() + 1600]
            nm = re.search(r'title="([^"]{1,80})"', blk)
            name = self._txt(nm.group(1)) if nm else ""
            if not name:
                nm2 = re.search(r'<img[^>]+alt="([^"]{1,80})"', blk)
                name = self._txt(nm2.group(1)) if nm2 else ""
            pm = re.search(r'<img[^>]+src="([^"]+)"', blk)
            pic = pm.group(1) if pm else ""
            rm = re.search(r'class="[^"]*(?:remark|badge|score)[^"]*"[^>]*>([^<]{1,30})<', blk)
            rem = self._txt(rm.group(1)) if rm else ""
            if not name:
                continue
            seen.add(vid)
            vlist.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._norm_pic(pic, self.host),
                "vod_remarks": rem,
            })
        return vlist

    # ---------------- 首页 ----------------
    def homeContent(self, filter):
        result = {"class": [], "filters": {}, "list": []}
        try:
            home = self._get(self.host + "/")
        except Exception:
            home = ""
        classes, seen = [], set()
        for key, name in re.findall(
                r'href="/vodtype/([a-z0-9_]+)\.html"[^>]*>.*?<span>([^<]{1,10})</span>', home, re.S):
            if key in seen:
                continue
            seen.add(key)
            classes.append({"type_id": key, "type_name": name.strip()})
        if not classes:
            classes = [{"type_id": k, "type_name": n} for k, n in
                       zip(CAT_KEYS, ["电影", "电视剧", "综艺", "动漫", "短剧"])]
        result["class"] = classes
        # 首页推荐：全站最新（该 JSON 接口忽略 tid）
        try:
            j = self._get_json("%s/index.php/ajax/data?mid=1&page=1&limit=30" % self.host,
                               headers={"Referer": self.host + "/"})
            for it in (j.get("list") or [])[:20]:
                m = re.search(r"/video/([A-Za-z0-9]+)\.html", it.get("detail_link") or "")
                if not m:
                    continue
                result["list"].append({
                    "vod_id": m.group(1),
                    "vod_name": it.get("vod_name") or "",
                    "vod_pic": self._norm_pic(it.get("vod_pic") or it.get("vod_pic_bak") or "", self.host),
                    "vod_remarks": it.get("vod_remarks") or "",
                })
        except Exception:
            pass
        return result

    # ---------------- 分类列表 ----------------
    def _cat_key(self, tid):
        tid = str(tid or "").strip()
        if tid in CAT_KEYS:
            return tid
        mp = {"1": "dianying", "2": "dianshiju", "3": "zongyi", "4": "dongman", "26": "duanju"}
        return mp.get(tid, "dianying")

    def categoryContent(self, tid, pg, filter, extend):
        key = self._cat_key(tid)
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        if page <= 1:
            url = "%s/vodshow/%s-----------.html" % (self.host, key)
        else:
            url = "%s/vodshow/%s-----------%d.html" % (self.host, key, page)
        try:
            s = self._get(url, headers={"Referer": self.host + "/vodtype/%s.html" % key})
        except Exception:
            return {"page": page, "pagecount": page, "limit": 0, "total": 0, "list": []}
        vlist = self._parse_cards(s)
        pagecount = page + 1 if len(vlist) >= 10 else page
        return {"page": page, "pagecount": pagecount, "limit": len(vlist),
                "total": 0, "list": vlist}

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else str(ids)
        vid = str(vid).strip()
        m = re.search(r"/video/([A-Za-z0-9]+)\.html", vid)
        if m:
            vid = m.group(1)
        url = self.host + "/video/%s.html" % vid
        try:
            s = self._get(url, headers={"Referer": self.host + "/"})
        except Exception:
            return {"list": []}

        def pick(pat):
            mm = re.search(pat, s, re.S)
            return self._txt(mm.group(1)) if mm else ""

        vod = {
            "vod_id": vid,
            "vod_name": pick(r'<h1 class="detail-title">(.*?)</h1>') or pick(r"<title>(.*?)</title>"),
            "vod_pic": pick(r'<meta property="og:image" content="([^"]+)"'),
            "vod_year": pick(r'<span class="detail-year">\(?(\d{4})?\)?</span>'),
            "vod_remarks": pick(r'<div class="poster-badge">(.*?)</div>'),
            "vod_actor": pick(r'id="actorValBox">(.*?)</div>'),
            "vod_director": pick(r'<span class="label">导演:</span>\s*<span class="val actor-val-box">(.*?)</span>'),
            "vod_area": pick(r'<span class="m-val">(.*?)</span>\s*<span class="m-lbl">制片国家/地区</span>'),
            "vod_content": pick(r'<meta name="description" content="([^"]+)"'),
            "vod_play_from": "",
            "vod_play_url": "",
        }
        vod["vod_pic"] = self._norm_pic(vod["vod_pic"], self.host)
        if not vod["vod_name"]:
            vod["vod_name"] = "未知"
        vod["vod_content"] = re.sub(r"欢迎在追影.{0,40}?。", "", vod["vod_content"]).strip()

        tabs = re.findall(
            r'<div class="source-tab"\s+data-target="(ep-list-\d+)"\s*>\s*<span class="tab-name">(.*?)</span>',
            s, re.S)
        froms, urls = [], []
        for target, name in tabs:
            blk = re.search(r'<div class="ep-square-list"\s+id="%s"[^>]*>(.*?)</div>' % re.escape(target),
                            s, re.S)
            if not blk:
                continue
            body = blk.group(1)
            eps = re.findall(r'<a\s+href="(/play/[^"]+?)"[^>]*?data-name="([^"]*)"', body)
            if not eps:
                eps = [(h, self._txt(t)) for h, t in
                       re.findall(r'<a\s+href="(/play/[^"]+?)"[^>]*>(.*?)</a>', body, re.S)]
            if not eps:
                continue
            froms.append(self._txt(name) or target)
            urls.append("#".join("%s$%s" % (self._txt(n) or ("第%d集" % (i + 1)), h)
                                 for i, (h, n) in enumerate(eps)))
        if not froms:
            eps = re.findall(r'href="(/play/[A-Za-z0-9]+-\d+-\d+\.html)"', s)
            uniq, seen = [], set()
            for e in eps:
                if e not in seen:
                    seen.add(e)
                    uniq.append(e)
            if uniq:
                froms = ["默认线路"]
                urls = ["#".join("第%d集$%s" % (i + 1, h) for i, h in enumerate(uniq))]
        vod["vod_play_from"] = "$$$".join(froms)
        vod["vod_play_url"] = "$$$".join(urls)
        return {"list": [vod]}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        kw = urllib.parse.quote(str(key).strip())
        url = ("%s/vod/search/wd/%s.html" % (self.host, kw) if page <= 1
               else "%s/vod/search/page/%d/wd/%s.html" % (self.host, page, kw))
        try:
            s = self._get(url, headers={"Referer": self.host + "/"})
        except Exception:
            return {"list": []}
        return {"list": self._parse_cards(s)}

    # ---------------- 播放解析 ----------------
    def playerContent(self, flag, id, vipFlags):
        pid = str(id).strip()
        if pid.startswith("http"):
            url = pid
        elif pid.startswith("/"):
            url = self.host + pid
        else:
            url = self.host + "/play/" + pid
            if not url.endswith(".html"):
                url += ".html"
        try:
            page = self._get(url, headers={"Referer": self.host + "/"})
        except Exception as e:
            return {"parse": 0, "playUrl": "", "url": "", "msg": "播放页请求失败: %s" % e}
        m = re.search(r"baseKey:\s*[\"']([^\"']+)[\"']", page)
        m2 = re.search(r"requestUrl:\s*[\"']([^\"']+)[\"']", page)
        if not (m and m2):
            return {"parse": 0, "playUrl": "", "url": "",
                    "msg": "该线路未使用 MAC_PLAY_CONFIG（可能为内置/外链播放器）"}
        base_key, req_url = m.group(1), m2.group(1)
        ts = int(time.time())
        token = hashlib.md5((base_key + str(ts) + UA).encode("utf-8")).hexdigest()
        post = urllib.parse.urlencode({"url": req_url, "timestamp": ts, "token": token}).encode("utf-8")
        api_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": url,
            "Origin": self.host,
        }
        try:
            j = self._get_json(self.host + "/player_api.php", headers=api_headers, data=post)
        except Exception as e:
            return {"parse": 0, "playUrl": "", "url": "", "msg": "player_api 请求失败: %s" % e}
        if j.get("error"):
            return {"parse": 0, "playUrl": "", "url": "", "msg": str(j.get("error"))}
        raw = j.get("data") or ""
        try:
            plain = base64.b64decode(raw[::-1]).decode("utf-8", "replace")
            info = json.loads(plain)
        except Exception as e:
            return {"parse": 0, "playUrl": "", "url": "", "msg": "播放数据解密失败: %s" % e}
        real = (info.get("jmurl") or info.get("url") or "").replace("\\/", "/")
        if not real:
            return {"parse": 0, "playUrl": "", "url": "", "msg": "接口未返回可用地址"}
        ph = dict(HEADERS)
        ph["Referer"] = self.host + "/"
        return {"parse": 0, "playUrl": "", "url": real,
                "header": json.dumps(ph), "format": info.get("urltype") or ""}

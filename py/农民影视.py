# -*- coding: utf-8 -*-
"""
旺旺影视 TVBox Python 爬虫 (修复版)
源站: 旺旺影视 (https://vip.wwgz.cn:5200/)  苹果CMS/海洋CMS 类模板
接口: getName / init / homeContent / homeVideoContent / categoryContent
      / detailContent / searchContent / playerContent
      / isVideoFormat / manualVideoCheck
依赖: requests, beautifulsoup4

【修复记录】
1. 筛选(类型/地区/年代)不再写死 id:
   旧版本把"剧情片=10、动作片=5..."等 id 写死在代码里, 与站点实际分类 id
   不一致, 导致在 TVBox 里选"剧情"等筛选时拼接出的 class-10 地址
   在站点上不存在, 列表加载为空。
   现改为: 首次进入分类时自动抓取站点自己的分类页, 从页面里的筛选链接
   中解析出真实的参数名和 id, 筛选条件全部按站点真实链接拼接。
2. 分类列表解析增加多选择器兜底 (.globalPicList / #data_list /
   .stui-vodlist / .pic-list / .m-list / .list), 防止模板结构调整后空白。
3. 筛选 URL 支持 路径(pathinfo) 与 query 两种风格, 多条件可合并。
4. absUrl 兼容 ./ 开头的相对链接。
"""
import re
import json
import base64
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


class Spider(object):
    def __init__(self):
        self.siteUrl = "https://vip.wwgz.cn:5200"
        self.headers = {
            "User-Agent": ("Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Mobile Safari/537.36"),
            "Referer": self.siteUrl + "/",
        }
        # 主分类 (静态兜底用)
        self.categories = [
            ("电影", "1"), ("电视剧", "2"), ("综艺", "3"),
            ("动漫", "4"), ("短剧", "26"),("国产剧", "12"), ("港台泰", "13"), ("日韩剧", "14"), ("欧美剧", "15"),("动作片", "5"), ("喜剧片", "6"), ("爱情片", "7"), ("科幻片", "8"),
                  ("恐怖片", "9"), ("剧情片", "10"), ("战争片", "11"),
                  ("惊悚片", "16"), ("奇幻片", "17"),
        ]
        # 静态兜底: 子分类 (仅当自动发现失败时使用)
        self.subClasses = {
            "1": [("动作片", "5"), ("喜剧片", "6"), ("爱情片", "7"), ("科幻片", "8"),
                  ("恐怖片", "9"), ("剧情片", "10"), ("战争片", "11"),
                  ("惊悚片", "16"), ("奇幻片", "17")],
            "2": [("国产剧", "12"), ("港台泰", "13"), ("日韩剧", "14"), ("欧美剧", "15")],
            "4": [("动漫剧", "18"), ("动漫片", "19")],
        }
        # 静态兜底: 地区
        self.areas = ["大陆", "香港", "台湾", "美国", "韩国", "日本", "泰国",
                      "新加坡", "马来西亚", "印度", "英国", "法国", "加拿大",
                      "西班牙", "俄罗斯", "其它"]
        # 静态兜底: 年代
        self.years = [str(y) for y in range(2026, 1999, -1)]
        # 筛选 key -> URL 参数名 (静态兜底映射, 自动发现时以页面实际为准)
        self._FALLBACK_PARAM = {"type": "class", "area": "area", "year": "year",
                                "by": "by", "lang": "lang", "letter": "letter"}
        self._FILTER_NAME = {"type": "类型", "area": "地区", "year": "年代",
                             "by": "排序", "lang": "语言", "letter": "字母"}
        # URL 中可识别的参数 token
        self._TOKEN_KEYS = ("id", "pg", "order", "by", "class", "year",
                            "letter", "area", "lang")
        # tid -> {"base", "groups": {key: {value: href}}, "param_of": {key: param},
        #         "labels": {key: {value: text}}}
        self._cat_info = {}
        # 手动嗅探关键词 / 过滤词
        self.sniff_keys = [".mp4", ".m3u8", "item/video", "video_mp4", "video/tos"]
        self.sniff_ban = [".html", "=http"]

    # ---------------- 基础工具 ----------------
    def getName(self):
        return "旺旺影视"

    def init(self, extend=""):
        pass

    def fetch(self, url, data=None, params=None, timeout=15):
        """请求网页, 返回按 UTF-8 解码的文本"""
        if data is not None:
            resp = requests.post(url, data=data, headers=self.headers,
                                 timeout=timeout, verify=False)
        else:
            resp = requests.get(url, headers=self.headers, params=params,
                                timeout=timeout, verify=False)
        resp.encoding = "utf-8"
        return resp.text

    def absUrl(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("./"):
            url = url[2:]
        if url.startswith("http"):
            return url
        return self.siteUrl + "/" + url.lstrip("/")

    def dealUrl(self, href):
        return self.absUrl(href)

    def _find_by_text(self, soup, selector, text):
        """选择器 + 文本包含匹配 (替代 :contains)"""
        for el in soup.select(selector):
            if text in el.get_text():
                return el
        return None

    # ---------------- URL 参数读写 ----------------
    def _extract_param(self, href, key):
        """从 pathinfo (?m=vod-list-id-1-...html) 或 query (?id=1) 链接取值"""
        if not href:
            return ""
        try:
            q = urlparse(href).query
            if q and "=" in q:
                qs = parse_qs(q)
                if key in qs and qs[key]:
                    return qs[key][0]
        except Exception:
            pass
        m = re.search(r"(?<![A-Za-z])" + re.escape(key) + r"-([^/?&#.-]*)", href)
        if m:
            return m.group(1)
        return ""

    def _set_param(self, href, key, value):
        """替换/追加 URL 中的参数值, 兼容两种链接风格"""
        if not href:
            return href
        value = str(value)
        try:
            if urlparse(href).query and re.search(r"[?&]" + re.escape(key) + r"=", href):
                return re.sub(r"([?&]" + re.escape(key) + r"=)[^&#]*",
                              lambda m: m.group(1) + value, href, count=1)
        except Exception:
            pass
        new, n = re.subn(r"(?<![A-Za-z])" + re.escape(key) + r"-[^/?&#.-]*",
                         lambda m: key + "-" + value, href, count=1)
        if n:
            return new
        # 原链接没有该参数, 追加
        if ".html" in href:
            return href.replace(".html", "-" + key + "-" + value + ".html", 1)
        if "?" in href:
            return href + ("&" if not href.endswith(("?", "&")) else "") + key + "=" + value
        return href + "-" + key + "-" + value

    # ---------------- 播放地址加解密 ----------------
    def _encode_play_url(self, url):
        """Base64 URL-safe 编码播放页地址, 去掉尾部 '='"""
        if not url:
            return ""
        raw = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8")
        return "WW" + raw.rstrip("=")

    def _decode_play_url(self, token):
        """还原被 _encode_play_url 加密的播放页地址"""
        if not token:
            return ""
        if not token.startswith("WW"):
            return token
        raw = token[2:]
        pad = (-len(raw)) % 4
        raw += "=" * pad
        try:
            return base64.urlsafe_b64decode(raw.encode("utf-8")).decode("utf-8")
        except Exception:
            return token

    # ---------------- 分类页筛选自动发现 ----------------
    def _base_list_url(self, tid, pg=1):
        return (self.siteUrl + "/index.php?m=vod-list-id-{0}-pg-{1}-order--by--"
                              "class--year--letter--area--lang-.html").format(tid, pg)

    def _discover(self, tid):
        """
        抓取分类页, 从页面筛选链接中解析真实参数:
        返回 {"base", "groups", "param_of", "labels"}
        """
        info = {"base": self._base_list_url(tid, 1), "groups": {},
                "param_of": {}, "labels": {}}
        try:
            html = self.fetch(info["base"], timeout=10)
        except Exception:
            return info
        soup = BeautifulSoup(html, "html.parser")
        base_tokens = {k: self._extract_param(info["base"], k)
                       for k in self._TOKEN_KEYS}
        main_ids = {v for _, v in self.categories}
        main_names = {n for n, _ in self.categories}
        skip_words = {"首页", "更多", "全部", "展开", "收起"}
        raw = {}  # param -> {value: (text, href)}
        for a in soup.find_all("a", href=True):
            href = self.absUrl(a.get("href", ""))
            if "vod-list" not in href and "vod-type" not in href:
                continue
            # 只认第 1 页链接, 排除分页
            if self._extract_param(href, "pg") not in ("", "1"):
                continue
            text = a.get_text(strip=True)
            if not text or text in skip_words or len(text) > 8:
                continue
            if text in main_names:
                continue
            changed = []
            for k in ("class", "id", "area", "year", "by", "lang", "letter", "order"):
                v = self._extract_param(href, k)
                if v and v != base_tokens.get(k, ""):
                    changed.append((k, v))
            if len(changed) != 1:
                continue
            param, value = changed[0]
            # 排除"跳转到其他主分类"的导航链接
            if param == "id" and value in main_ids:
                continue
            raw.setdefault(param, {})
            if value not in raw[param]:
                raw[param][value] = (text, href)
        key_of = {"class": "type", "id": "type", "area": "area", "year": "year",
                  "by": "by", "lang": "lang", "letter": "letter", "order": "by"}
        for param, items in raw.items():
            key = key_of.get(param)
            if not key or not items:
                continue
            g = info["groups"].setdefault(key, {})
            lb = info["labels"].setdefault(key, {})
            for value, (text, href) in items.items():
                g[value] = href
                lb[value] = text
            # type 可能同时存在 class/id 两种链接, 保留首个参数名
            info["param_of"].setdefault(key, param)
        return info

    def _cat_info_of(self, tid):
        tid = str(tid)
        if tid not in self._cat_info:
            try:
                self._cat_info[tid] = self._discover(tid)
            except Exception:
                self._cat_info[tid] = {"base": self._base_list_url(tid, 1),
                                       "groups": {}, "param_of": {}, "labels": {}}
        return self._cat_info[tid]

    # ---------------- 列表解析 (多选择器兜底) ----------------
    def _looks_like_detail(self, url, has_img):
        if any(x in url for x in ("vod-list", "vod-search", "vod-type", "javascript", "#")):
            return False
        if has_img:
            return True
        return any(x in url for x in ("detail", "video", "play", "vod/"))

    def _parse_vod_list(self, soup):
        selectors = [".globalPicList li", "#data_list li", ".stui-vodlist li",
                     ".pic-list li", ".m-list li", ".list li"]
        lis = []
        for sel in selectors:
            lis = soup.select(sel)
            if lis:
                break
        videos, seen = [], set()
        for li in lis:
            a = li.select_one("a[href]") or li.find("a")
            if a is None:
                continue
            img = li.find("img")
            href = a.get("href", "")
            if not href:
                continue
            vid = self.dealUrl(href)
            if vid in seen:
                continue
            if not self._looks_like_detail(vid, img is not None):
                continue
            seen.add(vid)
            t = li.select_one(".sTit") or li.select_one(".title")
            if t:
                name = t.get_text(strip=True)
            elif a.get("title"):
                name = a.get("title").strip()
            else:
                name = a.get_text(strip=True)
            pic = ""
            if img:
                pic = img.get("data-echo") or img.get("data-src") or img.get("src") or ""
            s = li.select_one(".sDes")
            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self.absUrl(pic),
                "vod_remarks": s.get_text(strip=True) if s else "",
            })
        return videos

    # ---------------- 首页 ----------------
    def homeContent(self, filter):
        classes = [{"type_id": v, "type_name": n} for n, v in self.categories]
        filters = {}
        for n, v in self.categories:
            info = self._cat_info_of(v)
            flist = []
            # 类型
            group = info["groups"].get("type", {})
            if group:
                vals = [{"n": "全部", "v": ""}] + [
                    {"n": info["labels"]["type"].get(val, val), "v": val}
                    for val in group]
                flist.append({"key": "type", "name": "类型", "value": vals})
            elif v in self.subClasses:
                flist.append({
                    "key": "type", "name": "类型",
                    "value": [{"n": "全部", "v": ""}] +
                             [{"n": n2, "v": v2} for n2, v2 in self.subClasses[v]],
                })
            # 地区
            group = info["groups"].get("area", {})
            if group:
                vals = [{"n": "全部", "v": ""}] + [
                    {"n": info["labels"]["area"].get(val, val), "v": val}
                    for val in group]
                flist.append({"key": "area", "name": "地区", "value": vals})
            else:
                flist.append({
                    "key": "area", "name": "地区",
                    "value": [{"n": "全部", "v": ""}] +
                             [{"n": a, "v": a} for a in self.areas],
                })
            # 年代
            group = info["groups"].get("year", {})
            if group:
                vals = [{"n": "全部", "v": ""}] + [
                    {"n": info["labels"]["year"].get(val, val), "v": val}
                    for val in group]
                flist.append({"key": "year", "name": "年代", "value": vals})
            else:
                flist.append({
                    "key": "year", "name": "年代",
                    "value": [{"n": "全部", "v": ""}] +
                             [{"n": y, "v": y} for y in self.years],
                })
            # 排序 (仅自动发现到时添加, 避免写错排序参数)
            if info["groups"].get("by"):
                group = info["groups"]["by"]
                vals = [{"n": "全部", "v": ""}] + [
                    {"n": info["labels"]["by"].get(val, val), "v": val}
                    for val in group]
                flist.append({"key": "by", "name": "排序", "value": vals})
            filters[v] = flist
        result = {"class": classes, "filters": filters}
        if not filter:
            result["list"] = self.homeVideoContent().get("list", [])
        return result

    def homeVideoContent(self):
        html = self.fetch(self.siteUrl + "/")
        soup = BeautifulSoup(html, "html.parser")
        return {"list": self._parse_vod_list(soup)}

    # ---------------- 分类 ----------------
    def categoryContent(self, tid, pg, filter, extend):
        ext = extend if isinstance(extend, dict) else json.loads(extend or "{}")
        tid = str(tid)
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        info = self._cat_info_of(tid)
        keys = ("type", "area", "year", "by", "lang", "letter")
        # 以分类基础地址为骨架 (含全部参数位), 逐项写入筛选值
        url = info.get("base") or self._base_list_url(tid, 1)
        for key in keys:
            sel = str(ext.get(key) or "").strip()
            if not sel:
                continue
            param = info["param_of"].get(key) or self._FALLBACK_PARAM.get(key, key)
            href = info["groups"].get(key, {}).get(sel, "")
            val = self._extract_param(href, param) if href else ""
            if not val:
                val = sel
            if self._extract_param(url, param) != val:
                url = self._set_param(url, param, val)
        url = self._set_param(url, "pg", str(pg))
        if not url.startswith("http"):
            url = self.absUrl(url)
        html = self.fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        videos = self._parse_vod_list(soup)
        page = pg
        return {
            "list": videos,
            "page": page,
            "pagecount": 9999 if videos else page,
            "limit": len(videos) or 30,
            "total": 999999,
        }

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        url = ids[0] if ids[0].startswith("http") else self.absUrl(ids[0])
        html = self.fetch(url)
        soup = BeautifulSoup(html, "html.parser")

        name = ""
        if soup.title and soup.title.string:
            name = re.split(r"[-_]", soup.title.string.strip())[0].strip()

        type_name = ""
        el = soup.select_one(".type-title")
        if el:
            type_name = el.get_text(strip=True)

        year = ""
        el = self._find_by_text(soup, "span", "年代：")
        if el:
            year = el.get_text(strip=True).replace("年代：", "").strip()

        actors = ""
        el = self._find_by_text(soup, ".sDes", "主演:")
        if el:
            actors = el.get_text(strip=True).replace("主演:", "").strip()

        desc = type_name

        lines, plays = [], []
        line_names = ["旺旺专线①", "旺旺专线②"]
        uls = soup.select("#leftTabBox ul")
        if not uls:
            uls = soup.select(".playfrom li, .playlist-title li")
        for idx, ul in enumerate(uls):
            if ul.find("li") is None and not ul.get_text(strip=True):
                continue
            if idx < len(line_names):
                line = line_names[idx]
            else:
                line = "旺旺专线"
            lines.append(line)
        num_lists = soup.select("#leftTabBox .numList")
        if not num_lists:
            num_lists = soup.select(".playlist ul, .play-list ul")
        for numList in num_lists:
            eps = []
            for a in numList.select("li a"):
                enc = self._encode_play_url(self.dealUrl(a.get("href", "")))
                eps.append("%s$%s" % (a.get_text(strip=True), enc))
            eps.reverse()
            plays.append("#".join(eps))
        # 线路数与播放列表数对齐
        while len(lines) < len(plays):
            lines.append("旺旺专线%d" % (len(lines) + 1))

        vod = {
            "vod_id": ids[0],
            "vod_name": name,
            "type_name": type_name,
            "vod_year": year,
            "vod_area": "",
            "vod_actor": actors,
            "vod_content": desc,
            "vod_play_from": "$$$".join(lines),
            "vod_play_url": "$$$".join(plays),
        }
        return {"list": [vod]}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick):
        """
        搜索: GET 方式, 结果列表与首页一致 (.globalPicList),
        兼容 #data_list 结构。
        """
        url = self.siteUrl + "/index.php"
        html = self.fetch(url, params={"m": "vod-search", "wd": key})
        soup = BeautifulSoup(html, "html.parser")
        videos = self._parse_vod_list(soup)

        # 兜底: 结构不符时手动扫 #data_list
        if not videos:
            box = soup.select_one("#data_list")
            if box:
                for a in box.select("li a"):
                    href = a.get("href", "")
                    if not href:
                        continue
                    img = a.find("img")
                    t = a.select_one(".sTit")
                    name = (t.get_text(strip=True) if t else
                            (a.get("title") or a.get_text(strip=True))).strip()
                    videos.append({
                        "vod_id": self.dealUrl(href),
                        "vod_name": name,
                        "vod_pic": self.absUrl(img.get("src") if img else ""),
                        "vod_remarks": "",
                    })

        seen, uniq = set(), []
        for v in videos:
            if v["vod_id"] in seen:
                continue
            seen.add(v["vod_id"])
            uniq.append(v)
        return {"list": uniq}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick)

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        real = self._decode_play_url(id)
        url = real if real.startswith("http") else self.absUrl(real)
        return {"parse": 1, "playUrl": "", "url": url, "header": self.headers}

    def isVideoFormat(self, url):
        for k in self.sniff_keys:
            if k in url:
                return not any(b in url for b in self.sniff_ban)
        return False

    def manualVideoCheck(self):
        return True

    def getDependence(self):
        return []

    def setExtendInfo(self, extend):
        pass

    def getExtendInfo(self):
        return {}

    def setFilterInfo(self, filter_):
        pass


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    spider = Spider()
    print("== search 狂飙 ==")
    sea = spider.searchContent("狂飙", False)
    print(json.dumps(sea, ensure_ascii=False)[:1200])

# -*- coding: utf-8 -*-
import re
import json
import base64
from urllib.parse import urlparse, parse_qs, quote

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
        self.categories = [
            ("电影", "1"),
            ("电视剧", "2"),
            ("综艺", "3"),
            ("动漫", "4"),
            ("短剧", "26"),
        ]
        self.subClasses = {
            "1": [("动作片", "5"), ("喜剧片", "6"), ("爱情片", "7"), ("科幻片", "8"),
                  ("恐怖片", "9"), ("剧情片", "10"), ("战争片", "11"),
                  ("惊悚片", "16"), ("奇幻片", "17")],
            "2": [("国产剧", "12"), ("港台泰", "13"), ("日韩剧", "14"), ("欧美剧", "15")],
            "3": [],
            "4": [("动漫剧", "18"), ("动漫片", "19")],
            "26": [],
        }
        self.areas = ["大陆", "香港", "台湾", "美国", "韩国", "日本", "泰国",
                      "新加坡", "马来西亚", "印度", "英国", "法国", "加拿大",
                      "西班牙", "俄罗斯", "其它"]
        self.years = [str(y) for y in range(2026, 1999, -1)]
        self._FALLBACK_PARAM = {"type": "class", "area": "area", "year": "year",
                                "by": "by", "lang": "lang", "letter": "letter"}
        self._TOKEN_KEYS = ("id", "pg", "order", "by", "class", "year",
                            "letter", "area", "lang")
        self._cat_info = {}
        self.sniff_keys = [".mp4", ".m3u8", "item/video", "video_mp4", "video/tos"]
        self.sniff_ban = [".html", "=http"]

    # ---------------- 基础工具 ----------------
    def getName(self):
        return "旺旺影视"

    def init(self, extend=""):
        pass

    def fetch(self, url, data=None, params=None, timeout=15, extra_headers=None):
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)
        if data is not None:
            resp = requests.post(url, data=data, headers=headers,
                                 timeout=timeout, verify=False)
        else:
            resp = requests.get(url, headers=headers, params=params,
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
        for el in soup.select(selector):
            if text in el.get_text():
                return el
        return None

    def _clean(self, s):
        return (s or "").replace("\xa0", " ").replace("\u3000", " ").strip()

    # ---------------- URL 参数读写 ----------------
    def _extract_param(self, href, key):
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
        if ".html" in href:
            return href.replace(".html", "-" + key + "-" + value + ".html", 1)
        if "?" in href:
            return href + ("&" if not href.endswith(("?", "&")) else "") + key + "=" + value
        return href + "-" + key + "-" + value

    # ---------------- 播放地址加解密 ----------------
    def _encode_play_url(self, url):
        if not url:
            return ""
        raw = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8")
        return "WW" + raw.rstrip("=")

    def _decode_play_url(self, token):
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
        raw = {}
        for a in soup.find_all("a", href=True):
            href = self.absUrl(a.get("href", ""))
            if "vod-list" not in href and "vod-type" not in href:
                continue
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

    # ---------------- 列表解析（精准匹配旺旺影视 wap1 模板） ----------------
    def _looks_like_detail(self, url):
        """详情页特征：/vod-detail-id-xxx.html"""
        if not url:
            return False
        if any(x in url for x in ("javascript", "#", "vod-search", "vod-type", "vod-list")):
            return False
        return "vod-detail" in url or "/vod/" in url or "detail" in url

    def _parse_vod_list(self, soup):
        """解析视频列表，优先 #data_list li（搜索页/列表页通用）"""
        # 精准选择器 + 兜底
        selectors = [
            "#data_list li",              # 搜索页 + 分类页（旺旺 wap1 模板）
            ".ulPicTxt li",
            ".globalPicList li",
            ".stui-vodlist li",
            ".pic-list li",
            ".m-list li",
            ".list li",
            ".module-list li",
            ".vodlist li",
        ]
        lis = []
        for sel in selectors:
            lis = soup.select(sel)
            if lis:
                break
        if not lis:
            # 最终兜底：直接扫所有 a，找详情页链接
            lis = soup.find_all("li")

        videos, seen = [], set()
        for li in lis:
            # 取封面链接（第一个 a）
            a = li.select_one("a[href]") or li.find("a")
            if a is None:
                continue
            href = a.get("href", "")
            if not href:
                continue
            vid = self.dealUrl(href)
            if vid in seen:
                continue
            if not self._looks_like_detail(vid):
                continue
            seen.add(vid)

            # 标题：.sTit 优先，其次 .title，其次 a[title]，最后 a 文本
            name = ""
            t = li.select_one(".sTit") or li.select_one(".title")
            if t:
                name = t.get_text(strip=True)
            if not name and a.get("title"):
                name = a.get("title").strip()
            if not name:
                name = a.get_text(strip=True)
            if not name:
                continue

            # 封面图
            img = li.find("img")
            pic = ""
            if img:
                pic = (img.get("data-src") or img.get("data-echo")
                       or img.get("src") or "")
            # 过滤 lazy 占位图
            if pic and ("lazyload" in pic or pic.endswith(".gif")):
                pic = img.get("data-src") or ""

            # 备注：优先取"评分：x.x"，其次 .sDes 汇总
            remark = ""
            for sdes in li.select(".sDes"):
                txt = sdes.get_text(" ", strip=True)
                if "评分" in txt:
                    remark = txt
                    break
            if not remark:
                s = li.select_one(".sDes")
                remark = s.get_text(" ", strip=True) if s else ""
            # 清理"主演："这种空信息
            remark = self._clean(remark).replace("主演：", "").strip()

            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self.absUrl(pic),
                "vod_remarks": remark,
            })
        return videos

    # ---------------- 首页 ----------------
    def homeContent(self, filter):
        classes = [{"type_id": v, "type_name": n} for n, v in self.categories]
        filters = {}
        for n, v in self.categories:
            info = self._cat_info_of(v)
            flist = []

            type_vals = [{"n": "全部", "v": ""}]
            for sub_name, sub_id in self.subClasses.get(v, []):
                type_vals.append({"n": sub_name, "v": sub_id})
            if len(type_vals) == 1 and info["groups"].get("type"):
                for val, label in info["labels"].get("type", {}).items():
                    type_vals.append({"n": label, "v": val})
            flist.append({"key": "type", "name": "类型", "value": type_vals})

            area_vals = [{"n": "全部", "v": ""}]
            if info["groups"].get("area"):
                for val, label in info["labels"].get("area", {}).items():
                    area_vals.append({"n": label, "v": val})
            else:
                for a in self.areas:
                    area_vals.append({"n": a, "v": a})
            flist.append({"key": "area", "name": "地区", "value": area_vals})

            year_vals = [{"n": "全部", "v": ""}]
            if info["groups"].get("year"):
                for val, label in info["labels"].get("year", {}).items():
                    year_vals.append({"n": label, "v": val})
            else:
                for y in self.years:
                    year_vals.append({"n": y, "v": y})
            flist.append({"key": "year", "name": "年代", "value": year_vals})

            if info["groups"].get("by"):
                by_vals = [{"n": "全部", "v": ""}]
                for val, label in info["labels"].get("by", {}).items():
                    by_vals.append({"n": label, "v": val})
                if len(by_vals) > 1:
                    flist.append({"key": "by", "name": "排序", "value": by_vals})

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
        return {
            "list": videos,
            "page": pg,
            "pagecount": 9999 if videos else pg,
            "limit": len(videos) or 30,
            "total": 999999,
        }

    # ---------------- 详情 ----------------
    def _desc_item(self, soup, label):
        for div in soup.select(".page-bd .desc_item"):
            sp = div.find("span")
            if sp and label in sp.get_text():
                clone = BeautifulSoup(str(div), "html.parser")
                csp = clone.find("span")
                if csp:
                    csp.extract()
                return self._clean(clone.get_text(" ", strip=True))
        return ""

    def _parse_play_lines(self, soup):
        lines, plays = [], []
        hd = soup.select("#leftTabBox .hd li")
        if hd:
            for li in hd:
                name = li.get_text(strip=True)
                if name:
                    lines.append(name)

        line_names = ["高清线路①", "备用线路②"]
        if not lines:
            uls = soup.select("#leftTabBox ul")
            if not uls:
                uls = soup.select(".playfrom li, .playlist-title li")
            for idx, ul in enumerate(uls):
                if ul.find("li") is None and not ul.get_text(strip=True):
                    continue
                if idx < len(line_names):
                    lines.append(line_names[idx])
                else:
                    lines.append("旺旺专线%d" % (idx + 1))

        for i in range(min(2, len(lines))):
            lines[i] = line_names[i]

        num_lists = soup.select("#leftTabBox .numList")
        if not num_lists:
            num_lists = soup.select(".playlist ul, .play-list ul")

        for numList in num_lists:
            eps = []
            for a in numList.select("li a"):
                if not a.get("href"):
                    continue
                enc = self._encode_play_url(self.dealUrl(a.get("href", "")))
                eps.append("%s$%s" % (a.get_text(strip=True), enc))
            if not eps:
                continue
            eps.reverse()
            plays.append("#".join(eps))

        while len(lines) < len(plays):
            lines.append("旺旺专线%d" % (len(lines) + 1))

        return lines, plays

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else ids
        url = raw_id if raw_id.startswith("http") else self.absUrl(raw_id)
        html = self.fetch(url)
        soup = BeautifulSoup(html, "html.parser")

        name = ""
        if soup.title and soup.title.string:
            name = re.split(r"[-_]", soup.title.string.strip())[0].strip()
        t = soup.select_one(".page-bd h1.title a") or soup.select_one(".page-bd h1.title")
        if t:
            nt = t.get_text(strip=True)
            if nt:
                name = nt

        type_name = ""
        el = soup.select_one("h1.type-title")
        if el:
            type_name = el.get_text(strip=True)

        remarks = self._desc_item(soup, "状态")
        actors = self._desc_item(soup, "主演")
        director = self._desc_item(soup, "导演")
        year = self._desc_item(soup, "年代")
        area = self._desc_item(soup, "地区")

        desc = ""
        p = soup.select_one(".detail-con p")
        if p:
            desc = self._clean(p.get_text(" ", strip=True))
            desc = re.sub(r"^简\s*介\s*[:：]\s*", "", desc)
        if not desc:
            el = soup.select_one(".detail-con")
            if el:
                desc = self._clean(el.get_text(" ", strip=True))
                desc = re.sub(r"^.*?介\s*[:：]\s*", "", desc)
        if not desc:
            desc = type_name

        lines, plays = self._parse_play_lines(soup)

        vod = {
            "vod_id": raw_id,
            "vod_name": name,
            "type_name": type_name,
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actors,
            "vod_director": director,
            "vod_remarks": remarks,
            "vod_content": desc,
            "vod_play_from": "$$$".join(lines),
            "vod_play_url": "$$$".join(plays),
        }
        return {"list": [vod]}

    # ---------------- 搜索 ----------------
    def _search_once(self, key, pg=1):
        """搜索，只走真实存在的两个接口"""
        key_q = quote(key, safe="")
        T = 8  # 搜索短超时，避免 OK影视 判超时

        # 接口1：GET 动态接口（截图已证明可用）
        try:
            url = self.siteUrl + "/index.php?m=vod-search&wd=" + key_q
            if pg and int(pg) > 1:
                url += "&page=" + str(pg)
            html = self.fetch(
                url, timeout=T,
                extra_headers={"Referer": self.siteUrl + "/index.php?m=vod-search"})
            soup = BeautifulSoup(html, "html.parser")
            videos = self._parse_vod_list(soup)
            if videos:
                return videos
        except Exception:
            pass

        # 接口2：POST（form action="/index.php?m=vod-search" method="post"）
        try:
            url = self.siteUrl + "/index.php"
            html = self.fetch(
                url, data={"m": "vod-search", "wd": key}, timeout=T,
                extra_headers={"Referer": self.siteUrl + "/index.php?m=vod-search"})
            soup = BeautifulSoup(html, "html.parser")
            videos = self._parse_vod_list(soup)
            if videos:
                return videos
        except Exception:
            pass

        return []

    def searchContent(self, key, quick, pg=1):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        videos = self._search_once(key, pg)
        seen, uniq = set(), []
        for v in videos:
            vid = v.get("vod_id", "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            uniq.append(v)
        if quick and uniq:
            uniq = uniq[:1]
        return {"list": uniq}

    def searchContentPage(self, key, quick, pg):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        videos = self._search_once(key, pg)
        seen, uniq = set(), []
        for v in videos:
            vid = v.get("vod_id", "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            uniq.append(v)
        # OK影视 严格要求这些字段
        return {
            "list": uniq,
            "page": pg,
            "pagecount": 9999 if uniq else pg,
            "limit": len(uniq) or 30,
            "total": 999999,
        }

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
    print("count:", len(sea.get("list", [])))
    for v in sea.get("list", [])[:3]:
        print(json.dumps(v, ensure_ascii=False))
    print("== searchPage 狂飙 pg=1 ==")
    sea2 = spider.searchContentPage("狂飙", False, 1)
    print("keys:", list(sea2.keys()))
    print("count:", len(sea2.get("list", [])))
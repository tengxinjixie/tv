# -*- coding: utf-8 -*-
"""
极速追剧 jisuzhuiju.com 的 TVBox 系 py 源（OK影视 / AVBOX / NEWBOX / TYBox 等）

约定：
- 入口类固定为 Spider，优先继承宿主注入的 base.spider.Spider，无宿主时自动降级为普通类；
- 仅使用 Python 标准库（urllib），不依赖 requests；
- header 一律用 dict；vod_play_url 用 "名称$id|线路|集号" 形式。

站点实测接口（2026-11-03）：
- 首页/推荐：GET /                                     （服务端渲染 vod-card 卡片）
- 分类筛选：  GET /filter?channel=&type=&area=&year=&sort=hot&page=N
- 详情：      GET /detail/<vodId>.html                 （线路 tab + 选集 /vodplay/<id>-<key>-<n>.html）
- 搜索：      GET /search?keyword=&field=all&page=N
- 播放解析：  GET /api/play-url?vodId=&playFrom=<key>&index=<n>
              -> {"mode":"native","code":200,"url":"https://.../index.m3u8"}
"""

import sys
import re
import json
import time
import html as htmlmod
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:  # 命令行 / 非宿主环境下降级
    class _BaseSpider(object):
        def __init__(self):
            pass


class Spider(_BaseSpider):
    HOST = 'https://jisuzhuiju.com'
    siteKey = 'jisuzhuiju'
    siteName = '极速追剧'
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    # 频道：channel 参数
    CHANNELS = [
        ('1', '电视剧'),
        ('2', '电影'),
        ('3', '动漫'),
        ('4', '综艺'),
        ('5', '短剧'),
    ]

    # 各频道「类型」筛选项（取自站点 /filter 页实测，value 为 type 参数）
    TYPES = {
        '1': [('剧情', '7'), ('古装', '9'), ('战争', '10'), ('谍战', '11'), ('爱情', '12'),
              ('罪案', '13'), ('悬疑', '14'), ('家庭', '15'), ('军旅', '16'), ('喜剧', '17'),
              ('都市', '18'), ('武侠', '19'), ('言情', '20'), ('偶像', '21'), ('青春', '22'),
              ('农村', '23'), ('穿越', '24'), ('奇幻', '25'), ('历史', '26'), ('年代', '27'),
              ('科幻', '28'), ('生活', '29'), ('励志', '31'), ('婚姻', '32'), ('警匪', '33'),
              ('犯罪', '34'), ('推理', '35'), ('商战', '36'), ('宫廷', '37'), ('仙侠', '38'),
              ('神话', '39'), ('动作', '40'), ('复仇', '41'), ('惊悚', '42')],
        '2': [('动作', '43'), ('喜剧', '44'), ('爱情', '45'), ('科幻', '46'), ('恐怖', '47'),
              ('悬疑', '48'), ('犯罪', '49'), ('战争', '50'), ('剧情', '51'), ('动画', '52'),
              ('惊悚', '53'), ('冒险', '54'), ('奇幻', '55'), ('武侠', '56'), ('古装', '57'),
              ('历史', '58'), ('灾难', '59')],
        '3': [('热血', '60'), ('恋爱', '61'), ('校园', '62'), ('搞笑', '63'), ('奇幻', '64'),
              ('冒险', '65'), ('科幻', '66'), ('萌系', '67'), ('机战', '68'), ('悬疑', '69'),
              ('推理', '70'), ('竞技', '71'), ('治愈', '72'), ('日常', '73'), ('古风', '74'),
              ('武侠', '75'), ('历史', '76')],
        '4': [('选秀', '77'), ('情感', '78'), ('访谈', '79'), ('播报', '80'), ('搞笑', '81'),
              ('真人秀', '82'), ('生活', '83'), ('音乐', '84'), ('游戏', '85'), ('旅游', '86'),
              ('美食', '87'), ('纪实', '88'), ('体育', '89'), ('晚会', '90'), ('少儿', '91')],
        '5': [],
    }

    AREAS = ['大陆', '香港', '台湾', '韩国', '日本', '美国', '泰国', '法国', '英国', '德国', '印度', '其他']
    YEARS = ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '其他']
    SORTS = [('热度', 'hot'), ('时间', 'time'), ('评分', 'score')]

    PAGE_SIZE = 12

    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self.extend = ''
        self._extra_hosts = []
        self._cache = {}

    # ------------------------------------------------------------------ 基础
    def init(self, extend=''):
        """宿主入口：extend 支持 JSON（可带 host / hosts 覆盖域名）。"""
        self.extend = extend or ''
        try:
            super(Spider, self).init(extend)
        except Exception:
            pass
        ext = {}
        if isinstance(extend, dict):
            ext = extend
        elif isinstance(extend, str) and extend.strip().startswith('{'):
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}
        hosts = []
        if isinstance(ext, dict):
            if ext.get('host'):
                hosts.append(str(ext['host']))
            if isinstance(ext.get('hosts'), list):
                hosts.extend([str(h) for h in ext['hosts']])
        for h in hosts:
            h = h.strip().rstrip('/')
            if h and h not in self._extra_hosts and h != self.HOST:
                self._extra_hosts.append(h)

    def getName(self):
        return self.siteName

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        return ('.m3u8' in low) or ('.mp4' in low) or ('.flv' in low) or low.endswith('.ts')

    def manualVideoCheck(self):
        return False

    def _bases(self):
        return [self.HOST] + self._extra_hosts

    def _fetch(self, path, referer=None, timeout=15, retry=2):
        """取页面文本；主域名失败自动切换候选域名。返回 (text, base)。"""
        last = None
        for base in self._bases():
            url = base + path if path.startswith('/') else path
            for _ in range(retry):
                try:
                    req = urllib.request.Request(url, headers={
                        'User-Agent': self.UA,
                        'Referer': referer or (base + '/'),
                        'Accept': 'text/html,application/json,*/*',
                        'Accept-Language': 'zh-CN,zh;q=0.9',
                    })
                    resp = urllib.request.urlopen(req, timeout=timeout)
                    raw = resp.read()
                    charset = 'utf-8'
                    ctype = resp.headers.get('Content-Type', '') or ''
                    m = re.search(r'charset=([\w-]+)', ctype, re.I)
                    if m:
                        charset = m.group(1)
                    return raw.decode(charset, 'ignore'), base
                except Exception as e:  # noqa
                    last = e
                    time.sleep(0.4)
        raise RuntimeError('请求失败: %s (%s)' % (path, last))

    @staticmethod
    def _clean(text):
        if text is None:
            return ''
        text = htmlmod.unescape(text)
        text = re.sub(r'<[^>]+>', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    # ------------------------------------------------------------- 首页/筛选
    def _filters(self):
        out = {}
        sorts = [{'key': 'sort', 'name': '排序', 'value': [{'n': n, 'v': v} for n, v in self.SORTS]}]
        areas = [{'key': 'area', 'name': '地区', 'value': [{'n': a, 'v': a} for a in self.AREAS]}]
        years = [{'key': 'year', 'name': '年份', 'value': [{'n': y, 'v': y} for y in self.YEARS]}]
        for cid, _name in self.CHANNELS:
            types = [{'key': 'type', 'name': '类型',
                      'value': [{'n': n, 'v': v} for n, v in self.TYPES.get(cid, [])]}]
            out[cid] = types + areas + years + sorts
        return out

    def homeContent(self, filter):
        classes = [{'type_id': cid, 'type_name': name} for cid, name in self.CHANNELS]
        return {'class': classes, 'filters': self._filters()}

    def homeVideoContent(self):
        try:
            html, base = self._fetch('/')
            items = self._parse_cards(html)
            return {'list': items[:30]}
        except Exception:
            return {'list': []}

    def _parse_cards(self, html):
        """解析 /filter 与首页的 vod-card 卡片。"""
        out = []
        seen = set()
        marks = list(re.finditer(r'<a href="/detail/(\d+)\.html"[^>]*>', html))
        for i, m in enumerate(marks):
            vid = m.group(1)
            if vid in seen:
                continue
            end = marks[i + 1].start() if i + 1 < len(marks) else min(len(html), m.end() + 2500)
            chunk = html[m.start():end]
            if 'class="vod-card"' not in chunk and 'vod-title' not in chunk:
                continue
            seen.add(vid)
            pic = re.search(r'<img[^>]+src="([^"]+)"', chunk)
            name = re.search(r'class="vod-title[^"]*"[^>]*>([^<]+)<', chunk)
            sub = re.search(r'class="vod-subtitle[^"]*"[^>]*>([^<]*)<', chunk)
            badge = re.search(r'class="vod-badge[^"]*"[^>]*>([^<]+)<', chunk)
            out.append({
                'vod_id': vid,
                'vod_name': self._clean(name.group(1)) if name else vid,
                'vod_pic': pic.group(1) if pic else '',
                'vod_remarks': self._clean(badge.group(1)) if badge else '',
                'vod_content': self._clean(sub.group(1)) if sub else '',
            })
        return out

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '').strip()
        ext = extend or {}
        if isinstance(ext, str):
            try:
                ext = json.loads(ext) if ext.strip().startswith('{') else {}
            except Exception:
                ext = {}
        if not isinstance(ext, dict):
            ext = {}
        channel = str(ext.get('channel') or (tid if tid in ('1', '2', '3', '4', '5') else '1'))
        try:
            page = int(pg)
        except Exception:
            page = 1
        query = {
            'channel': channel,
            'type': str(ext.get('type') or ''),
            'area': str(ext.get('area') or ''),
            'year': str(ext.get('year') or ''),
            'sort': str(ext.get('sort') or 'hot'),
            'page': str(page),
        }
        path = '/filter?' + urllib.parse.urlencode(query)
        try:
            html, _base = self._fetch(path)
        except Exception:
            return {'list': [], 'page': page, 'pagecount': page, 'limit': self.PAGE_SIZE, 'total': 0}
        items = self._parse_cards(html)
        # 翻页判定：优先看分页条里出现的最大页码，其次用「本页是否满 12 条」推断
        pages = [int(x) for x in re.findall(r'data-page="(\d+)"', html) if x.isdigit()]
        has_next = bool(re.search(r'class="page-num"[^>]*data-page="%d"' % (page + 1), html))
        if pages:
            pagecount = max(pages)
            if has_next and pagecount <= page:
                pagecount = page + 1
        else:
            pagecount = page if len(items) < self.PAGE_SIZE else page + 1
        return {
            'list': items,
            'page': page,
            'pagecount': pagecount,
            'limit': self.PAGE_SIZE,
            'total': pagecount * self.PAGE_SIZE,
        }

    # ---------------------------------------------------------------- 详情
    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        raw = str(raw or '')
        m = re.search(r'(\d+)', raw)
        if not m:
            return {'list': []}
        vid = m.group(1)
        html, base = self._fetch('/detail/%s.html' % vid)
        title = re.search(r'<h1 class="detail-title"[^>]*>([^<]+)</h1>', html)
        pic = re.search(r'class="detail-poster-wrapper"[^>]*>\s*<img[^>]+src="([^"]+)"', html)
        if not pic:
            pic = re.search(r'<img[^>]+src="([^"]+)"[^>]*alt="[^"]*海报', html)
        meta = {}
        for label, value in re.findall(r'<span class="meta-label">([^<]+)：</span>\s*<span class="meta-value">([^<]*)</span>', html):
            meta[self._clean(label)] = self._clean(value)
        synopsis = re.search(r'<div class="synopsis-content"[^>]*>(.*?)</div>', html, re.S)
        content = self._clean(synopsis.group(1)) if synopsis else meta.get('备注', '')

        # 线路 tab：data-target -> 线路名
        tabs = {}
        for target, name in re.findall(
                r'<button class="source-tab[^"]*"[^>]*data-target="([^"]+)"[^>]*>([^<]+)</button>', html):
            tabs[target] = self._clean(name)
        if not tabs:
            for target, name in re.findall(
                    r'<button class="source-tab[^"]*"[^>]*data-target="([^"]+)"[^>]*>\s*([^<\s][^<]*?)\s*</button>',
                    html, re.S):
                tabs[target] = self._clean(name)

        play_from = []
        play_urls = []
        chunks = html.split('class="source-panel"')[1:]
        for chunk in chunks:
            pid = re.search(r'id="([^"]+)"', chunk[:200])
            pid = pid.group(1) if pid else ''
            eps = re.findall(r'href="(/vodplay/(\d+)-([A-Za-z0-9]+)-(\d+)\.html)"[^>]*>(.*?)</a>', chunk, re.S)
            if not eps:
                continue
            label = tabs.get(pid) or pid or ('线路%d' % (len(play_from) + 1))
            names = []
            seen = set()
            for href, _vid, key, idx, epname in eps:
                if href in seen:
                    continue
                seen.add(href)
                name = self._clean(epname) or ('第%s集' % idx)
                if len(eps) > 1 and not name.startswith('第'):
                    pass
                names.append('%s$%s|%s|%s' % (name, vid, key, idx))
            if names:
                play_from.append(label)
                play_urls.append('#'.join(names))

        if not play_from:
            return {'list': []}

        vod = {
            'vod_id': vid,
            'vod_name': self._clean(title.group(1)) if title else vid,
            'vod_pic': pic.group(1) if pic else '',
            'vod_year': meta.get('年份', ''),
            'vod_area': meta.get('地区', ''),
            'vod_lang': meta.get('语言', ''),
            'vod_actor': meta.get('主演', ''),
            'vod_director': meta.get('导演', ''),
            'vod_remarks': meta.get('备注', ''),
            'vod_content': content,
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_urls),
        }
        return {'list': [vod]}

    # ---------------------------------------------------------------- 搜索
    def searchContent(self, key, quick, pg=1):
        try:
            page = int(pg)
        except Exception:
            page = 1
        query = {'keyword': key, 'field': 'all', 'page': str(page)}
        path = '/search?' + urllib.parse.urlencode(query)
        try:
            html, _base = self._fetch(path)
        except Exception:
            return {'list': [], 'page': page, 'pagecount': page, 'limit': self.PAGE_SIZE, 'total': 0}

        out = []
        blocks = re.split(r'<div class="search-item"', html)[1:]
        for b in blocks:
            m = re.search(r'href="/detail/(\d+)\.html"', b)
            if not m:
                continue
            vid = m.group(1)
            name = re.search(r'class="search-item-title[^"]*"[^>]*>([^<]+)<', b)
            pic = re.search(r'<img[^>]+src="([^"]+)"', b)
            typ = re.search(r'class="search-item-type"[^>]*>([^<]+)<', b)
            year = re.search(r'年份：</span>\s*<span[^>]*>([^<]*)<', b)
            actor = re.search(r'主演：</span>\s*<span[^>]*>([^<]*)<', b)
            out.append({
                'vod_id': vid,
                'vod_name': self._clean(name.group(1)) if name else vid,
                'vod_pic': pic.group(1) if pic else '',
                'vod_remarks': self._clean(typ.group(1)) if typ else '',
                'vod_year': self._clean(year.group(1)) if year else '',
                'vod_actor': self._clean(actor.group(1))[:40] if actor else '',
                'vod_content': '',
            })

        total = None
        m = re.search(r'共\s*<em>(\d+)</em>\s*个结果', html)
        if m:
            total = int(m.group(1))
        pages = [int(x) for x in re.findall(r'data-page="(\d+)"', html) if x.isdigit()]
        if pages:
            pagecount = max(pages)
        elif total is not None:
            pagecount = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        else:
            pagecount = page if len(out) < self.PAGE_SIZE else page + 1
        return {
            'list': out,
            'page': page,
            'pagecount': pagecount,
            'limit': self.PAGE_SIZE,
            'total': total if total is not None else pagecount * self.PAGE_SIZE,
        }

    # ---------------------------------------------------------------- 播放
    def playerContent(self, flag, id, vipFlags):
        raw = str(id or '')
        vid = key = index = ''
        if '|' in raw:
            parts = raw.split('|')
            if len(parts) >= 3:
                vid, key, index = parts[0], parts[1], parts[2]
        if not vid:
            m = re.match(r'(\d+)-([A-Za-z0-9]+)-(\d+)$', raw)
            if m:
                vid, key, index = m.group(1), m.group(2), m.group(3)
        if not vid:
            m = re.search(r'(\d+)', raw)
            vid = m.group(1) if m else ''
        if not key:
            key = str(flag or '').strip()
        index = index or '1'

        query = {'vodId': vid, 'playFrom': key, 'index': index}
        path = '/api/play-url?' + urllib.parse.urlencode(query)
        referer = '%s/vodplay/%s-%s-%s.html' % (self.HOST, vid, key, index)
        header = {'User-Agent': self.UA, 'Referer': self.HOST + '/'}
        try:
            text, _base = self._fetch(path, referer=referer, timeout=20)
            data = json.loads(text)
        except Exception as e:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': header, 'msg': str(e)}

        url = data.get('url') or ''
        hdrs = data.get('headers')
        if isinstance(hdrs, dict):
            for k, v in hdrs.items():
                header[str(k)] = str(v)
        header.setdefault('User-Agent', self.UA)
        header.setdefault('Referer', self.HOST + '/')
        if not url:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': header,
                    'msg': data.get('msg') or '播放地址解析失败'}
        mode = data.get('mode') or 'native'
        if mode == 'iframe':
            return {'parse': 1, 'playUrl': '', 'url': url, 'header': header}
        return {
            'parse': 0,
            'playUrl': '',
            'url': url,
            'header': header,
            'urltype': 'hls' if '.m3u8' in url.lower() else '',
        }

    def localProxy(self, param):
        return None


# -------------------------------------------------------------------- 自测
def _selftest():
    s = Spider()
    s.init('')
    print('[1] homeContent')
    home = s.homeContent(True)
    print('    classes:', [c['type_name'] for c in home['class']])
    print('    filter keys:', list(home['filters'].keys()))

    print('[2] categoryContent channel=1 page=1')
    cat = s.categoryContent('1', 1, False, {})
    print('    items=%d pagecount=%s' % (len(cat['list']), cat['pagecount']))
    for it in cat['list'][:3]:
        print('   ', it['vod_id'], it['vod_name'], it['vod_remarks'])

    print('[3] categoryContent channel=2 page=2 sort=time')
    cat2 = s.categoryContent('2', 2, False, {'sort': 'time'})
    print('    items=%d pagecount=%s' % (len(cat2['list']), cat2['pagecount']))

    print('[4] detailContent 102704')
    det = s.detailContent(['102704'])['list'][0]
    print('    name=%s year=%s area=%s remarks=%s' % (det['vod_name'], det['vod_year'], det['vod_area'], det['vod_remarks']))
    print('    play_from:', det['vod_play_from'])
    print('    first url:', det['vod_play_url'].split('$$$')[0][:120])

    print('[5] searchContent 爱情 p1')
    se = s.searchContent('爱情', False, 1)
    print('    items=%d total=%s pagecount=%s' % (len(se['list']), se['total'], se['pagecount']))
    for it in se['list'][:3]:
        print('   ', it['vod_id'], it['vod_name'], it['vod_remarks'])

    print('[6] playerContent')
    first = det['vod_play_url'].split('$$$')[0].split('#')[0].split('$')[-1]
    first_from = det['vod_play_from'].split('$$$')[0]
    pl = s.playerContent(first_from, first, [])
    print('    id=%s from=%s' % (first, first_from))
    print('    url:', pl.get('url'))
    print('    header:', pl.get('header'))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        _selftest()
    else:
        print('用法: python3 jisuzhuiju.py test   # 自测首页/分类/详情/搜索/播放')
        print('TVBox 系播放器里把本文件作为 py 源地址加载即可，类名 csp_Spider，扩展参数留空。')

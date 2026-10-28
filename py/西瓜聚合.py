# -*- coding: utf-8 -*-
"""
SOTVLA —— OK影视 / TVBox Python 源（直接在手机端加载，不用起服务）

多域名自动切换：
    内置域名池，按顺序尝试；某个域名连不上（超时 / 5xx / 返回空）就自动换下一个，
    并把可用域名缓存起来，后续请求优先用它。

    内置池：https://www.sotvla.cc/  https://www.sotvla6.cc/  https://www.sotvla3.cc/
    自定义：配置 ext 里写域名，多个用 | 或 , 分隔，会排在最前面优先尝试
            例："ext":"https://www.sotvla.cc|https://www.sotvla6.cc"

导入方式：
    TVBox/影视 → 资源 → 导入 → 选 Py → 选本文件（或填 raw 链接）
    文件名随意，但后缀必须是 .py，且内容里有 class Spider。

播放链路：
    播放页 -> <iframe src>（ppl.sotvla*.cc/?url=<官源页面>）
           -> iframe 页里的 apiToken
           -> 同域 /api/resolve.php?token=<apiToken> → m3u8
    优酷 / 爱奇艺 / 腾讯 / 芒果 / B站 等官源都走这条；解析不到时转 parse=1
    交给 TVBox 自带解析。
"""

import base64
import json
import re
from urllib.parse import quote, urlparse, parse_qs
import html as html_mod

try:
    from base.spider import Spider as _Base
except Exception:  # 部分内核不注入 base 模块，降级为纯 Python 类
    _Base = object


# 内置域名池（按顺序尝试）
HOST_POOL = [
    'https://www.sotvla.cc/',
    'https://www.sotvla6.cc/',
    'https://www.sotvla3.cc/',
]


class Spider(_Base):

    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

    TABS = [('movie', '电影'), ('teleplay', '电视剧'),
            ('anime', '动漫'), ('variety', '综艺')]
    TAB_NAMES = dict(TABS)

    SEARCH_RE = re.compile(r'window\.SOTV_SEARCH_PROGRESS\s*=\s*')
    TOKEN_RE = re.compile(r'apiToken\s*:\s*"([^"]+)"')

    # 类级默认值：内核不调 init 时也不会 AttributeError
    extend = ''
    hosts = list(HOST_POOL)
    HOST = HOST_POOL[0]
    _alive = None
    _titles = {}
    _cache = {}

    def init(self, extend=''):
        self.extend = (extend or '').strip()
        # 域名池：自定义优先，其后接内置池
        hosts = []
        if self.extend:
            for h in re.split(r'[|,\s]+', self.extend):
                h = h.strip()
                if h.startswith('http'):
                    hosts.append(h.rstrip('/') + '/')
        for h in HOST_POOL:
            if h not in hosts:
                hosts.append(h)
        self.hosts = hosts
        # 当前可用域名（首次请求时探测，成功后固定）
        self.HOST = hosts[0]
        self._alive = None
        self._titles = {}
        self._cache = {}
        return self

    def _ensure(self):
        """部分内核不调用 init，这里用实例级容器兜底。"""
        if '_cache' not in self.__dict__:
            self._cache = {}
            self._titles = {}

    def getName(self):
        return 'SOTVLA'

    def setting(self):
        return {'name': 'SOTVLA'}

    # ---------------------------------------------------------------- 域名切换

    def _fetch(self, url, headers, timeout=10):
        """优先用内核的 self.fetch（自带代理/Cookie），没有再退回 requests。"""
        fn = getattr(super(), 'fetch', None) if _Base is not object else None
        if callable(fn):
            try:
                return fn(url, headers=headers, timeout=timeout)
            except TypeError:
                try:
                    return fn(url, headers=headers)
                except Exception:
                    pass
            except Exception:
                pass
        import requests
        return requests.get(url, headers=headers, timeout=timeout)

    def _pick_host(self):
        """返回当前可用域名；不可用则依次尝试域名池。"""
        self._ensure()
        if self._alive:
            return self._alive
        for host in self.hosts:
            try:
                resp = self._fetch(host, {
                    'User-Agent': self.UA,
                    'Referer': host,
                }, timeout=8)
                text = getattr(resp, 'text', '') or ''
                code = getattr(resp, 'status_code', 200)
                if code and int(code) < 400 and len(text) > 500:
                    self._alive = host
                    self.HOST = host
                    return host
            except Exception:
                continue
        # 全部失败：退回原域名，让后续请求自行报错
        self._alive = self.hosts[0]
        self.HOST = self.hosts[0]
        return self.HOST

    def _get(self, url, referer=None, retry_host=True):
        """抓取；若失败且 url 指向的是域名池里的站点，自动换域名重试。"""
        self._ensure()
        host = self._pick_host()
        try:
            resp = self._fetch(url, {
                'User-Agent': self.UA,
                'Referer': referer or host,
            })
            text = getattr(resp, 'text', '') or ''
            code = getattr(resp, 'status_code', 200)
            if retry_host and code and int(code) >= 400:
                raise IOError('HTTP %s' % code)
            if text:
                return text
            if not retry_host:
                return ''
        except Exception:
            if not retry_host:
                return ''
        # 换下一个域名重试同一路径
        path = self._rebase(url, host)
        if not path:
            return ''
        for alt in self.hosts:
            if alt == host:
                continue
            try:
                resp = self._fetch(alt + path.lstrip('/'), {
                    'User-Agent': self.UA,
                    'Referer': alt,
                })
                text = getattr(resp, 'text', '') or ''
                code = getattr(resp, 'status_code', 200)
                if (not code or int(code) < 400) and text:
                    self._alive = alt
                    self.HOST = alt
                    return text
            except Exception:
                continue
        return ''

    @staticmethod
    def _rebase(url, old_host):
        """把绝对 url 换成相对于域名的 path，便于在备用域名上重放。"""
        try:
            p = urlparse(url)
            base = urlparse(old_host)
            if p.netloc and p.netloc != base.netloc:
                return None  # 第三方地址，不做域名替换
            return (p.path or '/') + (('?' + p.query) if p.query else '')
        except Exception:
            return None

    # ---------------------------------------------------------------- 首页 / 分类

    def homeContent(self, filter):
        return {'class': [{'type_id': i, 'type_name': n} for i, n in self.TABS]}

    def homeVideoContent(self):
        return {'list': self._hot('movie')}

    def categoryContent(self, tid, pg, filter, ext):
        tid = str(tid or 'movie')
        if tid not in self.TAB_NAMES:
            tid = 'movie'
        items = self._hot(tid) if str(pg) in ('1', '0', '') else []
        return {'list': items, 'page': int(pg or 1),
                'pagecount': 1, 'limit': len(items) or 20, 'total': len(items)}

    # ---------------------------------------------------------------- 搜索

    def searchContent(self, key, quick, pg=1):
        items = self._search(key)
        if str(pg) not in ('1', '0', ''):
            items = []
        return {'list': items, 'page': int(pg or 1)}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    # ---------------------------------------------------------------- 详情

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        if not vid:
            return {'list': []}

        if vid.startswith('q_'):
            title = self._token_title(vid[2:])
            vod = self._vod_by_title(title)
        elif '_' in vid:
            api_id, vod_id = vid.split('_', 1)
            vod = self._detail_vod(api_id, vod_id)
            if not vod:
                title = self._titles.get(vid)
                vod = self._vod_by_title(title) if title else None
                if vod:
                    vod['vod_id'] = vid
        else:
            vod = None
        return {'list': [vod] if vod else []}

    # ---------------------------------------------------------------- 播放

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        if not url:
            return {'parse': 1, 'playUrl': '', 'url': '', 'header': {}}
        if not url.startswith('http'):
            url = self.HOST + url.lstrip('/')
        else:
            # 播放地址里可能带的是失效域名，换成当前可用域名
            path = self._rebase(url, self.HOST)
            if path:
                url = self._pick_host().rstrip('/') + path

        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', url, re.I):
            return self._play(url, 0)

        page = self._get(url)
        player = self._iframe_url(page)
        if not player:
            return self._play(url, 1)

        # iframe 的 url 参数本身就是直链
        direct = self._media_param(player)
        if direct:
            return self._play(direct, 0)

        resolved = self._resolve_player(player)
        if resolved:
            return self._play(resolved, 0)

        # 解析不到 → 交给 TVBox 自带解析
        return self._play(player, 1)

    # ---------------------------------------------------------------- 站点抓取

    def _search_raw(self, keyword):
        keyword = (keyword or '').strip()
        if not keyword:
            return []
        key = 's:' + keyword
        if key in self._cache:
            return self._cache[key]

        page = self._get('%ssearch.php?q=%s' % (self._pick_host(), quote(keyword)))
        items = []
        m = self.SEARCH_RE.search(page or '')
        if m:
            try:
                data, _ = json.JSONDecoder().raw_decode(page, m.end())
                items = data.get('items') or []
            except ValueError:
                items = []
        self._cache[key] = items
        return items

    def _search(self, keyword):
        vods = []
        seen = set()
        for item in self._search_raw(keyword):
            api_id = item.get('_api_id')
            vod_id = item.get('vod_id')
            if api_id is None or not vod_id:
                continue
            vid = '%s_%s' % (api_id, vod_id)
            name = (item.get('vod_name') or '').strip()
            mark = (name, api_id)
            if not name or mark in seen:
                continue
            seen.add(mark)
            self._titles[vid] = name
            vods.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': item.get('vod_pic') or '',
                'vod_remarks': self._remarks(item),
                'vod_year': str(item.get('vod_year') or ''),
                'vod_area': item.get('vod_area') or '',
                'type_id': '1',
                'type_name': self._clean(item.get('vod_class') or '', 40),
            })
        # 官方平台聚合源（只能嵌网页）排后面
        official = ('无广告资源',)
        vods.sort(key=lambda v: 1 if any(h in v['vod_remarks'] for h in official) else 0)
        return vods[:40]

    def _hot(self, tab):
        key = 'h:' + tab
        if key in self._cache:
            return self._cache[key]
        page = self._get('%sapi/hot_movie.php?source=guduo&tab=%s'
                         % (self._pick_host(), quote(tab)))
        items = []
        try:
            data = json.loads(page)
            for it in (data.get('items') or []):
                title = (it.get('title') or '').strip()
                if title:
                    items.append({
                        'vod_id': 'q_' + self._title_token(title),
                        'vod_name': title,
                        'vod_pic': it.get('pic') or '',
                        'vod_remarks': '热播',
                        'vod_year': '',
                        'type_id': '1',
                        'type_name': self.TAB_NAMES.get(tab, ''),
                    })
        except Exception:
            items = []
        self._cache[key] = items
        return items

    def _detail(self, api_id, vod_id):
        key = 'd:%s_%s' % (api_id, vod_id)
        if key in self._cache:
            return self._cache[key]

        page = self._get('%sdetail.php?api_id=%s&vod_id=%s'
                         % (self._pick_host(), api_id, vod_id))
        title = self._tag(page, r'<div class="detail-info">\s*<h1>(.*?)</h1>')
        if not title:
            self._cache[key] = None
            return None

        info = {
            'vod_id': '%s_%s' % (api_id, vod_id),
            'vod_name': self._clean(title, 80),
            'vod_pic': self._tag(page, r'<div class="detail-poster">\s*<img[^>]*?src="([^"]+)"'),
            'vod_class': '',
            'vod_year': '',
            'vod_area': '',
            'vod_lang': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': '',
            'vod_remarks': '',
            'groups': [],
        }

        meta = self._tag(page, r'<div class="meta-list">([\s\S]*?)<p class="blurb"')
        if not meta:
            meta = self._tag(page, r'<div class="meta-list">([\s\S]*?)</div>\s*</div>')
        for label, field in (('分类', 'vod_class'), ('地区', 'vod_area'),
                             ('语言', 'vod_lang'), ('演员', 'vod_actor'),
                             ('导演', 'vod_director')):
            m = re.search(r'<strong>%s</strong>\s*(.*?)</div>' % label, meta or '', re.S)
            if m:
                info[field] = self._clean(m.group(1), 500)
        year = re.search(r'<strong>年代</strong>\s*(.*?)</div>', meta or '', re.S)
        if year:
            y = re.search(r'(\d{4})', self._clean(year.group(1)))
            info['vod_year'] = y.group(1) if y else ''

        info['vod_content'] = self._clean(
            self._tag(page, r'<p class="blurb">(.*?)</p>'), 3000)

        sources = {}
        for m in re.finditer(
                r'<button[^>]*class="play-source-tab[^"]*"[^>]*data-src="(\d+)"[^>]*>(.*?)</button>',
                page, re.S):
            sources[m.group(1)] = self._clean(m.group(2), 40) or ('线路%s' % m.group(1))

        for chunk in re.split(r'<div class="play-ep-panel"', page)[1:]:
            panel = re.match(r'\s*data-src-panel="(\d+)"', chunk)
            if not panel:
                continue
            src = panel.group(1)
            eps, seen = [], set()
            for a in re.finditer(
                    r'<a[^>]*href="[^"]*?src=%s&(?:amp;)?ep=(\d+)[^"]*"[^>]*>(.*?)</a>' % src,
                    chunk, re.S):
                ep = int(a.group(1))
                if ep in seen:
                    continue
                seen.add(ep)
                eps.append((self._clean(a.group(2), 40) or ('第%d集' % (ep + 1)), ep))
            if eps:
                info['groups'].append({
                    'src': src,
                    'name': sources.get(src, '线路%s' % src),
                    'episodes': eps,
                })

        if info['groups']:
            total = len(info['groups'][0]['episodes'])
            info['vod_remarks'] = '全%d集' % total if total > 1 else 'HD'
        self._cache[key] = info
        return info

    def _detail_vod(self, api_id, vod_id):
        info = self._detail(api_id, vod_id)
        if not info or not info['groups']:
            return None
        return self._to_vod(info)

    def _to_vod(self, info):
        host = self._pick_host().rstrip('/')
        froms, plays = [], []
        for g in info['groups']:
            links = []
            for name, ep in g['episodes']:
                links.append('%s$%s/play.php?api_id=%s&vod_id=%s&src=%s&ep=%s' % (
                    name, host, info['vod_id'].split('_')[0],
                    info['vod_id'].split('_')[1], g['src'], ep))
            froms.append(g['name'])
            plays.append('#'.join(links))
        vod = dict(info)
        vod.pop('groups', None)
        vod['vod_play_from'] = '$$$'.join(froms)
        vod['vod_play_url'] = '$$$'.join(plays)
        vod['type_id'] = '1'
        vod['type_name'] = self._clean(info.get('vod_class') or '', 40)
        return vod

    def _vod_by_title(self, title):
        if not title:
            return None
        for vod in self._search(title)[:4]:
            api_id, vod_id = vod['vod_id'].split('_', 1)
            made = self._detail_vod(api_id, vod_id)
            if made:
                made['vod_name'] = made.get('vod_name') or title
                return made
        return None

    # ---------------------------------------------------------------- 解析

    def _resolve_player(self, player_url):
        key = 'p:' + player_url
        if key in self._cache:
            return self._cache[key]
        result = ''
        page = self._get(player_url, retry_host=False)
        token = self.TOKEN_RE.search(page or '')
        if token:
            parsed = urlparse(player_url)
            api = '%s://%s/api/resolve.php?token=%s' % (
                parsed.scheme or 'https', parsed.netloc,
                quote(token.group(1), safe=''))
            raw = self._get(api, referer='%s://%s/' % (parsed.scheme or 'https', parsed.netloc),
                            retry_host=False)
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
            if str(data.get('code')) == '200':
                result = data.get('url') or ''
            if not result:
                m = re.search(r'"url"\s*:\s*"((?:[^"\\]|\\.)*)"', raw or '')
                if m:
                    result = m.group(1).replace('\\/', '/')
        self._cache[key] = result
        return result

    def _iframe_url(self, page):
        m = re.search(r'<iframe[^>]*?src="([^"]+)"', page or '', re.S)
        if m:
            return html_mod.unescape(m.group(1)).strip()
        m = re.search(r'embedAutoOn\s*=\s*"([^"]+)"', page or '')
        return html_mod.unescape(m.group(1)).strip() if m else ''

    def _media_param(self, iframe_url):
        params = parse_qs(urlparse(iframe_url).query)
        for name in ('url', 'v', 'video'):
            for value in reversed(params.get(name, [])):
                value = value.strip()
                if value.lower().startswith(('http://', 'https://')) \
                        and ('m3u8' in value.lower() or '.mp4' in value.lower()):
                    return value
        return ''

    def _play(self, url, parse):
        return {
            'parse': parse,
            'playUrl': '',
            'url': url,
            'header': {'User-Agent': self.UA},
        }

    # ---------------------------------------------------------------- 工具

    def _remarks(self, item):
        parts = []
        total = str(item.get('vod_total') or '').strip()
        serial = str(item.get('vod_serial') or '').strip()
        if total and total not in ('0', '1'):
            parts.append('全%s集' % total)
        if serial and serial not in ('0', ''):
            parts.append('更新至%s集' % serial)
        if item.get('_api_name'):
            parts.append(item['_api_name'])
        return ' · '.join(parts)

    def _tag(self, text, pattern):
        if not text:
            return ''
        m = re.search(pattern, text, re.S)
        return m.group(1).strip() if m else ''

    def _clean(self, text, limit=300):
        text = re.sub(r'<[^>]+>', '', text or '')
        text = html_mod.unescape(text).replace('\xa0', ' ')
        text = text.replace('$', '·').replace('#', ' ')
        return re.sub(r'\s+', ' ', text).strip()[:limit]

    def _title_token(self, title):
        return base64.urlsafe_b64encode(
            title.encode('utf-8')).decode('ascii').rstrip('=')

    def _token_title(self, token):
        if not token:
            return ''
        try:
            return base64.urlsafe_b64decode(
                token + '=' * (-len(token) % 4)).decode('utf-8', 'ignore')
        except Exception:
            return ''

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv)(\?|$)', url or '', re.I))

    def isTextFormat(self, url):
        return False

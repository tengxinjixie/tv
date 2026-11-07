# -*- coding: utf-8 -*-
"""
剧踪影视 (juzong01.me) —— OK影视 py 源
基于 2026-10-24 实测站点结构编写，播放链路已破解：
  1. 播放页 player_data.url 为加密 token
  2. 请求 https://jzpic.ok1333.cn/?url=<token> 取 WGART_PARSE_TOKEN
  3. 请求 /wgart/api.php?action=try_json_api&video_url=<token>&parse_token=<T> 得到直链
站点域名常变，失效时改 HOST 即可。
"""

import json
import re
import time
from urllib.parse import quote

from base.spider import Spider


class Spider(Spider):

    HOST = 'https://www.juzong01.me/'
    PLAYER_BASE = 'https://jzpic.ok1333.cn/'
    UA = ('Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/98.0.4758.101 Mobile Safari/537.36')

    headers = {
        'User-Agent': UA,
        'Referer': HOST,
    }

    CATES = '电影$1#电视剧$2#动漫$4#综艺$3#动作片$6#喜剧片$7#爱情片$8#科幻片$9#恐怖片$10#剧情片$11#战争片$12#犯罪片$22#动画片$23#国产剧$13#港台剧$14#日韩剧$15#欧美剧$16#海外剧$20'

    FILTERS = [
        {'key': 'class', 'name': '类型', 'value': [
            {'n': '全部', 'v': ''}, {'n': '动作', 'v': '动作'},
            {'n': '喜剧', 'v': '喜剧'}, {'n': '爱情', 'v': '爱情'},
            {'n': '科幻', 'v': '科幻'}, {'n': '恐怖', 'v': '恐怖'},
            {'n': '剧情', 'v': '剧情'}, {'n': '战争', 'v': '战争'},
            {'n': '犯罪', 'v': '犯罪'}]},
        {'key': 'area', 'name': '地区', 'value': [
            {'n': '全部', 'v': ''}, {'n': '大陆', 'v': '大陆'},
            {'n': '香港', 'v': '香港'}, {'n': '台湾', 'v': '台湾'},
            {'n': '美国', 'v': '美国'}, {'n': '韩国', 'v': '韩国'},
            {'n': '日本', 'v': '日本'}, {'n': '泰国', 'v': '泰国'},
            {'n': '其它', 'v': '其它'}]},
        {'key': 'lang', 'name': '语言', 'value': [
            {'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'},
            {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'},
            {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'},
            {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '年份', 'value': [
            {'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'},
            {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'},
            {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'},
            {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}]},
        {'key': 'by', 'name': '排序', 'value': [
            {'n': '时间', 'v': 'time'}, {'n': '人气', 'v': 'hits'},
            {'n': '评分', 'v': 'score'}]},
    ]

    def init(self, extend=''):
        pass

    def getName(self):
        return '剧踪影视'

    # ==================== 首页 ====================
    def homeContent(self, filter):
        classes = []
        for c in self.CATES.split('#'):
            n, i = c.split('$')
            classes.append({'type_name': n, 'type_id': i})
        result = {'class': classes}
        if filter:
            result['filters'] = {}
            for c in self.CATES.split('#'):
                result['filters'][c.split('$')[1]] = self.FILTERS
        return result

    def homeVideoContent(self):
        html = self._fetch_page(self.HOST, min_len=2000)
        return {'list': self._parse_list(html)[:12]}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, ext):
        ext = ext or {}
        url = '{0}vodshow/{1}-{2}-{3}-{4}-{5}-{6}---{7}---{8}.html'.format(
            self.HOST, tid,
            ext.get('area', ''), ext.get('by', ''), ext.get('class', ''),
            ext.get('lang', ''), ext.get('letter', ''), pg, ext.get('year', ''))
        html = self._fetch_page(url, min_len=2000)
        return {
            'list': self._parse_list(html),
            'page': int(pg), 'pagecount': 9999, 'limit': 90, 'total': 999999,
        }

    # ==================== 详情 ====================
    def detailContent(self, ids):
        vid = ids[0]
        if not vid.startswith('http'):
            vid = self.HOST.rstrip('/') + vid
        html = self._fetch_page(vid, min_len=2000)

        vod = {'vod_id': vid}
        vod['vod_name'] = self.regStr(html, r'<h1 class="title">([^<]+)</h1>') or ''
        vod['vod_pic'] = self.regStr(html, r'stui-content__thumb[\s\S]*?data-original="([^"]+)"')
        if not vod['vod_pic']:
            vod['vod_pic'] = self.regStr(html, r'stui-content__thumb[\s\S]*?src="([^"]+)"') or ''
        vod['vod_year'] = self.regStr(html, r'年份：</span>([^<]+)') or ''
        vod['vod_area'] = self.regStr(html, r'地区：</span>([^<]+)') or ''
        vod['vod_remarks'] = self.regStr(html, r'备注：</span>([^<]+)') or ''
        vod['vod_actor'] = self.regStr(html, r'主演：</span>([^<]+)') or ''
        vod['vod_director'] = self.regStr(html, r'导演：</span>([^<]+)') or ''
        desc = self.regStr(html, r'<span class="detail-sketch">([\s\S]*?)</span>')
        if not desc:
            desc = self.regStr(html, r'简介：</span>([\s\S]*?)</p>')
        vod['vod_content'] = re.sub(r'<[^>]+>', '', desc or '').strip()

        # 线路：h3 标题 + 对应 stui-content__playlist 列表
        tabs, plays = [], []
        for m in re.finditer(
                r'<h3 class="title">([\s\S]*?)</h3>[\s\S]*?<ul class="stui-content__playlist[^"]*">([\s\S]*?)</ul>',
                html):
            tab = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            eps = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', m.group(2))
            if tab and eps:
                tabs.append(tab)
                plays.append('#'.join(name + '$' + href for href, name in eps))
        vod['vod_play_from'] = '$$$'.join(tabs) or '默认线路'
        vod['vod_play_url'] = '$$$'.join(plays)
        return {'list': [vod]}

    # ==================== 播放 ====================
    # TYBox 定制：直链缓存。同一集被反复请求（播放 + 预载）时不再重复解析，
    # 解析一集要 3 次远程请求，缓存后预载起跑更快。
    PLAY_CACHE_TTL = 900
    _play_cache = {}
    _token_cache = {}

    def playerContent(self, flag, id, vipFlags):
        url = id if id.startswith('http') else self.HOST.rstrip('/') + '/' + id.lstrip('/')

        now = time.time()
        hit = self._play_cache.get(url)
        if hit and now - hit[0] < self.PLAY_CACHE_TTL:
            return self._play_result(hit[1])

        html = self._fetch_page(url, min_len=2000)
        direct = ''
        if html:
            # 优先取 player_data.url：有的是加密 token，有的直接就是 m3u8/mp4 直链
            pd_url = self._player_data_url(html)
            if pd_url:
                if self._is_media_url(pd_url):
                    direct = pd_url
                elif not pd_url.startswith('http'):
                    direct = self._resolve_token(pd_url)
            if not direct:
                direct = self._extract_inline_media(html)

        if direct:
            self._play_cache[url] = (now, direct)
            if len(self._play_cache) > 64:
                for k in list(self._play_cache)[:32]:
                    self._play_cache.pop(k, None)
            return self._play_result(direct)

        # 兜底：解析不出直链时仍按原方式走网页嗅探，保证能播
        return {
            'parse': 1,
            'playUrl': '',
            'url': url,
            'header': self.headers,
        }

    def _play_result(self, direct):
        return {
            'parse': 0,
            'playUrl': '',
            'url': direct,
            # 直链在 CDN 上，不校验 Referer，只带 UA 最稳
            'header': {'User-Agent': self.UA},
        }

    def _fetch_page(self, url, headers=None, min_len=0):
        """带重试的抓取：该站首次请求常返回 403 壳页，重试后可正常拿到内容。"""
        last = ''
        for _ in range(3):
            try:
                r = self.fetch(url, headers=headers or self.headers)
                text = getattr(r, 'text', '') or ''
                code = getattr(r, 'status_code', 200)
                last = text
                if code == 200 and len(text) >= min_len:
                    return text
            except Exception:
                pass
            time.sleep(0.6)
        return last if len(last) >= min_len else ''

    def _extract_inline_media(self, html):
        """播放页里若已内嵌 m3u8/mp4 直链，直接返回。"""
        m = re.search(r'(https?://[^"\'\s\\<>]+\.(?:m3u8|mp4)[^"\'\s\\<>]*)', html or '')
        return m.group(1).replace('\\/', '/') if m else ''

    def _is_media_url(self, u):
        return bool(re.search(r'\.(?:m3u8|mp4)(?:[?#]|$)', u or '', re.I))

    def _player_data_url(self, html):
        """从 player_data JSON 里取当前集的 url 字段。

        该字段有三种形态：
          1. 加密 token（juzong1-xxx）→ 走 _resolve_token 解析；
          2. m3u8/mp4 直链（部分线路直接给）→ 直接可用；
          3. 第三方页面地址（如 v.qq.com）→ 交给网页嗅探。
        注意：页面里另有 '"url":"www.juzong01.me"' 这类无关字段，
        简单正则 '"url":"..."' 会先命中它——必须解析 player_data 本身。
        """
        if not html:
            return ''
        m = re.search(r'player_data\s*=\s*(\{.*?\})\s*</script>', html, re.S)
        if m:
            try:
                pd = json.loads(m.group(1))
                u = (pd.get('url') or '').strip()
                if u:
                    return u
            except Exception:
                pass
        m2 = re.search(r'player_data[^}]*?"url"\s*:\s*"([^"]{16,})"', html, re.S)
        return m2.group(1).strip() if m2 else ''

    def _resolve_token(self, token):
        now = time.time()
        hit = self._token_cache.get(token)
        if hit and now - hit[0] < 600:
            return hit[1]
        try:
            # 2. 拿 parse_token
            page = self._fetch_page(
                self.PLAYER_BASE + '?url=' + quote(token),
                headers={'User-Agent': self.UA, 'Referer': self.HOST})
            if not page:
                return ''
            pt = self.regStr(page, r'WGART_PARSE_TOKEN="([^"]+)"')
            if not pt:
                return ''
            # 3. 解析直链
            api = (self.PLAYER_BASE + 'wgart/api.php?action=try_json_api'
                   '&video_url=' + quote(token) + '&parse_token=' + quote(pt))
            res = self._fetch_page(api, headers={
                'User-Agent': self.UA,
                'Referer': self.PLAYER_BASE,
            })
            if not res:
                return ''
            m = re.search(r'"url"\s*:\s*"([^"]+)"', res)
            if m:
                direct = m.group(1).replace('\\/', '/')
                if direct.startswith('http'):
                    self._token_cache[token] = (now, direct)
                    if len(self._token_cache) > 64:
                        for k in list(self._token_cache)[:32]:
                            self._token_cache.pop(k, None)
                    return direct
        except Exception:
            pass
        return ''

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg=1):
        url = '{0}vodsearch/-------------/?wd={1}&submit='.format(self.HOST, key)
        # 该站搜索有反爬：首次请求返回 403/200 壳页并靠 Set-Cookie 放行，
        # 这里最多重试 3 次，每轮把新发下的 Cookie 累积带上
        cookie = ''
        html = ''
        for _ in range(3):
            h = dict(self.headers)
            if cookie:
                h['Cookie'] = cookie
            resp = self.fetch(url, headers=h)
            html = resp.text
            if 'stui-vodlist__thumb' in html:
                break
            try:
                ck = resp.headers.get('Set-Cookie', '') if resp.headers else ''
            except Exception:
                ck = ''
            pairs = re.findall(r'(\w+)=([a-f0-9]{16,})', ck)
            new = dict(p.split('=', 1) for p in cookie.split('; ') if '=' in p)
            for k, v in pairs:
                new[k] = v
            if pairs and new:
                cookie = '; '.join(k + '=' + v for k, v in new.items())
        return {'list': self._parse_list(html), 'page': int(pg)}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    # ==================== 工具 ====================
    def _parse_list(self, html):
        """优化了正则匹配，完美提取更新集数（副标题）"""
        videos = []
        items = []
        
        # 模式1：尝试完整提取：链接、标题、封面、副标题（集数）
        pattern_full = re.compile(
            r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*href="([^"]+)"[^>]*title="([^"]*)"[^>]*data-original="([^"]*)"([\s\S]*?)</a>',
            re.S
        )
        for m in pattern_full.finditer(html):
            href, name, pic, inner_html = m.groups()
            # 在标签内部找更新集数（如：更新至第06集、全剧集、HD中字）
            remark_m = re.search(r'<span class="pic-text[^"]*">([^<]+)</span>', inner_html)
            remark = remark_m.group(1).strip() if remark_m else ''
            items.append((href, name, pic, remark))

        # 模式2（兜底）：如果没有 data-original，或者没有封面属性
        if not items:
            pattern_lite = re.compile(
                r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*href="([^"]+)"[^>]*title="([^"]*)"([\s\S]*?)</a>',
                re.S
            )
            for m in pattern_lite.finditer(html):
                href, name, inner_html = m.groups()
                pic_m = re.search(r'data-original="([^"]*)"', m.group(0))
                pic = pic_m.group(1) if pic_m else ''
                remark_m = re.search(r'<span class="pic-text[^"]*">([^<]+)</span>', inner_html)
                remark = remark_m.group(1).strip() if remark_m else ''
                items.append((href, name, pic, remark))

        for href, name, pic, remark in items:
            if href.startswith('/'):
                href = self.HOST.rstrip('/') + href
            videos.append({
                'vod_id': href,
                'vod_name': name.strip(),
                'vod_pic': pic,
                'vod_remarks': remark,  # 这里就是副标题啦
            })
        return videos

    def isVideoFormat(self, url):
        return True

    def isTextFormat(self, url):
        return False

    def setting(self):
        return {}
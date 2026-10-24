# -*- coding: utf-8 -*-
"""
剧踪影视 (juzong01.me) —— OK影视 py 源
基于 2026-10-24 实测站点结构编写，播放链路已破解：
  1. 播放页 player_data.url 为加密 token
  2. 请求 https://jzpic.ok1333.cn/?url=<token> 取 WGART_PARSE_TOKEN
  3. 请求 /wgart/api.php?action=try_json_api&video_url=<token>&parse_token=<T> 得到直链
站点域名常变，失效时改 HOST 即可。
"""

import re
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
        html = self.fetch(self.HOST, headers=self.headers).text
        return {'list': self._parse_list(html)[:12]}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, ext):
        ext = ext or {}
        url = '{0}vodshow/{1}-{2}-{3}-{4}-{5}-{6}---{7}---{8}.html'.format(
            self.HOST, tid,
            ext.get('area', ''), ext.get('by', ''), ext.get('class', ''),
            ext.get('lang', ''), ext.get('letter', ''), pg, ext.get('year', ''))
        html = self.fetch(url, headers=self.headers).text
        return {
            'list': self._parse_list(html),
            'page': int(pg), 'pagecount': 9999, 'limit': 90, 'total': 999999,
        }

    # ==================== 详情 ====================
    def detailContent(self, ids):
        vid = ids[0]
        if not vid.startswith('http'):
            vid = self.HOST.rstrip('/') + vid
        html = self.fetch(vid, headers=self.headers).text

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
    def playerContent(self, flag, id, vipFlags):
        url = id if id.startswith('http') else self.HOST.rstrip('/') + '/' + id.lstrip('/')
        html = self.fetch(url, headers=self.headers).text

        # 1. 提取加密 token
        token = self.regStr(html, r'"url":"([^"]+)"')
        direct = ''
        if token and not token.startswith('http'):
            direct = self._resolve_token(token)

        if direct:
            parse = 0
            play = direct
        else:
            # 兜底：直链正则 / 走嗅探
            m = re.search(r'(https?://[^"\'\s]+\.m3u8[^"\'\s]*)', html) or \
                re.search(r'(https?://[^"\'\s]+\.mp4[^"\'\s]*)', html)
            if m:
                parse, play = 0, m.group(1)
            else:
                parse, play = 1, url

        return {
            'parse': parse,
            'playUrl': '',
            'url': play,
            'header': {
                'User-Agent': self.UA,
                'Referer': self.PLAYER_BASE,
            },
        }

    def _resolve_token(self, token):
        try:
            # 2. 拿 parse_token
            page = self.fetch(
                self.PLAYER_BASE + '?url=' + quote(token),
                headers={'User-Agent': self.UA, 'Referer': self.HOST}).text
            pt = self.regStr(page, r'WGART_PARSE_TOKEN="([^"]+)"')
            if not pt:
                return ''
            # 3. 解析直链
            api = (self.PLAYER_BASE + 'wgart/api.php?action=try_json_api'
                   '&video_url=' + quote(token) + '&parse_token=' + quote(pt))
            res = self.fetch(api, headers={
                'User-Agent': self.UA,
                'Referer': self.PLAYER_BASE,
            }).text
            m = re.search(r'"url"\s*:\s*"([^"]+)"', res)
            if m:
                return m.group(1).replace('\\/', '/')
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
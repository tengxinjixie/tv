# -*- coding: utf-8 -*-
"""
西瓜_神马影院 (sszzyy.com) —— OK影视 py 源
基于 2026-10-25 实测站点结构编写。

播放链路说明（这就是原 XBPQ 配置播不出的原因）：
  该站多数片源为官源（v.qq.com / iqiyi / youku 等页面链接），
  站点自身走 https://hls.xiguadh.com 在线解析：
    1. 播放页取 player_aaaa.url 与 from
    2. url 若非直链 → 请求 hls.xiguadh.com/?url=<链接>（需 Cookie 会话）
       从页面提取 apiToken
    3. 请求 hls.xiguadh.com/api/resolve.php?token=<apiToken>（带同一 Cookie）
       返回 {"code":200,"url":"https://...m3u8..."} 直链
"""

import re
from urllib.parse import quote

from base.spider import Spider


class Spider(Spider):

    HOST = 'https://sszzyy.com/'
    PARSE = 'https://hls.xiguadh.com/'
    UA = ('Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/98.0.4758.101 Mobile Safari/537.36')

    headers = {
        'User-Agent': UA,
        'Referer': HOST + '/',
    }

    CATES = '电影$20#连续剧$37#综艺$45#动漫$43#B站$47#人人专区$60'

    TYPES = {
        '20': '动作片$21#喜剧片$22#爱情片$23#科幻片$24#恐怖片$25#剧情片$26#战争片$27#武侠片$33#奇幻片$34',
        '37': '国产剧$38#港台剧$39#欧美剧$40#日韩剧$41#其他剧$42',
        '43': '',
        '45': '',
        '47': '番剧（B站）$48#国创（B站）$49#电影（B站）$50#电视剧（B站）$51',
        '60': '连续剧$61#电影$62#动漫$63#综艺$64#纪录片$66',
    }

    YEARS = [{'n': '全部', 'v': ''}] + [
        {'n': str(y), 'v': str(y)} for y in range(2026, 2014, -1)]

    def init(self, extend=''):
        pass

    def getName(self):
        return '西瓜_神马影院'

    # ==================== 首页 ====================
    def homeContent(self, filter):
        classes = []
        for c in self.CATES.split('#'):
            n, i = c.split('$')
            classes.append({'type_name': n, 'type_id': i})
        result = {'class': classes}
        if filter:
            filters = {}
            for tid, val in self.TYPES.items():
                fl = [{'key': 'year', 'name': '年份', 'value': self.YEARS},
                      {'key': 'by', 'name': '排序', 'value': [
                          {'n': '最新', 'v': 'time'}, {'n': '最热', 'v': 'hits'},
                          {'n': '评分', 'v': 'score'}]}]
                if val:
                    sub = []
                    for c in val.split('#'):
                        n, i = c.split('$')
                        sub.append({'n': n, 'v': i})
                    fl.insert(0, {'key': 'class', 'name': '类型', 'value': sub})
                filters[tid] = fl
            result['filters'] = filters
        return result

    def homeVideoContent(self):
        html = self.fetch(self.HOST + '/', headers=self.headers).text
        return {'list': self._parse_list(html)[:20]}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, ext):
        ext = ext or {}
        # 子分类（动作片21、国产剧38等）是独立类型 id，必须放在 id/ 段
        if ext.get('class') and re.match(r'^\d+$', ext['class']):
            tid = ext['class']
        path = '/index.php/vod/show'
        if ext.get('area'):
            path += '/area/' + ext['area']
        if ext.get('by'):
            path += '/by/' + ext['by']
        if ext.get('year'):
            path += '/year/' + ext['year']
        path += '/id/' + tid + '/page/' + str(pg) + '.html'
        html = self.fetch(self.HOST + path, headers=self.headers).text
        return {
            'list': self._parse_list(html),
            'page': int(pg), 'pagecount': 9999, 'limit': 90, 'total': 999999,
        }

    # ==================== 详情 ====================
    def detailContent(self, ids):
        vid = ids[0]
        if not vid.startswith('http'):
            vid = self.HOST + vid
        html = self.fetch(vid, headers=self.headers).text

        vod = {'vod_id': vid}
        vod['vod_name'] = self.regStr(html, r'<h1[^>]*>([^<]+)</h1>') or ''
        vod['vod_pic'] = self.regStr(html, r'stui-content__thumb[\s\S]*?data-original="([^"]+)"')
        if not vod['vod_pic']:
            vod['vod_pic'] = self.regStr(html, r'stui-content__thumb[\s\S]*?src="([^"]+)"') or ''

        def _field(kw, stop='</p>'):
            seg = self.regStr(html, kw + r'([\s\S]*?)' + stop)
            return re.sub(r'<[^>]+>', '', seg).strip(' ：/').strip() if seg else ''

        vod['vod_director'] = _field('导演：')
        vod['vod_actor'] = _field('主演：')
        vod['vod_remarks'] = _field('状态：')
        meta = _field('类型：')
        # meta 形如 "爱情,喜剧 / 地区：美国 / 年份：2026"
        vod['vod_class'] = meta.split('/')[0].strip() if meta else ''
        vod['vod_area'] = ''
        m = re.search(r'地区[：:]\s*([^/]+)', meta)
        if m:
            vod['vod_area'] = m.group(1).strip()
        m = re.search(r'年份[：:]\s*([\d]+)', meta)
        if m:
            vod['vod_year'] = m.group(1).strip()

        desc = self.regStr(html, r'<span class="detail-sketch">([\s\S]*?)</span>')
        vod['vod_content'] = desc.strip() if desc else ''

        # 线路：nav-tabs 里 <a href="#playlistN">名字</a>，对应 id="playlistN" 的列表
        tabs = {}
        for href, name in re.findall(
                r'<a href="#(playlist\d+)"[^>]*>([^<]+)</a>', html):
            tabs[href] = name.strip()
        froms, plays = [], []
        for m in re.finditer(
                r'<div id="(playlist\d+)"[\s\S]*?<ul class="stui-content__playlist[^"]*">([\s\S]*?)</ul>',
                html):
            name = tabs.get(m.group(1), m.group(1))
            eps = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', m.group(2))
            if eps:
                eps_abs = [(h if h.startswith('http') else self.HOST + h, n) for h, n in eps]
                froms.append(name)
                plays.append('#'.join(n + '$' + h for h, n in eps_abs))
        vod['vod_play_from'] = '$$$'.join(froms) or '默认线路'
        vod['vod_play_url'] = '$$$'.join(plays)
        return {'list': [vod]}

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        url = id if id.startswith('http') else self.HOST + id
        html = self.fetch(url, headers=self.headers).text

        # player_aaaa={"flag":"play",...,"url":"...","from":"qq",...}
        raw = self.regStr(html, r'player_aaaa\s*=\s*(\{.*?\})\s*</script>')
        play, parse, u = '', 0, ''
        if raw:
            mu = re.search(r'"url"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            mf = re.search(r'"from"\s*:\s*"([^"]*)"', raw)
            u = mu.group(1).replace('\\/', '/') if mu else ''
            frm = mf.group(1) if mf else ''

            if re.search(r'\.(m3u8|mp4|flv)', u, re.I):
                play = u  # 自有直链
            elif u.startswith('http'):
                play = self._resolve(u, frm)  # 官源走解析
        if not play:
            # 兜底：嗅探
            parse = 1
            play = url

        return {
            'parse': parse,
            'playUrl': '',
            'url': play,
            'header': {
                'User-Agent': self.UA,
                'Referer': self.PARSE,
            },
        }

    def _resolve(self, video_url, frm=''):
        cookie = ''
        try:
            # 1. 解析页拿 apiToken + 下发的 Cookie
            resp = self.fetch(self.PARSE + '?url=' + quote(video_url, safe=''),
                              headers={'User-Agent': self.UA, 'Referer': self.HOST + '/'})
            page = resp.text
            token = self.regStr(page, r'apiToken:\s*"([^"]+)"')
            if not token:
                return ''
            try:
                ck = resp.headers.get('Set-Cookie', '') if resp.headers else ''
            except Exception:
                ck = ''
            pairs = re.findall(r'(\w+)=(?:[^;]+)', ck)
            got = re.findall(r'(\w+)=([^;,]+)', ck)
            if got:
                cookie = '; '.join(k + '=' + v for k, v in got)
            # 2. 调 resolve 接口（必须带同一 Cookie）
            api = (self.PARSE + 'api/resolve.php?token=' + quote(token, safe=''))
            res = self.fetch(api, headers={
                'User-Agent': self.UA,
                'Referer': self.PARSE,
                'Cookie': cookie,
            }).text
            mu = re.search(r'"url"\s*:\s*"((?:[^"\\]|\\.)*)"', res)
            if mu:
                out = mu.group(1).replace('\\/', '/')
                return out
        except Exception:
            pass
        # 3. 解析失败 → 回退网页嗅探
        return ''

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg=1):
        url = (self.HOST + '/index.php/vod/search.html?wd='
               + quote(key) + ('&pg=' + str(pg) if int(pg) > 1 else ''))
        html = self.fetch(url, headers=self.headers).text
        return {'list': self._parse_list(html), 'page': int(pg)}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    # ==================== 工具 ====================
    def _parse_list(self, html):
        videos = []
        items = re.findall(
            r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*href="([^"]+)"[^>]*title="([^"]*)"[^>]*data-original="([^"]*)"',
            html)
        if not items:
            items = re.findall(
                r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*href="([^"]+)"[^>]*title="([^"]*)"',
                html)
        for href, name, pic in items:
            if href.startswith('/'):
                href = self.HOST + href
            # 副标题：更新状态
            videos.append({
                'vod_id': href,
                'vod_name': name.strip(),
                'vod_pic': pic,
                'vod_remarks': '',
            })
        # 附带备注：取 pic-text（“更新至X集/已完结”），跳过 pic-text1（分类标签）
        marks = re.findall(
            r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[\s\S]*?<span class="pic-text(?!1)[^"]*">([\s\S]*?)</span>',
            html)
        for i, v in enumerate(videos):
            if i < len(marks):
                v['vod_remarks'] = re.sub(r'<[^>]+>', '', marks[i]).strip()
        return videos

    def isVideoFormat(self, url):
        return True

    def isTextFormat(self, url):
        return False

    def setting(self):
        return {}

var rule = {
    title: 'tengxin360资源',
    编码: '',
    搜索编码: '',
    host: 'https://360zy.com/',
    //url: '/api.php/provide/vod?ac=detail&t=fyclass&pg=fypage&f=',
    url: '/ajax/data?mid=1&tid=fyfilter&page=fypage&limit=20',
    class_name: '电影&电视剧&动漫&综艺&短剧',
    class_url: '1&2&4&3&46',
    homeUrl: '/api.php/provide/vod?ac=detail',
    searchUrl: '/api.php/provide/vod?ac=detail&wd=**&pg=fypage', 
    detailUrl: '/api.php/provide/vod?ac=detail&ids=fyid', 
    searchable: 2,
    quickSearch: 0,
    filterable: 1,
    filter_url: '{{fl.cateId}}',
    filter: {
        "1": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "" }, { "n": "动作片", "v": "6" }, { "n": "喜剧片", "v": "7" }, { "n": "爱情片", "v": "8" }, { "n": "科幻片", "v": "9" }, { "n": "恐怖片", "v": "10" }, { "n": "剧情片", "v": "11" }, { "n": "战争片", "v": "12" }, { "n": "惊悚片", "v": "20" }, { "n": "家庭片", "v": "21" }, { "n": "古装片", "v": "22" }, { "n": "历史片", "v": "23" }, { "n": "悬疑片", "v": "24" }, { "n": "犯罪片", "v": "25" }, { "n": "灾难片", "v": "26" }, { "n": "纪录片", "v": "27" }, { "n": "短片", "v": "28" }, { "n": "动画片", "v": "29" }, { "n": "西部片", "v": "45"  }] }],
        "2": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "" }, { "n": "国产剧", "v": "13" }, { "n": "香港剧", "v": "14" }, { "n": "韩国剧", "v": "15" }, { "n": "欧美剧", "v": "16" }, { "n": "台湾剧", "v": "30" }, { "n": "泰国剧", "v": "33" }] }],
      
        "4": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "" }, { "n": "国产动漫", "v": "38" }, { "n": "欧美动漫", "v": "39" }, { "n": "日韩动漫", "v": "40" }] }],
            "3": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "" }, { "n": "大陆综艺", "v": "34" }, { "n": "港台综艺", "v": "35" }, { "n": "日韩综艺", "v": "36" },  { "n": "欧美综艺", "v": "37"  }] }],
        "46": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "" }, { "n": "现代都市", "v": "47" }, { "n": "脑洞悬疑", "v": "48" }, { "n": "年代穿越", "v": "49" }, { "n": "古装仙侠", "v": "50" }, { "n": "反转爽剧", "v": "51" }, { "n": "女频恋爱", "v": "52" }, { "n": "成长逆袭", "v": "53" }] }]
    },
    filter_def:{
        1:{cateId:'1'},
        2:{cateId:'2'},
        4:{cateId:'4'},
        3:{cateId:'3'},
        46:{cateId:'46'}
    },
    play_parse: false,
    lazy: '',
    multi: 1,
    timeout: 5000,
    limit: 20,
    推荐: 'json:list;vod_name;vod_pic;vod_remarks;vod_id', // double: true, 
    一级: 'json:list;vod_name;vod_pic;vod_remarks;vod_id',
    /**
     * 
     */
    //二级: `json:list;vod_name;vod_pic;vod_remarks;vod_id`,
    二级: `js:
        let html = request(input);
        let list = JSON.parse(html).list;
        if(list.length===1){
           VOD = list[0];
VOD.vod_play_from = ('❤️腾影提示:勿信片中广告');
            VOD.vod_blurb = VOD.vod_blurb.replace(/　/g, '').replace(/<[^>]*>/g, '');
            VOD.vod_content = VOD.vod_content.replace(/　/g, '').replace(/<[^>]*>/g, '');
        }
    `,
    /**
     * 
     */
    搜索: 'json:list;vod_name;vod_pic;vod_remarks;vod_id',
}
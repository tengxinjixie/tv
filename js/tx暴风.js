var rule = {
    title: '暴风资源',
    编码: '',
    搜索编码: '',
//*https://bfzyapi.com/api.php/provide/vod/
    host: 'https://bfzyapi.com/',
    //url: '/api.php/provide/vod?ac=detail&t=fyclass&pg=fypage&f=',
    url: '/api.php/provide/vod?ac=detail&pg=fypage&t=fyfilter',
    class_name: '电影&电视剧&动漫&综艺&短剧',
    class_url: '20&30&39&45&58', 
    homeUrl: '/api.php/provide/vod?ac=detail',
    searchUrl: '/api.php/provide/vod?ac=detail&wd=**&pg=fypage', 
    detailUrl: '/api.php/provide/vod?ac=detail&ids=fyid', 
    searchable: 2,
    quickSearch: 0,
    filterable: 1,
    filter_url: '{{fl.cateId}}',
    filter: {
        "20": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "20" }, { "n": "动作片", "v": "21" }, { "n": "喜剧片", "v": "22" }, { "n": "爱情片", "v": "25" }, { "n": "科幻片", "v": "24" }, { "n": "恐怖片", "v": "23" }, { "n": "剧情片", "v": "26" }, { "n": "战争片", "v": "27" }, { "n": "纪录片", "v": "28" },{ "n": "动画片", "v": "50"  }] }],
        "30": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "30" }, { "n": "国产剧", "v": "31" }, { "n": "香港剧", "v": "33" }, { "n": "韩国剧", "v": "34" }, { "n": "欧美剧", "v": "32" }, { "n": "台湾剧", "v": "35" }, { "n": "泰国剧", "v": "38" }] }],   
        "39": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "39" }, { "n": "国产动漫", "v": "40" }, { "n": "港台动漫", "v": "43" },{ "n": "欧美动漫", "v": "42" }, { "n": "日韩动漫", "v": "41" }] }],
        "45": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "45" }, { "n": "大陆综艺", "v": "46" }, { "n": "港台综艺", "v": "47" }, { "n": "日韩综艺", "v": "48" },  { "n": "欧美综艺", "v": "49"  }] }],
        "58": [{ "key": "cateId", "name": "剧情", "value": [{ "n": "全部", "v": "58" }, { "n": "现代言情", "v": "67" }, { "n": "女恋总裁", "v": "69" }, { "n": "都市脑洞", "v": "71" }, { "n": "反转爽文", "v": "68" }, { "n": "重生民国", "v": "65" }, { "n": "古装仙侠", "v": "72" }, { "n": "闪婚离婚", "v": "70" }, { "n": "穿越年代", "v": "66" }] }]
    },
    filter_def:{
        20:{cateId:'20'},
        30:{cateId:'30'},
        39:{cateId:'39'},
        45:{cateId:'45'},
        58:{cateId:'58'}
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
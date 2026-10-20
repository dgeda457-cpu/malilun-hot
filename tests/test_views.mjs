// Pure view/event tests in Node's isolated VM. This is not a browser or screenshot test.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const html={innerHTML:''},listeners={},values={},storage=new Map();
const catalog=JSON.parse(fs.readFileSync('dist/data/catalog.json','utf8'));
const briefs=JSON.parse(fs.readFileSync('dist/data/briefs.json','utf8'));
const doc={querySelector:s=>s==='#main'?html:(values[s]??={value:'',textContent:''}),querySelectorAll:()=>[],addEventListener:(event,fn)=>listeners[event]=fn,createElement:()=>({click(){}})};
const context=vm.createContext({document:doc,location:{hash:'#home'},window:{addEventListener(){},scrollTo(){}},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},URLSearchParams,Intl,Date,Set,Map,console,encodeURIComponent,decodeURIComponent,Blob,URL,AbortSignal,setTimeout,FormData:class{constructor(form){return form.fields;}},fetch:async href=>({ok:true,json:async()=>href.endsWith('briefs.json')?briefs:catalog})});
vm.runInContext(fs.readFileSync('public/app.js','utf8'),context);
await new Promise(r=>setImmediate(r));
let count=0;
function check(label,fn){fn();console.log('PASS '+label);count++;}
check('首页展示真实标题',()=>assert.ok(html.innerHTML.includes(catalog.items[0].title)));
check('所有真实标题都有详情路由',()=>{for(const x of catalog.items){context.location.hash='#item/'+x.id;context.render();assert.ok(html.innerHTML.includes(x.title));assert.ok(html.innerHTML.includes('打开原始来源'));assert.ok(html.innerHTML.includes(x.url.replaceAll('&','&amp;')));}});
check('关键词检索能匹配实际作者',()=>{const author=catalog.items.find(x=>x.authors.length).authors[0];const result=context.search(new URLSearchParams({q:author}));assert.ok(result.includes(author));assert.ok(result.includes('检索结果'));});
check('无结果显示真实空状态',()=>assert.ok(context.search(new URLSearchParams({q:'__NO_SUCH_PUBLICATION_8437__'})).includes('没有匹配资料')));
check('日期范围错误可理解',()=>assert.ok(context.search(new URLSearchParams({from:'2026-10-20',to:'2026-01-01'})).includes('日期范围不正确')));
check('7天无样本不会填充假热点',()=>{vm.runInContext("rankDays='7'",context);assert.ok(context.rankings().includes('本时段样本不足'));});
check('雷达保存与筛选',()=>{context.location.hash='#radar';context.render();doc.querySelector('#radar-keywords').value='思想政治教育，红色文化';listeners.click({target:{id:'save-radar',closest(){return null;}}});assert.equal(JSON.parse(storage.get('malilun-radar-v1')).keywords.length,2);assert.ok(html.innerHTML.includes('个人学术日报视图'));});
check('导入配置拒绝非字符串与过长列表',()=>{assert.throws(()=>context.validateRadar({version:1,keywords:[{}]}));assert.throws(()=>context.validateRadar({version:1,keywords:Array(61).fill('x')}));});
check('文本中HTML被转义',()=>assert.equal(vm.runInContext("escape('<script>bad()</script>')",context),'&lt;script&gt;bad()&lt;/script&gt;'));
check('未知出版日不会显示编造日',()=>{const x=catalog.items.find(x=>x.kind==='paper'&&!x.publication_date);context.location.hash='#item/'+x.id;context.render();assert.ok(html.innerHTML.includes('期刊出版日期</span>未核实'));assert.ok(!html.innerHTML.includes('主要观点'));});
check('预设专题和日报可以渲染',()=>{for(const t of catalog.topics)assert.ok(context.topicPage(t.id).includes(t.name));for(const b of briefs)assert.ok(context.briefPage(b.date).includes(b.date));});
check('正式空数据也能渲染',()=>{vm.runInContext("data={schema_version:1,items:[],topics:[],sources:[],runs:[],rankings:{}};briefs=[]",context);context.location.hash='#home';context.render();assert.ok(html.innerHTML.includes('暂未收录学术成果'));});
fs.writeFileSync('evidence/view-test-results.json',JSON.stringify({test_kind:'Node isolated view and event logic; not browser visual QA',passed:count,at:new Date().toISOString()},null,2));
console.log(`${count} view/event checks passed. Browser visual QA is separate.`);

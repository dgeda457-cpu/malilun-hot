# 马理论 HOT

马克思主义理论学术情报平台。**判断止于证据，不替学界多说一步。**

公开网站：<https://malilun-hot.fast-plum-3707.chatgpt.site>

源码与数据：<https://github.com/dgeda457-cpu/malilun-hot>

## 日常使用

打开网站即可阅读，不用注册。学术前沿包括真实论文与高校成果报道；博士招生包括历史公告，不能据此判断今年是否仍能报名。我的雷达保存在本浏览器，可导出关键词配置。

网站使用 Sites 托管静态页面，GitHub Actions 在公开仓库的标准 Linux 运行器上每日低频采集，生成公开 JSON 和 RSS。页面优先展示随站备份，再读取仓库的最新数据；更新无需重新发布前端，也无需电脑开机。云端读不到时保留备份并显示提示。

**核心运行没有 AI API、数据库、后台、服务器、付费依赖或密钥。**

## 本地复现

需要 Python 3.11 或更新版本（建议3.12）。仅解析依赖 BeautifulSoup；前端为原生 HTML/CSS/JavaScript，无需安装 Node 包。

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/collect.py
python scripts/build.py
python scripts/validate.py
python -m http.server 4173 --directory dist
```

打开 <http://localhost:4173>。不能直接双击 index.html，因为浏览器会限制本地数据文件读取。

可选界面逻辑测试（Node 18+）：`node tests/test_views.mjs`。这不等于真实浏览器或手机截图验收。

## 项目文件

- `config/sources.json`：信源、栏目和低频采集上限。
- `config/topics.json`：主题与字面匹配关键词。
- `config/corrections.json`：有官方证据的人工纠错与撤除。
- `scripts/collect.py`：robots检查、HTTPS采集、解析、去重、故障隔离。
- `scripts/build.py`：7/30/90天统计、专题、规则日报、RSS与静态导出。
- `public/data/catalog.json`：采集档案，保留发现与核验时间。
- `public/data/site.json`：网站云端读取的数据。
- `public/data/briefs/`：每期日报，按首次发现时间编排。
- `public/feeds/`：全站、栏目、专题 RSS。
- `evidence/run-*.json`：真实HTTP状态、哈希、字段、错误和样本。
- `.github/workflows/update.yml`：每天11:23和23:23 UTC执行；纽约时间夏季07:23/19:23、冬季06:23/18:23。GitHub可能延迟运行。
- `docs/使用说明.md`：非程序员维护指南。

## 学术与版权边界

不采集受限全文。只公开题名、作者、日期、期刊、年期、原始链接与最多120字的公开摘要摘录。未取得开放转载许可；robots无禁止不构成版权许可。原文权利归原作者与出版机构所有。遇到拒绝访问停止本轮该来源详情请求，不使用代理、验证码绕过或登录爬取。

近期关注榜只使用核实精确出版日的独立论文/著作。按成果数、独立期刊或出版机构数、最近出版日依次排序，会议和转载不加分。出版日未知的记录正常展示并标注，不用网页日或采集日替代。主题是关键词检索关系，不是已证实的学术关系。详情没有“自动生成主要观点”功能。

## 借鉴与许可证

研究参考 [AIHOT](https://github.com/KKKKhazix/AIHOT)，核查提交 `5633b648b9ca6453caec5bcf70a76785a794286f`，MIT许可证。借鉴来源追踪、独立来源计数、去重和规则日报的思路；本项目独立实现，未导入其业务代码、品牌、运营信源或数据。

本项目代码采用 MIT；文章元数据与摘要摘录不因此转为MIT授权。详见 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`。

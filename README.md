# 咖啡资讯每日聚合 RSS

把**全球 / 全国 / 云南**三层咖啡资讯（新闻 · 价格 · 政策）聚合成**一条 RSS 2.0**，
通过 GitHub Actions 每天定时生成，并发布到 GitHub Pages，得到一个**永久订阅链接**。

## 当前订阅源（纯中文，4 个）

> 设计取舍：英文源（Daily Coffee News / Perfect Daily Grind / Sprudge）已全部移除——
> 无人值守的每日任务里挂翻译等于埋雷（需第三方 API key 或离线模型导致变慢且专有名词翻乱）。
> 国际动态由「咖啡金融网·咖啡资讯」以中文报道，覆盖全球产地与价格面。

| 源 | 层 | 接入方式 |
|---|---|---|
| 咖啡金融网·咖啡资讯 | 全球 | 抓取（scraper: coffinance_list） |
| 咖啡金融网·行业动态 | 全国 | 抓取（scraper: coffinance_list） |
| 咖啡金融网·中国云南 | 云南 | 抓取（scraper: coffinance_list，替代已停服的 YCE） |
| 云南省农业农村厅·云农快讯 | 云南 | 抓取（scraper: yunnong，按关键词「咖啡/热作」过滤） |

> 后续可在 `feeds.toml` 里加源，每次加一个 `[[sources]]` 块即可。
> 注：云南国际咖啡交易中心（YCE）官网因备案不合规已被关停；省农科院《咖啡双周报》
> 仅发 PDF + 微信公众号、无网页列表，暂无法自动抓取，已用「咖啡金融网·中国云南」替代。

## 本地运行

```bash
# 仅用 Python 标准库，无需任何依赖
python coffee_news_aggregator.py --config feeds.toml --out public --limit 50
```

生成 `public/feed.xml`（可订阅）与 `public/index.html`（预览页）。

可选参数：

- `--limit N` 限制条目数（默认 50）
- `--with-content` 抓取正文摘要（更慢）
- `--base https://你的pages地址` 设置 RSS `<link>` 自托管地址

## 部署到 GitHub Pages（永久订阅链接）

1. 把本目录推送到一个 GitHub 仓库（公开仓库；私有仓库需 GitHub Pro 才能用 Pages）。
2. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
3. 工作流 `.github/workflows/rss.yml` 会：
   - 每天 UTC 00:00（北京时间 08:00）自动运行；
   - 调用脚本生成 `public/feed.xml` + `index.html`；
   - 发布到 Pages。
4. 订阅地址即：
   - RSS：`https://<你的用户名>.github.io/<仓库名>/feed.xml`
   - 网页：`https://<你的用户名>.github.io/<仓库名>/`

把 RSS 地址丢进任意阅读器（Feedly / Inoreader / 鲜知 / NetNewsWire 等）即可每天收到更新。

## 文件说明

- `coffee_news_aggregator.py` —— 零依赖聚合器（RSS/Atom 解析 + 抓取器 + 合并去重排序）
- `feeds.toml` —— 订阅源配置（你主要改这个）
- `public/` —— 生成的产物（由 Actions 自动产出，本地也可手动生成）
- `.github/workflows/rss.yml` —— 定时生成 + Pages 发布

## 注意事项

- 抓取类源依赖对方页面结构，若对方改版导致解析失败，脚本会跳过该源并告警，不影响其他源。
- 综合农业栏目（如云农快讯）用 `keywords` 过滤，只保留标题/摘要命中关键词的条目，避免稀释 feed。
- 国内与云南部分优质信源（YCE、省农科院《咖啡双周报》）暂无网页版，后续若开通或改用公众号 RSS 桥接再接入。

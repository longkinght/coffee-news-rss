# 咖啡资讯每日聚合 RSS

把**全球 / 全国 / 云南**三层咖啡资讯（新闻 · 价格 · 政策）聚合成**一条 RSS 2.0**，
通过 GitHub Actions 每天定时生成，并发布到 GitHub Pages，得到一个**永久订阅链接**。

## 当前订阅源（MVP，5 个）

| 源 | 层 | 接入方式 |
|---|---|---|
| Daily Coffee News | 全球 | RSS |
| Perfect Daily Grind | 全球 | RSS |
| Sprudge | 全球 | RSS |
| 云南省农业农村厅·云农快讯 | 云南 | 抓取（scraper: yunnong） |
| 咖啡金融网 | 全国 | 抓取（scraper: coffinance） |

> 后续可在 `feeds.toml` 里加源（如 Global Coffee Report、云南国际咖啡交易中心、
> 省农科院《咖啡双周报》等），每次加一个 `[[sources]]` 块即可。

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

- 部分站点（Perfect Daily Grind / Sprudge）有反爬，已用 `curl/8.0` UA 规避。
- 抓取类源依赖对方页面结构，若对方改版导致解析失败，脚本会跳过该源并告警，不影响其他源。
- 国内与云南优质信源多在微信公众号，需「公众号 RSS 桥接」或抓取历史文章，后续版本再接入。

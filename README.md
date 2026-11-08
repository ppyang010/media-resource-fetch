# media-resource-fetch

影视资源查找 + 夸克网盘自动归档。给一句话的剧名，产出一个按剧名整理好的网盘文件夹。

零依赖：只用 Python 标准库，不需要 MoviePilot / Docker / 任何外部软件。

```
你说「找《XX》第5期下」
  → 微博搜帖 / 资源站扫描拿到夸克分享链接
  → 探测分享内容，判断该放哪个文件夹
  → 选择性转存（不整包拉几十 G 的合集）
  → 写入台账，刷新资源库快照
```

## 能力

| 能力 | 说明 |
|:--|:--|
| 多源找链接 | 微博搜帖（带 cookie 最快）、资源站搜索、sitemap 兜底、免登录镜像页 |
| 选择性转存 | 合集里只取要的那一集，不用把 387G 全拉下来 |
| 自动归档 | 有干净文件夹名就沿用，没有就按剧名建；同名目录复用不产生 `xxx(1)` |
| 台账 | `data/resources.jsonl` 记录找到过什么、转没转、在哪 |
| 环境自检 | `check_env.py` 六项检查，含 cookie 是否真能用 |

## 安装

**第一次装、机器上什么都没有？照 [`INSTALL.md`](INSTALL.md) 走，约 10 分钟**（含 Python 安装和 cookie 获取的每一步）。

已经装好 Python 的话，最短路径：

```bash
cd ~/.workbuddy/skills
git clone https://github.com/ppyang010/media-resource-fetch.git
cd media-resource-fetch
python install.py
```

`install.py` 会装到 `~/.workbuddy/skills/media-resource-fetch`、检查授权、跑一次自检。

也可以下载 release 里的 zip，解压后放进 `~/.workbuddy/skills/`，再执行 `python install.py`。

## 准备

| 项 | 必需 | 说明 |
|:--|:--|:--|
| Python 3.8+ | 是 | 只用标准库，不装任何 pip 包 |
| 夸克网盘 cookie | 是 | 需要能登录 `pan.quark.cn` |
| 微博 cookie | 否 | 配了才能用 `weibo.py` 搜帖，否则只能靠资源站 |

授权放在 `~/.workbuddy/media-fetch.json`（**不在本仓库内**）：

```json
{
  "quark_cookie": "浏览器 F12 → Network → 任一请求 → 整串 Cookie",
  "weibo_cookie": "SUB=xxx; SUBP=yyy",
  "default_dir": "/00影视-待看"
}
```

微博只需 `SUB` 和 `SUBP`（Domain 为 `.weibo.com`）。**逐步取法见 [`INSTALL.md`](INSTALL.md) 第 6 步**，踩坑记录见 `references/known-issues.md`。

## 用法

```bash
cd scripts

python check_env.py                          # 开工前自检
python get.py <分享链接> --dry                # 预演，看文件夹名对不对
python get.py <分享链接>                      # 执行：转存 + 归档 + 记账

python get.py <链接> --pick 会友 --name 后会友期   # 合集里只取一部
python get.py <链接> --name "现在就出发 第四季"    # 名字被插字时强制覆盖

python weibo.py search "剧名 第N期" --quark    # 微博搜帖，只出带夸克链的
python weibo.py user <uid> --quark            # 盯某个搬运号有没有更新

python probe_share.py <id>                    # 只看分享里有什么、多大
python quark_dir.py ls "/00影视-待看"          # 网盘目录操作
python res.py list                            # 看台账
```

完整流程、文件夹规则、何时必须先问用户，见 `SKILL.md`。

## 目录

```
SKILL.md                  主流程与规则（给 agent 读的说明书）
INSTALL.md                从零上手：装 Python、放目录、取 cookie、WorkBuddy 识别
MIGRATION.md              打包 / 分发 / 迁移（维护者用）
references/
  known-issues.md         踩过的坑、接口参数、渠道实测结论
  resource-library.md     资源库快照（由台账渲染）
scripts/
  get.py                  主入口：转存 + 归档 + 记账
  weibo.py                微博检索，挖帖子里的真实网盘直链
  probe_share.py          只读探测分享内容
  quark_save.py           选择性转存
  quark_dir.py            网盘目录 ls/mkdir/move/rm
  res.py                  台账增删改查
  check_env.py            环境自检
  mplib.py                公共层：配置、HTTP、任务轮询
pack.py / install.py      打包 / 安装
```

## 关于分发

分享仓库地址即可，对方 `git clone` + `python install.py`，然后自备 cookie。
仓库里**不含任何凭据**：cookie 存在 `~/.workbuddy/media-fetch.json`，本来就在仓库外，
`pack.py` 也不打包它。

`data/`（个人台账）与 `dist/`（打包产物）已在 `.gitignore` 里，不会被提交。

## 边界

仅用于个人观看。不要批量抓取整站、不要高频轮询、不要把转存内容再分发或商用。

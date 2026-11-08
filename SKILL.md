---
name: media-resource-fetch
description: 影视资源查找与网盘转存。当用户想找某部剧/电影/综艺的资源、说「找资源」「找片」「有 XX 吗」「帮我找 XX 剧」、或给出夸克分享链接要求「转存到网盘」时使用。涵盖：确认剧名与更新进度、从微博镜像页取短链、解析 t.cn 短链、探测分享内容、一条命令转存并自动按剧名归档、写入资源台账。适用于国产剧、泰剧、日剧、韩剧、美剧、综艺、电影。Use when the user wants to find and save video resources (dramas, movies, variety shows) to their Quark netdisk, or asks to transfer a pan.quark.cn share link.
agent_created: true
---

# 影视资源查找与转存

目标：用户说「找 XX」，最终产出是**网盘里一个以剧名命名的文件夹，里面是该剧的剧集文件**，
并在台账留一条记录。全程不需要用户手工操作网盘。

---

## 环境

这个 skill 是**独立单元**：脚本、数据、文档都在自己目录内，拷到任何机器都能跑，
不需要任何外部软件，也不需要 pip install 任何东西。

| 项 | 值 |
|:--|:--|
| 代码目录 | `<skill>\scripts`（跟着 skill 走） |
| 数据目录（台账） | `<skill>\data`，可用环境变量 `MEDIA_FETCH_DATA` 改 |
| Python | 任意 **3.9+**，只用标准库 |
| 夸克授权 | 环境变量 `QUARK_COOKIE` → 配置文件 `~/.workbuddy/media-fetch.json` |
| 微博授权（可选） | 环境变量 `WEIBO_COOKIE` → 同文件 `weibo_cookie`（只填了才能用 `weibo.py`） |
| 默认落盘目录 | `/00影视-待看` |

cookie 故意**不放在 skill 目录里**，这样 skill 可以整体打包分发而不泄露账号。

**先切换目录并跑环境自检**，不要跳过：

```powershell
$skill = "$env:USERPROFILE\.workbuddy\skills\media-resource-fetch\scripts"
cd $skill
$py = "python"          # 若 python 不在 PATH，换成完整解释器路径

& $py check_env.py
```

退出码 0 才继续。它检查五件事：脚本是否齐、Python 版本、数据目录可写、
cookie 从哪来、**cookie 是否真能列目录**（很多人以为 cookie 还在就是能用，其实早失效了）。

> 所有网盘操作直连夸克 API，不需要任何外部软件在运行。
> 换机器 / 分发给别人见 `MIGRATION.md`（装：`python install.py`；打包：`python pack.py`）。

---

## 第 0 步 · 先查资源库（省时间，别跳过）

`references/resource-library.md` 记录了**已经找过、转过**的资源清单。
用户问「有 XX 吗」时先翻这里：

| 库里的状态 | 该怎么回 |
|:--|:--|
| 已在网盘 | 直接说「已经在你网盘了，在 `/00影视-待看/XX/`，共 N 个文件」，不用重找 |
| 链接有效但没转 | 问要不要现在补转（链接约 6 天失效，别拖） |
| 已失效留档 | 说明「之前找过但链接失效了」，直接找新链接，不要去试旧链接 |

这个文件由 `scripts/sync_library.py` 从台账生成，`get.py` 转存后会自动刷新一次，
一般不用手动维护。想立刻更新就跑一次：

```powershell
& $py sync_library.py
```

---

## 第 1 步 · 找资源

目标是拿到一个 `https://pan.quark.cn/s/xxxxxxxx` 形式的链接。

### 1.1 先确认剧名和更新进度

用 WebSearch 查清楚三件事，**不要凭印象直接翻网盘**：

- **剧名有几种译法**。例：《午夜规则》同时叫《午夜法则》《午夜后的规则》，
  原名可能是泰文/韩文/英文（`The Rules`、`กฎหลังเที่ยงคืน`）。搜错名字会白跑。
- **更新到第几集了**。避免找到过期合集还以为是最新。
- **播出平台和更新节奏**。写进台账备注，也用于判断下次什么时候该找。

### 1.2 从微博拿分享链接

两条路，**配了微博 cookie 就先走 A**，一秒出结果。

#### A. 带登录态搜帖（首选）

```powershell
& $py weibo.py search "剧名 第N期" --quark   # 直接吐出带夸克链的帖子
& $py weibo.py user <uid> --quark            # 盯某个搬运号有没有更新
```

实测：某综艺第 5 期下 12:00 播出，20:25 起搬运号陆续发帖，
`search "现在就出发 第5期下" --quark` 一次拿到 7 条带夸克链的帖子。

关键机制：搜索结果里 `text` 中的 `t.cn` 是**广告占位**，直接 curl 会跳到广告页；
真链接在 `statuses/show` 的 `url_struct[].long_url`，`weibo.py` 已自动做这层二次请求。

#### B. 微博镜像页（免登录，但有代价）

微博的公开接口全要登录态（`m.weibo.cn/api/...` 432、`s.weibo.com/weibo` 302、
`rsshub` 403、`weibo.com/u/` 跳 passport）。唯一免登录的是新浪的静态镜像页：

```
https://www.sina.cn/media/<博主uid>
```

用 WebFetch 抓页面，找这种格式的帖子：

```
泰剧《某某》更新1-3集    度: http://t.cn/xxx    夸: http://t.cn/yyy
```

`度` = 百度网盘，`夸` = 夸克网盘。只要夸克那条。

两个坑：
- **只能按 uid 查，不能搜**。没有搜索就没有发现新 uid 的途径，别指望靠它找新号。
- **会滞后甚至停更**。2026-11 实测博主 `2265615342`（星星长乐未央）自 11-06 16:37
  起不再发帖，而同期对照组账号的镜像页能刷出 10 分钟内的新帖——是号停了，不是镜像坏了。
  判断方法：抓同一服务上另一个活跃 uid，比对时间戳。

### 1.3 解短链

```bash
curl -s --noproxy '*' -o /dev/null -w "%{redirect_url}" \
  -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)" \
  "http://t.cn/xxxxx"
# → https://pan.quark.cn/s/053c57393863
```

`--noproxy '*'` 必须加，本机系统代理会拦。

### 1.4 找不到时（含资源站这条备选）

按顺序试：

1. **微博镜像页** —— 最快，但有 1–2 天延迟，当天更新的常常还没出现
2. **资源站搜索页** —— 聚合站，更新及时，直链就写在 HTML 里
3. 换关键词（英文名 / 原名 / 主演）、换博主
4. 翻 `references/resource-library.md`，看之前是否找过

资源站用法（2026-11 实测，微博还没更新时靠它拿到的）：

```bash
# 1. 搜剧名，得到条目页（条目名带发布日期，如「11.07期」）
#    https://box.jiugeku.com/search?q=<剧名>

# 2. 直接抓条目页 HTML 里的夸克直链，不用登录也不用解短链
curl -s --noproxy '*' \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  "https://box.jiugeku.com/r/<条目id>" \
  | grep -oE "https?://pan\.quark\.cn/s/[A-Za-z0-9]+"
```

优势：免登录、免短链解析、同页能拿到夸克和百度两条链。
注意两点：条目名里的期数是**发布日期**（`11.07期` = 第 5 期上），要和播出表对一下；
这类站常同时给多个版本（4K / 1080p），用 `probe_share.py` 看清体积再决定转哪个。

**搜索没结果 ≠ 站上没有**。搜索索引会滞后，当天新集常常搜不到但条目已经建好了。
用 sitemap 兜底，按当天日期筛条目再批量看标题：

```bash
curl -s --noproxy '*' "https://box.jiugeku.com/sitemap.xml" -o /tmp/sm.xml
# 取 lastmod 为今天的所有 /r/<id>，再逐个抓 <title> 找剧名
```

11-08 实测：当天新增 104 条，搜索页里一个都没有，sitemap 里能全查到。
如果 sitemap 里当天条目也没有对应剧名，那就是真还没上传，别继续找——等几小时或次日再试。

**找不到就直说找不到**，不要给没验证过的链接。已验证的结论：
新剧主要靠微博和资源站这两条路，公共网盘搜索引擎大多已失效，别在它们上面浪费时间。

---

## 第 2 步 · 同步转存

先预演，确认文件夹名对不对：

```powershell
& $py get.py <链接> --dry
```

再执行：

```powershell
& $py get.py <链接>
```

一条命令完成：读分享结构 → 决定文件夹归属 → 转存 → 写台账。

**必须检查 `--dry` 输出的文件夹名**，原因见下一节。

---

## 文件夹规则

| 分享里的结构 | 处理 | 结果 |
|:--|:--|:--|
| 根下就是一个剧名文件夹 | 沿用原文件夹名，整包转 | `/00影视-待看/<原名>/` |
| 根下是散文件 | 按剧名新建，全部放进去 | `/00影视-待看/<剧名>/` |
| 目标已有同名文件夹 | 复用并入，不新建 `xxx(1)` | 文件追加 |
| **根下是多个剧的合集** | **必须加 `--pick <关键词>` 只取一个** | 只放那一部 |

### 合集分享（很常见，一定要注意）

很多博主会把十几部剧塞进一个分享，根下有十几个目录。实例：一个「综艺合集」分享
根下有 8 个综艺共 **321 个文件 / 387G**，你要的只是其中一个 12.9G 的目录。

`get.py` 遇到多目录会提示「这看着像合集」，但**不会自动只取一个**（它不知道你要哪个）。
必须显式指定：

```powershell
& $py get.py <链接> --pick 会友 --name "后会友期"
```

`--pick` 的匹配是**子串匹配目录名**。目录名常被插字（`HH会友QIQI` = 后会友期），
用其中能稳定匹配的片段即可；匹配不到时脚本会列出所有可选项。


### 插字坑（每次都要检查）

发布者会用插字符规避审查，`--dry` 显示的名字可能是垃圾：

| 实际显示 | 原意 |
|:--|:--|
| `X-现｜在｜4` | 现在就出发 第四季 |
| `H 现A就A发 第四季 (已更新)` | 现在就出发 第四季 |
| `现.zai.旧.出.发.4` | 现在就出发 第四季 |

**遇到就加 `--name` 覆盖**，用干净的剧名（带季数，便于区分）：

```powershell
& $py get.py <链接> --name "现在就出发 第四季"
```

判断标准：这个名字要让三个月后的人一眼认出是哪部剧。

---

## 何时必须先问用户

不要自行决定这几种情况：

- **体积异常**：待转存超过 50G（`--dry` 会显示总大小），确认是否只要其中几集
- **合集分享**：`--dry` 显示「N 个目录」且总体积巨大时，**不要直接转**，
  先确认用户要哪一部，再用 `--pick` 指定。实例：387G 的合集里只取 12.9G 的一部
- **内容不符**：分享里是第 1-2 季但用户要第 4 季，或片名对不上
- **多个候选**：搜到多个不同分享且内容不同，列出来让用户选
- **要删除**：`quark_dir.py rm` 会删整个目录，必须用户明确同意后才加 `--yes`
- **换目录**：用户没指定落盘位置时用默认 `/00影视-待看`；要改就用 `--dir`，不要猜

---

## 结果怎么汇报

给出四件事，不要只说「好了」：

1. **实际路径**：`/00影视-待看/午夜规则/`
2. **文件清单**：几个文件、各多大、对应第几集
3. **来源与时效**：来自哪个链接、什么时候发布（微博链接约 6 天失效，要提醒）
4. **下一步**：下次更新是什么时候

---

## 已知坑

摘要如下，完整版（含接口参数、报错原文）见 `references/known-issues.md`：

- **微博链接寿命约 6 天**。两个样本都是第 6 天 404。看到就转，别存链接。
- **微博只管 weibo.com 的 cookie**。`m.weibo.cn` 不认同一份凭据（`api/config` 返回
  `login:false`），别在 m 站上浪费请求；搜索走 `/ajax/statuses/search`。
- **搜索结果的 `t.cn` 是广告占位**，真链接要再查 `statuses/show` 的 `url_struct[].long_url`。
- **`file/move` 的参数是 `filelist`，不是 `file_ids`**，且与 `current_dir_fid` 互斥。
- **所有夸克请求必须带 `pr=ucpro&fr=pc&uc_param_str=`**，少一个写接口就 401。
- **写接口走 `drive.quark.cn`，读接口走 `drive-h.quark.cn`**。
- **Git Bash 下 `/` 开头的路径参数要加 `MSYS_NO_PATHCONV=1`**，否则被改写成 Windows 路径。
- 转存失败会回退成逐个文件转；若仍失败，先跑 `probe_share.py <id>` 确认分享本身没失效。

---

## 工具清单

全部在 `<skill>\scripts` 下，随 skill 一起走，零依赖：

| 命令 | 用途 |
|:--|:--|
| `get.py <链接> [--name] [--pick] [--dir] [--dry]` | **主入口**：转存 + 自动归档 + 记账 |
| `weibo.py search/user/show/check` | 微博搜帖、看搬运号更新、挖帖子里的真实网盘直链 |
| `probe_share.py <id>` | 只读：列分享里有什么、多大 |
| `quark_save.py <id> <关键词> <目录>` | 只要分享里某几个文件（`--all` 全要） |
| `quark_dir.py ls/mkdir/move/rm` | 网盘目录操作（`rm` 必须 `--yes`） |
| `res.py list/check/add/set/rm` | 台账：看记录、验链接死活、增删改 |
| `sync_library.py` | 把台账刷成 `references/resource-library.md` 快照 |
| `check_env.py` | 环境自检，开工前先跑 |

skill 根目录还有两个维护入口（不对日常业务）：

| 命令 | 用途 |
|:--|:--|
| `install.py [--force]` | 把 skill 装到 `~/.workbuddy/skills/` 并引导配 cookie |
| `pack.py [--no-data]` | 打成可分发 zip（`dist/`，不含凭据） |

用户问「之前找的那部剧还在吗」「链接还有效吗」→ 跑 `res.py check`；
问「我都有哪些资源」→ 读 `references/resource-library.md`。

---

## 使用边界

仅用于个人观看。不要批量抓取整站、不要高频轮询博主、不要把转存内容再分发或商用——
既会触发风控导致账号受限，也超出用户的实际需求。

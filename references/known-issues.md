# 已知问题与接口细节

排查时看这里。都是实测踩出来的，报错原文一并保留。

---

## 一、夸克接口

### 端点清单

```
读 - 分享 token    POST drive-h.quark.cn /1/clouddrive/share/sharepage/token
                     {pwd_id, passcode:"", support_visit_limit_private_share:true}
读 - 分享内容      GET  drive-h.quark.cn /1/clouddrive/share/sharepage/detail
                     ?pwd_id&stoken&pdir_fid&force=0&_page=1&_size=200&_fetch_total=1
写 - 转存          POST drive.quark.cn   /1/clouddrive/share/sharepage/save
                     {fid_list, fid_token_list, to_pdir_fid, pwd_id, stoken,
                      pdir_fid:"0", scene:"link"}      → task_id
读 - 我的目录      GET  drive-pc.quark.cn /1/clouddrive/file/sort
                     ?pdir_fid&_page=1&_size=200&_fetch_total=1&_sort=file_type:asc,file_name:asc
写 - 建目录        POST drive-pc.quark.cn /1/clouddrive/file
                     {pdir_fid, file_name, dir_path:"", dir_init_lock:false}  → data.fid
写 - 移动          POST drive-pc.quark.cn /1/clouddrive/file/move
                     {filelist:[...], to_pdir_fid}     → task_id
写 - 删除          POST drive-pc.quark.cn /1/clouddrive/file/delete
                     {filelist:[...]}                  → task_id
读 - 任务          GET  drive-h.quark.cn /1/clouddrive/task?task_id&retry_index
                     status: 0/1=进行中, 2=完成, 3=失败
```

**所有请求都要带** `pr=ucpro&fr=pc&uc_param_str=`，拼在 query 上。

### 坑 1：写接口 401 `require login [guest]`

```json
{"status":401,"code":31001,"message":"require login [guest]"}
```

cookie 完全有效（读接口正常），原因是缺 `pr=ucpro&fr=pc&uc_param_str=`。
补上立刻 200。不要误判成 cookie 过期去重新扫码。

### 坑 2：save 的 stoken 不能留空

`stoken` 必须用 token 接口取回的那个值原样传回去。留空或自己编 → 401。

### 坑 3：读 `drive-h`，写 `drive.quark.cn`

读接口在 `drive-h.quark.cn`，写接口（save）在 `drive.quark.cn`。
`file/*` 系列在 `drive-pc.quark.cn`。混用会 404 或 401。

### 坑 4：`file/move` 的参数名是 `filelist`

| 传法 | 结果 |
|:--|:--|
| `{"file_ids":[...]}` | 400 `[current_dir_fid,filelist 不能同时为空]` |
| `{"filelist":[...], "current_dir_fid":"..."}` | 400 `[current_dir_fid,filelist 不能同时存在值]` |
| `{"filelist":"[\"fid\"]"}`（字符串） | 500 `inner error` |
| `{"filelist":["fid"], "to_pdir_fid":"目标"}` | **200 + task_id** ✅ |

`filelist` 和 `current_dir_fid` 是**互斥**的，二选一。移动文件只传 `filelist`。

### 坑 5：`file/delete` 不能带 action_type

只传 `{"filelist":["fid"]}` → 200 + task_id。
加 `action_type:1` → 400 `[文件已经删除,请稍后重试]`（看着像失败，其实第一次已成功）。

### 坑 6：转存整个文件夹是可行的

`fid_list` 里放**目录的 fid**（配目录的 `share_fid_token`），
夸克会在 `to_pdir_fid` 下建成同名文件夹，内部结构完整保留。
不需要"建目录 + 逐个转文件"两步。

### 坑 7：转存后多出 `xxx(1)`

把目录本身转存到已有同名目录的父目录时，夸克不会合并，会建 `xxx(1)`。
所以转存前必须先在父目录里按名字查一遍，存在就复用其 fid。

### 坑 8：目录 fid 是稳定的

`/00影视-待看` 的 fid 一直是 `21c9248a39b44b9d814aa2ca72605220`，
`/00影视-待看/午夜规则` 是 `f1b014684813434eb5a331284c0a88aa`。
但不要写死，用 `quark_dir.py ls` 或 `get.py` 的 `resolve()` 现场解析。

---

## 二、授权凭据

cookie 只从两处取，先命中先用：

1. 环境变量 `QUARK_COOKIE`
2. 配置文件 `~/.workbuddy/media-fetch.json` 的 `quark_cookie`

没有第三种来源。获取方式只有一种可靠的：浏览器登录 `pan.quark.cn` →
F12 → Network → 任一请求 → 复制整串 `Cookie`。

### 坑 9：cookie 失效表现为 401，但 401 不一定是失效

```
{"status":401,"code":31001,"message":"require login [guest]"}
```

先确认请求带了 `pr=ucpro&fr=pc&uc_param_str=`（脚本已统一带上）。参数齐了还 401，
才是真的过期。

容易误判的地方：**读接口此时往往还能用**，只有写接口报 401。所以"能列目录"
不等于"能转存"。`check_env.py` 用读接口探测，只能证明授权没完全失效。

---

## 三、微博与短链

### 坑 10：微博接口全要登录态

```
GET https://m.weibo.cn/api/container/getIndex?...
  → 302  location: https://visitor.passport.weibo.cn/visitor/visitor?...
GET https://s.weibo.com/weibo?q=...
  → 302
```

**绕法**：`https://www.sina.cn/media/<uid>` 是静态 HTML 全文流，免登录可直接抓。
返回内容里带发布时间、正文、`t.cn` 短链。

### 坑 11：短链解析要指定移动端 UA

```bash
curl -s --noproxy '*' -o /dev/null -w "%{redirect_url}" \
  -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)" \
  "http://t.cn/xxxxx"
```

不带动移动 UA 有时不跳转。`--noproxy '*'` 必须加。

### 坑 12：微博分享寿命约 6 天

| 分享 | 发布 | 失效 |
|:--|:--|:--|
| `235ed3b887f4` | 2026-10-25 | 2026-10-31 |
| `0c220e4f0c37` | 2026-10-31 | 2026-11-06 |

都是第 6 天 token 404。**看到就转，别存链接。**

---

## 四、资源来源现状（2026-11 实测）

| 来源 | 要什么 | 能给夸克链接 | 结论 |
|:--|:--|:--|:--|
| **微博镜像页** `sina.cn/media/<uid>` | 无 | ✅ | 快，但有 1–2 天延迟。`2265615342` 在 2026-11-06 后停更，需换号 |
| **资源站** `box.jiugeku.com/search` | 无 | ✅ | 当天期数就有；HTML 里直接是 `pan.quark.cn` 直链，不用登录、不用解短链。**但当天集可能延后数小时才收录** |
| 小雅索引 | 无 | 部分 | 31.7 万部，但夸克只覆盖 58 个合集，新剧基本没有 |
| PanSou | 需自建 | ✅ | 公共实例全部失效（502/404） |
| UIndex / 海盗湾 | 无 | ❌ 只有磁力 | 能出结果，但必须下载再上传 |
| HDHive / HDHaven | 账号 / 积分 | ✅ | 未验证 |
| SeedHub | 无 | ❌ | Cloudflare 403 |
| AnimeGarden | 无 | ❌ | 番剧专用，搜电影必然 0 条 |

**结论**：免账号就能拿到夸克直链的只有两条——微博镜像页（快，但有 1–2 天延迟）
和资源站（当天期数就有）。小雅对新片无效，公共网盘搜索引擎大多已死。
两者互补：微博先试，没有就上资源站。

---

## 五、Windows 环境

### 坑 13：Git Bash 路径转换

以 `/` 开头的参数会被 Git Bash 当 Windows 路径转换：

```
--saved "/00影视-待看/xxx"  →  "D:/work/code_tools/.../00影视-待看/xxx"
```

加 `MSYS_NO_PATHCONV=1` 前缀。PowerShell 没有这个问题。

### 坑 14：系统代理

本机有代理环境变量时，脚本请求会被拦。所有 urllib 请求统一用
`build_opener(ProxyHandler({}))` 绕过；curl 用 `--noproxy '*'`。

---

## 六、版本辨识与时序

### 坑 15：抢发的「占位压缩版」

2026-11-22 实测《现在就出发》第 7 期下（12:00 播出）：

| 时间 | 现象 |
|:--|:--|
| 12:11 | 第一批帖出现，`20261122.第7期下.mp4` **906M** |
| 12:12 | 该文件 `created_at`，说明是刚建的 |
| 12:24 | 抽查 8 个不同分享，体积全是 **906/907M** |
| 16:20 | 真正的 4K 出现：`第7期下-4K60帧极清.mp4` **3.85G** |

**多个分享体积一致 ≠ 文件完整**，只能说明它们互转同一个源头。

判据（照这个判断，别问用户）：

- **和同系列比**。同分享里第 7 期上 4K 是 2.7G、第 6 期下 4K 是 4.39G，
  906M 不足 1/5 → 不完整或极低码率，不转。
- **看时间点**。播出后 1-2 小时内出现的大体积文件基本不可信。
- **看命名**。正规 4K 会带 `4K` / `2160p` / `60帧`；只有日期+期数的多为压缩转码。

### 坑 16：4K 的产出时间窗

同档综艺连续两期实测：

| 期 | 播出 | 4K 出现 | 间隔 |
|:--|:--|:--|:--|
| 第 6 期上 | 11-14 12:00 | 16:10 | 4h10m |
| 第 7 期下 | 11-22 12:00 | 16:20 | 4h20m |

规律：**中午播出的节目，4K 要等 15:00–16:30**。这之前的帖只有 906M–1.8G。

处理策略二选一：

1. **等**——15:30 之后一次找齐，目录里不会混入压缩版
2. **先收再升级**——立刻转压缩版让用户有得看，同时
   `watch.py pending-add` 记一笔，自动任务下次优先找 4K，转完删旧文件
   （`quark_dir.py rm "<路径>/<旧文件>" --yes` 现在支持删单个文件）

两种都可以，但要**明确告诉用户当前是哪种规格**，不要说「已更新」就完事。

### 识别「标题党」分享

2026-11-21 实测：某帖标题写「第7期**4K高码**」，`probe_share.py` 一看分享里
只有 1.8G 的 1080p。**标题不作数，只认 `probe_share.py` 输出里的实际体积**。


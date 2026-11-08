# 安装 / 分发 / 迁移

这个 skill 是**独立单元**：代码、数据、文档都在自己目录内，
只依赖 Python 3.8+ 标准库 + 一个夸克 cookie。

> **第一次在别人的机器上装？** 看 [`INSTALL.md`](INSTALL.md)——
> 那里有装 Python、放目录、取 cookie、让 WorkBuddy 识别的逐步指引。
> 本文档是给维护者看的：怎么打包、怎么迁移、数据放哪。

---

## 一、目标机器需要什么

| 项 | 要求 | 说明 |
|:--|:--|:--|
| **Python** | **3.9 或更高** | 只用标准库，不装任何包。`python --version` 确认 |
| **夸克网盘账号** | 能登录 `pan.quark.cn` | 需要一个 cookie |
| **微博账号**（可选） | 能登录 `weibo.com` | 配了才能用 `weibo.py` 搜帖；不配就只能靠资源站 |
| **目标目录** | 默认 `/00影视-待看` | 不存在会自动建；想换用 `--dir` |
| 网络 | 能访问 `pan.quark.cn` / `sina.cn` | 脚本已自动绕系统代理 |

**不需要**：任何外部软件、Docker、Node、第三方 Python 库。

---

## 二、在这台机器上打包

```powershell
cd "$env:USERPROFILE\.workbuddy\skills\media-resource-fetch"
python pack.py                # 含台账数据
python pack.py --no-data      # 不带历史记录（干净分发给别人）
```

产物在 `dist\`：

```
media-resource-fetch-<版本>.zip
media-resource-fetch-<版本>.zip.sha256
```

约 53 KB。**不含 cookie、不含缓存**——cookie 在
`~/.workbuddy/media-fetch.json`，本来就在 skill 目录外。

---

## 三、在目标机器安装

解压后进入 `media-resource-fetch` 目录：

```powershell
python install.py
```

它会自动：

1. 复制到 `~/.workbuddy/skills/media-resource-fetch`
2. 检查是否已配 cookie（没配就打印获取步骤）
3. 跑 `check_env.py` 自检

已有旧版本时加 `--force`，会先备份成 `media-resource-fetch.bak-<时间戳>`。

> 如果当前目录**就是**安装位置（已经放对了），`install.py` 只做检查，不会自我复制。

---

## 四、配置夸克授权（二选一）

### 方式 A · 配置文件（推荐，长期有效）

1. 浏览器登录 `https://pan.quark.cn`
2. F12 → Network → 刷新页面 → 点任意请求
3. Request Headers 里找 `Cookie:`，复制**整串**
4. 新建 `~/.workbuddy/media-fetch.json`：

```json
{
  "quark_cookie": "粘贴整串 Cookie"
}
```

UTF-8 编码，JSON 格式。Windows 上是
`C:\Users\<用户名>\.workbuddy\media-fetch.json`。

### 方式 B · 环境变量（临时 / 多账号切换）

```powershell
$env:QUARK_COOKIE = "粘贴整串 Cookie"
```

只在当前终端有效。

> 优先级：环境变量 → 配置文件。没有第三种来源，脚本不会去翻别处。

### 可选 · 微博授权（要用 weibo.py 搜帖才配）

只要两个字段，不需要整串 Cookie：

1. 浏览器登录 `https://weibo.com`
2. F12 → **Application → Cookies → `https://weibo.com`**
3. 取 **Domain 为 `.weibo.com`** 的 `SUB` 和 `SUBP` 的 Value
4. 追加进同一个 `media-fetch.json`：

```json
{
  "quark_cookie": "……",
  "weibo_cookie": "SUB=粘贴SUB; SUBP=粘贴SUBP"
}
```

注意 **`m.weibo.cn` 不认这份凭据**（`api/config` 会返回 `login:false`），
搜索走的是 `weibo.com/ajax/statuses/search`，别在 m 站上试。

验证：`python weibo.py check` 打印「搜索接口 OK」即通。

### 千万不要拷这个文件

`media-fetch.json` 等价于网盘登录态。**分发 skill 时不要带上它**，
每台机器单独配一次。`pack.py` 已经天然排除（它不在 skill 目录内）。

---

## 五、验证（三步）

```powershell
cd "$env:USERPROFILE\.workbuddy\skills\media-resource-fetch\scripts"

python check_env.py               # 1. 自检，六节全 [OK]
python res.py list                # 2. 看台账（新机器为空也正常）
python get.py <分享id> --dry      # 3. 预演一次转存
```

`check_env.py` 最后打印 `全部就绪，可以直接用 get.py 找片转存。` 才算成功。

---

## 六、数据放哪

| 项 | 位置 | 能否改 |
|:--|:--|:--|
| 台账 `resources.jsonl` | `<skill>\data\` | 环境变量 `MEDIA_FETCH_DATA` |
| 资源库快照 | `<skill>\references\resource-library.md` | 由台账渲染，不要手改 |
| cookie | `~/.workbuddy/media-fetch.json` | 环境变量 `MEDIA_FETCH_CONFIG` 可改路径 |

想把台账放到网盘同步目录、多台机器共用：

```powershell
$env:MEDIA_FETCH_DATA = "D:\我的影视台账"
```

---

## 七、常见问题

**Q: 提示「找不到夸克授权」**
按第四节配一次。脚本只认环境变量与配置文件两处。

**Q: 之前能用，现在 401 / code=31001**
cookie 过期了。重新复制一次。注意 401 也可能是缺 `pr=ucpro&fr=pc`
参数，但脚本已统一带上，所以大概率就是过期。

**Q: 公司网络下连不上**
所有请求已 `ProxyHandler({})` 绕过系统代理。若仍需走代理，
改 `scripts/mplib.py` 里的 `OPENER`。

**Q: 路径带中文报错**
Git Bash 下 `/` 开头的参数要加 `MSYS_NO_PATHCONV=1`，PowerShell 无此问题。

**Q: 想改版本号**
编辑 skill 根目录的 `VERSION`，`pack.py` 会用它命名产物。

---

## 八、一句话总结

**`python pack.py` 打包 → 解压 → `python install.py` → 配 cookie。**

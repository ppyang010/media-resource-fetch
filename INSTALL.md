# 从零上手（新机器 / 新 WorkBuddy）

给**手上只有仓库地址或一个 zip、机器上什么都没有**的人。
按顺序做完大约 10 分钟。已有环境的人可以直接跳到第 4 步。

> 只想看接口细节和踩坑记录？看 `MIGRATION.md`（打包/迁移）和
> `references/known-issues.md`（接口参数、报错原文）。

---

## 第 1 步 · 先看现状

**Windows（PowerShell）**

```powershell
python --version
git --version
Test-Path "$env:USERPROFILE\.workbuddy"
```

**macOS / Linux**

```bash
python3 --version
git --version
ls -d ~/.workbuddy
```

| 结果 | 含义 |
|:--|:--|
| 打印 `Python 3.8.x` 或更高 | 够用，跳到第 3 步 |
| 报「不是内部或外部命令」/ `command not found` | 没装，做第 2 步 |
| `git` 没有 | 不影响，第 3 步改用 zip 方式 |
| `.workbuddy` 不存在 | 说明这台机器还没用过 WorkBuddy，先装 WorkBuddy 并运行一次，它才会建这个目录 |

---

## 第 2 步 · 装 Python（只在缺了时做）

只用标准库，**不需要 pip install 任何东西**，所以装个干净的官方 Python 就行。

**Windows**

```powershell
winget install -e --id Python.Python.3.12
```

装完**关掉终端重开**，再 `python --version` 确认。

> 坑：如果输入 `python` 弹出 Microsoft Store，说明是系统的占位符。
> 去「设置 → 应用 → 应用执行别名」把 `python.exe` / `python3.exe` 两个开关关掉，
> 或者直接用完整路径调用。

**macOS**

```bash
brew install python@3.12
# 没装 Homebrew 的话：/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Linux（Debian/Ubuntu）**

```bash
sudo apt update && sudo apt install -y python3
```

> 3.8 也能跑（脚本都开了 `from __future__ import annotations`），
> 但最低限度别低于 3.8。

---

## 第 3 步 · 把 skill 放进 WorkBuddy 的 skill 目录

目录位置是固定的，WorkBuddy 只从这儿读：

| 系统 | 路径 |
|:--|:--|
| Windows | `C:\Users\<用户名>\.workbuddy\skills\` |
| macOS / Linux | `~/.workbuddy/skills/` |

**方式 A · git clone（推荐，能 `git pull` 更新）**

```bash
cd ~/.workbuddy/skills
git clone https://github.com/ppyang010/media-resource-fetch.git
```

Windows PowerShell 对应：

```powershell
cd "$env:USERPROFILE\.workbuddy\skills"
git clone https://github.com/ppyang010/media-resource-fetch.git
```

**方式 B · zip（不用装 git）**

从 Release 页下载 `media-resource-fetch-<版本>.zip`，解压后把**里面的
`media-resource-fetch` 文件夹**整个移到 `~/.workbuddy/skills/` 下。

> 检查点：`~/.workbuddy/skills/media-resource-fetch/SKILL.md` 必须能直接打开。
> 目录名不能改，也不能多套一层（变成 `media-resource-fetch/media-resource-fetch/` 就找不到）。

---

## 第 4 步 · 安装 + 自检

```bash
cd ~/.workbuddy/skills/media-resource-fetch
python install.py
```

它会做三件事：确认目录位置对 → 检查有没有配 cookie → 跑一次环境自检。

此时自检**第 4、5 节会报错**（还没配 cookie），这是正常的，做完第 5 步再跑一次。

单独跑自检：

```bash
cd scripts
python check_env.py
```

六节全 `[OK]`、最后一句是 `全部就绪，可以直接用 get.py 找片转存。`，才算通了。

---

## 第 5 步 · 配夸克 cookie（必须）

没有它，转存一律失败（写接口返回 `401 code:31001 require login [guest]`）。

1. 浏览器打开 `https://pan.quark.cn` 并**确保已登录**（能看到自己的网盘文件）
2. 按 `F12` 打开开发者工具
3. 切到 **Network（网络）** 面板
4. 按 `Ctrl+R` 刷新页面
5. 在请求列表里点**任意一条**发往 `drive-pc.quark.cn` 或 `drive.quark.cn` 的请求
6. 右侧 **Headers → Request Headers → `Cookie:`**
7. 右键 → **Copy value**，得到一整串 `__pus=...; __puus=...; ...`

然后创建配置文件：

**Windows**

```powershell
notepad "$env:USERPROFILE\.workbuddy\media-fetch.json"
```

**macOS / Linux**

```bash
nano ~/.workbuddy/media-fetch.json
```

内容：

```json
{
  "quark_cookie": "这里粘贴那一整串",
  "default_dir": "/00影视-待看"
}
```

保存为 **UTF-8**。cookie 本身只含字母数字和符号，不含双引号，可以直接粘进字符串里。

验证：

```powershell
python check_env.py
# 第 4 节：[OK] 来自配置文件 ...media-fetch.json
# 第 5 节：[OK] 根目录可访问，授权有效
```

> `default_dir` 是这个 skill 往你网盘里放东西的目录，不存在会自动创建。
> 想换位置就改这里，或每次命令加 `--dir`。

---

## 第 6 步 · 配微博 cookie（可选，但强烈建议）

配了才能用 `weibo.py` 直接搜帖。实测**当天更新能提前 6~8 小时拿到资源**——
资源站通常要等几小时，微博搬运号在播出后十几分钟就发。

1. 浏览器打开 `https://weibo.com` 并**确保已登录**
2. `F12` → **Application（应用）** → 左侧 **Cookies** → `https://weibo.com`
3. 在列表里找 **`SUB`** 和 **`SUBP`** 两行，双击 **Value** 单元格复制值
   （同名有多个时，取 **Domain 为 `.weibo.com`** 的那个）
4. 追加进同一个 `media-fetch.json`：

```json
{
  "quark_cookie": "……",
  "default_dir": "/00影视-待看",
  "weibo_cookie": "SUB=你复制的SUB值; SUBP=你复制的SUBP值"
}
```

验证：

```powershell
cd scripts
python weibo.py check
# cookie：SUB=_2A25H9BpSDe…（共 229 字符，SUB+SUBP 齐全）
# 搜索接口 OK，返回 50 条，最新一条：11-08 20:36
```

> **必须知道的两件事**
> 1. `SUB` 是 HttpOnly，浏览器控制台敲 `document.cookie` **取不到**，只能从
>    Application 面板或 Network 请求头拿。
> 2. `m.weibo.cn` **不认** weibo.com 的 cookie（`api/config` 返回 `login:false`）。
>    本 skill 走的是 `weibo.com/ajax/statuses/search`，别拿 m 站的报错当失败。

---

## 第 7 步 · 在 WorkBuddy 里跑通第一次

skill 是给 agent 读的说明书，装完要让 WorkBuddy 重新加载一次：

1. **重启 WorkBuddy**（或新开一个会话）
2. 直接说一句自然语言，例如：
   - 「找一下《现在就出发 第四季》最新一期，转存到我网盘」
   - 「《XX》有资源吗」
   - 「把这个夸克分享转存到网盘 https://pan.quark.cn/s/xxxx」

它会自己去读 `SKILL.md`、先查资源库、再找链接、`--dry` 预演、转存、写台账。

**如果它没反应 / 说找不到这个能力**，按顺序查：

| 检查 | 做法 |
|:--|:--|
| 目录名对吗 | 必须是 `~/.workbuddy/skills/media-resource-fetch/` |
| `SKILL.md` 在根目录吗 | 不是子目录里 |
| 重启过吗 | skill 列表在启动时扫描 |
| 要不要手动确认 | 有些版本需要在 skill 管理里启用，看一眼列表里有没有它 |

---

## 第 8 步 · 以后怎么更新

```bash
cd ~/.workbuddy/skills/media-resource-fetch
git pull
```

代码是纯 Python，不要编译、不要重装依赖。有版本升级时 `VERSION` 会变，
可以顺便看一眼 Release 说明改了什么。

用 zip 装的：重新下 zip 覆盖，或改用 git clone 一次。

---

## 第 9 步 · 想卸载

```bash
rm -rf ~/.workbuddy/skills/media-resource-fetch
rm ~/.workbuddy/media-fetch.json     # 凭据，删了就彻底断开
```

Windows 用 `Remove-Item -Recurse -Force` 对应删除。
**网盘里已经转存的文件不受影响**，skill 只是搬文件，不管删除。

---

## 常见问题

**Q: `python` 命令不存在，但明明装了**
PATH 没生效。关掉终端重开；或直接用完整路径（Windows 常见位置
`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`）。

**Q: 报 `找不到夸克授权`**
只认两个来源：环境变量 `QUARK_COOKIE`、配置文件 `~/.workbuddy/media-fetch.json`。
注意文件名是 `media-fetch.json`，不是 `mcp.json`，也不在 skill 目录里。

**Q: 昨天还能用，今天 401 / code=31001**
cookie 过期。重新做第 5 步。夸克的 cookie 一般能撑几周。

**Q: 微博搜出来一堆资讯号，没有网盘链**
用 `--quark` 过滤：`python weibo.py search "剧名" --quark`。
另外搬运号常把链接放评论区，而评论接口会「过滤部分评论」，
所以优先挑正文带「网页链接」的帖子。

**Q: 路径带中文报错（Git Bash）**
`/` 开头的参数会被 MSYS 改写成 Windows 路径，前面加 `MSYS_NO_PATHCONV=1`。
PowerShell 没这个问题。

**Q: 公司网络连不上**
脚本已用 `ProxyHandler({})` 绕过系统代理（本机代理反而会拦）。
若确实需要走代理，改 `scripts/mplib.py` 里的 `OPENER`。

**Q: 能不能多台机器共用一个台账**
可以，设 `MEDIA_FETCH_DATA` 指向网盘同步目录：

```powershell
$env:MEDIA_FETCH_DATA = "D:\我的影视台账"
```

---

## 一句话总结

**装 Python → clone 到 `~/.workbuddy/skills/` → `python install.py` →
配 `media-fetch.json` 里的 quark_cookie（可选加 weibo_cookie）→ 重启 WorkBuddy。**

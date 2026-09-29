# Camoufox 身份启动器（Windows MVP）

纯本地的两页身份启动器：身份列表与身份编辑。每个身份使用独立的 Camoufox 持久化目录。程序不需要账户，也没有广告、遥测或云同步。

## 安装与启动

1. 安装 Windows 版 Python 3.11 或更新版本，确保带有 Tkinter。当前开发验证使用 Python 3.12。
2. 双击 [setup.cmd](setup.cmd)。它会建立 `.venv`、安装依赖并下载 Camoufox Windows 浏览器及 GeoIP 数据。`setup.ps1` 是内部脚本；直接运行可能被 Windows PowerShell 的执行策略拦截。
3. 双击 [start.cmd](start.cmd)，或运行 `.\.venv\Scripts\python.exe run.py` 查看控制台错误。

浏览器在 Windows 原生进程中运行。脚本不设置固定屏幕尺寸、DPR、Windows 缩放比例或 `--force-device-scale-factor`；GUI 声明 Per-Monitor DPI 感知，浏览器使用自身的原生窗口处理。无需 WSL。

## 使用

在身份列表中点击“新建身份”，填写名称及可选代理。代理类型支持 HTTP、HTTPS、SOCKS5；主机只填域名或 IP，端口单独填写。点击“测试代理”可检查代理连通性并查看出口 IP；点击“按 IP 自动填充”则会继续用 Camoufox 的本地 GeoIP 数据填充国家/地区、时区、语言及经纬度。连接、认证和超时问题会分别提示。定位失败时所有地理字段都可手动填写。确认后保存、启动。

代理或凭据修改后，地理字段会清空，需重新定位或手动填写。代理出口变更后也应重新定位。无代理时，“按 IP 自动填充”使用本机公网出口。

关闭浏览器窗口或点击“停止”后，身份目录保留。启动器会在身份目录内额外保存会话 Cookie，并记录打开的 HTTP/HTTPS 标签页；下次启动时会恢复这些标签页。长期 Cookie、缓存和 LocalStorage 由 Camoufox 浏览器目录保存。身份列表底部会显示当前选用的 Camoufox 浏览器版本和发布渠道。

## 本地数据

所有身份配置、Profile 数据和应用日志位于 `%LOCALAPPDATA%\CamoufoxIdentityLauncher\`：

```text
CamoufoxIdentityLauncher/
  identities.json          身份配置；代理密码由 Windows DPAPI 加密
  profiles/<身份 ID>/     Cookie、缓存、LocalStorage、会话 Cookie、标签页列表等
  logs/launcher.log        轮转运行日志，只记录身份 ID 和事件/错误类型
```

可备份整个目录。DPAPI 加密的代理密码只可由原 Windows 用户解密；跨用户或跨电脑恢复时需重新填写密码。删除身份会删除对应 Profile。Camoufox 浏览器程序和 GeoIP 数据由 Camoufox 自身缓存管理，不在上述身份数据目录中。

自动定位会向 `api.ipify.org`（失败时 `checkip.amazonaws.com`）请求出口 IP；有代理时请求走该代理。GeoIP 计算使用 Camoufox 下载的本地数据库。程序没有自己的服务器或同步服务。

## 测试

在已完成安装的 Windows 环境运行：

```powershell
.\.venv\Scripts\python.exe -m tests.smoke_windows
.\.venv\Scripts\python.exe -m tests.smoke_geo
.\.venv\Scripts\python.exe -m tests.smoke_socks_relay
.\.venv\Scripts\python.exe -m tests.smoke_launcher
.\.venv\Scripts\python.exe -m tests.smoke_stale_active
```

本机结果及未完成的验收项见 [TEST_RESULTS.md](TEST_RESULTS.md)。

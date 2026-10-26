# 180题分包阅读试验

本目录是 `pilot/packed-reader-180` 分支的试验结果。`main` 和 `baseline-20261027` 保存重构前的完整题库。本轮不替换 `D:\高中化学\题库首页.html`，不修改资料层。

完整基线的Windows长路径恢复：建议使用较短的检出目录，并在克隆时设置 `git -c core.longpaths=true clone https://github.com/justlaughing/high-school-chemistry.git`；在仓库内设置 `git config core.longpaths true`，再按需检出 `baseline-20261027`。恢复校验脚本本身已支持长路径。

## 使用

在本机双击 `启动试验.cmd`。默认服务为 `http://127.0.0.1:8796/`，只监听本机；关闭服务窗口即停止。端口被占用时可运行 `python serve.py --port 8798`。

试验版通过本机服务读取二进制资源包，不支持直接双击 `reading/index.html`。原正式首页的离线双击阅读方式保留。

## 文件组织

- `sample.json` 固定9个批次各20题，主模块、图片、MathML、表格和小问都有覆盖，保留批次和原题号。
- `reading/` 是独立的静态阅读版，可整体复制到静态服务。只需要此目录，不需要原题HTML、分类工作区、Python或原Word/PDF。
- `reading/questions/` 按“批次哈希＋原题号哈希首位”固定分组，保持题号稳定，不依赖知识点目录位置。
- `reading/assets/` 按原始图片的SHA-256首位固定分成16包，内容去重；`asset-index.json` 记录每张图片的偏移、长度和格式。图片保持原始字节，浏览器对读取字节再次校验SHA-256。
- `styles.json` 共享重复样式，`reader.html` 和 `packed.js` 为共享阅读器。题干、表格和MathML继续使用原HTML内容。
- `manifest.json` 记录每个阅读文件的大小和哈希；浏览器使用文件哈希作为请求版本，避免更换内容后沿用旧缓存。
- `build.py`、`verify.py`、`qa/` 与报告保留在维护目录，不进入阅读版。

资源服务支持HTTP Range时按图片字节读取；不支持时回退到整包读取，并在本次浏览中复用。回退方式会增加首次阅读的传输量，公网速度需在目标服务上另测。来源名称和核对信息保留，打开本地原Word/PDF仍需要本机原资料。

## 重建与校验

在完整仓库内执行 `python pilot/build.py`。构建只读取已固定的样本，不重写相同内容。执行 `python pilot/verify.py` 核对产物及3118张去重图片，验证不变重建、单题内容变更和恢复；原题库输入不被修改。

浏览器核验使用 `python pilot/serve.py --qa`，打开 `/__qa__/index.html`。此模式额外提供工作副本的原题资源作对照，且只把结果写入 `browser-qa.json`；普通阅读服务不提供这些调试入口。

体积比较以同样180题的原HTML和实际引用图片为基准；阅读版数字包括共享界面、全文搜索目录、资源索引及清单。不能把这组样本的结果直接当成全量题库或公网同步的实测结果。

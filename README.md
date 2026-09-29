# WorkBuddy + WeChatRSS + IMA：公众号文章每日入库实践

一套按天运行的实践流程：从 WeChatRSS 获取订阅公众号的新文章，用 WorkBuddy 在本地定时运行增量脚本，再通过 IMA OpenAPI 将文章链接导入指定知识库。

**文章预览：**[打开图文预览](article/index.html)  
**文章正文：**[Markdown 版本](article/WeChatRSS_WorkBuddy_IMA.md)  
**示例脚本：**[wechatrss_to_ima_example.py](scripts/wechatrss_to_ima_example.py)

## 流程

~~~text
WeChatRSS 合并 RSS
        ↓
WorkBuddy 本地定时任务
        ↓
解析文章 URL → 按知识库去重 → 每批最多 10 条
        ↓
IMA OpenAPI import_urls
        ↓
成功后更新该知识库的状态文件
~~~

图文素材位于 [article/assets/](article/assets/)；其中 PNG 可用于公众号编辑器，SVG 是便于修改的源文件。WorkBuddy 配置图是教程示意图，不是产品界面截图。

## 前置条件

- 可访问网络的电脑，安装 python3 和 node。
- 可访问本地工作目录的 WorkBuddy 自动化任务。
- WeChatRSS 账号和有效的 RSS token。
- IMA OpenAPI skill 与 client_id、api_key。

## 配置要点

1. 在微信客户端关注目标公众号，并完成 WeChatRSS 客户端同步。
2. 将 WeChatRSS token 设为本地环境变量 WECHATRSS_TOKEN。
3. 将 IMA 凭证保存在本机 ~/.config/ima/client_id 和 ~/.config/ima/api_key，不要放进仓库。
4. 用 IMA 的 search_knowledge_base 按名称查找知识库，并在脚本 KBS 中填入 OpenAPI kb_id。
5. 每个目标知识库单独配置一个去重 JSON 文件。
6. 先手动运行并在 IMA 中确认文章可检索，再设置 WorkBuddy 每日定时。

~~~bash
export WECHATRSS_TOKEN="<your token>"
python3 scripts/wechatrss_to_ima_example.py
~~~

如果 ima_api.cjs 不在脚本默认位置，可设置 IMA_API_CJS 指向实际文件；也可设置 IMA_STATE_DIR 指定状态文件目录。当前示例默认在知识库根目录导入；如果你安装的 IMA skill 要求 folder_id，可按该版本文档将 IMA_IMPORT_ROOT_FOLDER=1 设入本地任务环境，使脚本把知识库根目录 ID 一并传入。

## 去重与失败重试

- 每个知识库各自比较“RSS URL 集合 − 已成功 URL 集合”。
- 每批最多提交 10 个 URL。
- 检查接口顶层 code 和每篇文章的 ret_code。
- 仅成功项写入去重文件；失败项保留给下一次运行重试。

## 安全

- 此仓库不包含真实 token、IMA API key、client ID、知识库 ID 或个人订阅清单。
- 请勿把凭证写进脚本、WorkBuddy 提示词、截图或提交记录。
- .gitignore 已排除本地环境变量文件和同步状态目录。
- 示例脚本和命令仅供参考；接口字段及产品界面可能变化，部署前请核对各服务当前文档。

## 官方入口

- [WeChatRSS](https://wechatrss.waytomaster.com/)
- [WorkBuddy 自动化文档](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Automation-Guide)
- [IMA](https://ima.qq.com)

## 许可

本仓库未附开源许可证。公开可见不代表授予复制、修改或再发布授权；使用其中内容时请尊重作者及第三方权利。

#!/usr/bin/env python3
"""WeChatRSS → IMA 增量导入示例。

使用前：
1. 设置 WECHATRSS_TOKEN；
2. 把 IMA_API_CJS 指向 ima_api.cjs；
3. 在 KBS 中填入通过 search_knowledge_base 得到的 OpenAPI kb_id；
4. 不要把 token、client_id、api_key 写入脚本或日志。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


RSS_BASE = "https://wechatrss.waytomaster.com/api/rss/all?token="
IMA_API_CJS = Path(os.environ.get("IMA_API_CJS", "./ima_api.cjs")).expanduser()
STATE_DIR = Path(os.environ.get("IMA_STATE_DIR", "./state"))

# 示例配置：将 kb_openapi 替换为 search_knowledge_base 返回的 OpenAPI kb_id。
# 多个知识库要分别配置自己的 dedup 文件。
KBS = [
    {
        "name": "知识库 A",
        "kb_openapi": "<OPENAPI_KB_ID>",
        "dedup": STATE_DIR / "kb-a.json",
    },
]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if local_name(child.tag) in names and (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def child_link(node: ET.Element) -> str:
    for child in list(node):
        if local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        if href:
            return href
        if (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def fetch_feed() -> list[dict[str, str]]:
    token = os.environ.get("WECHATRSS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少环境变量 WECHATRSS_TOKEN")

    url = RSS_BASE + urllib.parse.quote(token, safe="")
    request = urllib.request.Request(url, headers={"User-Agent": "WeChatRSS-IMA-Sync/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            xml_bytes = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError("WeChatRSS 返回 401：token 可能已过期") from exc
        raise RuntimeError(f"WeChatRSS HTTP 错误：{exc.code}") from exc

    root = ET.fromstring(xml_bytes)
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in root.iter():
        if local_name(node.tag) not in {"item", "entry"}:
            continue
        link = child_link(node)
        if not link or link in seen:
            continue
        seen.add(link)
        records.append(
            {
                "title": child_text(node, {"title"}),
                "url": link,
                "author": child_text(node, {"author", "creator"}),
                "date": child_text(node, {"pubdate", "published", "updated", "date"}),
            }
        )
    if not records:
        raise RuntimeError("RSS feed 为空：请检查 token、客户端同步状态和微信关注关系")
    return records


def load_state(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp.replace(path)


def import_batch(kb_id: str, urls: list[str]) -> dict:
    body = {"knowledge_base_id": kb_id, "urls": urls}

    # 这份手册验证过的兼容写法默认省略 folder_id，让文章落在根目录。
    # 如果当前 IMA API 明确要求 folder_id，可在 WorkBuddy 环境中设置：
    #   IMA_IMPORT_ROOT_FOLDER=1
    if os.environ.get("IMA_IMPORT_ROOT_FOLDER") == "1":
        body["folder_id"] = kb_id

    completed = subprocess.run(
        ["node", str(IMA_API_CJS), "openapi/wiki/v1/import_urls", json.dumps(body, ensure_ascii=False)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        # 不把 stderr 原样输出，避免第三方错误信息意外包含敏感内容。
        raise RuntimeError("IMA API 调用失败，请查看本地任务日志")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("IMA API 返回内容不是有效 JSON") from exc
    if payload.get("code") != 0:
        raise RuntimeError(f"IMA 业务错误：code={payload.get('code')}")
    return payload.get("data", {})


def main() -> int:
    try:
        feed = fetch_feed()
        total_new = total_success = total_failed = 0

        for kb in KBS:
            kb_id = str(kb["kb_openapi"])
            if kb_id.startswith("<"):
                raise RuntimeError(f"{kb['name']} 尚未填写 OpenAPI kb_id")
            state_path = Path(kb["dedup"])
            state = load_state(state_path)
            pending = [item for item in feed if item["url"] not in state]
            total_new += len(pending)

            for offset in range(0, len(pending), 10):
                batch = pending[offset : offset + 10]
                data = import_batch(kb_id, [item["url"] for item in batch])
                results = data.get("results", {})
                for item in batch:
                    result = results.get(item["url"], {})
                    if str(result.get("ret_code")) != "0":
                        total_failed += 1
                        continue
                    state[item["url"]] = {
                        **item,
                        "source": "WeChatRSS",
                        "saved_at": datetime.now(timezone.utc).isoformat(),
                        "kb": kb["name"],
                        "media_id": result.get("media_id", ""),
                        "method": "import_urls",
                    }
                    total_success += 1
                save_state(state_path, state)

        print(f"同步完成：新增候选 {total_new} 条，成功入库 {total_success} 条，失败 {total_failed} 条。")
        return 0 if total_failed == 0 else 2
    except (OSError, ET.ParseError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"同步失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

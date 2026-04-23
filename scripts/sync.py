#!/usr/bin/env python3
"""
Obsidian-Feishu Sync Script
实现 Obsidian 和飞书文档的双向同步
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
import yaml

# 导入转换器模块
from converter import (
    convert_lark_tables_to_markdown,
    convert_markdown_tables_to_lark,
    process_images_for_obsidian,
    process_images_for_feishu,
)

# 配置路径
OBSIDIAN_VAULT_PATH = Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "ObsidianVault"
SYNC_STATE_PATH = Path.home() / ".hermes" / "obsidian-feishu-sync" / "sync_state.json"
INBOX_DIR = "Inbox"


def log(message: str, level: str = "INFO"):
    """输出日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", file=sys.stderr if level == "ERROR" else sys.stdout)


def load_sync_state() -> dict:
    """加载同步状态"""
    if not SYNC_STATE_PATH.exists():
        return {}
    try:
        with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"加载同步状态失败: {e}", "ERROR")
        return {}


def save_sync_state(state: dict):
    """保存同步状态"""
    SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SYNC_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def compute_hash(content: str) -> str:
    """计算内容哈希"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def extract_doc_id(url: str) -> Optional[str]:
    """从飞书 URL 提取文档 ID"""
    # 支持多种 URL 格式
    patterns = [
        r"/docx/([a-zA-Z0-9]+)",
        r"/docs/([a-zA-Z0-9]+)",
        r"doc_token=([a-zA-Z0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def run_lark_command(args: list) -> tuple[bool, str]:
    """执行 lark-cli 命令"""
    try:
        result = subprocess.run(
            ["lark-cli"] + args,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "命令执行超时"
    except FileNotFoundError:
        return False, "lark-cli 未安装或不在 PATH 中"
    except Exception as e:
        return False, str(e)


def get_feishu_doc_content(doc_id: str) -> tuple[bool, str, str]:
    """获取飞书文档内容，返回 (成功, 标题, 内容)"""
    success, output = run_lark_command([
        "docs", "+fetch", "--doc", doc_id, "--format", "pretty"
    ])
    if not success:
        return False, "", output

    # 解析输出，提取标题和内容
    lines = output.strip().split("\n")
    title = "未命名文档"
    content = output

    # 尝试从第一个标题提取文档标题
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    return True, title, content


def create_feishu_doc(title: str, content: str, folder_token: Optional[str] = None) -> tuple[bool, str]:
    """创建飞书文档，返回 (成功, 文档ID)"""
    args = ["doc", "create", "--title", title]
    if folder_token:
        args.extend(["--folder", folder_token])

    # 先创建文档
    success, output = run_lark_command(args)
    if not success:
        return False, output

    # 从输出提取文档 ID
    doc_id_match = re.search(r"doc[_-]?token[=:]\s*([a-zA-Z0-9]+)", output, re.IGNORECASE)
    if not doc_id_match:
        # 尝试其他格式
        doc_id_match = re.search(r"([a-zA-Z0-9]{20,})", output)

    if not doc_id_match:
        return False, "无法从创建结果中提取文档 ID"

    doc_id = doc_id_match.group(1)

    # 更新文档内容
    if content:
        success, err = update_feishu_doc(doc_id, content)
        if not success:
            return False, f"创建文档成功但内容更新失败: {err}"

    return True, doc_id


def update_feishu_doc(doc_id: str, content: str) -> tuple[bool, str]:
    """更新飞书文档内容"""
    # 使用临时文件传递内容
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    try:
        success, output = run_lark_command([
            "doc", "update", doc_id, "--file", temp_path, "--format", "markdown"
        ])
        return success, output
    finally:
        os.unlink(temp_path)


def read_obsidian_file(path: str) -> tuple[bool, str]:
    """读取 Obsidian 文件内容"""
    full_path = OBSIDIAN_VAULT_PATH / path
    if not full_path.exists():
        return False, f"文件不存在: {path}"
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return True, f.read()
    except IOError as e:
        return False, str(e)


def write_obsidian_file(path: str, content: str) -> tuple[bool, str]:
    """写入 Obsidian 文件"""
    full_path = OBSIDIAN_VAULT_PATH / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, str(full_path)
    except IOError as e:
        return False, str(e)


def get_obsidian_file_mtime(path: str) -> Optional[datetime]:
    """获取 Obsidian 文件修改时间"""
    full_path = OBSIDIAN_VAULT_PATH / path
    if not full_path.exists():
        return None
    mtime = full_path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def find_sync_by_obsidian_path(state: dict, obsidian_path: str) -> Optional[str]:
    """通过 Obsidian 路径查找同步记录"""
    for doc_id, info in state.items():
        if info.get("obsidian_path") == obsidian_path:
            return doc_id
    return None


def find_sync_by_feishu_id(state: dict, feishu_id: str) -> Optional[dict]:
    """通过飞书文档 ID 查找同步记录"""
    return state.get(feishu_id)


# ============== Frontmatter Functions ==============

def parse_frontmatter(content: str) -> Tuple[dict, str]:
    """
    解析 Markdown 文件的 frontmatter。
    返回 (frontmatter_dict, body_content)
    """
    if not content.startswith("---"):
        return {}, content

    # 查找第二个 ---
    end_match = re.search(r'\n---\s*\n', content[3:])
    if not end_match:
        return {}, content

    frontmatter_str = content[3:end_match.start() + 3]
    body = content[end_match.end() + 3:]

    try:
        frontmatter = yaml.safe_load(frontmatter_str) or {}
        return frontmatter, body
    except yaml.YAMLError:
        return {}, content


def write_frontmatter(frontmatter: dict, body: str) -> str:
    """
    将 frontmatter 和 body 组合成完整的 Markdown 内容。
    """
    if not frontmatter:
        return body

    frontmatter_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return f"---\n{frontmatter_str}---\n\n{body}"


def update_frontmatter(content: str, updates: dict) -> str:
    """
    更新 Markdown 文件的 frontmatter，保留原有内容。
    """
    frontmatter, body = parse_frontmatter(content)
    frontmatter.update(updates)
    return write_frontmatter(frontmatter, body)


def get_feishu_doc_id_from_frontmatter(content: str) -> Optional[str]:
    """
    从 frontmatter 中提取飞书文档 ID。
    """
    frontmatter, _ = parse_frontmatter(content)
    return frontmatter.get("feishu_doc_id")


def find_sync_by_frontmatter(vault_path: Path = OBSIDIAN_VAULT_PATH) -> dict:
    """
    扫描 vault 中所有 md 文件，读取 frontmatter 中的 feishu_doc_id。
    返回 {feishu_doc_id: {"obsidian_path": path, "feishu_title": title, ...}}
    """
    result = {}

    if not vault_path.exists():
        log(f"Vault 路径不存在: {vault_path}", "ERROR")
        return result

    for md_file in vault_path.rglob("*.md"):
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter, body = parse_frontmatter(content)
            doc_id = frontmatter.get("feishu_doc_id")

            if doc_id:
                # 计算相对路径
                rel_path = str(md_file.relative_to(vault_path))

                result[doc_id] = {
                    "obsidian_path": rel_path,
                    "feishu_title": frontmatter.get("feishu_title", Path(rel_path).stem),
                    "last_sync_time": frontmatter.get("last_sync", ""),
                    "from_frontmatter": True
                }
        except (IOError, UnicodeDecodeError) as e:
            log(f"读取文件失败 {md_file}: {e}", "ERROR")
            continue

    return result


def write_sync_frontmatter(content: str, doc_id: str, title: str) -> str:
    """
    写入同步相关的 frontmatter。
    """
    frontmatter_updates = {
        "feishu_doc_id": doc_id,
        "feishu_title": title,
        "last_sync": datetime.now(timezone.utc).isoformat()
    }
    return update_frontmatter(content, frontmatter_updates)


def sync_from_feishu(url: str, target_path: Optional[str] = None) -> int:
    """从飞书同步到 Obsidian"""
    doc_id = extract_doc_id(url)
    if not doc_id:
        log(f"无法从 URL 提取文档 ID: {url}", "ERROR")
        return 1

    log(f"正在获取飞书文档: {doc_id}")
    success, title, content = get_feishu_doc_content(doc_id)
    if not success:
        log(f"获取飞书文档失败: {title}", "ERROR")
        return 1

    # 转換飛書表格為 Markdown 表格
    log(f"正在转换表格格式...")
    content = convert_lark_tables_to_markdown(content)

    # 處理圖片：下載到 attachments 目錄
    log(f"正在处理图片...")
    content = process_images_for_obsidian(content, doc_id, OBSIDIAN_VAULT_PATH)

    # 确定保存路径
    if not target_path:
        # 清理标题中的非法字符
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        target_path = f"{INBOX_DIR}/{safe_title}.md"

    # 确保路径以 .md 结尾
    if not target_path.endswith(".md"):
        target_path += ".md"

    # 写入 frontmatter
    content_with_frontmatter = write_sync_frontmatter(content, doc_id, title)

    log(f"正在写入 Obsidian: {target_path}")
    success, result = write_obsidian_file(target_path, content_with_frontmatter)
    if not success:
        log(f"写入 Obsidian 失败: {result}", "ERROR")
        return 1

    # 更新同步状态
    state = load_sync_state()
    state[doc_id] = {
        "obsidian_path": target_path,
        "feishu_title": title,
        "last_sync_time": datetime.now(timezone.utc).isoformat(),
        "obsidian_hash": compute_hash(content_with_frontmatter),
        "feishu_hash": compute_hash(content),
        "sync_direction": "bidirectional"
    }
    save_sync_state(state)

    log(f"同步成功!")
    log(f"  飞书文档: {title}")
    log(f"  Obsidian: {target_path}")
    return 0


def sync_to_feishu(obsidian_path: str, create: bool = False, folder_token: Optional[str] = None) -> int:
    """从 Obsidian 同步到飞书"""
    # 读取 Obsidian 文件
    success, content = read_obsidian_file(obsidian_path)
    if not success:
        log(f"读取 Obsidian 文件失败: {content}", "ERROR")
        return 1

    # 解析 frontmatter，提取已有的飞书文档 ID
    frontmatter, body = parse_frontmatter(content)
    existing_doc_id = frontmatter.get("feishu_doc_id")

    # 提取标题
    title = Path(obsidian_path).stem
    for line in body.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    state = load_sync_state()

    # 查找是否已有同步关系（优先使用 frontmatter）
    doc_id = existing_doc_id or find_sync_by_obsidian_path(state, obsidian_path)

    if doc_id:
        # 處理圖片：上傳本地圖片到飛書
        log(f"正在处理图片...")
        body = process_images_for_feishu(body, OBSIDIAN_VAULT_PATH, doc_id)

        # 轉換 Markdown 表格為飛書表格
        log(f"正在转换表格格式...")
        body = convert_markdown_tables_to_lark(body)

        # 更新现有文档
        log(f"正在更新飞书文档: {doc_id}")
        success, err = update_feishu_doc(doc_id, body)
        if not success:
            log(f"更新飞书文档失败: {err}", "ERROR")
            return 1
    elif create:
        # 創建新文檔時，先處理圖片和表格
        log(f"正在处理图片...")
        # 創建時暫時無法上傳圖片（沒有 doc_id），跳過
        log(f"  注意: 创建新文档时图片上传暂不支持，请在创建后再次同步")

        log(f"正在转换表格格式...")
        body = convert_markdown_tables_to_lark(body)

        # 创建新文档
        log(f"正在创建飞书文档: {title}")
        success, doc_id = create_feishu_doc(title, body, folder_token)
        if not success:
            log(f"创建飞书文档失败: {doc_id}", "ERROR")
            return 1
    else:
        log(f"未找到同步关系，使用 --create 创建新文档", "ERROR")
        return 1

    # 更新 Obsidian 文件的 frontmatter
    content_with_frontmatter = write_sync_frontmatter(body, doc_id, title)
    success, result = write_obsidian_file(obsidian_path, content_with_frontmatter)
    if not success:
        log(f"更新 Obsidian frontmatter 失败: {result}", "ERROR")

    # 更新同步状态
    state[doc_id] = {
        "obsidian_path": obsidian_path,
        "feishu_title": title,
        "last_sync_time": datetime.now(timezone.utc).isoformat(),
        "obsidian_hash": compute_hash(content_with_frontmatter),
        "feishu_hash": compute_hash(body),
        "sync_direction": "bidirectional"
    }
    save_sync_state(state)

    log(f"同步成功!")
    log(f"  Obsidian: {obsidian_path}")
    log(f"  飞书文档: {title} ({doc_id})")
    return 0


def sync_status() -> int:
    """显示同步状态"""
    state = load_sync_state()
    frontmatter_syncs = find_sync_by_frontmatter()

    # 合并所有同步关系
    all_doc_ids = set(state.keys()) | set(frontmatter_syncs.keys())

    if not all_doc_ids:
        log("暂无同步关系")
        return 0

    log("=" * 100)
    log(f"{'飞书文档 ID':<20} {'飞书标题':<18} {'Obsidian 路径':<25} {'最后同步':<16} {'FM'}")
    log("-" * 100)

    for doc_id in sorted(all_doc_ids):
        # 优先使用 frontmatter 信息
        if doc_id in frontmatter_syncs:
            fm_info = frontmatter_syncs[doc_id]
            title = fm_info.get("feishu_title", "未知")[:16]
            path = fm_info["obsidian_path"][:23]
            sync_time = fm_info.get("last_sync_time", "")
            has_fm = "✓"
        else:
            info = state.get(doc_id, {})
            title = info.get("feishu_title", "未知")[:16]
            path = info.get("obsidian_path", "未知")[:23]
            sync_time = info.get("last_sync_time", "")
            has_fm = "✗"

        if sync_time:
            try:
                dt = datetime.fromisoformat(sync_time.replace("Z", "+00:00"))
                sync_time = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass
        else:
            sync_time = "未知"

        log(f"{doc_id:<20} {title:<18} {path:<25} {sync_time:<16} {has_fm}")

    log("=" * 100)
    log(f"共 {len(all_doc_ids)} 个同步关系 (FM = frontmatter)")
    return 0


def sync_repair() -> int:
    """根据 frontmatter 重建 sync_state.json"""
    log("正在扫描 Obsidian vault 中的 frontmatter...")
    frontmatter_syncs = find_sync_by_frontmatter()

    if not frontmatter_syncs:
        log("未找到任何包含 feishu_doc_id 的 frontmatter")
        return 0

    # 加载现有状态
    state = load_sync_state()

    log(f"\n发现 {len(frontmatter_syncs)} 个 frontmatter 同步记录:")

    added_count = 0
    updated_count = 0

    for doc_id, fm_info in frontmatter_syncs.items():
        obsidian_path = fm_info["obsidian_path"]
        feishu_title = fm_info.get("feishu_title", "未知")
        last_sync = fm_info.get("last_sync_time", "")

        if doc_id in state:
            # 更新现有记录
            old_path = state[doc_id].get("obsidian_path", "")
            if old_path != obsidian_path:
                log(f"  更新路径: {doc_id}")
                log(f"    旧路径: {old_path}")
                log(f"    新路径: {obsidian_path}")
                state[doc_id]["obsidian_path"] = obsidian_path
                updated_count += 1
            else:
                log(f"  跳过（已存在）: {doc_id} -> {obsidian_path}")
        else:
            # 添加新记录
            log(f"  添加: {doc_id} -> {obsidian_path}")

            # 计算哈希
            success, content = read_obsidian_file(obsidian_path)
            if success:
                frontmatter, body = parse_frontmatter(content)
                obsidian_hash = compute_hash(content)
                feishu_hash = compute_hash(body)
            else:
                obsidian_hash = ""
                feishu_hash = ""

            state[doc_id] = {
                "obsidian_path": obsidian_path,
                "feishu_title": feishu_title,
                "last_sync_time": last_sync,
                "obsidian_hash": obsidian_hash,
                "feishu_hash": feishu_hash,
                "sync_direction": "bidirectional"
            }
            added_count += 1

    # 保存更新后的状态
    save_sync_state(state)

    log(f"\n修复完成:")
    log(f"  新增记录: {added_count}")
    log(f"  更新路径: {updated_count}")
    log(f"  总记录数: {len(state)}")
    return 0


def sync_remove(identifier: str) -> int:
    """移除同步关系"""
    state = load_sync_state()

    # 尝试通过飞书 ID 查找
    if identifier in state:
        info = state[identifier]
        obsidian_path = info.get("obsidian_path", "未知")
        del state[identifier]
        save_sync_state(state)
        log(f"已移除同步关系:")
        log(f"  飞书文档 ID: {identifier}")
        log(f"  Obsidian: {obsidian_path}")
        log(f"  注意: 文档未被删除，仅移除同步关系")
        return 0

    # 尝试通过 Obsidian 路径查找
    doc_id = find_sync_by_obsidian_path(state, identifier)
    if doc_id:
        info = state[doc_id]
        del state[doc_id]
        save_sync_state(state)
        log(f"已移除同步关系:")
        log(f"  飞书文档 ID: {doc_id}")
        log(f"  飞书标题: {info.get('feishu_title', '未知')}")
        log(f"  Obsidian: {identifier}")
        log(f"  注意: 文档未被删除，仅移除同步关系")
        return 0

    log(f"未找到同步关系: {identifier}", "ERROR")
    return 1


def sync_all(direction: str = "bidirectional") -> int:
    """同步所有已建立关系的文档"""
    state = load_sync_state()

    # 扫描 vault 中的 frontmatter，获取所有同步关系
    frontmatter_syncs = find_sync_by_frontmatter()

    # 合并状态：frontmatter 优先
    all_doc_ids = set(state.keys()) | set(frontmatter_syncs.keys())

    if not all_doc_ids:
        log("暂无同步关系")
        return 0

    success_count = 0
    fail_count = 0
    updated_paths = []  # 记录需要更新路径的文档

    for doc_id in all_doc_ids:
        # 优先使用 frontmatter 中的信息
        if doc_id in frontmatter_syncs:
            fm_info = frontmatter_syncs[doc_id]
            obsidian_path = fm_info["obsidian_path"]
            feishu_title = fm_info.get("feishu_title", "未知")

            # 检查路径是否变化
            if doc_id in state:
                old_path = state[doc_id].get("obsidian_path", "")
                if old_path and old_path != obsidian_path:
                    log(f"  检测到路径变化: {old_path} -> {obsidian_path}")
                    updated_paths.append((doc_id, obsidian_path))
        else:
            # 回退到 state 文件
            info = state.get(doc_id, {})
            obsidian_path = info.get("obsidian_path", "")
            feishu_title = info.get("feishu_title", "未知")

        log(f"\n正在同步: {feishu_title}")

        try:
            if direction in ["to-feishu", "bidirectional"]:
                # 检查 Obsidian 是否有更新
                success, content = read_obsidian_file(obsidian_path)
                if success:
                    # 解析 frontmatter
                    frontmatter, body = parse_frontmatter(content)
                    current_hash = compute_hash(body)

                    # 获取旧的哈希值
                    old_hash = state.get(doc_id, {}).get("obsidian_hash", "")

                    if current_hash != old_hash:
                        log(f"  Obsidian 有更新，同步到飞书...")
                        # 处理图片：上传本地图片到飞书
                        body = process_images_for_feishu(body, OBSIDIAN_VAULT_PATH, doc_id)
                        # 转换 Markdown 表格为飞书表格
                        body = convert_markdown_tables_to_lark(body)
                        success, err = update_feishu_doc(doc_id, body)
                        if success:
                            # 更新 frontmatter
                            content_with_fm = write_sync_frontmatter(body, doc_id, feishu_title)
                            write_obsidian_file(obsidian_path, content_with_fm)

                            state[doc_id] = {
                                "obsidian_path": obsidian_path,
                                "feishu_title": feishu_title,
                                "last_sync_time": datetime.now(timezone.utc).isoformat(),
                                "obsidian_hash": compute_hash(content_with_fm),
                                "feishu_hash": current_hash,
                                "sync_direction": "bidirectional"
                            }
                            success_count += 1
                        else:
                            log(f"  同步失败: {err}", "ERROR")
                            fail_count += 1
                            continue

            if direction in ["to-obsidian", "bidirectional"]:
                # 检查飞书是否有更新
                success, title, content = get_feishu_doc_content(doc_id)
                if success:
                    current_hash = compute_hash(content)
                    old_hash = state.get(doc_id, {}).get("feishu_hash", "")

                    if current_hash != old_hash:
                        log(f"  飞书有更新，同步到 Obsidian...")
                        # 转换飞书表格为 Markdown 表格
                        content = convert_lark_tables_to_markdown(content)
                        # 处理图片：下载到 attachments 目录
                        content = process_images_for_obsidian(content, doc_id, OBSIDIAN_VAULT_PATH)
                        # 写入带 frontmatter 的内容
                        content_with_fm = write_sync_frontmatter(content, doc_id, title)
                        success, result = write_obsidian_file(obsidian_path, content_with_fm)
                        if success:
                            state[doc_id] = {
                                "obsidian_path": obsidian_path,
                                "feishu_title": title,
                                "last_sync_time": datetime.now(timezone.utc).isoformat(),
                                "obsidian_hash": compute_hash(content_with_fm),
                                "feishu_hash": current_hash,
                                "sync_direction": "bidirectional"
                            }
                            success_count += 1
                        else:
                            log(f"  同步失败: {result}", "ERROR")
                            fail_count += 1
                            continue

            log(f"  已是最新")

        except Exception as e:
            log(f"  同步失败: {e}", "ERROR")
            fail_count += 1

    # 保存更新后的状态
    save_sync_state(state)

    log(f"\n同步完成: 成功 {success_count}, 失败 {fail_count}")
    return 0 if fail_count == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Obsidian-Feishu 双向同步工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s sync-from-feishu https://xxx.feishu.cn/docx/doxcnXXXXXX
  %(prog)s sync-from-feishu https://xxx.feishu.cn/docx/doxcnXXXXXX --path Notes/my-note.md
  %(prog)s sync-to-feishu Notes/my-note.md --create
  %(prog)s sync-status
  %(prog)s sync-remove doxcnXXXXXX
  %(prog)s sync-remove Inbox/my-note.md
  %(prog)s sync-all
  %(prog)s sync-all --direction to-feishu
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # sync-from-feishu
    p_from = subparsers.add_parser("sync-from-feishu", help="从飞书同步到 Obsidian")
    p_from.add_argument("url", help="飞书文档 URL")
    p_from.add_argument("--path", help="Obsidian 保存路径（默认: Inbox/文档标题.md）")

    # sync-to-feishu
    p_to = subparsers.add_parser("sync-to-feishu", help="从 Obsidian 同步到飞书")
    p_to.add_argument("obsidian_path", help="Obsidian 文件路径")
    p_to.add_argument("--create", action="store_true", help="如果飞书文档不存在则创建")
    p_to.add_argument("--folder", help="飞书文档保存的文件夹 token")

    # sync-status
    subparsers.add_parser("sync-status", help="查看所有同步关系")

    # sync-remove
    p_remove = subparsers.add_parser("sync-remove", help="移除同步关系")
    p_remove.add_argument("identifier", help="飞书文档 ID 或 Obsidian 路径")

    # sync-all
    p_all = subparsers.add_parser("sync-all", help="同步所有已建立关系的文档")
    p_all.add_argument("--direction", choices=["to-feishu", "to-obsidian", "bidirectional"],
                       default="bidirectional", help="同步方向（默认: bidirectional）")

    # sync-repair
    subparsers.add_parser("sync-repair", help="根据 frontmatter 重建 sync_state.json")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "sync-from-feishu":
        return sync_from_feishu(args.url, args.path)
    elif args.command == "sync-to-feishu":
        return sync_to_feishu(args.obsidian_path, args.create, args.folder)
    elif args.command == "sync-status":
        return sync_status()
    elif args.command == "sync-remove":
        return sync_remove(args.identifier)
    elif args.command == "sync-all":
        return sync_all(args.direction)
    elif args.command == "sync-repair":
        return sync_repair()

    return 0


if __name__ == "__main__":
    sys.exit(main())
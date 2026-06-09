#!/usr/bin/env python3
"""
Markdown-Feishu Sync Script
支持任意路径下 markdown 文件的飞书双向同步
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
import yaml

# 导入转换器模块
from converter import (
    convert_lark_tables_to_markdown,
    convert_markdown_tables_to_lark,
    process_images_for_obsidian,
    process_images_for_feishu,
    convert_callouts_to_markdown_alerts,
    convert_markdown_alerts_to_callouts,
    process_whiteboards_for_obsidian,
    process_whiteboards_for_feishu,
    convert_mentions_to_markdown_links,
    fix_bold_colons,
    convert_quotes_to_markdown,
)

# 默认配置
OBSIDIAN_VAULT_PATH = Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "ObsidianVault"
SYNC_STATE_PATH = Path(__file__).resolve().parent.parent / "sync_state.json"
CONFIG_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).parent.resolve()

# 全局 base_dir（通过 CLI --base-dir 或环境变量设置）
_GLOBAL_BASE_DIR: Optional[Path] = None


def log(message: str, level: str = "INFO"):
    """输出日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", file=sys.stderr if level == "ERROR" else sys.stdout)


# ============== 路径解析 ==============


def get_base_dir() -> Path:
    """获取当前 base_dir（优先 CLI 传入，其次环境变量，最后默认 Obsidian vault）"""
    env_base = os.environ.get("SYNC_BASE_DIR")
    if env_base:
        return Path(env_base).resolve()
    if _GLOBAL_BASE_DIR:
        return _GLOBAL_BASE_DIR.resolve()
    # 向后兼容：默认 Obsidian vault
    return OBSIDIAN_VAULT_PATH


def set_base_dir(path: str):
    """设置 base_dir（由 CLI 解析后调用）"""
    global _GLOBAL_BASE_DIR
    _GLOBAL_BASE_DIR = Path(path).resolve()


def resolve_path(path_str: str) -> Path:
    """
    解析文件路径：绝对路径直接使用，相对路径解析至 base_dir
    """
    p = Path(path_str)
    if p.is_absolute():
        return p.resolve()
    base = get_base_dir()
    return (base / path_str).resolve()


def short_path(path: Path, base: Optional[Path] = None) -> str:
    """显示短路径（相对于 base_dir），用于界面展示"""
    if base is None:
        base = get_base_dir()
    try:
        rel = path.relative_to(base)
        return str(rel)
    except ValueError:
        return str(path)


# ============== 同步状态管理（含旧版路径迁移） ==============


def load_sync_state() -> dict:
    """加载同步状态，自动迁移旧版相对路径到绝对路径"""
    if not SYNC_STATE_PATH.exists():
        return {}
    try:
        with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"加载同步状态失败: {e}", "ERROR")
        return {}

    # 自动迁移：将旧版相对路径转换为绝对路径
    migrated = False
    migration_count = 0
    base = get_base_dir()
    for doc_id, info in raw.items():
        path_val = info.get("obsidian_path", "")
        if path_val and not os.path.isabs(path_val):
            migration_count += 1
            # 旧版相对路径，尝试转换为绝对
            old_abs = (OBSIDIAN_VAULT_PATH / path_val).resolve()
            if old_abs.exists():
                info["obsidian_path"] = str(old_abs)
            else:
                info["obsidian_path"] = str((base / path_val).resolve())
            migrated = True

    if migrated:
        save_sync_state(raw)
        log(f"已迁移 {migration_count} 条旧版相对路径到绝对路径")

    return raw


def save_sync_state(state: dict):
    """保存同步状态"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SYNC_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def compute_hash(content: str) -> str:
    """计算内容哈希"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ============== 飞书 API 操作 ==============


def extract_doc_id(url: str) -> Optional[str]:
    """从飞书 URL 提取文档 ID"""
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
            timeout=120
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
    import tempfile
    # 在当前工作目录下创建临时文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", dir=".", delete=False, encoding="utf-8") as f:
        f.write(content if content else "# " + title)
        temp_path = f.name

    rel_path = "./" + os.path.basename(temp_path)
    args = ["docs", "+create", "--title", title, "--markdown", "@" + rel_path]
    if folder_token:
        args.extend(["--folder-token", folder_token])

    try:
        success, output = run_lark_command(args)
        if not success:
            return False, output

        # 从输出提取文档 ID
        doc_id_match = re.search(r"doc[_-]?token[=:]\s*([a-zA-Z0-9]+)", output, re.IGNORECASE)
        if not doc_id_match:
            doc_id_match = re.search(r"([a-zA-Z0-9]{20,})", output)

        if not doc_id_match:
            return False, "无法从创建结果中提取文档 ID"

        doc_id = doc_id_match.group(1)
        return True, doc_id
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def update_feishu_doc(doc_id: str, content: str, title: Optional[str] = None) -> tuple[bool, str]:
    """更新飞书文档内容和标题"""
    import tempfile
    # 在当前工作目录下创建临时文件以避开 lark-cli 对绝对路径的安全限制
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", dir=".", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    rel_path = "./" + os.path.basename(temp_path)
    try:
        cmd = [
            "docs", "+update", "--api-version", "v2", "--doc", doc_id, "--command", "overwrite", "--doc-format", "markdown", "--content", "@" + rel_path
        ]
        if title:
            cmd.extend(["--new-title", title])
        success, output = run_lark_command(cmd)
        return success, output
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


# ============== 文件读写（支持任意路径） ==============


def read_markdown_file(path: Path) -> tuple[bool, str]:
    """读取任意 markdown 文件内容"""
    if not path.exists():
        return False, f"文件不存在: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return True, f.read()
    except IOError as e:
        return False, str(e)


def write_markdown_file(path: Path, content: str) -> tuple[bool, str]:
    """写入 markdown 文件内容（自动创建父目录）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, str(path)
    except IOError as e:
        return False, str(e)


def get_file_mtime(path: Path) -> Optional[datetime]:
    """获取文件修改时间"""
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


# ============== Frontmatter 操作 ==============


def parse_frontmatter(content: str) -> Tuple[dict, str]:
    """解析 Markdown 文件的 frontmatter。返回 (frontmatter_dict, body_content)"""
    if not content.startswith("---"):
        return {}, content

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
    """将 frontmatter 和 body 组合成完整的 Markdown 内容"""
    if not frontmatter:
        return body
    frontmatter_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return f"---\n{frontmatter_str}---\n\n{body}"


def update_frontmatter(content: str, updates: dict) -> str:
    """更新 Markdown 文件的 frontmatter"""
    frontmatter, body = parse_frontmatter(content)
    frontmatter.update(updates)
    return write_frontmatter(frontmatter, body)


def get_feishu_doc_id_from_frontmatter(content: str) -> Optional[str]:
    """从 frontmatter 中提取飞书文档 ID"""
    frontmatter, _ = parse_frontmatter(content)
    return frontmatter.get("feishu_doc_id")


def write_sync_frontmatter(content: str, doc_id: str, title: str) -> str:
    """写入同步相关的 frontmatter"""
    frontmatter_updates = {
        "feishu_doc_id": doc_id,
        "feishu_title": title,
        "last_sync": datetime.now(timezone.utc).isoformat()
    }
    return update_frontmatter(content, frontmatter_updates)


# ============== 同步关系查找 ==============


def find_sync_by_obsidian_path(state: dict, obsidian_path: str) -> Optional[str]:
    """通过文件路径查找同步记录（支持绝对路径匹配和末尾匹配）"""
    # 精确匹配
    for doc_id, info in state.items():
        if info.get("obsidian_path") == obsidian_path:
            return doc_id

    # 模糊匹配（如果传入的是相对路径，尝试匹配以该路径结尾的绝对路径）
    if not os.path.isabs(obsidian_path):
        for doc_id, info in state.items():
            stored_path = info.get("obsidian_path", "")
            if stored_path.endswith(obsidian_path):
                return doc_id

    return None


def find_sync_by_feishu_id(state: dict, feishu_id: str) -> Optional[dict]:
    """通过飞书文档 ID 查找同步记录"""
    return state.get(feishu_id)


# ============== 扫描目录中的同步关系 ==============


def scan_directory_for_frontmatter(directory: Path) -> dict:
    """
    扫描指定目录树中所有 .md 文件，读取 frontmatter 中的 feishu_doc_id。
    返回 {feishu_doc_id: {"markdown_path": absolute_path, "feishu_title": title, ...}}
    """
    result = {}
    if not directory.exists():
        log(f"目录不存在: {directory}", "ERROR")
        return result

    md_files = list(directory.rglob("*.md"))
    log(f"正在扫描 {directory} 中的 {len(md_files)} 个 .md 文件...")

    for md_file in md_files:
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter, body = parse_frontmatter(content)
            doc_id = frontmatter.get("feishu_doc_id")

            if doc_id:
                result[doc_id] = {
                    "markdown_path": str(md_file.resolve()),
                    "obsidian_path": str(md_file.resolve()),  # 兼容旧字段名
                    "feishu_title": frontmatter.get("feishu_title", md_file.stem),
                    "last_sync_time": frontmatter.get("last_sync", ""),
                    "from_frontmatter": True
                }
        except (IOError, UnicodeDecodeError, FileNotFoundError) as e:
            log(f"读取文件失败 {md_file}: {e}", "WARN")
            continue

    return result


# ============== 核心同步函数 ==============


def sync_from_feishu(url: str, target_path: Optional[str] = None) -> int:
    """从飞书同步到本地 markdown 文件"""
    doc_id = extract_doc_id(url)
    if not doc_id:
        log(f"无法从 URL 提取文档 ID: {url}", "ERROR")
        return 1

    log(f"正在获取飞书文档: {doc_id}")
    success, title, content = get_feishu_doc_content(doc_id)
    if not success:
        log(f"获取飞书文档失败: {title}", "ERROR")
        return 1

    raw_feishu_hash = compute_hash(content)

    # 转换飞书表格为 Markdown 表格
    log(f"正在转换表格格式...")
    content = convert_lark_tables_to_markdown(content)

    # 转换飞书高亮块为 Markdown Alerts
    log(f"正在转换高亮块格式...")
    content = convert_callouts_to_markdown_alerts(content)

    # 转换飞书引用块为 Markdown 引用
    log(f"正在转换引用格式...")
    content = convert_quotes_to_markdown(content)

    # 转换 cite/mention-doc 标签为 Markdown 超链接
    content = convert_mentions_to_markdown_links(content)

    # 处理画板/Mermaid 图表
    log(f"正在处理画板图表...")
    content = process_whiteboards_for_obsidian(content)

    # 解析或生成目标路径
    if target_path:
        target = resolve_path(target_path)
    else:
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        target = get_base_dir() / f"Inbox/{safe_title}.md"

    # 确保以 .md 结尾
    if target.suffix != ".md":
        target = target.with_suffix(".md")

    # 处理图片：下载到 attachments 目录 (使用相对于 markdown 目标路径的 parent 目录，以支持正确相对解析)
    log(f"正在处理图片...")
    content = process_images_for_obsidian(content, doc_id, target.parent)

    # 写入 frontmatter
    content_with_frontmatter = write_sync_frontmatter(content, doc_id, title)

    log(f"正在写入文件: {target}")
    success, result = write_markdown_file(target, content_with_frontmatter)
    if not success:
        log(f"写入文件失败: {result}", "ERROR")
        return 1

    # 更新同步状态
    state = load_sync_state()
    state[doc_id] = {
        "obsidian_path": str(target),
        "feishu_title": title,
        "last_sync_time": datetime.now(timezone.utc).isoformat(),
        "obsidian_hash": compute_hash(content_with_frontmatter),
        "feishu_hash": raw_feishu_hash,
        "sync_direction": "bidirectional"
    }
    save_sync_state(state)

    log(f"同步成功!")
    log(f"  飞书文档: {title} ({doc_id})")
    log(f"  本地文件: {target}")
    return 0


def sync_to_feishu(file_path: str, create: bool = False, folder_token: Optional[str] = None) -> int:
    """从本地 markdown 文件同步到飞书"""
    path = resolve_path(file_path)

    # 读取文件
    success, content = read_markdown_file(path)
    if not success:
        log(f"读取文件失败: {content}", "ERROR")
        return 1

    # 解析 frontmatter，提取已有的飞书文档 ID
    frontmatter, body = parse_frontmatter(content)
    existing_doc_id = frontmatter.get("feishu_doc_id")

    # 提取标题
    title = path.stem
    for line in body.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    state = load_sync_state()

    # 查找是否已有同步关系
    doc_id = existing_doc_id or find_sync_by_obsidian_path(state, str(path))

    if doc_id:
        # 处理画板/Mermaid 图表
        log(f"正在处理画板图表...")
        feishu_body = process_whiteboards_for_feishu(body)

        # 处理图片：上传本地图片到飞书 (使用当前 markdown 所在目录作为图片根路径)
        log(f"正在处理图片...")
        feishu_body = process_images_for_feishu(feishu_body, path.parent, doc_id)

        # 转换 Markdown Alerts 为飞书高亮块
        log(f"正在转换高亮块格式...")
        feishu_body = convert_markdown_alerts_to_callouts(feishu_body)

        # 预处理：转换 cite/mention-doc 为 Markdown 超链接，并修复加粗冒号
        feishu_body = convert_mentions_to_markdown_links(feishu_body)
        feishu_body = fix_bold_colons(feishu_body)

        # 转换 Markdown 表格为飞书表格 (v2 API 已原生支持 Markdown 表格，此处不再转换为 HTML)
        # log(f"正在转换表格格式...")
        # feishu_body = convert_markdown_tables_to_lark(feishu_body)

        log(f"正在更新飞书文档: {doc_id}")
        success, err = update_feishu_doc(doc_id, feishu_body, title)
        if not success:
            log(f"更新飞书文档失败: {err}", "ERROR")
            return 1
    elif create:
        log(f"正在处理图片...")
        log(f"  注意: 创建新文档时图片上传暂不支持，请在创建后再次同步")
        feishu_body = body

        # 处理画板/Mermaid 图表
        log(f"正在处理画板图表...")
        feishu_body = process_whiteboards_for_feishu(feishu_body)

        # 转换 Markdown Alerts 为飞书高亮块
        log(f"正在转换高亮块格式...")
        feishu_body = convert_markdown_alerts_to_callouts(feishu_body)

        # 预处理：转换 cite/mention-doc 为 Markdown 超链接，并修复加粗冒号
        feishu_body = convert_mentions_to_markdown_links(feishu_body)
        feishu_body = fix_bold_colons(feishu_body)

        # log(f"正在转换表格格式...")
        # feishu_body = convert_markdown_tables_to_lark(feishu_body)

        log(f"正在创建飞书文档: {title}")
        success, doc_id = create_feishu_doc(title, feishu_body, folder_token)
        if not success:
            log(f"创建飞书文档失败: {doc_id}", "ERROR")
            return 1
    else:
        log(f"未找到同步关系，使用 --create 创建新文档，或先通过 sync-from-feishu 同步", "ERROR")
        return 1

    # 更新本地文件的 frontmatter (保留本地图片路径!)
    content_with_frontmatter = write_sync_frontmatter(body, doc_id, title)
    success, result = write_markdown_file(path, content_with_frontmatter)
    if not success:
        log(f"更新 frontmatter 失败: {result}", "ERROR")

    # 更新同步状态
    state[doc_id] = {
        "obsidian_path": str(path),
        "feishu_title": title,
        "last_sync_time": datetime.now(timezone.utc).isoformat(),
        "obsidian_hash": compute_hash(content_with_frontmatter),
        "feishu_hash": compute_hash(feishu_body),
        "sync_direction": "bidirectional"
    }
    save_sync_state(state)

    log(f"同步成功!")
    log(f"  本地文件: {path}")
    log(f"  飞书文档: {title} ({doc_id})")
    return 0


def sync_status() -> int:
    """显示同步状态"""
    state = load_sync_state()
    base = get_base_dir()

    if not state:
        log("暂无同步关系")
        return 0

    log("=" * 110)
    log(f"{'飞书文档 ID':<20} {'飞书标题':<18} {'本地文件路径':<35} {'最后同步':<16} {'状态'}")
    log("-" * 110)

    in_sync = 0
    out_of_sync = 0

    for doc_id in sorted(state.keys()):
        info = state[doc_id]
        title = info.get("feishu_title", "未知")[:16]
        stored_path = info.get("obsidian_path", "未知")
        sync_time = info.get("last_sync_time", "")
        sync_dir = info.get("sync_direction", "bidirectional")

        # 显示短路径
        path_obj = Path(stored_path)
        display_path = short_path(path_obj, base) if path_obj.exists() else stored_path[:33]

        if sync_time:
            try:
                dt = datetime.fromisoformat(sync_time.replace("Z", "+00:00"))
                sync_time = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass
        else:
            sync_time = "未知"

        # 检查文件是否存在
        exists = "✓" if path_obj.exists() else "⚠ 文件不存在"
        log(f"{doc_id:<20} {title:<18} {display_path:<35} {sync_time:<16} {exists}")

        if path_obj.exists():
            in_sync += 1
        else:
            out_of_sync += 1

    log("=" * 110)
    log(f"共 {len(state)} 个同步关系 | 文件存在: {in_sync} | 文件缺失: {out_of_sync}")
    return 0


def sync_remove(identifier: str) -> int:
    """移除同步关系（不删除文件）"""
    state = load_sync_state()

    # 尝试通过飞书 ID 查找
    if identifier in state:
        info = state[identifier]
        stored_path = info.get("obsidian_path", "未知")
        del state[identifier]
        save_sync_state(state)
        log(f"已移除同步关系:")
        log(f"  飞书文档 ID: {identifier}")
        log(f"  本地文件: {stored_path}")
        log(f"  注意: 文件未被删除，仅移除同步关系")
        return 0

    # 尝试通过绝对路径查找
    resolved = resolve_path(identifier)
    doc_id = find_sync_by_obsidian_path(state, str(resolved))
    if doc_id:
        info = state[doc_id]
        del state[doc_id]
        save_sync_state(state)
        log(f"已移除同步关系:")
        log(f"  飞书文档 ID: {doc_id}")
        log(f"  飞书标题: {info.get('feishu_title', '未知')}")
        log(f"  本地文件: {resolved}")
        log(f"  注意: 文件未被删除，仅移除同步关系")
        return 0

    log(f"未找到同步关系: {identifier}", "ERROR")
    return 1


def sync_all(direction: str = "bidirectional") -> int:
    """同步所有已建立关系的文档"""
    state = load_sync_state()

    if not state:
        log("暂无同步关系")
        return 0

    success_count = 0
    fail_count = 0
    updated_paths = []

    for doc_id, info in state.items():
        stored_path = info.get("obsidian_path", "")
        feishu_title = info.get("feishu_title", "未知")

        if not stored_path:
            log(f"\n  跳过 {doc_id}: 路径为空")
            continue

        path = Path(stored_path)

        # 检查文件是否存在
        if not path.exists():
            log(f"\n  跳过 {feishu_title}: 文件不存在 {path}")
            continue

        log(f"\n正在同步: {feishu_title} ({path.name})")

        try:
            if direction in ["to-feishu", "bidirectional"]:
                success, content = read_markdown_file(path)
                if success:
                    current_hash = compute_hash(content)
                    old_hash = state.get(doc_id, {}).get("obsidian_hash", "")

                    if current_hash != old_hash:
                        log(f"  本地有更新，同步到飞书...")
                        _, body = parse_frontmatter(content)
                        
                        # 处理画板/Mermaid 图表
                        log(f"正在处理画板图表...")
                        feishu_body = process_whiteboards_for_feishu(body)
                        
                        feishu_body = process_images_for_feishu(feishu_body, path.parent, doc_id)
                        
                        # 转换 Markdown Alerts 为飞书高亮块
                        log(f"正在转换高亮块格式...")
                        feishu_body = convert_markdown_alerts_to_callouts(feishu_body)

                        # 预处理：转换 cite/mention-doc 为 Markdown 超链接，并修复加粗冒号
                        feishu_body = convert_mentions_to_markdown_links(feishu_body)
                        feishu_body = fix_bold_colons(feishu_body)
                        
                        # 提取最新标题
                        doc_title = path.stem
                        for line in body.split("\n"):
                            if line.startswith("# "):
                                doc_title = line[2:].strip()
                                break

                        # body = convert_markdown_tables_to_lark(body)
                        success, err = update_feishu_doc(doc_id, feishu_body, doc_title)
                        if success:
                            # Write back the original local body (with local paths) to local file
                            content_with_fm = write_sync_frontmatter(body, doc_id, doc_title)
                            write_markdown_file(path, content_with_fm)
                            state[doc_id] = {
                                "obsidian_path": str(path),
                                "feishu_title": doc_title,
                                "last_sync_time": datetime.now(timezone.utc).isoformat(),
                                "obsidian_hash": compute_hash(content_with_fm),
                                "feishu_hash": compute_hash(feishu_body),
                                "sync_direction": "bidirectional"
                            }
                            success_count += 1
                        else:
                            log(f"  同步失败: {err}", "ERROR")
                            fail_count += 1
                            continue

            if direction in ["to-obsidian", "bidirectional"]:
                success, title, content = get_feishu_doc_content(doc_id)
                if success:
                    current_hash = compute_hash(content)
                    old_hash = state.get(doc_id, {}).get("feishu_hash", "")

                    if current_hash != old_hash:
                        log(f"  飞书有更新，同步到本地...")
                        content = convert_lark_tables_to_markdown(content)
                        
                        # 转换飞书高亮块为 Markdown Alerts
                        log(f"正在转换高亮块格式...")
                        content = convert_callouts_to_markdown_alerts(content)

                        # 转换飞书引用块为 Markdown 引用
                        log(f"正在转换引用格式...")
                        content = convert_quotes_to_markdown(content)

                        # 转换 cite/mention-doc 标签为 Markdown 超链接
                        content = convert_mentions_to_markdown_links(content)
                        
                        # 处理画板/Mermaid 图表
                        log(f"正在处理画板图表...")
                        content = process_whiteboards_for_obsidian(content)
                        
                        content = process_images_for_obsidian(content, doc_id, path.parent)
                        content_with_fm = write_sync_frontmatter(content, doc_id, title)
                        success, result = write_markdown_file(path, content_with_fm)
                        if success:
                            state[doc_id] = {
                                "obsidian_path": str(path),
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

    save_sync_state(state)

    log(f"\n同步完成: 成功 {success_count}, 失败 {fail_count}")
    return 0 if fail_count == 0 else 1


def sync_repair(directory: Optional[str] = None) -> int:
    """根据 frontmatter 重建 sync_state.json"""
    if directory:
        scan_dir = resolve_path(directory)
        log(f"正在扫描目录: {scan_dir}")
        frontmatter_syncs = scan_directory_for_frontmatter(scan_dir)
    else:
        # 默认扫描 base_dir
        scan_dir = get_base_dir()
        log(f"正在扫描 base_dir: {scan_dir}")
        frontmatter_syncs = scan_directory_for_frontmatter(scan_dir)

    if not frontmatter_syncs:
        log("未找到任何包含 feishu_doc_id 的 frontmatter")
        return 0

    state = load_sync_state()

    log(f"\n发现 {len(frontmatter_syncs)} 个 frontmatter 同步记录:")

    added_count = 0
    updated_count = 0

    for doc_id, fm_info in frontmatter_syncs.items():
        md_path = fm_info["markdown_path"]
        feishu_title = fm_info.get("feishu_title", "未知")
        last_sync = fm_info.get("last_sync_time", "")

        if doc_id in state:
            old_path = state[doc_id].get("obsidian_path", "")
            if old_path != md_path:
                log(f"  更新路径: {doc_id}")
                log(f"    旧路径: {old_path}")
                log(f"    新路径: {md_path}")
                state[doc_id]["obsidian_path"] = md_path
                updated_count += 1
            else:
                log(f"  跳过（已存在）: {doc_id} -> {short_path(Path(md_path))}")
        else:
            log(f"  添加: {doc_id} -> {short_path(Path(md_path))}")
            success, content = read_markdown_file(Path(md_path))
            if success:
                _, body = parse_frontmatter(content)
                obsidian_hash = compute_hash(content)
                feishu_hash = compute_hash(body)
            else:
                obsidian_hash = ""
                feishu_hash = ""

            state[doc_id] = {
                "obsidian_path": md_path,
                "feishu_title": feishu_title,
                "last_sync_time": last_sync,
                "obsidian_hash": obsidian_hash,
                "feishu_hash": feishu_hash,
                "sync_direction": "bidirectional"
            }
            added_count += 1

    save_sync_state(state)

    log(f"\n修复完成:")
    log(f"  新增记录: {added_count}")
    log(f"  更新路径: {updated_count}")
    log(f"  总记录数: {len(state)}")
    return 0


# ============== 主入口 ==============


def main():
    parser = argparse.ArgumentParser(
        description="Markdown-Feishu 双向同步工具 — 支持任意路径下 markdown 文件的飞书同步",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s sync-from-feishu https://xxx.feishu.cn/docx/doxcnXXXXXX
  %(prog)s sync-from-feishu https://xxx.feishu.cn/docx/doxcnXXXXXX --path ~/my-docs/note.md
  %(prog)s sync-to-feishu ~/my-docs/note.md --create
  %(prog)s sync-to-feishu Notes/my-note.md --create           # 相对路径（默认 base_dir 为 Obsidian vault）
  %(prog)s --base-dir ~/Projects/thoughts-public sync-to-feishu posts/hello.md --create
  %(prog)s sync-status
  %(prog)s sync-remove doxcnXXXXXX
  %(prog)s sync-remove ~/my-docs/note.md
  %(prog)s sync-all
  %(prog)s sync-all --direction to-feishu
  %(prog)s sync-repair                                          # 扫描 base_dir
  %(prog)s --base-dir ~/Projects/thoughts-public sync-repair    # 扫描指定目录
  %(prog)s scan ~/Documents/my-md-project                       # 扫描目录中的同步关系
        """
    )

    parser.add_argument(
        "--base-dir",
        help=f"基础目录（用于解析相对路径，默认: {OBSIDIAN_VAULT_PATH}。也可通过 SYNC_BASE_DIR 环境变量设置）"
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # sync-from-feishu
    p_from = subparsers.add_parser("sync-from-feishu", help="从飞书同步到本地 markdown")
    p_from.add_argument("url", help="飞书文档 URL")
    p_from.add_argument("--path", help="本地保存路径（绝对路径或相对路径，默认: Inbox/文档标题.md）")

    # sync-to-feishu
    p_to = subparsers.add_parser("sync-to-feishu", help="从本地 markdown 同步到飞书")
    p_to.add_argument("markdown_path", help="本地 markdown 文件路径（绝对路径或相对路径）")
    p_to.add_argument("--create", action="store_true", help="如果飞书文档不存在则创建")
    p_to.add_argument("--folder", help="飞书文档保存的文件夹 token")

    # sync-status
    subparsers.add_parser("sync-status", help="查看所有同步关系")

    # sync-remove
    p_remove = subparsers.add_parser("sync-remove", help="移除同步关系（不删除文件）")
    p_remove.add_argument("identifier", help="飞书文档 ID 或本地文件路径")

    # sync-all
    p_all = subparsers.add_parser("sync-all", help="同步所有已建立关系的文档")
    p_all.add_argument("--direction", choices=["to-feishu", "to-obsidian", "bidirectional"],
                       default="bidirectional", help="同步方向（默认: bidirectional）")

    # sync-repair
    p_repair = subparsers.add_parser("sync-repair", help="根据 frontmatter 重建 sync_state.json")
    p_repair.add_argument("directory", nargs="?", help="要扫描的目录（可选，默认 base_dir）")

    # scan
    p_scan = subparsers.add_parser("scan", help="扫描目录中的 feishu_doc_id frontmatter，列出同步关系")
    p_scan.add_argument("directory", nargs="?", help="要扫描的目录（可选，默认 base_dir）")

    args = parser.parse_args()

    # 设置 base_dir
    if args.base_dir:
        set_base_dir(args.base_dir)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "sync-from-feishu":
        return sync_from_feishu(args.url, args.path)
    elif args.command == "sync-to-feishu":
        return sync_to_feishu(args.markdown_path, args.create, args.folder)
    elif args.command == "sync-status":
        return sync_status()
    elif args.command == "sync-remove":
        return sync_remove(args.identifier)
    elif args.command == "sync-all":
        return sync_all(args.direction)
    elif args.command == "sync-repair":
        return sync_repair(args.directory)
    elif args.command == "scan":
        scan_dir = resolve_path(args.directory) if args.directory else get_base_dir()
        result = scan_directory_for_frontmatter(scan_dir)
        if not result:
            log(f"在 {scan_dir} 中未找到包含 feishu_doc_id 的文件")
            return 0
        log(f"在 {scan_dir} 中找到 {len(result)} 个同步关系:")
        log("-" * 80)
        for doc_id, info in result.items():
            path_short = short_path(Path(info["markdown_path"]))
            log(f"  {doc_id:<22} {info['feishu_title']:<18} {path_short}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Markdown 与飞书文档块格式转换工具
"""

import re
import json
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser


class BlockType(Enum):
    TEXT = "text"
    HEADING1 = "heading1"
    HEADING2 = "heading2"
    HEADING3 = "heading3"
    BULLET = "bullet"
    ORDERED = "ordered"
    TODO = "todo"
    CODE = "code"
    QUOTE = "quote"
    DIVIDER = "divider"
    IMAGE = "image"
    TABLE = "table"


@dataclass
class Block:
    type: BlockType
    content: str = ""
    children: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


class LarkTableParser(HTMLParser):
    """解析飞书表格 HTML 标签"""
    
    def __init__(self):
        super().__init__()
        self.rows: List[List[str]] = []
        self.current_row: List[str] = []
        self.current_cell: str = ""
        self.in_table = False
        self.in_row = False
        self.in_cell = False
    
    def handle_starttag(self, tag, attrs):
        if tag == "lark-table":
            self.in_table = True
        elif tag == "lark-tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag == "lark-td" and self.in_row:
            self.in_cell = True
            self.current_cell = ""
    
    def handle_endtag(self, tag):
        if tag == "lark-table":
            self.in_table = False
        elif tag == "lark-tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag == "lark-td" and self.in_cell:
            self.in_cell = False
            self.current_row.append(self.current_cell.strip())
    
    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data
    
    def get_table(self) -> List[List[str]]:
        return self.rows


def lark_table_to_markdown(lark_table_html: str) -> str:
    """将飞书表格 HTML 转换为 Markdown 表格"""
    parser = LarkTableParser()
    parser.feed(lark_table_html)
    rows = parser.get_table()
    
    if not rows:
        return ""
        
    # 处理单元格内部的换行，用 <br /> 替代，以符合 Markdown 表格单行要求
    cleaned_rows = []
    for row in rows:
        cleaned_row = []
        for cell in row:
            lines = [line.strip() for line in cell.split("\n")]
            cleaned_cell = "<br />".join([l for l in lines if l])
            cleaned_row.append(cleaned_cell)
        cleaned_rows.append(cleaned_row)
    rows = cleaned_rows
    
    # 计算每列最大宽度
    col_count = max(len(row) for row in rows)
    col_widths = [0] * col_count
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                col_widths[i] = max(col_widths[i], len(cell))
    
    # 生成 Markdown 表格
    lines = []
    for i, row in enumerate(rows):
        # 补齐列数
        padded_row = row + [""] * (col_count - len(row))
        cells = [cell.ljust(col_widths[j]) for j, cell in enumerate(padded_row)]
        lines.append("| " + " | ".join(cells) + " |")
        
        # 第一行后添加分隔线
        if i == 0:
            separator = "|-" + "-|-".join(["-" * w for w in col_widths]) + "-|"
            lines.append(separator)
    
    return "\n".join(lines)


def markdown_table_to_lark_table(md_table: str) -> str:
    """将 Markdown 表格转换为飞书表格 HTML"""
    lines = [line.strip() for line in md_table.strip().split("\n") if line.strip()]
    
    if len(lines) < 2:
        return ""
    
    # 解析表格数据
    rows = []
    for line in lines:
        if line.startswith("|") and line.endswith("|"):
            # 跳过分隔线
            if re.match(r"^\|[-:|]+\|$", line):
                continue
            cells = [cell.strip() for cell in line[1:-1].split("|")]
            rows.append(cells)
    
    if not rows:
        return ""
    
    # 生成飞书表格 HTML
    row_count = len(rows)
    col_count = max(len(row) for row in rows)
    
    # 计算列宽（平均分配）
    col_widths = [200] * col_count  # 默认宽度
    col_widths_str = ",".join(map(str, col_widths))
    
    html = f'<lark-table rows="{row_count}" cols="{col_count}" column-widths="{col_widths_str}">\n'
    
    for row in rows:
        html += "  <lark-tr>\n"
        padded_row = row + [""] * (col_count - len(row))
        for cell in padded_row:
            # 将 Markdown 的 <br /> 标签转回物理换行，使飞书端渲染自然换行
            feishu_cell = cell.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
            html += f"    <lark-td>\n      {feishu_cell}\n    </lark-td>\n"
        html += "  </lark-tr>\n"
    
    html += "</lark-table>"
    return html


def convert_lark_tables_to_markdown(content: str) -> str:
    """将内容中的所有飞书表格转换为 Markdown 表格"""
    # 匹配 <lark-table>...</lark-table>
    pattern = r'<lark-table[^>]*>.*?</lark-table>'
    
    def replace_table(match):
        lark_html = match.group(0)
        return lark_table_to_markdown(lark_html)
    
    return re.sub(pattern, replace_table, content, flags=re.DOTALL)


def convert_markdown_tables_to_lark(content: str) -> str:
    """将内容中的所有 Markdown 表格转换为飞书表格"""
    # 匹配 Markdown 表格（以 | 开头的连续行）
    pattern = r'(\|[^\n]+\|\n)+(\|[-:|]+\|\n)?(\|[^\n]+\|\n)*'
    
    def replace_table(match):
        md_table = match.group(0)
        return markdown_table_to_lark_table(md_table)
    
    return re.sub(pattern, replace_table, content)


# ============================================================================
# 图片处理
# ============================================================================

import os
import hashlib
import urllib.request
import urllib.error
from pathlib import Path


def download_image(url: str, save_dir: Path, filename: Optional[str] = None) -> Optional[Path]:
    """
    下载图片到本地
    
    Args:
        url: 图片 URL
        save_dir: 保存目录
        filename: 文件名（可选，默认根据 URL 生成）
    
    Returns:
        保存的文件路径，失败返回 None
    """
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        if not filename:
            # 从 URL 提取扩展名
            ext = ".png"
            if "." in url.split("/")[-1]:
                ext = "." + url.split(".")[-1].split("?")[0][:4]  # 限制扩展名长度
            # 用 URL hash 作为文件名
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            filename = f"img_{url_hash}{ext}"
        
        save_path = save_dir / filename
        
        # 如果已存在，直接返回
        if save_path.exists():
            return save_path
        
        # 下载
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            save_path.write_bytes(data)
        
        return save_path
    except Exception as e:
        print(f"[WARN] 下载图片失败: {url} - {e}")
        return None


def extract_image_urls(content: str) -> List[Tuple[str, str, str]]:
    """
    从内容中提取所有图片 URL
    
    Returns:
        List of (full_match, alt_text, url)
    """
    # Markdown 格式: ![alt](url)
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    matches = []
    
    for match in re.finditer(pattern, content):
        full_match = match.group(0)
        alt_text = match.group(1)
        url = match.group(2)
        matches.append((full_match, alt_text, url))
    
    return matches


def download_feishu_media(token: str, save_dir: Path) -> Optional[Path]:
    """
    使用 lark-cli docs +media-download 下载飞书媒体文件并返回本地路径
    """
    import subprocess
    import json
    import os
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"img_{token}.png"
    jpg_path = save_dir / f"img_{token}.jpg"
    
    if save_path.exists():
        return save_path
    if jpg_path.exists():
        return jpg_path
        
    try:
        # 使用 save_dir 作为 cwd，避免 lark-cli 的 "unsafe output path" 限制
        cmd = ["lark-cli", "docs", "+media-download", "--token", token, "--output", f"./img_{token}.png", "--overwrite"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=save_dir)
        if proc.returncode == 0:
            output = proc.stdout.strip()
            try:
                json_start = output.find("{")
                if json_start != -1:
                    json_str = output[json_start:]
                    parsed = json.loads(json_str)
                    if parsed.get("ok"):
                        content_type = parsed.get("data", {}).get("content_type", "")
                        if "jpeg" in content_type or "jpg" in content_type:
                            new_path = save_dir / f"img_{token}.jpg"
                            if save_path.exists():
                                save_path.rename(new_path)
                            return new_path
                        return save_path
            except Exception:
                pass
            return save_path
    except Exception as e:
        print(f"[WARN] 无法通过 lark-cli 下载媒体 {token}: {e}")
    return None


def get_obsidian_attachment_dir(markdown_dir: Path) -> Optional[Path]:
    """
    如果 markdown_dir 在 Obsidian 库中，则根据 .obsidian/app.json 查找附件保存目录。
    返回附件目录的绝对 Path，如果不在库中则返回 None。
    """
    current = markdown_dir.resolve()
    while current != current.parent:
        obsidian_dir = current / ".obsidian"
        if obsidian_dir.is_dir():
            vault_root = current
            app_json_path = obsidian_dir / "app.json"
            attachment_folder = None
            if app_json_path.is_file():
                try:
                    with open(app_json_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                        attachment_folder = config.get("attachmentFolderPath")
                except Exception as e:
                    print(f"[WARN] 无法读取 Obsidian 配置文件: {e}")
            
            if not attachment_folder:
                # 默认保存在库根目录
                return vault_root
            
            if attachment_folder.startswith("./") or attachment_folder.startswith("../"):
                return (markdown_dir / attachment_folder).resolve()
            return (vault_root / attachment_folder).resolve()
        current = current.parent
    return None


def process_images_for_obsidian(
    content: str, 
    doc_id: str,
    markdown_dir: Path,
    lark_cli_path: str = "lark-cli"
) -> str:
    """
    处理飞书文档中的图片，根据配置下载并替换为本地相对路径
    
    Args:
        content: 文档内容
        doc_id: 飞书文档 ID
        markdown_dir: markdown 所在目录
        lark_cli_path: lark-cli 命令路径
    
    Returns:
        处理后的内容（图片链接替换为本地路径）
    """
    # 查找 Obsidian 附件配置，找不到则默认保存在当前 md 同级下的 assets 目录
    obsidian_attachment_dir = get_obsidian_attachment_dir(markdown_dir)
    if obsidian_attachment_dir:
        attachments_dir = obsidian_attachment_dir
    else:
        attachments_dir = markdown_dir / "assets"
        
    result = content
    
    # 辅助函数：执行图片下载并返回相对路径
    def handle_image_download(token_or_url: str) -> Optional[str]:
        if token_or_url.startswith("http"):
            local_path = download_image(token_or_url, attachments_dir)
        else:
            local_path = download_feishu_media(token_or_url, attachments_dir)
            
        if local_path:
            # 计算图片相对于 markdown_dir 的相对路径
            rel_path = os.path.relpath(local_path, markdown_dir).replace("\\", "/")
            return rel_path
        return None
    
    # 1. 提取并处理 HTML 格式的 <image token="..." .../> 标签
    image_tag_pattern = r'<image\s+token="([a-zA-Z0-9_-]+)"[^>]*>(?:</image>)?'
    for match in re.finditer(image_tag_pattern, content):
        full_match = match.group(0)
        token = match.group(1)
        rel_path = handle_image_download(token)
        if rel_path:
            new_img = f"![图片]({rel_path})"
            result = result.replace(full_match, new_img)
            
    # 2. 提取并处理 Markdown 格式的 ![alt](url) 标签
    images = extract_image_urls(result)
    for full_match, alt_text, url in images:
        # 如果是本地图片路径（既不是 http，也不符合简单的 feishu token 格式），则跳过
        if not url.startswith("http") and not re.match(r"^[a-zA-Z0-9_-]+$", url):
            continue
            
        rel_path = handle_image_download(url)
        if rel_path:
            new_img = f"![{alt_text}]({rel_path})"
            result = result.replace(full_match, new_img)
            
    return result


def get_image_size(file_path: Path) -> Optional[Tuple[int, int]]:
    """读取 PNG, JPEG, GIF 图片尺寸"""
    import struct
    if not file_path.exists():
        return None
    try:
        with open(file_path, "rb") as f:
            head = f.read(24)
            # PNG
            if len(head) >= 24 and head.startswith(b"\x89PNG\r\n\x1a\n"):
                w, h = struct.unpack(">II", head[16:24])
                return int(w), int(h)
            # GIF
            elif len(head) >= 10 and head.startswith((b"GIF87a", b"GIF89a")):
                w, h = struct.unpack("<HH", head[6:10])
                return int(w), int(h)
            # JPEG
            elif head.startswith(b"\xff\xd8"):
                f.seek(0)
                # Read SOI (2 bytes)
                f.read(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2:
                        break
                    # Check marker validity
                    if marker[0] != 0xff:
                        # Scan for next 0xff
                        while len(marker) > 0 and marker[0] != 0xff:
                            marker = f.read(1)
                        if len(marker) == 0:
                            break
                        # Read the marker type byte
                        marker_type = f.read(1)
                        if len(marker_type) == 0:
                            break
                        marker = b"\xff" + marker_type
                    
                    # If marker is SOS (Start of Scan) \xff\xda or EOI \xff\xd9, we stop scanning
                    if marker in (b"\xff\xda", b"\xff\xd9"):
                        break
                    
                    # Read length
                    len_bytes = f.read(2)
                    if len_bytes < 2:
                        break
                    length = struct.unpack(">H", len_bytes)[0]
                    
                    # SOF0 - SOF15 markers (except SOF4, SOF8, SOF12)
                    if marker[1] in [0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]:
                        # Read precision (1 byte)
                        f.read(1)
                        h_bytes = f.read(2)
                        w_bytes = f.read(2)
                        if len(h_bytes) < 2 or len(w_bytes) < 2:
                            break
                        h = struct.unpack(">H", h_bytes)[0]
                        w = struct.unpack(">H", w_bytes)[0]
                        return int(w), int(h)
                    else:
                        # Skip this segment
                        f.read(length - 2)
    except Exception as e:
        print(f"[WARN] 获取图片尺寸失败 {file_path}: {e}")
    return None


def process_images_for_feishu(
    content: str,
    markdown_dir: Path,
    doc_id: str,
) -> str:
    """
    处理 Obsidian 文档中的本地图片，上传到飞书
    
    Args:
        content: 文档内容
        markdown_dir: markdown 文件所在目录
        doc_id: 飞书文档 ID
    
    Returns:
        处理后的内容（本地图片链接替换为飞书 URL）
    """
    import subprocess
    import json
    
    images = extract_image_urls(content)
    
    if not images:
        return content
    
    result = content
    for full_match, alt_text, url in images:
        # 只处理本地图片
        if url.startswith("http"):
            continue
        
        # 解析本地路径（相对于 markdown_dir）
        local_path = (markdown_dir / url).resolve()
        
        if not local_path.exists():
            continue
        
        # 上传到飞书（使用 lark-cli docs +media-insert）
        try:
            # lark-cli 要求文件路径为当前目录下的相对路径
            rel_path = os.path.relpath(local_path, os.getcwd())
            if not rel_path.startswith("."):
                rel_path = "./" + rel_path
            
            # 先上传图片获取 token
            cmd = ["lark-cli", "docs", "+media-insert", "--doc", doc_id, "--file", rel_path]
            size = get_image_size(local_path)
            if size:
                width, height = size
                cmd.extend(["--width", str(width), "--height", str(height)])
            
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if proc.returncode == 0:
                # 解析输出获取图片 URL
                # lark-cli 返回格式可能是 JSON 或纯文本，并且可能混有调试日志
                output = proc.stdout.strip()
                
                # 尝试解析 JSON
                try:
                    json_start = output.find("{")
                    if json_start != -1:
                        json_str = output[json_start:]
                        parsed = json.loads(json_str)
                        file_token = None
                        if "file_token" in parsed:
                            file_token = parsed["file_token"]
                        elif "data" in parsed and isinstance(parsed["data"], dict) and "file_token" in parsed["data"]:
                            file_token = parsed["data"]["file_token"]
                        
                        if file_token:
                            size = get_image_size(local_path)
                            if size:
                                width, height = size
                                new_img = f'<img src="{file_token}" width="{width}" height="{height}" />'
                            else:
                                new_img = f'<img src="{file_token}" />'
                            result = result.replace(full_match, new_img)
                except Exception:
                    # 容错：使用正则直接匹配 file_token 或 URL
                    token_match = re.search(r'"file_token"\s*:\s*"([a-zA-Z0-9]+)"', output)
                    if token_match:
                        file_token = token_match.group(1)
                        size = get_image_size(local_path)
                        if size:
                            width, height = size
                            new_img = f'<img src="{file_token}" width="{width}" height="{height}" />'
                        else:
                            new_img = f'<img src="{file_token}" />'
                        result = result.replace(full_match, new_img)
                    else:
                        url_match = re.search(r'https://[^\s]+', output)
                        if url_match:
                            feishu_url = url_match.group(0).strip("'\")")
                            size = get_image_size(local_path)
                            if size:
                                width, height = size
                                new_img = f'<img src="{feishu_url}" width="{width}" height="{height}" />'
                            else:
                                new_img = f'<img src="{feishu_url}" />'
                            result = result.replace(full_match, new_img)
        except Exception as e:
            print(f"[WARN] 上传图片到飞书失败: {local_path} - {e}")
    
    return result


def markdown_to_blocks(markdown: str) -> list[Block]:
    """将 Markdown 转换为飞书文档块结构"""
    blocks = []
    lines = markdown.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # 空行
        if not line.strip():
            i += 1
            continue

        # 标题
        if line.startswith("# "):
            blocks.append(Block(BlockType.HEADING1, line[2:].strip()))
        elif line.startswith("## "):
            blocks.append(Block(BlockType.HEADING2, line[3:].strip()))
        elif line.startswith("### "):
            blocks.append(Block(BlockType.HEADING3, line[4:].strip()))
        elif line.startswith("#### "):
            blocks.append(Block(BlockType.HEADING3, line[5:].strip()))  # 飞书最多支持3级标题

        # 代码块
        elif line.startswith("```"):
            code_lines = []
            lang = line[3:].strip()
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append(Block(BlockType.CODE, "\n".join(code_lines), extra={"language": lang}))

        # 引用
        elif line.startswith("> "):
            blocks.append(Block(BlockType.QUOTE, line[2:].strip()))

        # 分割线
        elif line.strip() in ["---", "***", "___"]:
            blocks.append(Block(BlockType.DIVIDER))

        # 无序列表
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append(Block(BlockType.BULLET, line[2:].strip()))

        # 有序列表
        elif re.match(r"^\d+\. ", line):
            content = re.sub(r"^\d+\. ", "", line)
            blocks.append(Block(BlockType.ORDERED, content.strip()))

        # 待办事项
        elif line.startswith("- [ ] ") or line.startswith("- [x] "):
            checked = line[2] == "x"
            blocks.append(Block(BlockType.TODO, line[6:].strip(), extra={"checked": checked}))

        # 表格（简化处理）
        elif line.startswith("|") and "|" in line:
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            i -= 1  # 回退一行
            blocks.append(Block(BlockType.TABLE, "\n".join(table_lines)))

        # 普通文本
        else:
            blocks.append(Block(BlockType.TEXT, line))

        i += 1

    return blocks


def blocks_to_markdown(blocks: list[Block]) -> str:
    """将飞书文档块结构转换为 Markdown"""
    lines = []

    for block in blocks:
        if block.type == BlockType.HEADING1:
            lines.append(f"# {block.content}")
        elif block.type == BlockType.HEADING2:
            lines.append(f"## {block.content}")
        elif block.type == BlockType.HEADING3:
            lines.append(f"### {block.content}")
        elif block.type == BlockType.TEXT:
            lines.append(block.content)
        elif block.type == BlockType.BULLET:
            lines.append(f"- {block.content}")
        elif block.type == BlockType.ORDERED:
            lines.append(f"1. {block.content}")
        elif block.type == BlockType.TODO:
            checked = "x" if block.extra.get("checked") else " "
            lines.append(f"- [{checked}] {block.content}")
        elif block.type == BlockType.CODE:
            lang = block.extra.get("language", "")
            lines.append(f"```{lang}")
            lines.append(block.content)
            lines.append("```")
        elif block.type == BlockType.QUOTE:
            lines.append(f"> {block.content}")
        elif block.type == BlockType.DIVIDER:
            lines.append("---")
        elif block.type == BlockType.TABLE:
            lines.append(block.content)
        elif block.type == BlockType.IMAGE:
            alt = block.extra.get("alt", "")
            url = block.content
            lines.append(f"![{alt}]({url})")

        lines.append("")  # 块之间添加空行

    return "\n".join(lines)


def extract_title(markdown: str) -> Optional[str]:
    """从 Markdown 中提取标题"""
    for line in markdown.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return None


def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def convert_callouts_to_markdown_alerts(content: str) -> str:
    """将飞书 HTML 格式的 callout 块转换为 GitHub-style markdown alerts"""
    pattern = r'<callout\s+emoji="([^"]+)"[^>]*>(.*?)</callout>'
    
    def replace_callout(match):
        emoji = match.group(1)
        body = match.group(2)
        
        # 默认使用 IMPORTANT
        alert_type = "IMPORTANT"
        if emoji in ("ℹ️", "info", "note"):
            alert_type = "NOTE"
        elif emoji in ("💡", "tip"):
            alert_type = "IMPORTANT"  # 用户要求灯泡映射为 IMPORTANT
        elif emoji in ("⚠️", "warning"):
            alert_type = "WARNING"
        elif emoji in ("🚨", "danger", "caution"):
            alert_type = "CAUTION"
            
        # 格式化每行，并在类型行后加上空行
        body = body.strip("\n")
        lines = body.split("\n")
        
        formatted_lines = [f"> [!{alert_type}]", ">"]
        for line in lines:
            if line.strip():
                formatted_lines.append(f"> {line}")
            else:
                formatted_lines.append(">")
                
        return "\n".join(formatted_lines)
        
    return re.sub(pattern, replace_callout, content, flags=re.DOTALL)


def convert_markdown_alerts_to_callouts(content: str) -> str:
    """将 GitHub-style markdown alerts 转换为飞书 HTML 格式的 callout 块"""
    lines = content.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"^>\s*\[\!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$", line.strip())
        if match:
            alert_type = match.group(1)
            emoji = "💡"
            if alert_type == "NOTE":
                emoji = "ℹ️"
            elif alert_type == "TIP":
                emoji = "💡"
            elif alert_type == "IMPORTANT":
                emoji = "💡"
            elif alert_type == "WARNING":
                emoji = "⚠️"
            elif alert_type == "CAUTION":
                emoji = "🚨"
                
            callout_lines = []
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if next_line.startswith(">"):
                    content_line = next_line[1:]
                    if content_line.startswith(" "):
                        content_line = content_line[1:]
                    callout_lines.append(content_line)
                    i += 1
                else:
                    break
            
            while callout_lines and not callout_lines[0].strip():
                callout_lines.pop(0)
            while callout_lines and not callout_lines[-1].strip():
                callout_lines.pop()
                
            callout_content = "\n".join(callout_lines)
            new_lines.append(f'<callout emoji="{emoji}" background-color="light-gray" border-color="gray">\n\n{callout_content}\n\n</callout>')
        else:
            new_lines.append(line)
            i += 1
            
    return "\n".join(new_lines)


def get_feishu_whiteboard_mermaid(token: str) -> tuple[bool, str]:
    """获取飞书画板中的 Mermaid 代码"""
    import subprocess
    import json
    try:
        cmd = ["lark-cli", "whiteboard", "+query", "--whiteboard-token", token, "--output_as", "code", "--as", "user"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            output = result.stdout.strip()
            json_start = output.find("{")
            if json_start != -1:
                parsed = json.loads(output[json_start:])
                if parsed.get("ok"):
                    data = parsed.get("data", {})
                    if data.get("syntax_type") == "mermaid":
                        return True, data.get("code", "")
            return False, "无法解析画板代码输出"
        return False, result.stderr
    except Exception as e:
        return False, str(e)


def update_feishu_whiteboard_mermaid(token: str, mermaid_code: str) -> tuple[bool, str]:
    """更新飞书画板内容为 Mermaid 代码"""
    import subprocess
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", dir=".", delete=False, encoding="utf-8") as f:
        f.write(mermaid_code)
        temp_path = f.name
        
    rel_path = "./" + os.path.basename(temp_path)
    try:
        cmd = ["lark-cli", "whiteboard", "+update", "--whiteboard-token", token, "--input_format", "mermaid", "--source", "@" + rel_path, "--overwrite", "--as", "user"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def process_whiteboards_for_obsidian(content: str) -> str:
    """将 <whiteboard token="xxx"/> 标签转换为 ```mermaid ``` 代码块"""
    whiteboard_pattern = r'<whiteboard\s+token="([a-zA-Z0-9_-]+)"[^>]*>(?:</whiteboard>)?'
    result = content
    for match in re.finditer(whiteboard_pattern, content):
        full_match = match.group(0)
        token = match.group(1)
        
        print(f"[INFO] 正在获取画板 {token} 的 Mermaid 代码...")
        success, code = get_feishu_whiteboard_mermaid(token)
        if success:
            new_block = f"```mermaid\n%% whiteboard_token: {token}\n{code}\n```"
            result = result.replace(full_match, new_block)
        else:
            print(f"[WARN] 无法获取画板 {token} 的 Mermaid 代码: {code}")
            
    return result


def process_whiteboards_for_feishu(content: str) -> str:
    """将 ```mermaid ... ``` 代码块中的画板上传并还原为 <whiteboard token="xxx"/> 标签"""
    pattern = r'```mermaid\s*\n%%\s*whiteboard_token:\s*([a-zA-Z0-9_-]+)\s*\n(.*?)\n```'
    
    result = content
    for match in re.finditer(pattern, content, flags=re.DOTALL):
        full_match = match.group(0)
        token = match.group(1)
        mermaid_code = match.group(2)
        
        mermaid_code = mermaid_code.strip("\n")
        
        print(f"[INFO] 正在更新画板 {token}...")
        success, err = update_feishu_whiteboard_mermaid(token, mermaid_code)
        if success:
            new_tag = f'<whiteboard token="{token}"/>'
            result = result.replace(full_match, new_tag)
        else:
            print(f"[WARN] 无法更新画板 {token}: {err}")
            
    return result


def convert_mentions_to_markdown_links(content: str) -> str:
    """将 <mention-doc> 或 <cite> 等标签转换为标准 Markdown 超链接，防止飞书同步时出现格式问题"""
    # 替换 <mention-doc token="xxx" type="wiki">标题</mention-doc>
    def replace_mention(match):
        token = match.group(1)
        doc_type = match.group(2)
        title = match.group(3)
        # 根据 type 决定是 wiki 还是 docx，默认 wiki
        path_type = "wiki" if doc_type == "wiki" else "docx"
        return f"[{title}](https://xreal.feishu.cn/{path_type}/{token})"

    pattern_mention = r'<mention-doc\s+token="([^"]+)"\s+type="([^"]+)"[^>]*>(.*?)</mention-doc>'
    content = re.sub(pattern_mention, replace_mention, content, flags=re.DOTALL)

    # 替换 <cite doc-id="xxx" file-type="wiki" title="标题" ...></cite>
    def replace_cite(match):
        doc_id = match.group(1)
        file_type = match.group(2)
        title = match.group(3)
        path_type = "wiki" if file_type == "wiki" else "docx"
        return f"[{title}](https://xreal.feishu.cn/{path_type}/{doc_id})"

    pattern_cite = r'<cite\s+doc-id="([^"]+)"\s+file-type="([^"]+)"\s+title="([^"]+)"[^>]*>(.*?)</cite>'
    content = re.sub(pattern_cite, replace_cite, content, flags=re.DOTALL)
    
    # 兼容自闭合格式 <cite doc-id="xxx" file-type="wiki" title="标题" />
    pattern_cite_self_closing = r'<cite\s+doc-id="([^"]+)"\s+file-type="([^"]+)"\s+title="([^"]+)"[^>]*/>'
    content = re.sub(pattern_cite_self_closing, replace_cite, content, flags=re.DOTALL)

    return content


def fix_bold_colons(content: str) -> str:
    """将 Markdown 加粗语法中包裹在内部的冒号（中英文）移到加粗符号外部，防止飞书解析错误"""
    # 匹配 **文本：** 或 **文本:**
    content = re.sub(r'\*\*([^*]+?)([：:])\*\*', r'**\1**\2', content)
    # 匹配 __文本：__ 或 __文本:__
    content = re.sub(r'__([^_]+?)([：:])__', r'__\1__\2', content)
    return content


if __name__ == "__main__":
    # 测试
    test_md = """
# 测试文档

这是一段普通文本。

## 二级标题

- 无序列表项 1
- 无序列表项 2

### 三级标题

1. 有序列表项 1
2. 有序列表项 2

> 这是一段引用

```python
print("Hello, World!")
```

---

- [ ] 待办事项
- [x] 已完成事项
"""

    blocks = markdown_to_blocks(test_md)
    print(f"解析到 {len(blocks)} 个块:")
    for block in blocks:
        print(f"  {block.type.value}: {block.content[:30] if block.content else ''}...")

    print("\n转换回 Markdown:")
    print(blocks_to_markdown(blocks))
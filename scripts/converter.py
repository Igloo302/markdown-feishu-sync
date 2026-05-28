#!/usr/bin/env python3
"""
Markdown 与飞书文档块格式转换工具
"""

import re
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


def process_images_for_obsidian(
    content: str, 
    doc_id: str,
    obsidian_vault: Path,
    lark_cli_path: str = "lark-cli"
) -> str:
    """
    处理飞书文档中的图片，下载到 Obsidian attachments 目录
    
    Args:
        content: 文档内容
        doc_id: 飞书文档 ID
        obsidian_vault: Obsidian vault 路径
        lark_cli_path: lark-cli 命令路径
    
    Returns:
        处理后的内容（图片链接替换为本地路径）
    """
    # 提取图片 URL
    images = extract_image_urls(content)
    
    if not images:
        return content
    
    # 创建 attachments 目录
    attachments_dir = obsidian_vault / "attachments" / doc_id
    
    result = content
    for full_match, alt_text, url in images:
        # 判断是否是飞书图片
        if "feishu.cn" in url or "larksuite.com" in url:
            # 下载图片
            local_path = download_image(url, attachments_dir)
            if local_path:
                # 替换为 Obsidian 相对路径
                relative_path = f"attachments/{doc_id}/{local_path.name}"
                new_img = f"![{alt_text}]({relative_path})"
                result = result.replace(full_match, new_img)
        else:
            # 非飞书图片，尝试直接下载
            local_path = download_image(url, attachments_dir)
            if local_path:
                relative_path = f"attachments/{doc_id}/{local_path.name}"
                new_img = f"![{alt_text}]({relative_path})"
                result = result.replace(full_match, new_img)
    
    return result


def process_images_for_feishu(
    content: str,
    obsidian_vault: Path,
    doc_id: str,
) -> str:
    """
    处理 Obsidian 文档中的本地图片，上传到飞书
    
    Args:
        content: 文档内容
        obsidian_vault: Obsidian vault 路径
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
        
        # 解析本地路径
        if url.startswith("attachments/"):
            local_path = obsidian_vault / url
        else:
            local_path = obsidian_vault / url
        
        if not local_path.exists():
            continue
        
        # 上传到飞书（使用 lark-cli docs +media-insert）
        try:
            # 先上传图片获取 token
            cmd = ["lark-cli", "docs", "+media-insert", "--doc", doc_id, str(local_path)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if proc.returncode == 0:
                # 解析输出获取图片 URL
                # lark-cli 返回格式可能是 JSON 或纯文本
                output = proc.stdout.strip()
                
                # 尝试解析 JSON
                try:
                    data = json.loads(output)
                    if "file_token" in data:
                        feishu_url = f"https://open.feishu.cn/open-apis/drive/v1/medias/{data['file_token']}/download"
                        new_img = f"![{alt_text}]({feishu_url})"
                        result = result.replace(full_match, new_img)
                except json.JSONDecodeError:
                    # 纯文本输出，尝试提取 URL
                    url_match = re.search(r'https://[^\s]+', output)
                    if url_match:
                        feishu_url = url_match.group(0)
                        new_img = f"![{alt_text}]({feishu_url})"
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
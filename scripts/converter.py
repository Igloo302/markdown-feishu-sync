#!/usr/bin/env python3
"""
Markdown 与飞书文档块格式转换工具
"""

import re
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum


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
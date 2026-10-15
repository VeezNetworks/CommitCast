import html
from datetime import datetime

def escape_html_text(text: str) -> str:
    if not text:
        return ""
    return html.escape(str(text))

def format_short_sha(sha: str, length: int = 7) -> str:
    if not sha:
        return ""
    return sha[:length]

def format_github_commit_link(repository: str, sha: str) -> str:
    short_sha = format_short_sha(sha)
    url = f"https://github.com/{repository}/commit/{sha}"
    return f'<a href="{url}"><code>{short_sha}</code></a>'

def format_iso_timestamp(timestamp_str: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y %H:%M UTC")
    except Exception:
        return timestamp_str

import re

def markdown_to_telegram_html(text: str, max_length: int = 3500) -> str:
    """
    Parses both Markdown and HTML input from GitHub (issues, PRs, commits),
    protecting code blocks, inline code, and links, while rendering valid Telegram HTML
    and eliminating unparsed raw HTML tags or Telegram entity nesting issues.
    """
    if not text:
        return ""
    text = str(text).strip()
    if len(text) > max_length:
        text = text[:max_length] + "\n... (truncated)"

    # 1. Normalize linebreaks
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # 2. Extract and protect code blocks (both ```...``` and <pre><code>...</code></pre> and <pre>...</pre>)
    code_blocks = []
    def save_code_block(code_content, lang=""):
        pure_code = html.unescape(code_content.strip("\r\n"))
        # If code block lines have leading markdown quote prefix "> " or "&gt; ", strip it
        code_lines = pure_code.split("\n")
        cleaned_lines = []
        for line in code_lines:
            line_cleaned = re.sub(r"^(?:>|&gt;)\s?", "", line)
            cleaned_lines.append(line_cleaned)
        pure_code = "\n".join(cleaned_lines)
        escaped_code = html.escape(pure_code)
        idx = len(code_blocks)
        code_blocks.append(f"<pre><code>{escaped_code}</code></pre>")
        return f"\n@@@CODEBLOCK_{idx}@@@\n"

    # Match ```lang\ncode\n```
    def replace_fenced_code(m):
        lang = m.group(1).strip()
        code = m.group(2)
        return save_code_block(code, lang)
    text = re.sub(r"```([a-zA-Z0-9_+-]*)\r?\n?(.*?)```", replace_fenced_code, text, flags=re.DOTALL)

    # Match <pre><code>...</code></pre> or <pre>...</pre>
    def replace_html_pre(m):
        code = m.group(1)
        code = re.sub(r"^<code(?:\s+[^>]*)?>(.*?)</code>$", r"\1", code, flags=re.DOTALL | re.IGNORECASE)
        return save_code_block(code)
    text = re.sub(r"<pre(?:\s+[^>]*)?>(.*?)</pre>", replace_html_pre, text, flags=re.DOTALL | re.IGNORECASE)

    # 3. Extract and protect inline code (both `...` and <code>...</code>)
    inline_codes = []
    def save_inline_code(code_content):
        pure_code = html.unescape(code_content)
        escaped_code = html.escape(pure_code)
        idx = len(inline_codes)
        inline_codes.append(f"<code>{escaped_code}</code>")
        return f"@@@INLINECODE_{idx}@@@"

    text = re.sub(r"<code(?:\s+[^>]*)?>(.*?)</code>", lambda m: save_inline_code(m.group(1)), text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"`([^`\r\n]+)`", lambda m: save_inline_code(m.group(1)), text)

    # 4. Extract and protect existing valid links: [text](url) and <a href="...">...</a>
    links = []
    def save_link(url, link_text):
        idx = len(links)
        safe_url = html.escape(url.strip())
        safe_text = html.escape(html.unescape(link_text.strip()))
        links.append(f'<a href="{safe_url}">{safe_text}</a>')
        return f"@@@LINK_{idx}@@@"

    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', lambda m: save_link(m.group(1), m.group(2)), text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", lambda m: save_link(m.group(2), m.group(1)), text)

    # 5. Normalize HTML blockquotes: <blockquote>...</blockquote>
    text = re.sub(r"<blockquote(?:\s+[^>]*)?>", "\n@@@BQ_START@@@\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</blockquote>", "\n@@@BQ_END@@@\n", text, flags=re.IGNORECASE)

    # 6. Normalize Markdown blockquotes (> line)
    lines = text.split("\n")
    new_lines = []
    in_quote = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("> "):
            if not in_quote:
                new_lines.append("@@@BQ_START@@@")
                in_quote = True
            new_lines.append(stripped[2:])
        elif stripped == ">":
            if not in_quote:
                new_lines.append("@@@BQ_START@@@")
                in_quote = True
            new_lines.append("")
        else:
            if in_quote and stripped != "@@@BQ_START@@@" and stripped != "@@@BQ_END@@@":
                new_lines.append("@@@BQ_END@@@")
                in_quote = False
            new_lines.append(line)
    if in_quote:
        new_lines.append("@@@BQ_END@@@")
    text = "\n".join(new_lines)

    # 7. Flatten nested blockquotes so Telegram never receives nested <blockquote>
    tokens = text.split("\n")
    merged_lines = []
    depth = 0
    for l in tokens:
        s = l.strip()
        if s == "@@@BQ_START@@@":
            if depth == 0:
                merged_lines.append("@@@BQ_START@@@")
            depth += 1
        elif s == "@@@BQ_END@@@":
            depth = max(0, depth - 1)
            if depth == 0:
                merged_lines.append("@@@BQ_END@@@")
        else:
            merged_lines.append(l)
    if depth > 0:
        merged_lines.append("@@@BQ_END@@@")
    text = "\n".join(merged_lines)

    # 8. Prevent <pre> from ever being inside <blockquote>: split blockquote around @@@CODEBLOCK_
    lines = text.split("\n")
    split_lines = []
    in_bq = False
    for l in lines:
        s = l.strip()
        if s == "@@@BQ_START@@@":
            in_bq = True
            split_lines.append(l)
        elif s == "@@@BQ_END@@@":
            in_bq = False
            split_lines.append(l)
        elif "@@@CODEBLOCK_" in l:
            if in_bq:
                split_lines.append("@@@BQ_END@@@")
                split_lines.append(l)
                split_lines.append("@@@BQ_START@@@")
            else:
                split_lines.append(l)
        else:
            split_lines.append(l)
    text = "\n".join(split_lines)

    # Remove empty blockquotes: @@@BQ_START@@@ followed immediately by @@@BQ_END@@@
    text = re.sub(r"@@@BQ_START@@@\s*@@@BQ_END@@@", "", text)

    # 9. Escape all raw characters (so arbitrary angle brackets or & won't break Telegram)
    text = html.escape(html.unescape(text))

    # 10. Convert Markdown & HTML inline formatting:
    # Headers
    text = re.sub(r"^(?:#{1,6})\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Bold: **bold** or __bold__ or <b>/<strong>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"&lt;b&gt;(.*?)&lt;/b&gt;", r"<b>\1</b>", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;strong&gt;(.*?)&lt;/strong&gt;", r"<b>\1</b>", text, flags=re.IGNORECASE)

    # Italic: *italic* or _italic_ or <i>/<em>
    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"&lt;i&gt;(.*?)&lt;/i&gt;", r"<i>\1</i>", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;em&gt;(.*?)&lt;/em&gt;", r"<i>\1</i>", text, flags=re.IGNORECASE)

    # Strikethrough
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"&lt;s&gt;(.*?)&lt;/s&gt;", r"<s>\1</s>", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;del&gt;(.*?)&lt;/del&gt;", r"<s>\1</s>", text, flags=re.IGNORECASE)

    # Bullets
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)

    # 11. Clean up and restore blockquotes
    text = text.replace("@@@BQ_START@@@", "<blockquote>")
    text = text.replace("@@@BQ_END@@@", "</blockquote>")

    # Clean empty blockquotes
    text = re.sub(r"<blockquote>\s*</blockquote>", "", text)

    # 12. Restore links
    for i, l_tag in enumerate(links):
        text = text.replace(f"@@@LINK_{i}@@@", l_tag)

    # 13. Restore inline code
    for i, code_tag in enumerate(inline_codes):
        text = text.replace(f"@@@INLINECODE_{i}@@@", code_tag)

    # 14. Restore code blocks
    for i, code_block_tag in enumerate(code_blocks):
        text = text.replace(f"@@@CODEBLOCK_{i}@@@", code_block_tag)

    # Clean multiple excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

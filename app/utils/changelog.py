import re
from datetime import datetime

class ChangelogFormatter:
    @staticmethod
    def extract_title_and_description(raw_line: str):
        cleaned = raw_line.strip()
        cleaned = re.sub(r"^[a-zA-Z0-9_\-\./]+#\d+\s*", "", cleaned)
        cleaned = re.sub(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|add|update)(\([^\)]+\))?!?:+\s*", "", cleaned, flags=re.I)
        if not cleaned:
            return "General Updates", "Routine code maintenance and enhancements."
        separators = [" – ", " - ", ": "]
        for sep in separators:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                title_candidate = parts[0].strip().title()
                desc_candidate = parts[1].strip()
                if len(title_candidate) > 2 and len(desc_candidate) > 2:
                    return title_candidate, desc_candidate[0].upper() + desc_candidate[1:]
        lower_cleaned = cleaned.lower()
        file_ext_match = re.search(r"([a-zA-Z0-9_\-]+)\.(go|py|js|ts|rs|c|cpp|java|kt|json|yaml|yml|md)", lower_cleaned)
        if file_ext_match:
            module_name = file_ext_match.group(1).replace("_", " ").replace("-", " ").title()
            ext = file_ext_match.group(2)
            if "bot" in lower_cleaned:
                return "Bot Core Engine", "Implemented bot setup, event handlers, and core application logic."
            elif "file" in lower_cleaned:
                return "File Management", "Added file processing, storage handlers, and data operations."
            elif "main" in lower_cleaned:
                return "Application Main Entry", "Updated core application bootstrap and lifecycle management."
            elif "config" in lower_cleaned:
                return "Configuration Module", "Updated configuration settings, variables, and environment setup."
            else:
                return f"{module_name} Module", f"Implemented {module_name.lower()} components and service routines."

        words = cleaned.split()
        if len(words) <= 3:
            first_w = words[0].lower()
            remainder = " ".join(words[1:]) if len(words) > 1 else words[0]
            if first_w in ["add", "new", "create", "support", "init"]:
                title = remainder.title() if remainder else cleaned.title()
                desc = f"Added {remainder.lower()} to enhance project capabilities."
                return title, desc
            elif first_w in ["fix", "patch", "resolve", "bug"]:
                title = remainder.title() if remainder else cleaned.title()
                desc = f"Resolved issues in {remainder.lower()} for improved reliability."
                return title, desc
            elif first_w in ["update", "edit", "change", "refactor"]:
                title = remainder.title() if remainder else cleaned.title()
                desc = f"Refined {remainder.lower()} with modern implementation standards."
                return title, desc
            else:
                title = cleaned.title()
                desc = f"Integrated and tested {cleaned.lower()} for current release cycle."
                return title, desc
        title_word_count = min(3, max(2, len(words) // 2))
        title = " ".join(words[:title_word_count]).title()
        desc = cleaned[0].upper() + cleaned[1:]
        return title, desc

    @classmethod
    def categorize_commits(cls, commits_list: list):
        additions_list = []
        breaking_list = []
        improvements_list = []
        for item in commits_list:
            message_text = item.get("commit_message", "").strip()
            first_line = message_text.splitlines()[0] if message_text else "Update"
            lower_line = first_line.lower()
            title, desc = cls.extract_title_and_description(first_line)
            if any(k in lower_line for k in ["break", "deprecat", "drop", "breaking change"]):
                breaking_list.append((title, desc))
            elif any(lower_line.startswith(p) for p in ["feat", "add", "new", "create", "support", "allow", "implement", "init"]):
                additions_list.append((title, desc))
            elif any(k in lower_line for k in ["feat", "feature", "support", "add", ".go", ".py", ".js"]):
                additions_list.append((title, desc))
            else:
                improvements_list.append((title, desc))
        return additions_list, breaking_list, improvements_list

    @staticmethod
    def resolve_link_emoji(title: str):
        lower_title = title.lower()
        if any(w in lower_title for w in ["doc", "guide", "wiki"]):
            return '<tg-emoji emoji-id="5368324170671202286">📑</tg-emoji>'
        if any(w in lower_title for w in ["group", "chat", "support", "community"]):
            return '<tg-emoji emoji-id="5368324170671202288">📚</tg-emoji>'
        if any(w in lower_title for w in ["news", "update", "channel", "about"]):
            return '<tg-emoji emoji-id="5368324170671202286">⭐</tg-emoji>'
        if any(w in lower_title for w in ["changelog", "release"]):
            return '<tg-emoji emoji-id="5368324170671202287">🔥</tg-emoji>'
        if any(w in lower_title for w in ["install", "pypi", "npm", "crate", "package", "download"]):
            return '<tg-emoji emoji-id="5368324170671202288">📟</tg-emoji>'
        if any(w in lower_title for w in ["web", "site"]):
            return '<tg-emoji emoji-id="5368324170671202286">🌐</tg-emoji>'
        return '<tg-emoji emoji-id="5368324170671202288">🔗</tg-emoji>'

    @classmethod
    def generate_release_notes_text(cls, month_title: str, commits_list: list, repository_name: str = "Repository", custom_links: list = None, is_premium: bool = True):
        repo_short_name = repository_name.split("/")[-1] if "/" in repository_name else repository_name
        additions, breaking, improvements = cls.categorize_commits(commits_list)
        sparkle = '<tg-emoji emoji-id="5368324170671202286">✨</tg-emoji>'
        party = '<tg-emoji emoji-id="5368324170671202288">🎉</tg-emoji>'
        alert = '<tg-emoji emoji-id="5368324170671202287">‼️</tg-emoji>'
        tools = '<tg-emoji emoji-id="5368324170671202288">🛠️</tg-emoji>'
        idea = '<tg-emoji emoji-id="5368324170671202286">💡</tg-emoji>'
        folder = '<tg-emoji emoji-id="5368324170671202288">📁</tg-emoji>'

        if additions:
            if len(additions) >= 2:
                header_title = f"{sparkle} <b>{additions[0][0]}, {additions[1][0]} and More!</b>"
            else:
                header_title = f"{sparkle} <b>{additions[0][0]} and More!</b>"
        elif improvements:
            header_title = f"{sparkle} <b>Performance Enhancements, Bug Fixes and More!</b>"
        else:
            header_title = f"{sparkle} <b>{repo_short_name} — {month_title} Release Updates!</b>"
        sections = [header_title, ""]
        sections.append(f"{party} <b>What's New?</b>")
        if additions:
            for title, desc in additions[:8]:
                sections.append(f"• <b>{title}</b> – {desc}")
        elif not improvements and not breaking:
            sections.append(f"• <b>Continuous Stability & Maintenance</b> – Regular updates and maintenance cycles for {repo_short_name}.")
            sections.append(f"• <b>Performance Optimizations</b> – Refined internal logic and automated quality checks.")
        else:
            for title, desc in improvements[:4]:
                sections.append(f"• <b>{title}</b> – {desc}")
        sections.append("")
        if breaking:
            sections.append(f"{alert} <b>Breaking Changes</b>")
            for title, desc in breaking[:5]:
                sections.append(f"• <b>{title}</b> – {desc}")
            sections.append("")
        if improvements and additions:
            sections.append(f"{tools} <b>Improvements & Fixes</b>")
            for title, desc in improvements[:6]:
                sections.append(f"• <b>{title}</b> – {desc}")
            sections.append("")
        sections.append("<blockquote>")
        sections.append(f"{idea} <b>{repo_short_name} {month_title} Notes</b>")
        sections.append(f"All updates have been verified for stability. Update to the latest release to take advantage of these features!")
        sections.append("</blockquote>")
        sections.append("")
        sections.append(f"{folder} <b>{repo_short_name} Repo</b>")
        sections.append(f"https://github.com/{repository_name}")
        sections.append("")
        if custom_links:
            for link_item in custom_links:
                title = link_item.get("title", "Link")
                target = link_item.get("target") or link_item.get("url", "")
                if "<tg-emoji" in title:
                    sections.append(f"<b>{title}</b>")
                else:
                    emoji = cls.resolve_link_emoji(title)
                    sections.append(f"{emoji} <b>{title}</b>")
                sections.append(f"{target}")
                sections.append("")
        return "\n".join(sections).strip()

changelog_service = ChangelogFormatter()

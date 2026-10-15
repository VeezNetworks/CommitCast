import re
from pyrogram.enums import ButtonStyle, MessageEntityType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

class ButtonMarkupBuilder:
    @staticmethod
    def parse_custom_markup_definitions(input_text: str, entities: list = None):
        structured_buttons = []
        raw_lines = [line.strip() for line in input_text.strip().splitlines() if line.strip()]
        
        custom_emoji_map = {}
        if entities:
            search_index = 0
            for line in raw_lines:
                pos = input_text.find(line, search_index)
                if pos != -1:
                    line_end = pos + len(line)
                    search_index = line_end
                    for ent in entities:
                        if getattr(ent, "type", None) == MessageEntityType.CUSTOM_EMOJI:
                            if pos <= ent.offset < line_end:
                                custom_emoji_map[line] = str(ent.custom_emoji_id)

        for line in raw_lines:
            tokens = [token.strip() for token in line.split("-")]
            if len(tokens) >= 3 and tokens[0].lower() == "btn":
                button_caption = tokens[1]
                target_value = tokens[2]
                style_name = tokens[3].lower() if len(tokens) >= 4 else "default"
                
                icon_emoji_id = custom_emoji_map.get(line)
                if not icon_emoji_id:
                    tag_match = re.search(r'emoji-id=["\'](\d+)["\']', line)
                    if tag_match:
                        icon_emoji_id = tag_match.group(1)

                clean_caption = re.sub(r'<[^>]+>', '', button_caption).strip() or button_caption
                is_url_action = target_value.startswith("http://") or target_value.startswith("https://") or target_value.startswith("t.me/")
                if target_value.startswith("t.me/"):
                    target_value = "https://" + target_value
                    is_url_action = True

                structured_buttons.append({
                    "caption": clean_caption,
                    "target": target_value,
                    "is_url": is_url_action,
                    "icon_custom_emoji_id": icon_emoji_id,
                    "style": style_name
                })
        return structured_buttons

    @staticmethod
    def parse_custom_links_definitions(input_text: str):
        structured_links = []
        raw_lines = [line.strip() for line in input_text.strip().splitlines() if line.strip()]
        for line in raw_lines:
            tokens = [token.strip() for token in line.split("-")]
            if len(tokens) >= 3 and tokens[0].lower() == "link":
                structured_links.append({"title": tokens[1], "target": tokens[2]})
            elif len(tokens) >= 2:
                structured_links.append({"title": tokens[0], "target": tokens[1]})
        return structured_links

    @staticmethod
    def build_inline_keyboard_from_definitions(button_definitions: list, enable_rich_styles: bool = True):
        if not button_definitions:
            return None
        style_map = {
            "primary": ButtonStyle.PRIMARY,
            "danger": ButtonStyle.DANGER,
            "success": ButtonStyle.SUCCESS,
            "default": ButtonStyle.DEFAULT
        }
        keyboard_rows = []
        for item in button_definitions:
            caption = item.get("caption", "Button")
            target = item.get("target", "")
            icon_emoji_id = item.get("icon_custom_emoji_id") if enable_rich_styles else None
            style_token = item.get("style", "default")
            style_val = style_map.get(str(style_token).lower(), ButtonStyle.DEFAULT) if enable_rich_styles else ButtonStyle.DEFAULT

            if item.get("is_url", False):
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=caption,
                        url=target,
                        icon_custom_emoji_id=icon_emoji_id,
                        style=style_val
                    )
                ])
            else:
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=caption,
                        callback_data=f"notify_alert:{target[:60]}",
                        icon_custom_emoji_id=icon_emoji_id,
                        style=style_val
                    )
                ])
        return InlineKeyboardMarkup(keyboard_rows)

    @staticmethod
    def build_fallback_inline_keyboard(button_definitions: list):
        return ButtonMarkupBuilder.build_inline_keyboard_from_definitions(button_definitions, enable_rich_styles=False)

    @staticmethod
    def construct_month_selection_markup(months_list: list, action_prefix: str):
        buttons = []
        for month_name in months_list:
            callback_value = f"{action_prefix}:{month_name.lower()}"
            buttons.append(InlineKeyboardButton(text=f"📅 {month_name}", callback_data=callback_value))
        nested_rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
        return InlineKeyboardMarkup(nested_rows)

markup_builder = ButtonMarkupBuilder()

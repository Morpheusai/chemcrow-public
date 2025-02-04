from googletrans import Translator

class TranslationAgent:
    def __init__(self):
        """
        初始化翻译 Agent，使用 googletrans 提供的 Translator 类。
        """
        self.translator = Translator()

    def detect_language(self, text):
        """
        检测输入文本的语言。
        :param text: 输入文本
        :return: 检测到的语言代码（如 "en", "zh-cn"）
        """
        detected = self.translator.detect(text)
        return detected.lang

    def translate(self, text, target_lang="en", source_lang=None):
        """
        翻译文本。
        :param text: 输入文本
        :param target_lang: 目标语言代码（如 "zh-cn"）
        :param source_lang: 源语言代码（可选，默认自动检测）
        :return: 翻译后的文本
        """
        if source_lang:
            translation = self.translator.translate(text, src=source_lang, dest=target_lang)
        else:
            translation = self.translator.translate(text, dest=target_lang)
        return translation.text

# 示例使用
if __name__ == "__main__":
    agent = TranslationAgent()

    # 示例文本
    text = "你好，请问你是谁？"

    # 检测语言
    detected_lang = agent.detect_language(text)
    print(f"检测到的语言: {detected_lang}")

    # 翻译文本
    translated_text = agent.translate(text, target_lang="en")
    print(f"翻译: {translated_text}")

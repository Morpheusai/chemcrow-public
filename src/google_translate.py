import os
import requests
import logging

class googleTranslationAgent:
    def __init__(self):
        """ 初始化 Google 翻译 API 的 URL 和 API 密钥。"""
        self.api_key = os.getenv("GOOGLE_API_KEY")  # 读取环境变量中的 API 密钥
        self._translate_url = "https://translation.googleapis.com/language/translate/v2"
        self._detect_url = "https://translation.googleapis.com/language/translate/v2/detect"

    def detect_language(self, text: str) -> str:
        """检测输入文本的语言。"""
        params = {
            "q": text,
            "key": self.api_key
        }
        try:
            response = requests.post(self._detect_url, data=params, timeout=15)
            if response.status_code == 200:
                result = response.json()
                detected_language = result["data"]["detections"][0][0]["language"]
                logging.info(f"Detected language: {detected_language}")
                return detected_language
            else:
                error_message = f"Error: {response.status_code} - {response.text}"
                logging.error(f"Language detection failed. {error_message}")
                return "error"
        except Exception as e:
            logging.exception(f"An error occurred during language detection,please check the logs for more information.")
            return "An error occurred while detecting text for the input language"

    def translate(self, target: str, text: str) -> dict:
        """将文本翻译成目标语言，如果输入语言和目标语言不同的话。"""
        detected_language = self.detect_language(text)
        
        if detected_language == target:
            # 如果源语言和目标语言相同，直接返回原文本
            logging.info(f"Input text is already in {target}. No translation required.")
            return text, detected_language
        
        # 如果是其它语言，进行翻译
        params = {
            "q": text,
            "target": target,
            "key": self.api_key
        }
        try:
            # 发送 POST 请求到 Google 翻译 API
            response = requests.post(self._translate_url, data=params, timeout=15)
            
            # 检查是否成功响应
            if response.status_code == 200:
                result = response.json()
                translate_text = result["data"]["translations"][0]["translatedText"]
                detected_source_language = result["data"]["translations"][0]["detectedSourceLanguage"]
                
                logging.info(f"Successfully translated: {text} -> {translate_text} (Detected Source: {detected_source_language})")
                return translate_text, detected_source_language
            else:
                # 如果请求失败，记录错误并返回错误信息
                error_message = f"Error: {response.status_code} - {response.text}"
                logging.error(f"Translation failed. {error_message}")
                return None, error_message
        except Exception as e:
            # 捕获任何异常并记录到日志
            logging.exception(f"An error occurred while translating: {e}")
            return None, f"An error occurred, please check the logs for more information."

if __name__ == "__main__":
    # 创建一个 googleTranslationAgent 对象
    agent = googleTranslationAgent()
    
    # 调用 translate 方法进行翻译
    translated_text, detected_language = agent.translate("zh-CN", "hello, world")
    
    # 输出翻译结果
    if translated_text:
        print(f"Translated Text: {translated_text}")
        print(f"Detected Source Language: {detected_language}")
    else:
        print(f"Translation failed: {detected_language}")


    print("\n")

    # 测试输入为非英文
    translated_text, detected_language = agent.translate("zh-CN", "你好，世界")
    print(f"Translated Text: {translated_text}")
    print(f"Detected Language: {detected_language}")

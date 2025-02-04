# Description: 上下文处理代理，用于处理对话历史并生成对话总结      
from langchain.chat_models import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage, SystemMessage

class ContextProcessingAgent:
    def __init__(self, openai_api_key, model="gpt-4"):
        """初始化上下文处理代理，基于 LangChain 实现"""
        self.model = ChatOpenAI(
            model=model,
            openai_api_key=openai_api_key,
            temperature=0.7,
        )

    def process_context(self, messages):
        """
        处理上下文.
        支持 LangChain 消息格式 (AIMessage, HumanMessage 等).
        """
        if not isinstance(messages, list) or not all(hasattr(msg, 'content') for msg in messages):
            return "Error: Invalid message format"
        
        # 格式化消息内容为 role: content
        # context = "\n".join(
        #     f"{type(msg).__name__.replace('Message', '').lower()}: {msg.content}"
        #     for msg in messages
        # )
        context = "\n".join(
            f"{msg.type}: {msg.content}"
            for msg in messages
        )
        summary = self.summarize_context(context)
        return summary

    def summarize_context(self, context):
        """使用 LangChain 的 OpenAI 模型生成上下文总结."""
        messages = [
            SystemMessage(content="You are an intelligent assistant that summarizes the conversation history and generates a more complete and accurate concise question based on the context. Your job is to fully understand the context of the conversation, extract key information, and rephrase the final user question in an output that is clearly understandable without context."),
            HumanMessage(content=f"Here is the conversation history:\n{context}\nPlease summarize the key messages of the conversation and generate a more complete concise question based on the last user question so that it can be clearly understood without context:")
        ]
        
        try:
            response = self.model(messages)
            summary = response.content.strip()
            return summary
        except Exception as e:
            return f"Error: Unable to generate summary({str(e)})"

if __name__ == "__main__":
    import os
    api = os.getenv("OPENAI_API_KEY")
    agent = ContextProcessingAgent(api)
    messages = [
        HumanMessage(content="布洛芬的结构是什么？"),
        AIMessage(content="布洛芬是一种非甾体抗炎药（NSAID），其化学结构为 C13H18O2，具体结构为一个芳香环连接一个羧基和一个异丁基。"),
        HumanMessage(content="它的分子量是什么？")
    ]
    # context = agent.process_context(messages)
    # print(context)
    # summary = agent.summarize_context(context)
    # print(summary)
    summary = agent.process_context(messages)
    print(summary)





    
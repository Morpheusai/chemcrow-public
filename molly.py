import os
import pandas as pd
import streamlit as st
import uuid

from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from PIL import Image

from config import CONFIG_YAML
from chemcrow.agents import ChemCrow
from langchain.callbacks import FileCallbackHandler
from chemcrow.frontend.streamlit_callback_handler import StreamlitCallbackHandlerChem

from src.context_process_agent import ContextProcessingAgent
from src.log import logger
from src.translate_agent import TranslationAgent

MODEL_NAME = CONFIG_YAML["LLM"]["model_name"]
TEMPER = CONFIG_YAML["LLM"]["temperature"]

#获取api加载模型工具
llm_api_key = os.getenv("OPENAI_API_KEY") 

logo = Image.open("assets/molly_icon.png")
st.set_page_config(page_title="Molly", page_icon=logo)

#chemcrow agent 
chem_agent = ChemCrow(
    model = MODEL_NAME, 
    tools_model = MODEL_NAME, 
    temp = TEMPER, 
    streaming = True,
    openai_api_key = llm_api_key,
    local_rxn = True
).agent_executor

# translator
trans_agent = TranslationAgent()

# 上下文处理
context_agent = ContextProcessingAgent(
    openai_api_key = llm_api_key,
    model = MODEL_NAME
)

# 设置侧边栏样式
st.markdown(
    """
    <style>
    [data-testid="stSidebar"][aria-expanded="true"]{
        min-width: 350px;
        max-width: 350px;
    }
    """,
    unsafe_allow_html=True,
)

tools = chem_agent.tools

tool_list = pd.Series(
    {f"✅ {t.name}":t.description for t in tools}
).reset_index()
tool_list.columns = ['Tool', 'Description']

# sidebar
with st.sidebar:
    chemcrow_logo = Image.open('assets/molly.png')
    st.image(chemcrow_logo)

    st.markdown('---')
    # Display available tools
    st.markdown(f"# {len(tool_list)} available tools")
    st.dataframe(
        tool_list,
        use_container_width=True,
        hide_index=True,
        height=200
    )

#message处理
if "messages" not in st.session_state:
    st.session_state.messages = []
if 'session_id' not in st.session_state:
    st.session_state['session_id'] = st.query_params.get('session_id', [str(uuid.uuid4())])[0]  

# Ensure input counter is set
if 'input_counter' not in st.session_state:
    st.session_state['input_counter'] = 0

# Set up memory
msgs = StreamlitChatMessageHistory(key="messages")
if len(msgs.messages) == 0:
    msgs.add_ai_message("How can I help you?")

# Render current messages from StreamlitChatMessageHistory
for msg in msgs.messages:
    st.chat_message(msg.type).write(msg.content)    
    assert msg.type in ["human", "ai"]
    # assert msg.type in ["human", "assistant"]

if question := st.chat_input("please ask me a question"):
    st.chat_message("human").write(question)
    msgs.add_user_message(question)
    st.session_state['input_counter'] += 1
    logger.info(f"ID: {st.session_state['session_id']}, 用户输入: \n{question}")
    # st.session_state.messages.append({'role':'user','content':question})
    with st.chat_message("ai"):
        #file_callback = FileCallbackHandler(CONFIG_YAML["LOGGER"]["file"])
        file_callback = FileCallbackHandler(CONFIG_YAML["LOGGER"]["dir"] + st.session_state['session_id'])
        st_callback = StreamlitCallbackHandlerChem(
            st.container(),
            max_thought_containers = 3,
            collapse_completed_thoughts = True,
            output_placeholder=st.session_state
        )
        # Process context only if there are two or more inputs
        if st.session_state['input_counter'] >= 2:
            logger.info(f"!!!ID: {st.session_state['session_id']}, 多轮输入，需要进行上下文处理!!!")
            context = context_agent.process_context(msgs.messages)
            full_input = f"{context}"
        else:
            full_input = question
        logger.info(f"ID: {st.session_state['session_id']}, 用户经过多轮预处理后的输入:\n{full_input}")

        question_det_lang = trans_agent.detect_language(question)
        full_det_lang = trans_agent.detect_language(full_input)
        # Translate the full_input content to English, if it is not in English
        if not full_det_lang == "en":
            logger.info(f"!!!ID: {st.session_state['session_id']}, 中文输入，需要进行中转英处理!!!")
            full_input = trans_agent.translate(full_input)
        logger.info(f"ID: {st.session_state['session_id']}, 用户经过转译预处理后的输入:\n{full_input}")
        
        try:
            answer = chem_agent.run(full_input, callbacks=[st_callback, file_callback])
            logger.info(f"ID: {st.session_state['session_id']}, agent输出:\n{answer}")
            if not question_det_lang == "en":
                answer = trans_agent.translate(answer, target_lang=question_det_lang)
            logger.info(f"ID: {st.session_state['session_id']}, 经过转译后的最终输出:\n{answer}")
            st.markdown(answer)
            msgs.add_ai_message(answer)
        except Exception as e:
            st.error("There was an error processing your request. Please try again.")
            logger.error(f"ID: {st.session_state['session_id']}, Error: {e}")
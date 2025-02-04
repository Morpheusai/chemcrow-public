import streamlit as st
import os
from ansi2html import Ansi2HTMLConverter

# 设置页面标题
st.title("日志查看器")

# 读取并显示log.txt文件
log_file_path = os.path.join("logs", "log.txt")
if os.path.exists(log_file_path):
    with open(log_file_path, "r", encoding="utf-8") as f:
        log_content = f.read()
    st.header("log.txt 内容")
    # 使用st.text_area显示log.txt内容，并设置高度为网页的一半
    st.text_area(
        "log.txt 内容",
        value=log_content,
        height=400,  # 设置高度为400px（可根据需要调整）
        key="log_content",
        disabled=True,  # 禁止用户编辑
    )
else:
    st.error("log.txt 文件不存在")

# 获取logs文件夹下的所有.log文件
log_files = [f for f in os.listdir("logs") if f.endswith(".log")]

# 显示Agent日志文件列表
if log_files:
    st.header("选择Agent Callback日志文件")
    # 在下拉菜单中添加一个空选项
    selected_file = st.selectbox("选择一个Agent Callback日志文件", ["请选择一个ID文件"] + log_files)
    
    # 如果用户选择了文件（且不是默认的空选项），则显示文件内容
    if selected_file != "请选择一个ID文件":
        selected_file_path = os.path.join("logs", selected_file)
        with open(selected_file_path, "r", encoding="utf-8") as f:
            selected_content = f.read()
        
        # 使用 ansi2html 转换 ANSI 转义序列为 HTML
        conv = Ansi2HTMLConverter()
        html_content = conv.convert(selected_content, full=True)
        
        st.header(f"{selected_file} 内容")
        # 使用 st.components.v1.html 渲染 HTML 内容
        st.components.v1.html(html_content, height=400, scrolling=True)
else:
    st.info("logs文件夹下没有其他日志文件")
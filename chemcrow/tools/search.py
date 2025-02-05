import os
import re
import asyncio
import langchain
import molbloom
import paperqa
import paperscraper
from langchain import SerpAPIWrapper
from langchain.base_language import BaseLanguageModel
from langchain.tools import BaseTool
from langchain.embeddings.openai import OpenAIEmbeddings
from pypdf.errors import PdfReadError
from pathlib import Path
from chemcrow.utils import is_multiple_smiles, split_smiles



def paper_search(llm, query,serp_api_key= None, semantic_scholar_api_key=None):
    prompt = langchain.prompts.PromptTemplate(
        input_variables=["question"],
        template="""
        I would like to find scholarly papers to answer
        this question: {question}. Your response must be at
        most 10 words long.
        'A search query that would bring up papers that can answer
        this question would be: '""",
    )

    query_chain = langchain.chains.llm.LLMChain(llm=llm, prompt=prompt)

    search = query_chain.run(query)
    print("\nSearch:", search)
    #修改处
    search_stripped = search.strip()
    search_cleaned = re.sub(r'[<>:"/\\|?*]', '', search_stripped)
    pdir = Path("query") / search_cleaned
    papers = paperscraper.search_papers(search_cleaned, pdir=pdir, serp_api_key= serp_api_key, semantic_scholar_api_key=semantic_scholar_api_key)
    return papers


def scholar2result_llm(llm, query, k=5, max_sources=2, openai_api_key=None,serp_api_key= None, semantic_scholar_api_key=None):
    """Useful to answer questions that require
    technical knowledge. Ask a specific question."""
    try:
        papers = paper_search(llm, query, serp_api_key=serp_api_key,semantic_scholar_api_key=semantic_scholar_api_key)
    except RuntimeError as e:
    # 捕获 RuntimeError 错误
        return (f"RuntimeError occurred while searching papers: {e}")

    except Exception as e:
    # 捕获所有其他类型的异常
        return (f"An unexpected error occurred: {e}")
 
    if len(papers) == 0:
        return "Not enough papers found"
    docs = paperqa.Docs(
        llm=llm,
        summary_llm=llm,
        embeddings=OpenAIEmbeddings(openai_api_key=openai_api_key),
    )
    not_loaded = 0
    if isinstance(papers, dict):
        for path, data in papers.items():
            try:
                docs.add(path, data["citation"])
            except (ValueError, FileNotFoundError, PdfReadError, UnboundLocalError, PermissionError, AttributeError) as e:
                not_loaded += 1
        if not_loaded > 0:
            print(f"\nFound {len(papers.items())} papers but couldn't load {not_loaded}.")
        else:
            print(f"\nFound {len(papers.items())} papers and loaded all of them.")                
    else:
        return "Unexpected data format for papers."

    answer = docs.query(query, k=k, max_sources=max_sources).formatted_answer
    return answer


class Scholar2ResultLLM(BaseTool):
    name = "LiteratureSearch"
    description = (
        "Useful to answer questions that require technical "
        "knowledge. Ask a specific question."
    )
    llm: BaseLanguageModel = None
    openai_api_key: str = None
    serp_api_key: str = None
    semantic_scholar_api_key: str = None


    def __init__(self, llm, openai_api_key,serp_api_key):
        super().__init__()
        self.llm = llm
        # api keys
        self.openai_api_key = openai_api_key
        self.serp_api_key=serp_api_key

    def _run(self, query) -> str:
        return scholar2result_llm(
            self.llm,
            query,
            openai_api_key=self.openai_api_key,
            serp_api_key=self.serp_api_key
        )

    async def _arun(self, query) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("this tool does not support async")


def web_search(keywords, search_engine="google"):
    try:
        return SerpAPIWrapper(
            serpapi_api_key=os.getenv("SERP_API_KEY"), search_engine=search_engine
        ).run(keywords)
    except:
        return "No results, try another search"


class WebSearch(BaseTool):
    name = "WebSearch"
    description = (
        "Input a specific question, returns an answer from web search. "
        "Do not mention any specific molecule names, but use more general features to formulate your questions."
    )
    serp_api_key: str = None

    def __init__(self, serp_api_key: str = None):
        super().__init__()
        self.serp_api_key = serp_api_key

    def _run(self, query: str) -> str:
        if not self.serp_api_key:
            return (
                "No SerpAPI key found. This tool may not be used without a SerpAPI key."
            )
        return web_search(query)

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("Async not implemented")


class PatentCheck(BaseTool):
    name = "PatentCheck"
    description = "Input SMILES, returns if molecule is patented. You may also input several SMILES, separated by a period."

    def _run(self, smiles: str) -> str:
        """Checks if compound is patented. Give this tool only one SMILES string"""
        if is_multiple_smiles(smiles):
            smiles_list = split_smiles(smiles)
        else:
            smiles_list = [smiles]
        try:
            output_dict = {}
            for smi in smiles_list:
                r = molbloom.buy(smi, canonicalize=True, catalog="surechembl")
                if r:
                    output_dict[smi] = "Patented"
                else:
                    output_dict[smi] = "Novel"
            return str(output_dict)
        except:
            return "Invalid SMILES string"

    async def _arun(self, query: str) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError()

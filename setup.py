from setuptools import find_packages, setup

exec(open("chemcrow/version.py").read())

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="chemcrow",
    python_requires=">=3.9, <3.12",  # this temporarily fixes molbloom install, which breaks with 3.12
    version=__version__,
    description="Accurate solution of reasoning-intensive chemical tasks, powered by LLMs.",
    author="Andres M Bran, Sam Cox, Andrew White, Philippe Schwaller",
    author_email="andrew.white@rochester.edu",
    url="https://github.com/ur-whitelab/chemcrow-public",
    license="MIT",
    packages=find_packages(),
    package_data={"chemcrow": ["data/chem_wep_smi.csv"]},
    install_requires=[
        "ipython==8.32.0",
        "python-dotenv",
        "rdkit",
        "synspace==0.3.0",
        "openai==0.27.8",
        "beautifulsoup4==4.9.0",
        "molbloom",
        "paper-qa==1.1.1",
        "google-search-results",
        "googletrans==4.0.0rc1",
        "langchain_community==0.3.14",
        "langchain==0.0.275",
        "langchain_core==0.0.2",
        "nest_asyncio",
        "tiktoken",
        "rmrkl",
        "paper-scraper@git+https://github.com/blackadad/paper-scraper.git",
        "streamlit==1.41.1",
        "rxn4chemistry",
        "duckduckgo-search",
        "wikipedia",
    ],
    test_suite="tests",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)

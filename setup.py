"""
Setup script for the TradingAgents package.
"""

from setuptools import setup, find_packages

setup(
    name="tradingagents",
    version="0.1.0",
    description="Multi-Agents LLM Financial Trading Framework",
    author="TradingAgents Team",
    author_email="yijia.xiao@cs.ucla.edu",
    url="https://github.com/TauricResearch",
    packages=find_packages(),
    install_requires=[
        "langchain-openai>=0.0.2",
        "langchain-experimental>=0.0.40",
        "langgraph>=0.0.20",
        "langchain-google-genai>=0.0.10",
        "langchain-community>=0.3.0",
        "dashscope>=1.18.0",
        "pandas>=2.0.0",
        "feedparser>=6.0.0",
        "requests>=2.31.0",
        "chromadb>=0.4.0",
        "typer>=0.9.0",
        "rich>=13.0.0",
        "questionary>=2.0.1",
        "python-dotenv>=1.0.0",
        "binance-connector>=3.7.0",
        "binance-sdk-derivatives-trading-usds-futures>=4.0.0",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "tradingagents=cli.main:app",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Financial and Trading Industry",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
)

FROM quay.io/jupyter/minimal-notebook:2025-09-30

# 資源對齊 NB_RAG_Agentic，允許自訂 UID/GID 以匹配主機使用者
ARG NB_UID=1026
ARG NB_GID=516

COPY requirements.txt /tmp/requirements.txt

USER root

# 將 jovyan 的 UID/GID 調整為與主機一致，並修正主目錄權限
RUN groupmod -g ${NB_GID} users && \
    usermod -u ${NB_UID} jovyan && \
    chown -R ${NB_UID}:${NB_GID} /home/jovyan

# 必要套件：Node/npm + 三家 CLI、Python 依賴、sudo 權限
RUN apt-get update && apt-get install -yq nodejs npm && \
    npm install -g @openai/codex@latest && \
    npm install -g @anthropic-ai/claude-code@latest && \
    npm install -g @google/gemini-cli@latest && \
    npm install -g @github/copilot && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt && \
    echo "jovyan ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER ${NB_UID}

WORKDIR /home/jovyan/work

# 同時啟動 Codex app-server 與 Jupyter，禁用 token/password（限內網使用）
CMD ["sh", "-c", "codex app-server & start-notebook.py --port=${JUPYTER_PORT:-25678} --NotebookApp.token='' --NotebookApp.password=''"]

FROM mambaorg/micromamba:2.0.5

LABEL org.opencontainers.image.title="OmicHub Analysis Core"
LABEL org.opencontainers.image.description="Independent micromamba Python/R task runtime for OmicStudio and toolbox executors"
LABEL org.omichub.runtime.family="omichub-analysis"
LABEL org.omichub.runtime.profile="analysis-core"

USER root
COPY requirements-agent.txt /tmp/requirements-agent.txt
COPY sandbox_agent.py /opt/omichub/sandbox_agent.py
RUN usermod --uid 10001 "$MAMBA_USER" \
    && groupmod --gid 10001 "$MAMBA_USER" \
    && chown -R 10001:10001 /home/"$MAMBA_USER" /opt/conda \
    && chown -R 10001:10001 /opt/omichub /tmp/requirements-agent.txt \
    && mkdir -p /workspace/.logs \
    && chown -R 10001:10001 /workspace

USER "$MAMBA_USER"
RUN micromamba install -y -n base -c conda-forge -c bioconda \
      python=3.12 \
      r-base=4.4 \
      pip=24.3 \
      pandas=2.2.3 \
      numpy=2.1.3 \
      scipy=1.14.1 \
      scikit-learn=1.5.2 \
      statsmodels=0.14.4 \
      openpyxl=3.1.5 \
      pyarrow=18.1.0 \
      bioconductor-deseq2=1.46.0 \
      bioconductor-edger=4.4.0 \
      bioconductor-limma=3.62.1 \
    && micromamba run -n base pip install -r /tmp/requirements-agent.txt \
    && micromamba clean --all --yes

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg SANDBOX_WORKSPACE=/workspace
WORKDIR /workspace
CMD ["micromamba", "run", "-n", "base", "sh", "-c", "rm -f /workspace/.agent.sock && exec uvicorn --app-dir /opt/omichub sandbox_agent:app --uds /workspace/.agent.sock"]

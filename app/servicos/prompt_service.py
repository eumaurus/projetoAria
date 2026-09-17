"""Carregamento de templates de prompt em arquivos .txt."""

from __future__ import annotations

import logging
from pathlib import Path

from app.servicos.base_service import BaseService
from app.servicos.config import Config


class PromptService(BaseService):
    """Lê e preenche templates da pasta app/prompts/."""

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        super().__init__(config, logger)
        self._cache: dict[str, str] = {}

    def carregar(self, nome_template: str) -> str:
        """Carrega template .txt pelo nome (sem extensão)."""
        if nome_template in self._cache:
            return self._cache[nome_template]

        caminho = self._resolver_caminho(nome_template)
        conteudo = caminho.read_text(encoding="utf-8")
        self._cache[nome_template] = conteudo
        self.logger.debug("Template carregado: %s", caminho.name)
        return conteudo

    def preencher(self, nome_template: str, **variaveis: str) -> str:
        """Preenche placeholders {chave} do template."""
        template = self.carregar(nome_template)
        try:
            return template.format(**variaveis)
        except KeyError as exc:
            raise KeyError(f"Variável ausente no template '{nome_template}': {exc}") from exc

    def _resolver_caminho(self, nome_template: str) -> Path:
        caminho = self.config.pasta_prompts / f"{nome_template}.txt"
        if not caminho.exists():
            raise FileNotFoundError(f"Template não encontrado: {caminho}")
        return caminho

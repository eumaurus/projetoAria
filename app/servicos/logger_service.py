"""Política centralizada de logging em console e arquivo."""

from __future__ import annotations

import logging
from datetime import datetime

from app.servicos.base_service import BaseService
from app.servicos.config import Config


class LoggerService(BaseService):
    """Configura e expõe loggers nomeados para o projeto."""

    _loggers: dict[str, logging.Logger] = {}

    def __init__(self, config: Config) -> None:
        super().__init__(config, logging.getLogger("lux"))
        self._configurar_raiz()

    def _configurar_raiz(self) -> None:
        nivel = getattr(logging, self.config.nivel_log.upper(), logging.INFO)
        formato = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        if not logging.getLogger().handlers:
            logging.basicConfig(level=nivel)

        logging.getLogger().setLevel(nivel)

        arquivo_log = (
            self.config.pasta_logs
            / f"lux_{datetime.now().strftime('%Y%m%d')}.log"
        )
        handler_arquivo = logging.FileHandler(arquivo_log, encoding="utf-8")
        handler_arquivo.setFormatter(formato)
        handler_arquivo.setLevel(nivel)

        if not any(isinstance(h, logging.FileHandler) for h in logging.getLogger().handlers):
            logging.getLogger().addHandler(handler_arquivo)

    def obter(self, nome: str) -> logging.Logger:
        """Retorna logger nomeado, reutilizando instâncias existentes."""
        if nome not in self._loggers:
            logger = logging.getLogger(f"lux.{nome}")
            logger.setLevel(getattr(logging, self.config.nivel_log.upper(), logging.INFO))
            self._loggers[nome] = logger
        return self._loggers[nome]

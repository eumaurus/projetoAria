"""Classe base para todos os serviços da plataforma."""

from __future__ import annotations

import logging
from abc import ABC

from app.servicos.config import Config


class BaseService(ABC):
    """Fornece acesso padronizado a configuração e logger."""

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

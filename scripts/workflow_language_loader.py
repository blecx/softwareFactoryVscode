import os
from typing import Any, Dict, Optional

import yaml


class TermAmbiguityError(Exception):
    """Exception raised when a term ID collides across contexts without explicit disambiguation."""

    pass


class LanguageLoader:
    """
    Reads factory workflow language and optional host project language
    while preserving ownership and enforcing collision rules.
    """

    def __init__(
        self,
        factory_file: str = "configs/workflow_language.yml",
        host_file: str = ".copilot/project-language.yml",
    ):
        self.factory_file = factory_file
        self.host_file = host_file

    def load(self, project_root: str) -> Dict[str, Any]:
        """
        Loads the factory and host namespaces into separate dictionaries.
        """
        factory_path = os.path.join(project_root, self.factory_file)
        host_path = os.path.join(project_root, self.host_file)

        factory_terms = self._load_yml(factory_path)
        host_terms = self._load_yml(host_path)

        factory_dict = {
            term["term_id"]: term
            for term in factory_terms.get("terms", [])
            if "term_id" in term
        }
        host_dict = {
            term["term_id"]: term
            for term in host_terms.get("terms", [])
            if "term_id" in term
        }

        return {"factory": factory_dict, "host": host_dict}

    def _load_yml(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
            except yaml.YAMLError:
                return {}

    def get_term(
        self, term_id: str, namespaces: Dict[str, Any], context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves a term by term_id.
        If context is provided ('factory' or 'host'), fetches specifically from there.
        If context is None and the term exists in both, raises TermAmbiguityError (blocker).
        """
        factory_dict = namespaces.get("factory", {})
        host_dict = namespaces.get("host", {})

        in_factory = term_id in factory_dict
        in_host = term_id in host_dict

        if context == "factory":
            return factory_dict.get(term_id)
        elif context == "host":
            return host_dict.get(term_id)
        else:
            if in_factory and in_host:
                raise TermAmbiguityError(
                    f"Ambiguous term '{term_id}' exists in both factory and host languages. Explicit context required."
                )
            if in_factory:
                return factory_dict[term_id]
            if in_host:
                return host_dict[term_id]
            return None

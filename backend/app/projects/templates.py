"""Project templates are YAML files under ``app/projects/data``. The model never changes them."""

from pathlib import Path

import yaml

from app.projects.schema import Template, TemplateSummary

DATA_DIR = Path(__file__).parent / "data"


class UnknownTemplateError(LookupError):
    pass


class Templates:
    """Every template file, loaded once at startup and validated."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self._by_id: dict[str, Template] = {}
        for path in sorted(data_dir.glob("*.yaml")):
            with path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
            template = Template.model_validate(raw)
            if template.id != path.stem:
                raise ValueError(
                    f"{path.name} declares id {template.id!r}; the file name must match"
                )
            keys = [r.key for r in template.requirements]
            if len(keys) != len(set(keys)):
                raise ValueError(f"template {template.id!r} repeats a requirement key")
            if not any(r.blocking for r in template.requirements):
                raise ValueError(f"template {template.id!r} has no blocking requirement")
            self._by_id[template.id] = template

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def get(self, template_id: str) -> Template:
        try:
            return self._by_id[template_id]
        except KeyError as exc:
            raise UnknownTemplateError(f"no template {template_id!r}") from exc

    def summaries(self) -> list[TemplateSummary]:
        return [
            TemplateSummary(
                id=t.id,
                label=t.label,
                goal=t.goal,
                effort=t.effort,
                requirements=[f"{r.key}: {r.label}" for r in t.requirements],
            )
            for t in (self._by_id[i] for i in self.ids())
        ]

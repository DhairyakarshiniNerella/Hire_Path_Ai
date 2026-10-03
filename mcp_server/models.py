from pydantic import BaseModel


class Job(BaseModel):
    """The one common job shape every source is converted into."""
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    source: str = ""
    source_id: str = ""
    employment_type: str = "Unknown"


class SearchResult(BaseModel):
    """What a search tool returns: the jobs plus which source they came from."""
    source: str
    count: int
    jobs: list[Job]
    # source name -> error message, for sources that failed (others still returned jobs)
    errors: dict[str, str] = {}

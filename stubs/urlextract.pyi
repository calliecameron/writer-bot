from typing import List

class URLExtract:
    def find_urls(
        self,
        text: str,
        only_unique: bool = False,
        check_dns: bool = False,
        get_indices: bool = False,
        with_schema_only: bool = False,
    ) -> List[str]: ...

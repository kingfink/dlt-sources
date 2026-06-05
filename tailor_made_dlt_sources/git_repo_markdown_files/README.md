# git_repo_markdown_files

Git repository markdown files dlt source.

This source loads markdown files from a local git repository into one or more
dlt resources. Each row includes the file path, parsed YAML frontmatter,
markdown body, git-derived created and modified timestamps, and a stable
incremental cursor.

## Resources

Resources are created from the `resource_globs` mapping that you pass to
`git_repo_markdown_files_source`.

| Column | Type | Notes |
|---|---|---|
| `file_path` | text | Primary key |
| `frontmatter` | json | Parsed YAML frontmatter |
| `content` | text | Markdown body |
| `created_at` | timestamp | Oldest git author timestamp |
| `modified_at` | timestamp | Newest git author timestamp |
| `modified_at_cursor` | text | Incremental cursor |

Files whose stem is `index` are skipped by default.

## Example

```python
import dlt

from tailor_made_dlt_sources.git_repo_markdown_files import git_repo_markdown_files_source

pipeline = dlt.pipeline(
    pipeline_name="git_repo_markdown_files_demo",
    destination="duckdb",
    dataset_name="repo_content",
)
info = pipeline.run(
    git_repo_markdown_files_source(
        repo_root="/path/to/repo",
        resource_globs={
            "documents": "docs/**/*.md",
            "blog_posts": "content/blog/**/*.md",
        },
    )
)
print(info)
```

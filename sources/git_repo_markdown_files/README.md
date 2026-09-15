# git_repo_markdown_files

Git repository markdown files dlt source.

This source loads markdown files from a local git repository into one or more dlt resources. Each row includes the file path, parsed YAML frontmatter, markdown body, git-derived created and modified timestamps, and a stable incremental cursor.

## Resources

Resources are created from the `resource_globs` mapping that you pass to `git_repo_markdown_files_source`.

| Column | Type | Notes |
|---|---|---|
| `file_path` | text | Primary key |
| `frontmatter` | json | Parsed YAML frontmatter |
| `content` | text | Markdown body |
| `created_at` | timestamp | Oldest git author timestamp |
| `modified_at` | timestamp | Newest git author timestamp |
| `modified_at_cursor` | text | Incremental cursor |

Files whose stem is `index` are skipped by default.

Frontmatter starts and ends with an unindented line containing only `---` and optional spaces or tabs. Inline triple hyphens in URLs or text, and indented separators inside YAML block scalars, remain part of the field value.

After upgrading a parser fix, reprocess existing files even when their Git timestamps have not changed. An ordinary incremental run skips files behind its cursor, so use the consuming pipeline's backfill or refresh procedure to repair previously loaded frontmatter.

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

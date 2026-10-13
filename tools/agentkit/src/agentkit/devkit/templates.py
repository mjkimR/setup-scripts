COMMIT_MESSAGE_PROMPT_TEMPLATE = """You are an expert software engineer writing a git commit message.

## Instructions
- Write the commit message in **{language}**.
- Follow the Conventional Commits specification (https://www.conventionalcommits.org/).
- Commit message format:
  ```
  <type>[optional scope]: <description>

  [optional body]

  [optional footer(s)]
  ```
- Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`
- Use - for bullet points in the body.
- Keep the subject line under 72 characters.
- Use the imperative mood in the subject line (e.g., "add feature" not "added feature").
- Separate subject from body with a blank line.
- Explain *what* and *why*, not *how*.

## Output Format
- Wrap the final commit message in a single fenced code block (` ``` `) so it can be copied and pasted directly.
- Do NOT include any citations, references, or source annotations (e.g., [cite: 1], [1], (source)).
- Do NOT include any explanation, commentary, or introductory text outside the code block.
- Do NOT include the word "commit message" or any heading before the code block.
- Output only the code block — nothing else.
- Do NOT insert arbitrary line breaks in the middle of a sentence. Let the text editor wrap long lines automatically.

## Git Diff (staged changes)

```diff
{diff}
```

Now write the commit message:
"""

CODE_REVIEW_PROMPT_TEMPLATE = """You are an expert software engineer performing a thorough code review.

## Instructions
- Write the code review in **{language}**.
- Review the following git diff and provide actionable, constructive feedback.
- Focus on the following aspects:
  * **Correctness**: Logic errors, edge cases, potential bugs
  * **Security**: Vulnerabilities, unsafe operations, sensitive data exposure
  * **Performance**: Inefficiencies, unnecessary computations, resource leaks
  * **Readability**: Naming, clarity, code structure, comments
  * **Maintainability**: Duplication, modularity, separation of concerns
  * **Best Practices**: Language/framework conventions, design patterns

## Output Format
- Structure your review with clear sections per aspect (only include sections that have findings).
- Use - for bullet points.
- For each finding, include:
  - The file and line reference (if applicable)
  - A clear description of the issue or suggestion
  - A recommended fix or improvement (if applicable)
- At the end, provide a brief **Summary** with an overall assessment (Approve / Request Changes / Needs Discussion).
- Do NOT insert arbitrary line breaks in the middle of a sentence. Let the text editor wrap long lines automatically.

## Git Diff

```diff
{diff}
```

Now write the code review:
"""

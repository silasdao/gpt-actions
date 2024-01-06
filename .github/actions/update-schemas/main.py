# Imports
import os, re, json, unicodedata
from git import Repo, Git
from github import Github

# Generates a new schema entry for the README
def new_readme_entry(info, schema):
    format = info["format"].lower()
    return f"""
<!-- START_SCHEMA: "{info['title']}" -->
<tr></tr><tr><td><details><summary><b>{info['title']}</b> - <i>{info['shortdesc']}</i></summary><p><ul>
<li><b>Author:</b> <a href="https://github.com/{info['author']}">{info['author']}</a></li>
<li><b>Schema format:</b> {format.upper()}</li>
<li><b>Authentication type:</b> {info['auth']}</li></ul></p>
<p><b>Description:</b><br>

{info['desc']}</p>
<p><b>Import URL:</b><br>

```
https://raw.githubusercontent.com/bapo2/gpt-actions/main/schemas/{info['folder_title']}/schema.{format}
```
</p><details><summary><b>Schema</b></summary>

```{format}
{schema}
```
</details></details></td></tr>
<!-- END_SCHEMA: "{info['title']}" -->
"""

# Slugifies a title so that it can be used as a directory name
def slugify(title):
    title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^\w\s-]', '', title.lower()).strip('-_').replace(' ', '-')

# Updates the README with the new schema directory
def update_readme(readme_path, directory):
    with open(readme_path, 'r') as f: readme_text = f.read()
    if schema_directory_section := re.search(
        r'<!-- START_SCHEMA_DIRECTORY -->(.*?)<!-- END_SCHEMA_DIRECTORY -->',
        readme_text,
        re.DOTALL,
    ):
        if schema_directory_section: updated_readme = readme_text.replace(schema_directory_section.group(1), directory)
    else:
        updated_readme = f"{readme_text}<!-- START_SCHEMA_DIRECTORY -->{directory}<!-- END_SCHEMA_DIRECTORY -->"
    updated_readme = re.sub(r'https://img.shields.io/badge/(\d+)%20actions%20contributed', r'https://img.shields.io/badge/' + str(len(os.listdir(os.path.join('repo', 'schemas')))) + r'%20actions%20contributed', updated_readme)
    return updated_readme

# The main function
def run():
    # Environment variables and setup
    token, repo_path = os.environ['GITHUB_TOKEN'], os.environ['INPUT_REPO_PATH']
    issue_numbers = os.environ['INPUT_ISSUE_LIST'].replace('"','').replace('#','').split(',')
    repo = Repo.clone_from(f"https://{token}@github.com/{repo_path}.git", 'repo')
    git = Git('repo')
    git.config('credential.helper', f'!echo password={token};')

    # Get issues and extract information
    g_repo = Github(token).get_repo(repo_path)
    schemas_dir = os.path.join('repo', 'schemas')
    issues_info = []
    pattern = r"### 📂 Name\s*\n*(.*?)\n*?\s*### 📰 Short Description\s*\n*(.*?)\n*?\s*### 📜 Format\s*\n*(.*?)\n*?\s*### 📋 Schema\s*\n*```(?:json|yaml)\n([\s\S]*?)\n```(?:\n*?)\s*### 🔑 Authentication\s*\n*(.*?)\n*?\s*### 📝 Description\s*\n*([\s\S]*?)(?=\n*###|$)"
    for number in issue_numbers:
        issue = g_repo.get_issue(number=int(number))
        title, shortdesc, format, schema, auth, desc = re.findall(pattern, issue.body, re.DOTALL)[0]
        folder_title = slugify(title)
        info = {'title': title, 'shortdesc': shortdesc, 'format': format, 'schema': schema, 'auth': auth, 'desc': desc, 'author': issue.user.login, 'folder_title': folder_title}
        issues_info.append(info)

        # Save info.json for each new schema
        info_path = os.path.join(schemas_dir, folder_title, 'info.json')
        os.makedirs(os.path.join(schemas_dir, folder_title), exist_ok=True)
        if os.path.exists(info_path): raise Exception(f"Schemas directory already contains a schema with the title {title}.")
        with open(info_path, 'w') as f: json.dump(info, f, indent=4)
        with open(os.path.join(schemas_dir, folder_title, f'schema.{format.lower()}'), 'w') as f: f.write(schema)

    # Create schema directories and files
    os.makedirs(schemas_dir, exist_ok=True)
    directory_entries = ""
    schemas = sorted(os.listdir(schemas_dir))
    for folder in schemas:
        folder_path = os.path.join(schemas_dir, folder)
        if os.path.isdir(folder_path):
            info_path = os.path.join(folder_path, 'info.json')
            with open(info_path, 'r') as f:
                info = json.load(f)
            schema = open(os.path.join(folder_path, f'schema.{info["format"].lower()}'), 'r').read()
            if 'folder_title' not in info:
                info['folder_title'] = slugify(info['title'])
            directory_entries += new_readme_entry(info, schema)

    # Update README
    readme_path = os.path.join('repo', '.github', 'README.md')
    updated_readme = update_readme(readme_path, directory_entries)
    with open(readme_path, 'w') as f: f.write(updated_readme)

    # Git operations: commit and create PR
    repo.git.add(A=True)
    repo.index.commit('ci(schemas): Add new approved schemas')
    update_schemas_branch = Repo.create_head(repo, 'update-schemas', 'main')
    update_schemas_branch.checkout()
    repo.git.push('origin', 'update-schemas')
    pr_body = f"This pull request was automatically generated by the update-schemas action, and will add the following schemas to the repository:\n" + "\n".join([f'- {info["title"]}' for info in issues_info]) + "\n\nThis will close the following issues:\n" + "\n".join([f'- Closes #{num}' for num in issue_numbers])
    g_repo.create_pull(title='ci(schemas): Add new approved schemas', body=pr_body, base='main', head=update_schemas_branch.name)

if __name__ == '__main__': run()
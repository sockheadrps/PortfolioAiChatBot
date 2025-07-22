#!/usr/bin/env python3
"""
Repository Data Analysis Script
Analyzes repo_data.json to provide comprehensive statistics about:
- Total constructs (if statements, loops, functions, classes)
- Total Python files and lines of code
- File extension distribution
- Library usage statistics
"""

import json
import os
from collections import defaultdict, Counter
from typing import Dict, List, Any
from datetime import datetime


def load_repo_data(file_path: str = "repo_data.json") -> Dict[str, Any]:
    """Load repository data from JSON file"""
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        print("💡 Please run the data_scrape.py script first to generate repo_data.json")
        return None

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        print(f"✅ Loaded data from {file_path}")
        return data
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON: {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return None


def analyze_constructs(repo_data: Dict[str, Any]) -> Dict[str, int]:
    """Analyze total constructs across all repositories"""
    print("\n🔍 Analyzing Python constructs...")

    total_constructs = {
        "if_statements": 0,
        "while_loops": 0,
        "for_loops": 0,
        "regular_functions": 0,
        "async_functions": 0,
        "classes": 0,
        "total_functions": 0,
        "total_loops": 0
    }

    for repo in repo_data.get("repo_stats", []):
        constructs = repo.get("construct_counts", {})
        total_constructs["if_statements"] += constructs.get("if statements", 0)
        total_constructs["while_loops"] += constructs.get("while loops", 0)
        total_constructs["for_loops"] += constructs.get("for loops", 0)
        total_constructs["regular_functions"] += constructs.get(
            "regular functions created", 0)
        total_constructs["async_functions"] += constructs.get(
            "async functions created", 0)
        total_constructs["classes"] += constructs.get("classes created", 0)

    # Calculate totals
    total_constructs["total_functions"] = total_constructs["regular_functions"] + \
        total_constructs["async_functions"]
    total_constructs["total_loops"] = total_constructs["while_loops"] + \
        total_constructs["for_loops"]

    return total_constructs


def analyze_python_files(repo_data: Dict[str, Any]) -> Dict[str, int]:
    """Analyze Python file statistics"""
    print("🔍 Analyzing Python files...")

    stats = {
        "total_python_files": 0,
        "total_python_lines": 0,
        "repos_with_python": 0,
        "avg_lines_per_file": 0
    }

    repos_with_python = 0
    for repo in repo_data.get("repo_stats", []):
        python_files = repo.get("total_python_files", 0)
        python_lines = repo.get("total_python_lines", 0)

        if python_files > 0:
            repos_with_python += 1
            stats["total_python_files"] += python_files
            stats["total_python_lines"] += python_lines

    stats["repos_with_python"] = repos_with_python

    if stats["total_python_files"] > 0:
        stats["avg_lines_per_file"] = stats["total_python_lines"] // stats["total_python_files"]

    return stats


def analyze_file_extensions(repo_data: Dict[str, Any]) -> Dict[str, int]:
    """Analyze programming file extension distribution"""
    print("🔍 Analyzing programming file extensions...")

    # Define programming-related file extensions
    programming_extensions = {
        # Programming languages
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.hpp',
        '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala', '.clj',
        '.hs', '.ml', '.fs', '.dart', '.r', '.m', '.mm', '.pl', '.sh', '.bash',
        '.zsh', '.fish', '.ps1', '.bat', '.cmd', '.vbs', '.lua', '.sql', '.asm',

        # Web technologies
        '.html', '.htm', '.css', '.scss', '.sass', '.less', '.xml', '.svg',
        '.vue', '.svelte', '.elm', '.coffee', '.litcoffee', '.iced',

        # Configuration and build files
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.config',
        '.env', '.properties', '.gradle', '.maven', '.pom', '.sbt', '.cabal',
        '.package.json', '.bower.json', '.composer.json', '.requirements.txt',
        '.setup.py', '.pyproject.toml', '.Cargo.toml', '.go.mod', '.go.sum',
        '.Gemfile', '.Gemfile.lock', '.package-lock.json', '.yarn.lock',
        '.Dockerfile', '.dockerignore', '.gitignore', '.gitattributes',

        # Documentation (programming-related)
        '.md', '.rst', '.txt', '.adoc', '.wiki',

        # Data and serialization
        '.csv', '.tsv', '.xml', '.jsonl', '.ndjson', '.parquet', '.avro',
        '.proto', '.thrift', '.graphql', '.gql',

        # Templates and frameworks
        '.j2', '.jinja', '.jinja2', '.ejs', '.pug', '.hbs', '.handlebars',
        '.erb', '.haml', '.slim', '.mustache', '.liquid', '.njk',

        # Testing and spec files
        '.test.js', '.test.ts', '.test.py', '.spec.js', '.spec.ts', '.spec.py',
        '.test.jsx', '.test.tsx', '.spec.jsx', '.spec.tsx',

        # Type definitions
        '.d.ts', '.d.tsx',

        # Other programming files
        '.ipynb', '.r', '.R', '.m', '.mat', '.stan', '.jl', '.nim', '.zig',
        '.v', '.vhdl', '.verilog', '.sv', '.tcl', '.awk', '.sed', '.groovy',
        '.gvy', '.gradle', '.kt', '.kts', '.sc', '.scala', '.sbt', '.clj',
        '.edn', '.cljs', '.cljc', '.boot', '.deps.edn', '.project.clj'
    }

    extension_counts = Counter()

    for repo in repo_data.get("repo_stats", []):
        file_extensions = repo.get("file_extensions", {})
        for ext, count in file_extensions.items():
            # Only count programming-related extensions
            if ext in programming_extensions:
                extension_counts[ext] += count

    return dict(extension_counts.most_common())


def analyze_libraries(repo_data: Dict[str, Any]) -> Dict[str, int]:
    """Analyze library usage across all repositories"""
    print("🔍 Analyzing library usage...")

    library_counts = Counter()

    for repo in repo_data.get("repo_stats", []):
        libraries = repo.get("libraries", [])
        for lib in libraries:
            library_counts[lib] += 1

    return dict(library_counts.most_common())


def analyze_repository_summary(repo_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide overall repository summary"""
    print("🔍 Analyzing repository summary...")

    repos = repo_data.get("repo_stats", [])
    total_repos = len(repos)

    summary = {
        "total_repositories": total_repos,
        "repos_with_commits": 0,
        "repos_with_python": 0,
        "total_commits": 0,
        "recent_commits": len(repo_data.get("recent_commits", [])),
        "avg_commits_per_repo": 0,
        "most_active_repos": []
    }

    repo_activity = []
    for repo in repos:
        commits = repo.get("total_commits", 0)
        summary["total_commits"] += commits

        if commits > 0:
            summary["repos_with_commits"] += 1
            repo_activity.append((repo["repo_name"], commits))

        if repo.get("total_python_files", 0) > 0:
            summary["repos_with_python"] += 1

    if summary["total_repositories"] > 0:
        summary["avg_commits_per_repo"] = summary["total_commits"] // summary["total_repositories"]

    # Get top 10 most active repositories
    repo_activity.sort(key=lambda x: x[1], reverse=True)
    summary["most_active_repos"] = repo_activity[:10]

    return summary


def print_analysis_results(
    constructs: Dict[str, int],
    python_stats: Dict[str, int],
    extensions: Dict[str, int],
    libraries: Dict[str, int],
    summary: Dict[str, Any]
):
    """Print formatted analysis results"""

    print("\n" + "="*80)
    print("📊 REPOSITORY DATA ANALYSIS RESULTS")
    print("="*80)

    # Repository Summary
    print(f"\n🏠 REPOSITORY SUMMARY")
    print(f"   Total repositories: {summary['total_repositories']}")
    print(f"   Repositories with commits: {summary['repos_with_commits']}")
    print(f"   Repositories with Python: {summary['repos_with_python']}")
    print(f"   Total commits: {summary['total_commits']:,}")
    print(f"   Recent commits (90 days): {summary['recent_commits']}")
    print(f"   Average commits per repo: {summary['avg_commits_per_repo']}")

    # Python File Statistics
    print(f"\n🐍 PYTHON FILE STATISTICS")
    print(f"   Total Python files: {python_stats['total_python_files']:,}")
    print(f"   Total Python lines: {python_stats['total_python_lines']:,}")
    print(f"   Average lines per file: {python_stats['avg_lines_per_file']:,}")
    print(f"   Repositories with Python: {python_stats['repos_with_python']}")

    # Construct Analysis
    print(f"\n🔧 PYTHON CONSTRUCTS")
    print(f"   If statements: {constructs['if_statements']:,}")
    print(f"   While loops: {constructs['while_loops']:,}")
    print(f"   For loops: {constructs['for_loops']:,}")
    print(f"   Total loops: {constructs['total_loops']:,}")
    print(f"   Regular functions: {constructs['regular_functions']:,}")
    print(f"   Async functions: {constructs['async_functions']:,}")
    print(f"   Total functions: {constructs['total_functions']:,}")
    print(f"   Classes: {constructs['classes']:,}")

    # File Extensions
    print(
        f"\n📁 PROGRAMMING FILE EXTENSIONS (All {len(extensions)} extensions)")
    for i, (ext, count) in enumerate(extensions.items(), 1):
        print(f"   {i:3d}. {ext:15} : {count:,}")

    # Library Usage
    print(f"\n📚 LIBRARY USAGE (Top 20)")
    for i, (lib, count) in enumerate(list(libraries.items())[:20], 1):
        print(f"   {i:2d}. {lib:20} : {count} repos")

    # Most Active Repositories
    print(f"\n⭐ MOST ACTIVE REPOSITORIES (Top 10)")
    for i, (repo_name, commits) in enumerate(summary['most_active_repos'], 1):
        print(f"   {i:2d}. {repo_name:30} : {commits:,} commits")


def save_detailed_report(
    constructs: Dict[str, int],
    python_stats: Dict[str, int],
    extensions: Dict[str, int],
    libraries: Dict[str, int],
    summary: Dict[str, Any],
    filename: str = "analysis_report.json"
):
    """Save detailed analysis report to JSON file"""

    report = {
        "summary": summary,
        "python_statistics": python_stats,
        "constructs": constructs,
        "file_extensions": extensions,
        "libraries": libraries,
        "generated_at": datetime.now().isoformat()
    }

    try:
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n💾 Detailed report saved to: {filename}")
    except Exception as e:
        print(f"❌ Error saving report: {e}")


def create_detailed_json_report(
    constructs: Dict[str, int],
    python_stats: Dict[str, int],
    extensions: Dict[str, int],
    libraries: Dict[str, int],
    summary: Dict[str, Any],
    filename: str = "detailed_analysis.json"
):
    """Create a comprehensive JSON report with all analysis data"""

    # Convert extensions and libraries to lists for better JSON structure
    extensions_list = [{"extension": ext, "count": count}
                       for ext, count in extensions.items()]
    libraries_list = [{"library": lib, "repository_count": count}
                      for lib, count in libraries.items()]

    # Convert most active repos to list of dicts
    active_repos_list = [{"repository": repo, "commits": commits}
                         for repo, commits in summary['most_active_repos']]

    report = {
        "analysis_summary": {
            "generated_at": datetime.now().isoformat(),
            "total_repositories": summary['total_repositories'],
            "repos_with_commits": summary['repos_with_commits'],
            "repos_with_python": summary['repos_with_python'],
            "total_commits": summary['total_commits'],
            "recent_commits": summary['recent_commits'],
            "avg_commits_per_repo": summary['avg_commits_per_repo']
        },
        "python_statistics": {
            "total_python_files": python_stats['total_python_files'],
            "total_python_lines": python_stats['total_python_lines'],
            "repos_with_python": python_stats['repos_with_python'],
            "avg_lines_per_file": python_stats['avg_lines_per_file']
        },
        "constructs": {
            "if_statements": constructs['if_statements'],
            "while_loops": constructs['while_loops'],
            "for_loops": constructs['for_loops'],
            "total_loops": constructs['total_loops'],
            "regular_functions": constructs['regular_functions'],
            "async_functions": constructs['async_functions'],
            "total_functions": constructs['total_functions'],
            "classes": constructs['classes']
        },
        "file_extensions": extensions_list,
        "libraries": libraries_list,
        "most_active_repositories": active_repos_list
    }

    try:
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"💾 Detailed analysis saved to: {filename}")
    except Exception as e:
        print(f"❌ Error saving detailed analysis: {e}")


def main():
    """Main analysis function"""
    print("🚀 Repository Data Analysis")
    print("="*50)

    # Load data
    repo_data = load_repo_data()
    if not repo_data:
        return 1

    # Perform analysis
    constructs = analyze_constructs(repo_data)
    python_stats = analyze_python_files(repo_data)
    extensions = analyze_file_extensions(repo_data)
    libraries = analyze_libraries(repo_data)
    summary = analyze_repository_summary(repo_data)

    # Print results
    print_analysis_results(constructs, python_stats,
                           extensions, libraries, summary)

    # Save reports
    save_detailed_report(constructs, python_stats,
                         extensions, libraries, summary)
    create_detailed_json_report(
        constructs, python_stats, extensions, libraries, summary)

    print(f"\n🎉 Analysis completed successfully!")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Analysis interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Analysis failed with error: {e}")
        exit(1)

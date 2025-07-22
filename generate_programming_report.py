#!/usr/bin/env python3
"""
Programming Report Generator
Creates a nice formatted report from analysis_report.json for displaying
programming statistics when people ask about programming experience.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any


def load_analysis_data(file_path: str = "analysis_report.json") -> Dict[str, Any]:
    """Load analysis data from JSON file"""
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        print("💡 Please run analyze_repo_data.py first to generate analysis_report.json")
        return None

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return None


def format_number(num: int) -> str:
    """Format large numbers with commas"""
    return f"{num:,}"


def generate_programming_report(data: Dict[str, Any]) -> str:
    """Generate a nice formatted programming report"""

    # Extract data
    summary = data.get("summary", {})
    python_stats = data.get("python_statistics", {})
    constructs = data.get("constructs", {})
    extensions = data.get("file_extensions", {})
    libraries = data.get("libraries", {})

    # Calculate some additional stats
    total_repos = summary.get("total_repositories", 0)
    repos_with_python = python_stats.get("repos_with_python", 0)
    python_percentage = (repos_with_python / total_repos *
                         100) if total_repos > 0 else 0

    # Get top libraries (limit to top 10)
    top_libraries = list(libraries.items())[:10]

    # Get top file extensions (limit to top 10)
    top_extensions = list(extensions.items())[:10]

    # Generate the report
    report = f"""
🎯 **Programming Portfolio Overview**

📊 **Repository Statistics**
• Total repositories: {format_number(total_repos)}
• Repositories with Python: {format_number(repos_with_python)} ({python_percentage:.1f}%)
• Total commits: {format_number(summary.get("total_commits", 0))}
• Recent commits (90 days): {format_number(summary.get("recent_commits", 0))}

🐍 **Python Development**
• Python files: {format_number(python_stats.get("total_python_files", 0))}
• Lines of Python code: {format_number(python_stats.get("total_python_lines", 0))}
• Average lines per file: {format_number(python_stats.get("avg_lines_per_file", 0))}

🔧 **Code Constructs**
• Functions: {format_number(constructs.get("total_functions", 0))} (regular: {format_number(constructs.get("regular_functions", 0))}, async: {format_number(constructs.get("async_functions", 0))})
• Classes: {format_number(constructs.get("classes", 0))}
• Control structures: {format_number(constructs.get("if_statements", 0))} if statements, {format_number(constructs.get("total_loops", 0))} loops

📁 **Top File Types**
{chr(10).join([f"• {ext}: {format_number(count)}" for ext, count in top_extensions])}

📚 **Most Used Libraries**
{chr(10).join([f"• {lib}: {count} repositories" for lib, count in top_libraries])}

💡 **Programming Focus**
Based on the analysis, I primarily work with Python development, with expertise in web technologies, data processing, and modern development practices. My repositories show a strong focus on practical applications and real-world projects.
"""

    return report.strip()


def generate_short_report(data: Dict[str, Any]) -> str:
    """Generate a shorter version for quick responses"""

    summary = data.get("summary", {})
    python_stats = data.get("python_statistics", {})
    constructs = data.get("constructs", {})

    total_repos = summary.get("total_repositories", 0)
    repos_with_python = python_stats.get("repos_with_python", 0)
    python_percentage = (repos_with_python / total_repos *
                         100) if total_repos > 0 else 0

    short_report = f"""
🎯 **Quick Programming Stats**
• {format_number(total_repos)} repositories • {format_number(python_stats.get("total_python_files", 0))} Python files
• {format_number(python_stats.get("total_python_lines", 0))} lines of Python code • {format_number(constructs.get("total_functions", 0))} functions
• {format_number(constructs.get("classes", 0))} classes • {format_number(summary.get("total_commits", 0))} total commits
• {python_percentage:.1f}% of repos contain Python code
"""

    return short_report.strip()


def generate_technical_report(data: Dict[str, Any]) -> str:
    """Generate a technical-focused report"""

    summary = data.get("summary", {})
    python_stats = data.get("python_statistics", {})
    constructs = data.get("constructs", {})
    libraries = data.get("libraries", {})
    extensions = data.get("file_extensions", {})

    # Get top 5 libraries and extensions
    top_libraries = list(libraries.items())[:5]
    top_extensions = list(extensions.items())[:5]

    technical_report = f"""
🔬 **Technical Programming Profile**

**Code Metrics:**
• Python files: {format_number(python_stats.get("total_python_files", 0))}
• Total lines: {format_number(python_stats.get("total_python_lines", 0))}
• Functions: {format_number(constructs.get("total_functions", 0))} (async: {format_number(constructs.get("async_functions", 0))})
• Classes: {format_number(constructs.get("classes", 0))}
• Control flow: {format_number(constructs.get("if_statements", 0))} conditionals, {format_number(constructs.get("total_loops", 0))} loops

**Technology Stack:**
• Primary languages: {', '.join([ext.replace('.', '') for ext, _ in top_extensions[:3]])}
• Key libraries: {', '.join([lib for lib, _ in top_libraries[:3]])}

**Development Activity:**
• Active repositories: {format_number(summary.get("total_repositories", 0))}
• Recent commits: {format_number(summary.get("recent_commits", 0))} (90 days)
• Average commits per repo: {format_number(summary.get("avg_commits_per_repo", 0))}
"""

    return technical_report.strip()


def save_report_to_file(report: str, filename: str = "programming_report.txt"):
    """Save the report to a text file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"💾 Report saved to: {filename}")
    except Exception as e:
        print(f"❌ Error saving report: {e}")


def main():
    """Main function to generate reports"""
    print("🚀 Programming Report Generator")
    print("="*40)

    # Load data
    data = load_analysis_data()
    if not data:
        return 1

    # Generate different types of reports
    print("\n📋 Generating reports...")

    # Full report
    full_report = generate_programming_report(data)
    print("\n" + "="*60)
    print("📊 FULL PROGRAMMING REPORT")
    print("="*60)
    print(full_report)

    # Short report
    short_report = generate_short_report(data)
    print("\n" + "="*60)
    print("⚡ QUICK STATS")
    print("="*60)
    print(short_report)

    # Technical report
    technical_report = generate_technical_report(data)
    print("\n" + "="*60)
    print("🔬 TECHNICAL PROFILE")
    print("="*60)
    print(technical_report)

    # Save reports to files
    save_report_to_file(full_report, "full_programming_report.txt")
    save_report_to_file(short_report, "quick_programming_stats.txt")
    save_report_to_file(technical_report, "technical_programming_profile.txt")

    # Create a combined report for the bot
    combined_report = f"""
{full_report}

---
{short_report}

---
{technical_report}
"""
    save_report_to_file(combined_report, "bot_programming_report.txt")

    print(f"\n🎉 Reports generated successfully!")
    print("📁 Files created:")
    print("   • full_programming_report.txt")
    print("   • quick_programming_stats.txt")
    print("   • technical_programming_profile.txt")
    print("   • bot_programming_report.txt")

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Report generation interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Report generation failed with error: {e}")
        exit(1)

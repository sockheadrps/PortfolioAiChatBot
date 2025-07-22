#!/usr/bin/env python3
"""
HTML Programming Report Generator
Creates a beautiful HTML report from analysis_report.json for displaying
programming statistics on the web page.
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


def generate_html_report(data: Dict[str, Any]) -> str:
    """Generate a beautiful HTML report"""

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

    # Get top libraries and extensions
    top_libraries = list(libraries.items())[:10]
    top_extensions = list(extensions.items())[:10]

    # Generate the HTML
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Programming Portfolio Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 300;
        }}
        
        .header p {{
            font-size: 1.2em;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .stat-card {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            border-left: 4px solid #667eea;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }}
        
        .stat-card h3 {{
            color: #667eea;
            font-size: 1.3em;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        
        .section {{
            margin-bottom: 40px;
        }}
        
        .section h2 {{
            color: #2c3e50;
            font-size: 1.8em;
            margin-bottom: 20px;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }}
        
        .list-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }}
        
        .list-item {{
            background: #f8f9fa;
            padding: 15px 20px;
            border-radius: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-left: 4px solid #667eea;
        }}
        
        .list-item .name {{
            font-weight: 500;
            color: #2c3e50;
        }}
        
        .list-item .count {{
            background: #667eea;
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: 500;
        }}
        
        .highlight-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 15px;
            margin: 30px 0;
        }}
        
        .highlight-box h3 {{
            font-size: 1.5em;
            margin-bottom: 15px;
        }}
        
        .highlight-box p {{
            font-size: 1.1em;
            line-height: 1.6;
            opacity: 0.95;
        }}
        
        .progress-bar {{
            background: rgba(255,255,255,0.2);
            border-radius: 10px;
            height: 8px;
            margin-top: 10px;
            overflow: hidden;
        }}
        
        .progress-fill {{
            background: #fff;
            height: 100%;
            border-radius: 10px;
            transition: width 1s ease;
        }}
        
        @media (max-width: 768px) {{
            .stats-grid {{
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            }}
            
            .list-grid {{
                grid-template-columns: 1fr;
            }}
            
            .header {{
                padding: 20px;
            }}
            
            .content {{
                padding: 20px;
            }}
        }}
        
        .emoji {{
            font-size: 1.2em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Programming Portfolio Report</h1>
            <p>Comprehensive analysis of my programming experience and project</p>
        </div>
        
        <div class="content">
            <!-- Key Statistics -->
            <div class="stats-grid">
                <div class="stat-card">
                    <h3><span class="emoji">📊</span> Total Repositories</h3>
                    <div class="stat-number">{format_number(total_repos)}</div>
                    <div class="stat-label">GitHub repositories analyzed</div>
                </div>
                
                <div class="stat-card">
                    <h3><span class="emoji">🐍</span> Python Files</h3>
                    <div class="stat-number">{format_number(python_stats.get("total_python_files", 0))}</div>
                    <div class="stat-label">Python files across all repos</div>
                </div>
                
                <div class="stat-card">
                    <h3><span class="emoji">📝</span> Lines of Code</h3>
                    <div class="stat-number">{format_number(python_stats.get("total_python_lines", 0))}</div>
                    <div class="stat-label">Total Python lines written</div>
                </div>
                
                <div class="stat-card">
                    <h3><span class="emoji">🔧</span> Functions</h3>
                    <div class="stat-number">{format_number(constructs.get("total_functions", 0))}</div>
                    <div class="stat-label">Functions created ({format_number(constructs.get("async_functions", 0))} async)</div>
                </div>
                
                <div class="stat-card">
                    <h3><span class="emoji">🏗️</span> Classes</h3>
                    <div class="stat-number">{format_number(constructs.get("classes", 0))}</div>
                    <div class="stat-label">Classes and objects designed</div>
                </div>
                
                <div class="stat-card">
                    <h3><span class="emoji">📈</span> Total Commits</h3>
                    <div class="stat-number">{format_number(summary.get("total_commits", 0))}</div>
                    <div class="stat-label">Git commits across all projects</div>
                </div>
            </div>
            
            <!-- Python Focus -->
            <div class="highlight-box">
                <h3>🐍 Python Development Focus</h3>
                <p>
                    <strong>{python_percentage:.1f}%</strong> of my repositories contain Python code, 
                    demonstrating a strong focus on Python development. I've written 
                    <strong>{format_number(python_stats.get("total_python_lines", 0))} lines of Python code</strong> 
                    across <strong>{format_number(python_stats.get("total_python_files", 0))} files</strong>, 
                    with an average of <strong>{format_number(python_stats.get("avg_lines_per_file", 0))} lines per file</strong>.
                </p>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {python_percentage}%"></div>
                </div>
            </div>
            
            <!-- Code Constructs -->
            <div class="section">
                <h2>🔧 Code Constructs & Patterns</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3><span class="emoji">⚡</span> Async Functions</h3>
                        <div class="stat-number">{format_number(constructs.get("async_functions", 0))}</div>
                        <div class="stat-label">Modern async/await patterns</div>
                    </div>
                    
                    <div class="stat-card">
                        <h3><span class="emoji">🔄</span> Control Flow</h3>
                        <div class="stat-number">{format_number(constructs.get("if_statements", 0))}</div>
                        <div class="stat-label">Conditional statements</div>
                    </div>
                    
                    <div class="stat-card">
                        <h3><span class="emoji">🔄</span> Loops</h3>
                        <div class="stat-number">{format_number(constructs.get("total_loops", 0))}</div>
                        <div class="stat-label">For and while loops</div>
                    </div>
                </div>
            </div>
            
            <!-- File Types -->
            <div class="section">
                <h2>📁 Most Used File Types</h2>
                <div class="list-grid">
"""

    # Add file extensions
    for ext, count in top_extensions:
        html += f"""
                    <div class="list-item">
                        <span class="name">{ext}</span>
                        <span class="count">{format_number(count)}</span>
                    </div>"""

    html += """
                </div>
            </div>
            
            <!-- Libraries -->
            <div class="section">
                <h2>📚 Most Used Libraries</h2>
                <div class="list-grid">
"""

    # Add libraries
    for lib, count in top_libraries:
        html += f"""
                    <div class="list-item">
                        <span class="name">{lib}</span>
                        <span class="count">{count} repos</span>
                    </div>"""

    html += """
                </div>
            </div>
            

        </div>
    </div>
    
    <script>
        // Add some nice animations
        document.addEventListener('DOMContentLoaded', function() {{
            // Animate progress bars
            const progressBars = document.querySelectorAll('.progress-fill');
            progressBars.forEach(bar => {{
                const width = bar.style.width;
                bar.style.width = '0%';
                setTimeout(() => {{
                    bar.style.width = width;
                }}, 500);
            }});
            
            // Add hover effects to stat cards
            const statCards = document.querySelectorAll('.stat-card');
            statCards.forEach(card => {{
                card.addEventListener('mouseenter', function() {{
                    this.style.transform = 'translateY(-5px) scale(1.02)';
                }});
                
                card.addEventListener('mouseleave', function() {{
                    this.style.transform = 'translateY(0) scale(1)';
                }});
            }});
        }});
    </script>
</body>
</html>
"""

    return html


def save_html_report(html: str, filename: str = "programming_report.html"):
    """Save the HTML report to a file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"💾 HTML report saved to: {filename}")
    except Exception as e:
        print(f"❌ Error saving HTML report: {e}")


def main():
    """Main function to generate HTML report"""
    print("🚀 HTML Programming Report Generator")
    print("="*40)

    # Load data
    data = load_analysis_data()
    if not data:
        return 1

    # Generate HTML report
    print("\n📋 Generating HTML report...")
    html_report = generate_html_report(data)

    # Save the report
    save_html_report(html_report, "programming_report.html")

    print(f"\n🎉 HTML report generated successfully!")
    print("📁 File created: programming_report.html")
    print("🌐 You can now open this file in a web browser or load it into your chat interface")

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

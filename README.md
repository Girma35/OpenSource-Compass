# OpenSource-Compass 🧭

OpenSource-Compass is a collection of tools designed to help developers navigate and contribute to open-source projects more effectively.

## 🛠 Features

- **Issue Finder**: Automatically scan GitHub repositories for high-quality, beginner-friendly, or specific types of issues based on PR history.
- *More tools coming soon...*

---

## 🔍 Issue Finder

The `issue_finder` is a Python script that leverages the GitHub GraphQL API to find open issues associated with merged Pull Requests that meet specific complexity criteria.

### 🚀 Key Features
- **Complexity Filtering**: Filter by the number of files changed and lines of code modified in successful PRs.
- **Smart Detection**: Finds open issues that were referenced by these high-quality PRs.
- **State Persistence**: Saves scan progress to resume later.
- **Documentation Skip**: Automatically skips PRs marked as documentation fixes.

### 📋 Prerequisites
- Python 3.x
- `requests` library

```bash
pip install requests
```

### ⚙️ Setup
1. **GitHub Token**: For optimal performance and higher rate limits, use a GitHub Personal Access Token (PAT).
2. **Environment Variable**: Set your token in your environment:
   ```bash
   export GITHUB_TOKEN=your_personal_access_token
   ```

### 📖 Usage
Navigate to the `issues_finder` directory and run:
```bash
python issue_finder.py <repository_url>
```
Example:
```bash
python issue_finder.py https://github.com/pallets/flask
```

**Options:**
- `--reset`: Clears the scan progress for the specified repository and starts from the beginning.

### 📂 Output
- `issues.txt`: A list of discovered issue links and their titles.
- `scan_progress.json`: Tracks which PR pages have already been scanned.

---

## 📁 Repository Structure
```
.
├── issues_finder/
│   ├── issue_finder.py    # Main script
│   ├── issues.txt         # Discovered issues (ignored by git)
│   └── scan_progress.json # Scanning state (ignored by git)
└── README.md
```

## 🤝 Contributing
Contributions are welcome! Feel free to open issues or submit pull requests to add more tools or improve existing ones.

---
*Built with ❤️ to make open source more accessible.*
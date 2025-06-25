# Contributing to Cassandra Analyzer

First off, thank you for considering contributing to Cassandra Analyzer! It's people like you that make Cassandra Analyzer such a great tool.

## Code of Conduct

This project and everyone participating in it is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to support@axonops.com.

## How Can I Contribute?

### Reporting Bugs

This section guides you through submitting a bug report for Cassandra Analyzer. Following these guidelines helps maintainers and the community understand your report, reproduce the behavior, and find related reports.

Before creating bug reports, please check [this list](#before-submitting-a-bug-report) as you might find out that you don't need to create one. When you are creating a bug report, please [include as many details as possible](#how-do-i-submit-a-good-bug-report).

#### Before Submitting A Bug Report

* **Check the [documentation](README.md)** for a list of common questions and problems.
* **Check the [discussions](https://github.com/axonops/cassandra-analyzer/discussions)** for a list of common questions and problems.
* **Perform a [cursory search](https://github.com/axonops/cassandra-analyzer/issues)** to see if the problem has already been reported. If it has **and the issue is still open**, add a comment to the existing issue instead of opening a new one.

#### How Do I Submit A (Good) Bug Report?

Bugs are tracked as [GitHub issues](https://github.com/axonops/cassandra-analyzer/issues). Create an issue and provide the following information:

* **Use a clear and descriptive title** for the issue to identify the problem.
* **Describe the exact steps which reproduce the problem** in as many details as possible.
* **Provide specific examples to demonstrate the steps**. Include links to files or GitHub projects, or copy/pasteable snippets, which you use in those examples.
* **Describe the behavior you observed after following the steps** and point out what exactly is the problem with that behavior.
* **Explain which behavior you expected to see instead and why.**
* **Include screenshots and animated GIFs** which show you following the described steps and clearly demonstrate the problem.
* **If the problem wasn't triggered by a specific action**, describe what you were doing before the problem happened and share more information using the guidelines below.

Provide more context by answering these questions:

* **Did the problem start happening recently** (e.g. after updating to a new version of Cassandra Analyzer) or was this always a problem?
* **If the problem started happening recently**, can you reproduce the problem in an older version of Cassandra Analyzer? What's the most recent version in which the problem doesn't happen?
* **Can you reliably reproduce the issue?** If not, provide details about how often the problem happens and under which conditions it normally happens.
* **What's your environment?** (OS, Python version, AxonOps version, etc.)

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for Cassandra Analyzer, including completely new features and minor improvements to existing functionality.

#### Before Submitting An Enhancement Suggestion

* **Check the [documentation](README.md)** to see if the enhancement is already available.
* **Perform a [cursory search](https://github.com/axonops/cassandra-analyzer/issues)** to see if the enhancement has already been suggested. If it has, add a comment to the existing issue instead of opening a new one.

#### How Do I Submit A (Good) Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](https://github.com/axonops/cassandra-analyzer/issues). Create an issue and provide the following information:

* **Use a clear and descriptive title** for the issue to identify the suggestion.
* **Provide a step-by-step description of the suggested enhancement** in as many details as possible.
* **Provide specific examples to demonstrate the steps**. Include copy/pasteable snippets which you use in those examples.
* **Describe the current behavior** and **explain which behavior you expected to see instead** and why.
* **Include screenshots and animated GIFs** which help you demonstrate the steps or point out the part of Cassandra Analyzer which the suggestion is related to.
* **Explain why this enhancement would be useful** to most Cassandra Analyzer users.
* **List some other tools where this enhancement exists.**

### Your First Code Contribution

Unsure where to begin contributing to Cassandra Analyzer? You can start by looking through these `beginner` and `help-wanted` issues:

* [Beginner issues](https://github.com/axonops/cassandra-analyzer/labels/beginner) - issues which should only require a few lines of code, and a test or two.
* [Help wanted issues](https://github.com/axonops/cassandra-analyzer/labels/help-wanted) - issues which should be a bit more involved than `beginner` issues.

### Pull Requests

The process described here has several goals:

- Maintain Cassandra Analyzer's quality
- Fix problems that are important to users
- Engage the community in working toward the best possible Cassandra Analyzer
- Enable a sustainable system for Cassandra Analyzer's maintainers to review contributions

Please follow these steps to have your contribution considered by the maintainers:

1. **Sign the CLA** - Follow the instructions in the pull request to sign our Contributor License Agreement.
2. **Follow the [styleguides](#styleguides)**
3. **Write tests** - We follow Test-Driven Development (TDD). Write tests first, then implementation.
4. **Update documentation** - Ensure the README.md and any other relevant documentation are kept up-to-date.
5. **Create a pull request** - Follow the [pull request template](.github/PULL_REQUEST_TEMPLATE.md)

While the prerequisites above must be satisfied prior to having your pull request reviewed, the reviewer(s) may ask you to complete additional design work, tests, or other changes before your pull request can be ultimately accepted.

## Styleguides

### Git Commit Messages

* Use the present tense ("Add feature" not "Added feature")
* Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
* Limit the first line to 72 characters or less
* Reference issues and pull requests liberally after the first line
* When only changing documentation, include `[ci skip]` in the commit title
* Consider starting the commit message with an applicable emoji:
    * 🎨 `:art:` when improving the format/structure of the code
    * 🐎 `:racehorse:` when improving performance
    * 🚱 `:non-potable_water:` when plugging memory leaks
    * 📝 `:memo:` when writing docs
    * 🐧 `:penguin:` when fixing something on Linux
    * 🍎 `:apple:` when fixing something on macOS
    * 🏁 `:checkered_flag:` when fixing something on Windows
    * 🐛 `:bug:` when fixing a bug
    * 🔥 `:fire:` when removing code or files
    * 💚 `:green_heart:` when fixing the CI build
    * ✅ `:white_check_mark:` when adding tests
    * 🔒 `:lock:` when dealing with security
    * ⬆️ `:arrow_up:` when upgrading dependencies
    * ⬇️ `:arrow_down:` when downgrading dependencies
    * 👕 `:shirt:` when removing linter warnings

### Python Styleguide

The project follows a relaxed version of [PEP 8](https://www.python.org/dev/peps/pep-0008/) to maintain compatibility with existing code.

#### Current Approach

Due to the existing codebase, we use relaxed linting rules. For new code, please follow these guidelines:

* **Line length**: Up to 120 characters (instead of 80)
* **Imports**: Group imports logically (stdlib, third-party, local)
* **Naming**: Follow PEP 8 naming conventions
* **Docstrings**: Add docstrings to new functions and classes

#### Linting

The project uses flake8 with relaxed rules. To check your code:

```bash
# This will use the .flake8 config with relaxed rules
flake8 cassandra_analyzer
# Or
make lint
```

#### Future Goals

While we currently have relaxed formatting rules to preserve the existing codebase, we aim to gradually improve code quality. When modifying existing code:

* Fix obvious issues (like syntax errors)
* Don't reformat entire files
* Focus on the specific lines you're changing

For entirely new files, you're encouraged to use stricter formatting:

```bash
# For new files only
black path/to/new/file.py
isort path/to/new/file.py
```

### Test Styleguide

* **Follow TDD** - Write tests first, then implementation
* Use descriptive test names
* Each test should test one thing
* Use pytest fixtures for common setup
* Aim for 100% code coverage for new code
* Mock external dependencies (AxonOps API calls)

Example test structure:

```python
def test_should_identify_high_cpu_usage_when_above_threshold():
    # Arrange
    analyzer = InfrastructureAnalyzer()
    metrics = create_test_metrics(cpu_usage=85.0)
    
    # Act
    recommendations = analyzer.analyze(metrics)
    
    # Assert
    assert len(recommendations) == 1
    assert recommendations[0].severity == "HIGH"
    assert "CPU usage" in recommendations[0].description
```

### Documentation Styleguide

* Use [Markdown](https://daringfireball.net/projects/markdown)
* Reference functions using the full path (e.g., `cassandra_analyzer.analyzers.infrastructure.analyze()`)
* Use docstrings for all public functions, classes, and modules
* Include examples in docstrings where appropriate

## Additional Notes

### Issue and Pull Request Labels

This section lists the labels we use to help us track and manage issues and pull requests.

* `bug` - Something isn't working
* `enhancement` - New feature or request
* `documentation` - Improvements or additions to documentation
* `good first issue` - Good for newcomers
* `help wanted` - Extra attention is needed
* `invalid` - This doesn't seem right
* `question` - Further information is requested
* `wontfix` - This will not be worked on
* `duplicate` - This issue or pull request already exists

## Development Setup

1. Fork and clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
4. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```
5. Create a branch for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

### Pre-commit Hooks

This project uses pre-commit hooks to maintain code quality. The hooks are configured to be minimal and non-intrusive, focusing on catching common issues without enforcing strict formatting that would change existing code.

#### What the pre-commit hooks check:

- **YAML/JSON/TOML syntax** - Ensures configuration files are valid
- **Large file detection** - Prevents accidentally committing large files
- **Merge conflict markers** - Catches unresolved merge conflicts
- **Debug statements** - Finds forgotten debug print/breakpoint statements
- **Flake8 (relaxed rules)** - Basic Python linting with many rules disabled

#### Troubleshooting pre-commit issues:

**Error: "failed to find interpreter for Builtin discover of python_spec='python3.11'"**

This happens when pre-commit is configured for a different Python version than what's installed on your system.

Solution:
```bash
# Check your Python version
python3 --version

# If you see Python 3.12 or another version, the pre-commit config has been updated
# to work with any Python 3.x version. Clean and reinstall:
pre-commit clean
pre-commit install
```

**Error: Black/isort wants to reformat all files**

The project currently has relaxed formatting rules to avoid changing existing code. Black and isort are disabled in the pre-commit configuration. If you want to use them locally:

```bash
# Format your new code only (not recommended for existing files)
black --check path/to/your/new/file.py
isort --check-only path/to/your/new/file.py
```

**Error: Flake8 is too strict**

The project uses a `.flake8` configuration file with relaxed rules. If you're still getting too many errors:

1. Make sure flake8 is using the config file:
   ```bash
   flake8 --config=.flake8 cassandra_analyzer
   ```

2. The following rules are already ignored:
   - Line length (up to 120 characters)
   - Whitespace issues (W291, W292, W293)
   - Unused imports (F401)
   - Various formatting preferences (E128, E501, E129, E303, etc.)

**Temporarily skip pre-commit hooks** (not recommended):
```bash
git commit --no-verify -m "Your commit message"
```

**Run pre-commit manually on all files:**
```bash
pre-commit run --all-files
```

**Run pre-commit on staged files only:**
```bash
pre-commit run
```

**Update pre-commit hooks to latest versions:**
```bash
pre-commit autoupdate
```

## Testing

Run the test suite:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=cassandra_analyzer --cov-report=html
```

## Questions?

Feel free to open a [discussion](https://github.com/axonops/cassandra-analyzer/discussions) if you have questions about contributing.
# Contributing to Slop Bot

Thank you for your interest in contributing to Slop Bot! We welcome contributions from everyone. This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Code Linting](#code-linting)
- [Documentation](#documentation)
- [Commit Messages](#commit-messages)
- [Pull Requests](#pull-requests)
- [Reporting Issues](#reporting-issues)
- [Security](#security)

## Code of Conduct

This project follows a code of conduct to ensure a welcoming environment for all contributors. By participating, you agree to:

- Treat all people with respect and sensitivity
- Communicate professionally and constructively
- Accept responsibility for mistakes and learn from them
- Show empathy towards other contributors
- Help create an inclusive and positive community

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- A Discord account and server for testing

### Development Setup

1. **Fork the repository** on GitHub

2. **Clone your fork:**
   ```bash
   git clone https://github.com/your-username/slopbot.git
   cd slopbot
   ```

3. **Set up Python environment:**
   ```bash
   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows

   # Install dependencies
   pip install -e .[dev]
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Discord token and OpenRouter key
   ```

5. **Install pre-commit hooks:**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

6. **Verify setup:**
   ```bash
   python -m pytest tests/ --tb=short
   python -m src.bot --help
   ```

## Development Workflow

### 1. Choose an Issue

- Check the [issues](https://github.com/your-org/slopbot/issues) page
- Start with issues labeled `good first issue` or `help wanted`
- Comment on the issue to indicate you're working on it

### 2. Create a Feature Branch

```bash
# Create and switch to new feature branch
git checkout -b feature/your-feature-name

# Or for bug fixes
git checkout -b fix/issue-number-description
```

Branch naming conventions:
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring
- `chore/description` - Maintenance tasks

### 3. Implement Your Changes

- Write clear, focused commits
- Add or update tests for new functionality
- Update documentation if needed
- Ensure all tests pass locally

### 4. Test Your Changes

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_commands.py

# Run with coverage
pytest --cov=src --cov-report=html

# Run type checking
pyright
```

### 5. Lint Your Changes

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint code
ruff check src/ tests/

# Auto-fix issues where possible
ruff check --fix src/ tests/
```

### 6. Commit Your Changes

```bash
# Stage your changes
git add .

# Commit with conventional commit format
git commit -m "feat: add new command for image blending"
```

See [Commit Messages](#commit-messages) section for details.

### 7. Update Changelog

If your change is user-facing, add an entry to `CHANGELOG.md`:

```markdown
## [Unreleased]

### Added
- New `/blend` command for combining images (#123)
```

### 8. Push and Create Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name

# Create pull request on GitHub
# - Use the GitHub web interface
# - Fill out the PR template
# - Link to any related issues
```

## Coding Standards

### Python Style Guide

We follow PEP 8 with some modifications via Black:

#### Code Formatting

- Use `black` for automatic code formatting
- Maximum line length: 88 characters
- Use double quotes for strings (configured in `pyproject.toml`)

```python
# Good
def calculate_image_score(image_path: str, weights: dict[str, float]) -> float:
    """Calculate image quality score using specified weights."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    return sum(weights[key] for key in weights.keys())


# Bad - not formatted with Black
def calculate_image_score(image_path:str,weights:dict[str,float])->float:
    """Calculate image quality score."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    return sum(weights[key] for key in weights.keys())
```

#### Naming Conventions

- **Classes:** `PascalCase` (e.g., `ImageProcessor`)
- **Functions:** `snake_case` (e.g., `process_image`)
- **Variables:** `snake_case` (e.g., `user_count`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `MAX_IMAGE_SIZE`)
- **Private methods:** Start with single underscore (e.g., `_validate_input`)

#### Type Hints

Use modern type hints throughout the codebase:

```python
from typing import Optional, List, Dict, Union
from pathlib import Path

def load_config(config_path: Path) -> dict[str, str]:
    """Load configuration from file."""
    with open(config_path, 'r') as f:
        return json.load(f)

async def fetch_image(url: str) -> Optional[bytes]:
    """Fetch image data from URL."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return response.content
        except Exception as e:
            logger.error(f"Failed to fetch image: {e}")
    return None
```

### Project Structure

Maintain the existing project structure:

```
slopbot/
├── src/
│   ├── bot.py          # Main bot application
│   ├── commands/       # Bot commands
│   │   ├── __init__.py
│   │   ├── imagine.py  # Imagine command
│   │   ├── edit.py     # Edit command
│   │   └── ...
│   └── utils/          # Utility modules
│       ├── __init__.py
│       ├── logging.py
│       ├── image_processing.py
│       └── ...
├── tests/
│   ├── __init__.py
│   ├── conftest.py     # Test configuration
│   ├── test_bot.py
│   ├── test_commands.py
│   └── ...
├── docs/
│   └── examples.md
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── ...
```

## Testing

### Test Structure

We use `pytest` for testing with the following structure:

```python
# tests/test_commands.py
import pytest
from unittest.mock import Mock, patch
from src.commands.imagine import ImagineCommand


class TestImagineCommand:
    @pytest.fixture
    def command(self):
        return ImagineCommand()

    @pytest.mark.asyncio
    async def test_imagine_success(self, command):
        """Test successful image generation."""
        # Arrange
        mock_interaction = Mock()
        mock_interaction.user.id = 123456789

        # Act
        with patch('src.services.openrouter.generate_image') as mock_generate:
            mock_generate.return_value = "https://example.com/image.png"
            await command.handle(mock_interaction, prompt="a sunset")

        # Assert
        mock_generate.assert_called_once_with("a sunset")
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_imagine_rate_limit(self, command):
        """Test rate limiting behavior."""
        # Test implementation here
        pass
```

### Test Categories

1. **Unit Tests:** Individual functions and methods
2. **Integration Tests:** Multiple components working together
3. **End-to-End Tests:** Full workflow from command to response
4. **Performance Tests:** Load testing and stress testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_commands.py

# Run tests matching pattern
pytest -k "test_imagine"

# Run tests in verbose mode
pytest -v

# Debug failing test
pytest --pdb --tb=long

# Run integration tests only
pytest -m integration
```

### Writing Tests

#### Best Practices

- **Write tests first** (TDD approach)
- **One assertion per test** (where possible)
- **Descriptive test names** that explain what they're testing
- **Test both success and failure cases**
- **Mock external dependencies** (discord.py, API calls)
- **Use fixtures** for setup/teardown code

#### Test Coverage Goals

- **Minimum coverage:** 80%
- **Critical paths:** 100% coverage
- **New features:** 100% coverage before merge

```bash
# Check coverage
pytest --cov=src --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=src --cov-fail-under=80
```

## Code Linting

We use multiple tools to ensure code quality:

### Ruff

Ruff is our primary linter that combines the functionality of multiple tools:

```bash
# Install ruff
pip install ruff

# Lint code
ruff check src/

# Auto-fix issues
ruff check --fix src/

# Format imports (alternative to isort)
ruff check --select=I --fix src/
```

Ruff configuration in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 88
target-version = "py311"
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # Pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # Line too long (handled by black)
    "B008",  # Do not perform function calls in argument defaults
    "C901",  # Too complex
]

[tool.ruff.per-file-ignores]
"tests/**/*" = ["B011", "S101"]  # assert used, assert statements
```

### Black

Black is used for consistent code formatting:

```bash
# Install black
pip install black

# Format code
black src/ tests/

# Check if code needs formatting
black --check src/ tests/
```

Black configuration:

```toml
[tool.black]
line-length = 88
target-version = ['py311']
include = '\.pyi?$'
extend-exclude = '''
/(
    \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | build
  | dist
)/
'''
```

### isort

isort manages import sorting and organization:

```bash
# Install isort
pip install isort

# Sort imports
isort src/ tests/

# Check import sorting
isort --check-only --diff src/ tests/
```

isort configuration:

```toml
[tool.isort]
profile = "black"
multi_line_output = 3
line_length = 88
known_first_party = ["src"]
known_third_party = ["discord"]
```

### pyright

pyright provides static type checking:

```bash
# Install pyright
pip install pyright

# Type check
pyright

# Type check with stricter settings
pyright --strict
```

pyright configuration in `pyrightconfig.json`:

```json
{
  "include": ["src"],
  "exclude": ["**/__pycache__", "**/node_modules", "venv"],
  "reportMissingImports": true,
  "reportMissingTypeStubs": false,
  "pythonVersion": "3.11",
  "typeCheckingMode": "basic",
  "useLibraryCodeForTypes": true,
  "stubPath": "src"
}
```

## Documentation

### Docstring Standards

Use Google-style docstrings for all public functions:

```python
def generate_image(prompt: str, style: Optional[str] = None) -> Optional[str]:
    """
    Generate an image from a text prompt.

    Args:
        prompt: Text description of the image to generate
        style: Optional artistic style to apply

    Returns:
        URL of the generated image, or None if generation failed

    Raises:
        ValueError: If prompt is empty or too long
        APIError: If the external API call fails

    Example:
        >>> url = generate_image("a sunset over mountains")
        >>> print(url)
        https://example.com/generated-image.png
    """
```

### Documentation Updates

When adding new features:

1. **Update README.md** if it's a user-facing feature
2. **Add to docs/examples.md** if there are usage examples
3. **Update inline documentation** with docstrings
4. **Add changelog entry** in CHANGELOG.md

## Commit Messages

We follow conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

### Types

- **feat:** New feature
- **fix:** Bug fix
- **docs:** Documentation changes
- **style:** Code style changes (formatting, missing semicolons, etc.)
- **refactor:** Code refactoring
- **perf:** Performance improvements
- **test:** Adding or correcting tests
- **chore:** Maintenance tasks (dependencies, tooling, etc.)
- **ci:** CI/CD changes
- **build:** Build system changes

### Scope

Optional scope to specify the affected area:

- `commands` - Bot commands
- `api` - API integrations
- `config` - Configuration
- `docs` - Documentation
- `tests` - Test suite

### Examples

```bash
# New feature
feat(commands): add /blend command for image composition

# Bug fix
fix(api): handle OpenRouter timeout errors gracefully

# Documentation
docs(readme): add troubleshooting section

# Test addition
test(commands): add integration tests for /imagine command

# Performance improvement
perf(caching): implement LRU cache for API responses

# Refactoring
refactor(utils): split image processing into separate module
```

### Breaking Changes

Prefix description with `BREAKING CHANGE:` or use `!` after type:

```bash
feat(commands)!: change /imagine command signature

BREAKING CHANGE: The `quality` parameter now accepts values 1-10 instead of high/medium/low
```

## Pull Requests

### PR Template

All PRs should include:

```markdown
## Description
[Brief description of the changes]

## Type of Change
- [ ] Bug fix (non-breaking change)
- [ ] New feature (non-breaking change)
- [ ] Breaking change (fix or feature)
- [ ] Documentation update
- [ ] Refactoring
- [ ] Performance improvement

## Changes Made
- [x] Added new battle system
- [x] Updated documentation
- [x] Added tests

## Testing
- [x] Unit tests pass
- [x] Integration tests pass
- [x] Manual testing performed

## Screenshots (if applicable)

## Notes
[Any additional context or notes]
```

### PR Review Process

1. **Automated checks:**
   - Tests pass
   - Linting passes
   - Type checking passes
   - Coverage meets threshold

2. **Manual review:**
   - Code quality check
   - Documentation review
   - Functional testing

3. **Merge approval:**
   - At least one maintainer approval
   - All automated checks pass
   - No breaking changes without discussion

### Merge Strategies

- **Squash merge** for clean history
- **Merge commit** for preserving context
- **Rebase merge** rarely used

## Reporting Issues

### Bug Reports

Please include:

1. **Descriptive title:** "Bot crashes when uploading PNG images"
2. **Detailed description:**
   - What you were doing
   - What you expected to happen
   - What actually happened
3. **Steps to reproduce:**
   1. Use `/imagine` command with PNG attachment
   2. Wait for processing
   3. Bot crashes with error message
4. **Environment:**
   - Bot version
   - Discord.py version
   - Python version
   - Operating system
5. **Logs/Screenshots:** Any error messages or screenshots

### Feature Requests

Please include:

1. **Use case:** Describe what you want to do
2. **Current behavior:** How it works now
3. **Proposed solution:** How you'd like it to work
4. **Alternatives considered:** Other solutions you've thought of

## Security

- **Never commit secrets** or credentials
- **Report security vulnerabilities** directly to maintainers via email
- **Follow security best practices** outlined in SECURITY.md
- **Security issues should not be discussed publicly** until resolved

---

Thank you for contributing to Slop Bot! Your contributions help make the project better for everyone.

[⬆ Back to top](#contributing-to-slop-bot)
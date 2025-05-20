#!/bin/bash
# Setup script for the meta-disco schema validation component

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "Poetry is not installed. Please install it first:"
    echo "curl -sSL https://install.python-poetry.org | python3 -"
    exit 1
fi

# Clear any existing Poetry environment settings for this project
echo "Clearing Poetry environment settings..."

# Remove any local Poetry configuration
rm -f poetry.toml 2>/dev/null || true

# Force Poetry to forget about any in-project virtual environment
poetry config virtualenvs.in-project false --local

# Set environment variable to ensure Poetry doesn't use in-project venv
export POETRY_VIRTUALENVS_IN_PROJECT=false

# Clean up any existing environments for this project
echo "Cleaning up existing environments..."
find "$(poetry config virtualenvs.path)" -name "*meta-disco*" -type d -exec rm -rf {} \; 2>/dev/null || true

# Create a fresh environment
echo "Creating a fresh virtual environment..."

# Extract Python version from pyproject.toml (macOS compatible)
PYTHON_VERSION=$(grep 'python = ' pyproject.toml | sed 's/python = "\^\([0-9.]*\)"/\1/')
if [ -z "$PYTHON_VERSION" ]; then
    echo "Error: Unable to determine Python version from pyproject.toml."
    exit 1
fi
echo "Using Python version: $PYTHON_VERSION"

# Check if the specified Python version is installed
if ! pyenv versions --bare | grep -q "^${PYTHON_VERSION}\(\..*\)\?$"; then
  echo
  echo "Python version ${PYTHON_VERSION} is not installed. Installing it with pyenv..."
  pyenv install "${PYTHON_VERSION}"
fi

# Temporarily set Pyenv version in order to create Poetry environment
export PYENV_VERSION="$PYTHON_VERSION"

poetry env use "python$PYTHON_VERSION"

# Install dependencies using Poetry
echo "Installing dependencies for meta-disco schema validation..."
poetry install

# Show environment info
echo "\nVirtual environment information:"
poetry env info

echo "\nSetup complete for meta-disco schema validation component!"
echo "Run 'poetry shell' to activate the virtual environment or use 'poetry run' to execute commands."
